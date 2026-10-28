"""reader: 원본 parquet에서 요청 구간·target의 행을 원본 그대로 잘라 시간순으로 내보낸다.

하는 일: 시간대 변환(파일명 CST ↔ 내부 UTC), 파일 선택, 시각 필터, target 행 필터, ts 정렬.
안 하는 일: 열 통일·값 변환·형식 변환·quirk 해석·수집 상태 판정 → selector·system card (생각.txt 아이디어 6).
원본 보존: 추가 열은 `ts`(UTC) 하나, 빼는 열은 `kpi_name` 하나 (중국어, data/CLAUDE.md 16).

target 규칙 하나: 행의 주인(log k8_pod, trace pod 태그, apm 파일명, infra pod/kubernetes_node)이 target 이름과 같은 행만 남긴다.
확장 없음 — service의 하위 pod, node 위의 pod 같은 관계는 따라가지 않는다 (관계 지식은 system card, 모델이 target을 여러 번 호출).
type은 metric 폴더를 고르는 데만 쓴다. 남는 행이 없으면 빈 DataFrame — 해석은 프롬프트 규칙 몫.
"""
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

DATA_ROOT = Path(__file__).resolve().parents[2] / "data" / "aiopschallenge2025"
CST = timedelta(hours=8)  # 파일명·날짜 폴더는 CST(UTC+8), 데이터 내부는 UTC

SOURCES = ("log", "trace", "metric")
TARGET_TYPES = ("pod", "service", "node", "tidb", "tikv", "pd")
METRIC_GLOBS = {  # type별 metric 파일군 (metric-parquet 기준 상대 경로)
    "node": ["infra/infra_node/*.parquet"],
    "tidb": ["infra/infra_tidb/*.parquet"],
    "tikv": ["other/infra_tikv_*.parquet"],
    "pd": ["other/infra_pd_*.parquet"],
    None: ["**/*.parquet"],
}


def read(sources, target, start_time, end_time):
    """[start_time, end_time] (UTC ISO, 양끝 포함, 초 정밀도) 구간의 원본 행.

    target: None(전 엔티티) | {"type": pod|service|node|tidb|tikv|pd, "name": str}
    반환: 요청한 source만 {"log": DF, "trace": DF, "metric": {file_key: DF}}
    """
    sources = list(sources)
    if not sources or any(s not in SOURCES for s in sources):
        raise ValueError(f"sources must be a non-empty subset of {SOURCES}: {sources}")
    if target is not None and (target.get("type") not in TARGET_TYPES or not target.get("name")):
        raise ValueError(f"target must be None or {{type: {TARGET_TYPES}, name}}: {target}")
    start, end = _parse(start_time), _parse(end_time)
    if start > end:
        raise ValueError(f"start_time > end_time: {start_time} {end_time}")
    return {s: (_read_metric if s == "metric" else _read_hourly)(s, target, start, end) for s in sources}


def _parse(iso):
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(timezone.utc)


def _floor_min(t):
    return t.replace(second=0, microsecond=0)


# ---------- log / trace (1시간 파일) ----------

def _read_hourly(source, target, start, end):
    folder, prefix = {"log": ("log-parquet", "log_filebeat-server"), "trace": ("trace-parquet", "trace_jaeger-span")}[source]
    paths, hour = [], start.replace(minute=0, second=0, microsecond=0)
    while hour <= end:
        c = hour + CST
        p = DATA_ROOT / f"{c:%Y-%m-%d}" / folder / f"{prefix}_{c:%Y-%m-%d_%H}-00-00.parquet"
        if p.exists():
            paths.append(p)
        hour += timedelta(hours=1)

    if source == "log":
        # @timestamp는 ms 포함 ISO 문자열 → 경계도 ms 형식으로 맞춰야 문자열 비교가 맞음 ("…02.045Z" < "…02Z"가 참이 되는 문제)
        filters = [("@timestamp", ">=", f"{start:%Y-%m-%dT%H:%M:%S}.000Z"), ("@timestamp", "<=", f"{end:%Y-%m-%dT%H:%M:%S}.999Z")]
    else:
        # span 시작 기준. startTime(μs)이 startTimeMillis(ms)보다 정밀
        lo = int(start.timestamp()) * 1_000_000
        filters = [("startTime", ">=", lo), ("startTime", "<=", int(end.timestamp()) * 1_000_000 + 999_999)]
    tables = [pq.read_table(p, filters=filters).to_pandas() for p in paths]
    df = pd.concat(tables, ignore_index=True) if tables else pd.DataFrame()
    if len(df):
        df["ts"] = pd.to_datetime(df["@timestamp"], utc=True) if source == "log" else pd.to_datetime(df["startTime"], unit="us", utc=True)
    else:
        df["ts"] = pd.Series(dtype="datetime64[us, UTC]")

    if target is not None and len(df):
        pods = df["k8_pod"] if source == "log" else df["process"].map(_trace_pod)
        df = df[pods == target["name"]]
    return df.sort_values("ts", kind="stable", ignore_index=True)


def _trace_pod(process):
    # pod명 키가 서비스마다 다름: 대부분 name, cartservice·redis span은 podName (값은 원본에 그대로 둠)
    tags = {t["key"]: t["value"] for t in process["tags"]}
    return tags.get("name") or tags.get("podName")


# ---------- metric (1일 파일, 지표·대상마다 파일 1개) ----------

def _metric_files(day_dir, target):
    base = day_dir / "metric-parquet"
    typ = None if target is None else target["type"]
    if typ == "service":  # service 단위 집계 파일 하나 (파일명 = 행 주인)
        return [p for p in [base / "apm" / "service" / f"service_{target['name']}_{day_dir.name}.parquet"] if p.exists()]
    if typ == "pod":  # apm pod 파일(파일명 = 행 주인, 재생성 흔적 " (deleted)" 접미 포함) + infra_pod(행 필터)
        pod_file = re.compile(rf"^pod_{re.escape(target['name'])}( \(deleted\))?_\d{{4}}-\d\d-\d\d\.parquet$")
        return ([p for p in sorted((base / "apm" / "pod").glob("*.parquet")) if pod_file.match(p.name)]
                + sorted((base / "infra" / "infra_pod").glob("*.parquet")))
    return [p for g in METRIC_GLOBS[typ] for p in sorted(base.glob(g))]


def _read_metric(_, target, start, end):
    # time은 분 라벨 → 경계를 분 단위로 내림 (안 하면 16:10:02 시작 시 16:10 행이 빠지고 1초 장애는 0행)
    filters = [("time", ">=", f"{_floor_min(start):%Y-%m-%dT%H:%M:%S}Z"), ("time", "<=", f"{_floor_min(end):%Y-%m-%dT%H:%M:%S}Z")]
    days = sorted({(start + CST).date(), (end + CST).date()})
    frames = {}
    for d in days:
        day_dir = DATA_ROOT / f"{d:%Y-%m-%d}"
        for p in _metric_files(day_dir, target):
            cols = [c for c in pq.read_schema(p).names if c != "kpi_name"]
            df = pq.read_table(p, columns=cols, filters=filters).to_pandas()
            df["ts"] = pd.to_datetime(df["time"], utc=True)
            key = p.relative_to(day_dir / "metric-parquet").as_posix().removesuffix(f"_{d:%Y-%m-%d}.parquet")
            frames.setdefault(key, []).append(df)
    out = {k: pd.concat(v, ignore_index=True) for k, v in frames.items()}

    # 행 주인 열이 있는 파일만 행으로 거름. apm·TiDB 계층은 파일 선택으로 끝
    owner_col = {"pod": ("infra/infra_pod/", "pod"), "node": ("infra/infra_node/", "kubernetes_node")}.get(target and target["type"])
    if owner_col:
        prefix, col = owner_col
        out = {k: df[df[col] == target["name"]] if k.startswith(prefix) else df for k, df in out.items()}
    return {k: df.sort_values("ts", kind="stable", ignore_index=True) for k, df in out.items() if len(df)}


if __name__ == "__main__":
    import time

    def check(sources, target, s, e):
        t0 = time.time()
        r = read(sources, target, s, e)
        rows = {k: (sum(map(len, v.values())) if k == "metric" else len(v)) for k, v in r.items()}
        print(f"{target} {s}~{e}: {time.time() - t0:.2f}s rows={rows}")
        return r

    # 1) 06-06 첫 케이스 전체: 구간·정렬·원본 열 보존
    S, E = "2025-06-05T16:10:02Z", "2025-06-05T16:31:02Z"
    r = check(SOURCES, None, S, E)
    raw_log = pq.read_table(DATA_ROOT / "2025-06-06/log-parquet/log_filebeat-server_2025-06-06_00-00-00.parquet").to_pandas()
    raw_log = raw_log[(raw_log["@timestamp"] >= "2025-06-05T16:10:02.000Z") & (raw_log["@timestamp"] <= "2025-06-05T16:31:02.999Z")]
    log = r["log"]
    assert list(log.columns) == list(raw_log.columns) + ["ts"], "log 열은 원본 + ts"
    assert len(log) == len(raw_log) and sorted(log["message"]) == sorted(raw_log["message"]), "log 행·값 원본과 동일"
    assert (log["@timestamp"] < "2025-06-05T16:10:03").any(), "start 초에 찍힌 log 포함 (경계 문자열 비교 회귀 방지)"
    for name, df in [("log", log), ("trace", r["trace"])] + list(r["metric"].items()):
        assert df["ts"].is_monotonic_increasing, f"{name} 정렬"
        assert df["ts"].min() >= pd.Timestamp("2025-06-05T16:10:00Z") and df["ts"].max() <= pd.Timestamp(E) + pd.Timedelta("999ms"), f"{name} 구간"
        assert "kpi_name" not in df.columns
    trace_cols = pq.read_schema(DATA_ROOT / "2025-06-06/trace-parquet/trace_jaeger-span_2025-06-06_00-00-00.parquet").names
    assert list(r["trace"].columns) == trace_cols + ["ts"], "trace 열은 원본 + ts (중첩 열 포함)"
    assert r["metric"]["infra/infra_pod/infra_pod_pod_cpu_usage"]["cf"].eq("null").all(), "'null' 문자열 원본 유지"

    # 2) pod target: 전 source가 그 pod 자신의 행만, redis span(serviceName=redis, podName=cartservice-0) 포함
    r = check(SOURCES, {"type": "pod", "name": "cartservice-0"}, S, E)
    assert (r["trace"]["process"].map(_trace_pod) == "cartservice-0").all()
    assert (r["trace"]["process"].map(lambda p: p["serviceName"]) == "redis").any()
    assert (r["log"]["k8_pod"] == "cartservice-0").all() and len(r["log"])
    m = r["metric"]
    assert "apm/pod/pod_cartservice-0" in m and not any(k.startswith("apm/") and k != "apm/pod/pod_cartservice-0" for k in m)
    assert (m["infra/infra_pod/infra_pod_pod_cpu_usage"]["pod"] == "cartservice-0").all()

    # 3) service target: service 집계 파일만, log·trace는 행 주인이 pod라 빈 결과 (하위 pod로 확장 안 함)
    r = check(SOURCES, {"type": "service", "name": "cartservice"}, S, E)
    assert list(r["metric"]) == ["apm/service/service_cartservice"] and not len(r["log"]) and not len(r["trace"])

    # 4) node target (ef2a4fbb-87): infra_node 행만, log·trace는 행 주인이 pod라 빈 결과 (미리 막지 않음)
    r = check(SOURCES, {"type": "node", "name": "aiops-k8s-03"}, "2025-06-05T23:10:13Z", "2025-06-05T23:24:13Z")
    assert all(k.startswith("infra/infra_node/") for k in r["metric"]) and r["metric"]
    assert all((df["kubernetes_node"] == "aiops-k8s-03").all() for df in r["metric"].values())
    assert not len(r["log"]) and not len(r["trace"])

    # 5) 빈 결과·공백: trace 파일 없음(06-09 CST 01시) / 일부 공백(d0be3c58-178, 19분 중 3분) / 계측 없음 / TiDB 계층
    assert not len(check(["trace"], None, "2025-06-08T17:00:00Z", "2025-06-08T17:10:00Z")["trace"])
    t = check(["trace"], None, "2025-06-09T21:10:22Z", "2025-06-09T21:28:22Z")["trace"]
    assert t["ts"].dt.floor("min").nunique() == 3
    assert not len(check(["trace"], {"type": "pod", "name": "adservice-0"}, S, E)["trace"])
    r = check(SOURCES, {"type": "tikv", "name": "tikv"}, S, E)
    assert not len(r["log"]) and r["metric"] and all(k.startswith("other/infra_tikv_") for k in r["metric"])

    print("ok")
