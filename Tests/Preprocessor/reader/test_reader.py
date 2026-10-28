"""reader 검증: 독립 oracle(원본 파일 전체를 pandas로 직접 자른 결과)과 행 단위로 대조.

실행 (레포 루트): .venv/Scripts/python.exe Tests/Preprocessor/reader/test_reader.py [--skip-sweep]
결과: Tests/Preprocessor/reader/output/<YYYY-MM-DD_HHMMSS>/ (report.md, cases/, sweep_rows.csv)

oracle은 reader 코드를 재사용하지 않는다: 시간대는 tz DB(Asia/Shanghai), 파일은 구간 앞뒤 1시간·1일까지 넓게 읽고,
경계는 pandas Timestamp 비교로 따로 계산 → reader와 같은 버그를 공유하지 않게.
검사 하나가 실패해도 멈추지 않고 전부 실행한 뒤 리포트로 모은다.
"""
import argparse
import importlib.util
import json
import re
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
DATA = ROOT / "data" / "aiopschallenge2025"
_spec = importlib.util.spec_from_file_location("reader", ROOT / "Agent" / "Preprocessor" / "reader.py")
reader = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(reader)

SRC = ["log", "trace", "metric"]
SERVICES = ["adservice", "cartservice", "checkoutservice", "currencyservice", "emailservice", "frontend",
            "paymentservice", "productcatalogservice", "recommendationservice", "redis-cart", "shippingservice"]
NO_SPAN = {"adservice", "currencyservice", "paymentservice", "redis-cart"}  # 계측 없음 → 이 서비스 pod의 trace는 빈 결과가 정상
SEC = pd.Timedelta(seconds=1)

RESULTS = []  # (group, name, status, detail)


def test(group, name, info=False):
    """데코레이터: 함수를 바로 실행해 결과를 기록. 함수는 detail 문자열을 반환하거나 assert로 실패.
    info=True: reader 범위 밖(Agent Loop가 검사할 항목) → 실패해도 INFO로 기록, exit code에 반영 안 함."""
    def wrap(fn):
        t0 = time.time()
        try:
            detail = fn() or ""
            RESULTS.append((group, name, "PASS", f"{detail} ({time.time() - t0:.1f}s)"))
        except AssertionError as e:
            RESULTS.append((group, name, "INFO" if info else "FAIL", str(e) or traceback.format_exc(limit=1).strip().splitlines()[-1]))
        except Exception as e:
            RESULTS.append((group, name, "ERROR", f"{type(e).__name__}: {e} @ {traceback.extract_tb(e.__traceback__)[-1].lineno}"))
        print(f"[{RESULTS[-1][2]}] {group} / {name}")
        return fn
    return wrap


# ---------- oracle ----------

def ts_utc(iso):
    return pd.Timestamp(iso).tz_convert("UTC")


def oracle_hourly(source, start, end):
    """구간 앞뒤 1시간 파일까지 전부 읽고 Timestamp 비교로 자름. [start, end + 1s) = 초 정밀도 양끝 포함."""
    folder, prefix = {"log": ("log-parquet", "log_filebeat-server"), "trace": ("trace-parquet", "trace_jaeger-span")}[source]
    hours = pd.date_range(start.floor("h") - pd.Timedelta(hours=1), end.floor("h") + pd.Timedelta(hours=1), freq="h")
    frames = []
    for h in hours:
        c = h.tz_convert("Asia/Shanghai")
        p = DATA / c.strftime("%Y-%m-%d") / folder / f"{prefix}_{c.strftime('%Y-%m-%d_%H')}-00-00.parquet"
        if p.exists():
            frames.append(pq.read_table(p).to_pandas())
    df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if not len(df):
        return df
    t = pd.to_datetime(df["@timestamp"], utc=True) if source == "log" else pd.to_datetime(df["startTime"], unit="us", utc=True)
    df = df[(t >= start) & (t < end + SEC)].copy()
    df["ts"] = t[df.index]
    return df.sort_values("ts", kind="stable", ignore_index=True)


def oracle_metric(start, end):
    """앞뒤 하루까지 모든 metric 파일을 읽어 분 내림 구간으로 자름 → {file_key: DF}."""
    lo, hi = start.floor("min"), end.floor("min")
    days = pd.date_range((start.tz_convert("Asia/Shanghai") - pd.Timedelta(days=1)).normalize().tz_localize(None),
                         (end.tz_convert("Asia/Shanghai") + pd.Timedelta(days=1)).normalize().tz_localize(None), freq="D")
    frames = {}
    for d in days:
        base = DATA / d.strftime("%Y-%m-%d") / "metric-parquet"
        for p in sorted(base.rglob("*.parquet")) if base.exists() else []:
            df = pq.read_table(p).to_pandas()
            t = pd.to_datetime(df["time"], utc=True)
            df = df[(t >= lo) & (t <= hi)].drop(columns=["kpi_name"], errors="ignore").copy()
            df["ts"] = t[df.index]
            key = re.sub(r"_\d{4}-\d\d-\d\d\.parquet$", "", p.relative_to(base).as_posix())
            if len(df):  # 빈 frame을 concat에 섞으면 이웃 날짜 dtype(int64/double)으로 승격됨
                frames.setdefault(key, []).append(df)
    out = {k: pd.concat(v, ignore_index=True) for k, v in frames.items()}
    return {k: v.sort_values("ts", kind="stable", ignore_index=True) for k, v in out.items() if len(v)}


def span_has_owner(process, pod):
    # 키 이름(name/podName)에 기대지 않음: process.tags 값 중 하나라도 그 pod명이면 그 pod의 span (node_name 값은 pod명과 안 겹침)
    return any(t["value"] == pod for t in process["tags"])


def assert_frame_same(a, b, label):
    """원본 열·값·순서 동일 (ts 포함). 중첩 열은 repr로 비교."""
    assert list(a.columns) == list(b.columns), f"{label} 열 다름: {list(a.columns)} vs {list(b.columns)}"
    assert len(a) == len(b), f"{label} 행 수 reader {len(a)} vs oracle {len(b)}"
    a, b = a.reset_index(drop=True), b.reset_index(drop=True)
    for c in a.columns:
        if a[c].dtype == object:
            same = a[c].map(repr).tolist() == b[c].map(repr).tolist()
        else:
            same = a[c].equals(b[c])
        assert same, f"{label} 열 '{c}' 값/순서 다름"
        assert a[c].dtype == b[c].dtype, f"{label} 열 '{c}' dtype {a[c].dtype} vs {b[c].dtype}"


def read_spy(*args):
    """reader.read를 실행하며 실제로 연 parquet 경로를 기록 (reader가 source를 미리 건너뛰는지 확인용)."""
    opened, orig = [], reader.pq.read_table
    reader.pq.read_table = lambda p, *a, **k: (opened.append(Path(p)), orig(p, *a, **k))[1]
    try:
        return reader.read(*args), opened
    finally:
        reader.pq.read_table = orig


def assert_no_owner_rows(r, opened):
    """log·trace는 행 주인이 pod라 node·TiDB target엔 행이 없어야 하지만, reader가 미리 막지 않고 실제로 읽었는지까지 확인."""
    for s, folder in (("log", "log-parquet"), ("trace", "trace-parquet")):
        assert not len(r[s]), f"{s}: {len(r[s])}행"
        assert any(p.parent.name == folder for p in opened), f"{s}: 파일을 읽지 않고 건너뜀"


def minutes(df):
    return df["ts"].dt.floor("min").nunique() if len(df) else 0


def assert_metric_same(got, exp, label):
    assert set(got) == set(exp), f"{label} file_key 차이: reader만 {sorted(set(got) - set(exp))[:5]}, oracle만 {sorted(set(exp) - set(got))[:5]}"
    for k in exp:
        assert_frame_same(got[k], exp[k], f"{label} {k}")


# ---------- 결과 파일 ----------

def dump_case(out, name, result):
    d = out / "cases" / name
    (d / "metric").mkdir(parents=True, exist_ok=True)
    lines = [f"case: {name}"]
    for s, v in result.items():
        if s == "metric":
            lines.append(f"\n[metric] file 수 {len(v)}, 총 행 {sum(map(len, v.values()))}")
            for k, df in v.items():
                lines.append(f"  {k}: {len(df)}행, ts {df['ts'].min()} ~ {df['ts'].max()}")
                (d / "metric" / (k.replace("/", "__") + ".csv")).write_text(df.head(30).to_csv(index=False), encoding="utf-8-sig")
            continue
        lines.append(f"\n[{s}] {len(v)}행" + (f", ts {v['ts'].min()} ~ {v['ts'].max()}" if len(v) else ""))
        if len(v):
            pods = v["k8_pod"] if s == "log" else v["process"].map(lambda p: next((t["value"] for t in p["tags"] if t["key"] in ("name", "podName")), None))
            lines.append("  pod 분포: " + ", ".join(f"{p}={n}" for p, n in pods.value_counts(dropna=False).items()))
            pd.concat([v.head(30), v.tail(30)]).to_csv(d / f"{s}.csv", index=False, encoding="utf-8-sig")
    (d / "summary.txt").write_text("\n".join(lines), encoding="utf-8")


def write_report(out, elapsed):
    n = {k: sum(r[2] == k for r in RESULTS) for k in ("PASS", "FAIL", "ERROR", "INFO")}
    md = [f"# reader 검증 결과 ({out.name})", "",
          f"- 대상: `Agent/Preprocessor/reader.py`",
          f"- 총 {len(RESULTS)}건: PASS {n['PASS']} / FAIL {n['FAIL']} / ERROR {n['ERROR']} / INFO {n['INFO']}",
          "- INFO = reader 범위 밖, Agent Loop가 tool 인자를 넘기기 전에 검사할 항목 (생각.txt 아이디어 6 'Agent Loop 입력 검사')",
          f"- 소요: {elapsed:.0f}s", ""]
    icon = {"PASS": "✅", "INFO": "ℹ️"}
    for g in dict.fromkeys(r[0] for r in RESULTS):
        md += [f"## {g}", "", "| 검사 | 결과 | 상세 |", "|---|---|---|"]
        md += [f"| {name} | {icon.get(st, '❌')} {st} | {detail.replace('|', '/')} |" for gg, name, st, detail in RESULTS if gg == g]
        md.append("")
    (out / "report.md").write_text("\n".join(md), encoding="utf-8")
    return n


# ---------- 검사 ----------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-sweep", action="store_true", help="groundtruth 400건 전수 실행 생략 (~20분)")
    args = ap.parse_args()
    out = HERE / "output" / datetime.now().strftime("%Y-%m-%d_%H%M%S")
    out.mkdir(parents=True)
    t_all = time.time()

    S1, E1 = "2025-06-05T16:10:02Z", "2025-06-05T16:31:02Z"  # 06-06 첫 케이스 (emailservice cpu stress)
    s1, e1 = ts_utc(S1), ts_utc(E1)
    r1 = reader.read(SRC, None, S1, E1)
    dump_case(out, "01_W1_none", r1)
    o_log, o_trace, o_metric = oracle_hourly("log", s1, e1), oracle_hourly("trace", s1, e1), oracle_metric(s1, e1)

    # 1. 입력 검증
    bad_inputs = {
        "sources 빈 리스트": ([], None, S1, E1),
        "sources 미지원 값": (["logs"], None, S1, E1),
        "sources 문자열": ("metric", None, S1, E1),
        "target type 오타": (SRC, {"type": "Service", "name": "cartservice"}, S1, E1),
        "target name 누락": (SRC, {"type": "service"}, S1, E1),
        "target name 빈 문자열": (SRC, {"type": "service", "name": ""}, S1, E1),
        "target name 숫자": (SRC, {"type": "service", "name": 123}, S1, E1),
        "target이 dict 아님": (SRC, "cartservice", S1, E1),
        "start > end": (SRC, None, E1, S1),
        "잘못된 ISO": (SRC, None, "2025-06-05 16:10", E1),
        "날짜 아닌 문자열": (SRC, None, "yesterday", E1),
    }
    loop_only = {"target name 숫자", "target이 dict 아님", "잘못된 ISO"}  # Agent Loop가 걸러서 reader엔 안 들어옴
    for label, a in bad_inputs.items():
        @test("1. 입력 검증", f"{label} → ValueError" + (" [Agent Loop 검사]" if label in loop_only else ""), info=label in loop_only)
        def _(a=a):
            try:
                reader.read(*a)
            except ValueError as e:
                return f"ValueError: {e}"[:120]
            except Exception as e:
                raise AssertionError(f"ValueError가 아니라 {type(e).__name__}: {e}")
            raise AssertionError("예외 없이 통과함")

    @test("1. 입력 검증", "시간대 없는 ISO(…02)는 UTC로 처리되거나 거부 [Agent Loop 검사]", info=True)
    def _():
        try:
            r = reader.read(["log"], None, S1.rstrip("Z"), E1.rstrip("Z"))
        except ValueError:
            return "ValueError로 거부"
        assert len(r["log"]) == len(r1["log"]), \
            f"Z 없는 입력이 로컬 시간대로 해석됨: 행 {len(r['log'])} vs UTC {len(r1['log'])}"
        return "UTC로 처리"

    @test("1. 입력 검증", "+08:00 오프셋 입력 = 같은 UTC 구간")
    def _():
        r = reader.read(["log"], None, "2025-06-06T00:10:02+08:00", "2025-06-06T00:31:02+08:00")
        assert_frame_same(r["log"], r1["log"], "log")

    # 2. 원본 보존 + oracle 대조
    @test("2. 원본 보존", "log 열·값·순서·dtype = oracle")
    def _():
        raw_cols = pq.read_schema(DATA / "2025-06-06/log-parquet/log_filebeat-server_2025-06-06_00-00-00.parquet").names
        assert list(r1["log"].columns) == raw_cols + ["ts"], "열 = 원본 + ts 아님"
        assert_frame_same(r1["log"], o_log, "log")
        return f"{len(o_log)}행"

    @test("2. 원본 보존", "trace 열·값·순서·dtype = oracle (중첩 열 포함)")
    def _():
        raw_cols = pq.read_schema(DATA / "2025-06-06/trace-parquet/trace_jaeger-span_2025-06-06_00-00-00.parquet").names
        assert list(r1["trace"].columns) == raw_cols + ["ts"], "열 = 원본 + ts 아님"
        assert_frame_same(r1["trace"], o_trace, "trace")
        return f"{len(o_trace)}행"

    @test("2. 원본 보존", "trace ts가 startTimeMillis와 ms 단위로 일치")
    def _():
        t = r1["trace"]
        assert (t["ts"].astype("int64") // 1_000 == t["startTimeMillis"]).all() or \
               (t["ts"].dt.floor("ms") == pd.to_datetime(t["startTimeMillis"], unit="ms", utc=True)).all()

    @test("2. 원본 보존", "metric 전 파일 열·값·순서·dtype = oracle, kpi_name 없음")
    def _():
        assert_metric_same(r1["metric"], o_metric, "metric")
        assert all("kpi_name" not in df.columns for df in r1["metric"].values())
        return f"{len(o_metric)}개 파일"

    @test("2. 원본 보존", "'null' 문자열 원본 유지 (null로 변환 안 됨)")
    def _():
        df = r1["metric"]["infra/infra_pod/infra_pod_pod_cpu_usage"]
        assert df["cf"].eq("null").all() and df["cf"].notna().all()

    @test("2. 원본 보존", "trace의 pod 키(name/podName)가 없는 span 수 (모든 service target에서 빠짐)")
    def _():
        no_pod = r1["trace"]["process"].map(lambda p: not any(t["key"] in ("name", "podName") for t in p["tags"])).sum()
        assert no_pod == 0, f"pod 키 없는 span {no_pod}개"

    # 3. 시각 경계
    @test("3. 시각 경계", "log: start 초·end 초 포함, end+1초 제외")
    def _():
        raw = pq.read_table(DATA / "2025-06-06/log-parquet/log_filebeat-server_2025-06-06_00-00-00.parquet").to_pandas()
        t = pd.to_datetime(raw["@timestamp"], utc=True).dt.floor("s").value_counts()
        busy = sorted(s for s in t.index if t.get(s + pd.Timedelta(seconds=60), 0) and t.get(s + pd.Timedelta(seconds=61), 0))
        s, e = busy[len(busy) // 2], busy[len(busy) // 2] + pd.Timedelta(seconds=60)
        r = reader.read(["log"], None, s.strftime("%Y-%m-%dT%H:%M:%SZ"), e.strftime("%Y-%m-%dT%H:%M:%SZ"))["log"]
        sec = r["ts"].dt.floor("s")
        assert (sec == s).sum() == t[s], f"start 초 {s}: {(sec == s).sum()} / 원본 {t[s]}"
        assert (sec == e).sum() == t[e], f"end 초 {e}: {(sec == e).sum()} / 원본 {t[e]}"
        assert (r["ts"] >= e + SEC).sum() == 0, "end+1초 행 포함됨"
        return f"start초 {t[s]}행, end초 {t[e]}행 포함"

    @test("3. 시각 경계", "trace: μs 양끝 경계 (start 초 첫 span, end 초 마지막 μs)")
    def _():
        t = o_trace["ts"]
        lo_n, hi_n = (t.dt.floor("s") == s1).sum(), (t.dt.floor("s") == e1).sum()
        got = r1["trace"]["ts"].dt.floor("s")
        assert (got == s1).sum() == lo_n and (got == e1).sum() == hi_n, f"start초 {(got == s1).sum()}/{lo_n}, end초 {(got == e1).sum()}/{hi_n}"
        return f"start초 {lo_n}, end초 {hi_n} span"

    @test("3. 시각 경계", "metric: 분 내림 (16:10:02 시작 → 16:10 행 포함)")
    def _():
        df = r1["metric"]["infra/infra_node/infra_node_node_cpu_usage_rate"]
        assert df["ts"].min() == s1.floor("min") and df["ts"].max() == e1.floor("min"), f"{df['ts'].min()} ~ {df['ts'].max()}"

    @test("3. 시각 경계", "1초 장애 0718e0f9-92: metric 행 > 0, 전부 04:03 분")
    def _():
        r = reader.read(SRC, None, "2025-06-06T04:03:03Z", "2025-06-06T04:03:04Z")
        dump_case(out, "02_1sec_fault", r)
        n = sum(map(len, r["metric"].values()))
        assert n > 0, "metric 0행"
        assert all((df["ts"] == pd.Timestamp("2025-06-06T04:03:00Z")).all() for df in r["metric"].values())
        return f"metric {n}행, log {len(r['log'])}, trace {len(r['trace'])}"

    @test("3. 시각 경계", "start == end (0초 구간) = oracle")
    def _():
        s = "2025-06-06T04:03:03Z"
        r = reader.read(SRC, None, s, s)
        assert_frame_same(r["log"], oracle_hourly("log", ts_utc(s), ts_utc(s)), "log")
        assert_frame_same(r["trace"], oracle_hourly("trace", ts_utc(s), ts_utc(s)), "trace")
        return f"log {len(r['log'])}, trace {len(r['trace'])}"

    # 4. 파일 경계
    for label, (s, e) in {"UTC 시 경계 (16:50~17:10)": ("2025-06-05T16:50:00Z", "2025-06-05T17:10:00Z"),
                          "CST 자정 경계 (06-06→06-07)": ("2025-06-06T15:50:00Z", "2025-06-06T16:10:00Z")}.items():
        @test("4. 파일 경계", f"{label}: log·trace·metric = oracle")
        def _(s=s, e=e, label=label):
            r = reader.read(SRC, None, s, e)
            if "자정" in label:
                dump_case(out, "03_cst_midnight", r)
            assert_frame_same(r["log"], oracle_hourly("log", ts_utc(s), ts_utc(e)), "log")
            assert_frame_same(r["trace"], oracle_hourly("trace", ts_utc(s), ts_utc(e)), "trace")
            assert_metric_same(r["metric"], oracle_metric(ts_utc(s), ts_utc(e)), "metric")
            hours = r["log"]["ts"].dt.floor("h").nunique()
            assert hours == 2, f"두 시간대 행이 다 있어야 함: {hours}"
            return f"log {len(r['log'])}, trace {len(r['trace'])}, metric {len(r['metric'])}파일"

    @test("4. 파일 경계", "데이터 없는 날짜(06-15 CST) → 전 source 빈 결과, 예외 없음")
    def _():
        r = reader.read(SRC, None, "2025-06-14T18:00:00Z", "2025-06-14T18:10:00Z")
        dump_case(out, "04_missing_day", r)
        assert not len(r["log"]) and not len(r["trace"]) and not r["metric"]

    # 5. 정렬
    @test("5. 정렬", "모든 반환 DF ts 단조 증가")
    def _():
        dfs = [("log", r1["log"]), ("trace", r1["trace"])] + list(r1["metric"].items())
        bad = [k for k, df in dfs if not df["ts"].is_monotonic_increasing]
        assert not bad, f"비정렬: {bad[:5]}"

    @test("5. 정렬", "원본 log는 실제로 비정렬 (정렬이 일을 했는지)")
    def _():
        raw = pq.read_table(DATA / "2025-06-06/log-parquet/log_filebeat-server_2025-06-06_00-00-00.parquet", columns=["@timestamp"]).to_pandas()
        assert not raw["@timestamp"].is_monotonic_increasing
        return "원본 비정렬 확인 → 순서 일치는 2번 그룹 oracle 대조에서 검증"

    # 6. target 필터 — 규칙 하나: 행 주인 == target 이름, 확장 없음
    # pod 목록은 oracle에서 따로 뽑음 (log k8_pod ∪ infra_pod pod)
    pods_w1 = sorted((set(o_log["k8_pod"]) | set(o_metric["infra/infra_pod/infra_pod_pod_cpu_usage"]["pod"])) - {"null"})
    r_cart = None
    for pod in pods_w1:
        @test("6. target 필터 / pod", f"{pod}: log·trace·metric = oracle (누락·초과)")
        def _(pod=pod):
            nonlocal r_cart
            r = reader.read(SRC, {"type": "pod", "name": pod}, S1, E1)
            if pod == "cartservice-0":
                r_cart = r
                dump_case(out, "05_pod_cartservice-0", r)
            exp_log = o_log[o_log["k8_pod"] == pod].reset_index(drop=True)
            exp_trace = o_trace[o_trace["process"].map(lambda p: span_has_owner(p, pod))].reset_index(drop=True)
            for s, exp in (("log", exp_log), ("trace", exp_trace)):
                if len(exp):
                    assert_frame_same(r[s], exp, s)
                else:
                    assert not len(r[s]), f"{s} {len(r[s])}행 (oracle 0)"
            svc = pod.rsplit("-", 1)[0]
            if svc in SERVICES and len(exp_log):  # 데이터 사실 확인 (reader 동작 아님): 로그가 있는(활동 중인) pod 중 계측 없는 서비스만 trace가 빔
                # infra_pod에만 있고 log·trace가 없는 pod도 있음 (W1: checkoutservice-0/1, recommendationservice-1/2)
                assert (len(exp_trace) == 0) == (svc in NO_SPAN), f"계측 없음 목록과 불일치: trace {len(exp_trace)}행"
            exp_m = {}
            for k, df in o_metric.items():
                if re.match(rf"^apm/pod/pod_{re.escape(pod)}( \(deleted\))?$", k):
                    exp_m[k] = df
                elif k.startswith("infra/infra_pod/"):
                    f = df[df["pod"] == pod].reset_index(drop=True)
                    if len(f):
                        exp_m[k] = f
            assert_metric_same(r["metric"], exp_m, "metric")
            return f"log {len(exp_log)}, trace {len(exp_trace)}, metric {len(exp_m)}파일"

    @test("6. target 필터 / pod", "cartservice-0에 redis span(serviceName=redis) 포함, redis-cart 혼입 없음")
    def _():
        n_redis = (r_cart["trace"]["process"].map(lambda p: p["serviceName"]) == "redis").sum()
        assert n_redis > 0, "redis span 없음"
        assert not any("redis-cart" in k for k in r_cart["metric"])
        return f"redis span {n_redis}개"

    for pod, day in [("productcatalogservice-1", "2025-06-06"), ("productcatalogservice-2", "2025-06-06"), ("cartservice-2", "2025-06-07")]:
        @test("6. target 필터 / pod", f"(deleted) apm 파일 포함: {pod} {day}")
        def _(pod=pod, day=day):
            d = pd.Timestamp(day).tz_localize("Asia/Shanghai").tz_convert("UTC")
            r = reader.read(["metric"], {"type": "pod", "name": pod}, d.strftime("%Y-%m-%dT%H:%M:%SZ"),
                            (d + pd.Timedelta(days=1) - SEC).strftime("%Y-%m-%dT%H:%M:%SZ"))
            assert f"apm/pod/pod_{pod} (deleted)" in r["metric"], f"반환 apm 키 {[k for k in r['metric'] if k.startswith('apm/')]}"
            return ", ".join(k for k in r["metric"] if k.startswith("apm/"))

    for typ, name in [("pod", "cartservice"), ("pod", "cartservice-.*"), ("service", "cart"), ("service", "nosuchservice")]:
        @test("6. target 필터 / 이름 일치", f"{typ} '{name}' → 아무것도 안 잡힘 (부분·정규식·없는 이름)")
        def _(typ=typ, name=name):
            r = reader.read(SRC, {"type": typ, "name": name}, S1, E1)
            n = len(r["log"]) + len(r["trace"]) + len(r["metric"])
            assert n == 0, f"{n}개 잡힘"

    for svc in SERVICES:
        @test("6. target 필터 / service", f"{svc}: apm service 파일만 = oracle, log·trace는 읽은 뒤 빈 결과 (하위 pod 확장 없음)")
        def _(svc=svc):
            r, opened = read_spy(SRC, {"type": "service", "name": svc}, S1, E1)
            key = f"apm/service/service_{svc}"
            assert_metric_same(r["metric"], {key: o_metric[key]} if key in o_metric else {}, "metric")
            assert_no_owner_rows(r, opened)
            return f"metric {list(r['metric'])}"

    nodes = sorted(set(o_metric["infra/infra_node/infra_node_node_cpu_usage_rate"]["kubernetes_node"]) - {"null"})
    for node in nodes:
        @test("6. target 필터 / node", f"{node}: infra_node 행만 = oracle, log·trace는 읽은 뒤 빈 결과")
        def _(node=node):
            r, opened = read_spy(SRC, {"type": "node", "name": node}, S1, E1)
            exp = {k: df[df["kubernetes_node"] == node].reset_index(drop=True) for k, df in o_metric.items() if k.startswith("infra/infra_node/")}
            assert_metric_same(r["metric"], {k: v for k, v in exp.items() if len(v)}, "metric")
            assert_no_owner_rows(r, opened)
            return f"{len(r['metric'])}파일"

    @test("6. target 필터 / node", "ef2a4fbb-87 (aiops-k8s-03 node cpu stress) 케이스 저장")
    def _():
        r = reader.read(SRC, {"type": "node", "name": "aiops-k8s-03"}, "2025-06-05T23:10:13Z", "2025-06-05T23:24:13Z")
        dump_case(out, "06_node_aiops-k8s-03", r)
        assert "infra/infra_node/infra_node_node_cpu_usage_rate" in r["metric"]

    for typ, prefix in [("tidb", "infra/infra_tidb/"), ("tikv", "other/infra_tikv_"), ("pd", "other/infra_pd_")]:
        @test("6. target 필터 / TiDB 계층", f"{typ}: file_key = '{prefix}*' 전부 = oracle, 행 필터 없음")
        def _(typ=typ, prefix=prefix):
            r, opened = read_spy(SRC, {"type": typ, "name": typ}, S1, E1)
            if typ == "tikv":
                dump_case(out, "07_tikv", r)
            assert_metric_same(r["metric"], {k: v for k, v in o_metric.items() if k.startswith(prefix)}, "metric")
            assert_no_owner_rows(r, opened)
            objs = set().union(*(set(df["object_type"]) for df in r["metric"].values()))
            assert objs == {typ}, f"object_type {objs}"
            return f"{len(r['metric'])}파일"

    # 7. 빈 결과·공백 (reader는 판정하지 않음 → 데이터 그대로인지만 확인)
    @test("7. 빈 결과·공백", "파일 없는 구간: 06-08 17:00 UTC trace (06-09 CST 01시) → 빈 DF")
    def _():
        t = reader.read(["trace"], None, "2025-06-08T17:00:00Z", "2025-06-08T17:10:00Z")["trace"]
        assert not len(t) and "ts" in t.columns, f"{len(t)}행, 열 {list(t.columns)}"

    @test("7. 빈 결과·공백", "일부 공백: d0be3c58-178 trace = oracle, 19분 중 3분만 행 있음")
    def _():
        s, e = "2025-06-09T21:10:22Z", "2025-06-09T21:28:22Z"
        r = reader.read(SRC, None, s, e)
        dump_case(out, "08_gap_d0be3c58-178", r)
        assert_frame_same(r["trace"], oracle_hourly("trace", ts_utc(s), ts_utc(e)), "trace")
        assert minutes(r["trace"]) == 3, minutes(r["trace"])
        return f"trace {len(r['trace'])}행, 3/19분"

    @test("7. 빈 결과·공백", "계측 없는 서비스의 pod(adservice-0) trace → 빈 DF, 파일은 읽음")
    def _():
        r, opened = read_spy(["trace"], {"type": "pod", "name": "adservice-0"}, S1, E1)
        assert not len(r["trace"]) and any(p.parent.name == "trace-parquet" for p in opened)

    # 8. 결정성
    @test("8. 결정성", "같은 입력 2회 호출 결과 동일")
    def _():
        a = reader.read(SRC, {"type": "service", "name": "frontend"}, S1, E1)
        b = reader.read(SRC, {"type": "service", "name": "frontend"}, S1, E1)
        assert_frame_same(a["log"], b["log"], "log")
        assert_frame_same(a["trace"], b["trace"], "trace")
        assert_metric_same(a["metric"], b["metric"], "metric")

    # 9. 전수 sweep
    if args.skip_sweep:
        RESULTS.append(("9. 전수 sweep", "groundtruth 400건", "PASS", "생략 (--skip-sweep)"))
    else:
        rows, problems = [], []
        gt = [json.loads(l) for l in open(DATA / "groundtruth.jsonl", encoding="utf-8")]
        for i, g in enumerate(gt, 1):
            s, e = g["start_time"], g["end_time"]
            row = {"uuid": g["uuid"], "cst_date": ts_utc(s).tz_convert("Asia/Shanghai").strftime("%Y-%m-%d"), "start": s, "end": e,
                   "duration_s": int((ts_utc(e) - ts_utc(s)).total_seconds())}
            t0 = time.time()
            try:
                r = reader.read(SRC, None, s, e)
                total = int((ts_utc(e).floor("min") - ts_utc(s).floor("min")).total_seconds() // 60) + 1
                metric_ts = pd.concat([df[["ts"]] for df in r["metric"].values()]) if r["metric"] else pd.DataFrame({"ts": []})
                for src, df in [("log", r["log"]), ("trace", r["trace"]), ("metric", metric_ts)]:
                    row.update({f"{src}_rows": len(df), f"{src}_minutes": minutes(df), f"{src}_total": total})
                lo, hi = ts_utc(s), ts_utc(e) + SEC
                for k, df in [("log", r["log"]), ("trace", r["trace"])] + list(r["metric"].items()):
                    if len(df) and not df["ts"].is_monotonic_increasing:
                        problems.append(f"{g['uuid']} {k} 비정렬")
                    if len(df) and (df["ts"].min() < (lo.floor("min") if k not in ("log", "trace") else lo) or df["ts"].max() >= hi):
                        problems.append(f"{g['uuid']} {k} 구간 밖 행")
                row["error"] = ""
            except Exception as ex:
                row["error"] = f"{type(ex).__name__}: {ex}"
                problems.append(f"{g['uuid']} {row['error']}")
            row["read_s"] = round(time.time() - t0, 2)
            rows.append(row)
            if i % 20 == 0:
                print(f"  sweep {i}/{len(gt)}")
        sw = pd.DataFrame(rows)
        sw.to_csv(out / "sweep_rows.csv", index=False, encoding="utf-8-sig")

        RESULTS.append(("9. 전수 sweep", "400건 예외·비정렬·구간 밖 행 없음",
                        "PASS" if not problems else "FAIL", f"문제 {len(problems)}건: {problems[:5]}; 평균 {sw['read_s'].mean():.1f}s, 최대 {sw['read_s'].max():.1f}s"))
        for src, expect in [("log", 21), ("trace", 40)]:
            n0 = int((sw[f"{src}_rows"] == 0).sum()) if f"{src}_rows" in sw else -1
            RESULTS.append(("9. 전수 sweep", f"{src} 행 0인 케이스 = {expect}건 (data/CLAUDE.md)", "PASS" if n0 == expect else "FAIL", f"{n0}건"))
        for src in SRC:
            if f"{src}_minutes" in sw:
                part = sw[(sw[f"{src}_minutes"] > 0) & (sw[f"{src}_minutes"] < sw[f"{src}_total"])]
                miss = part[f"{src}_total"] - part[f"{src}_minutes"]
                RESULTS.append(("9. 전수 sweep", f"{src} 일부 분 공백 (참고)", "PASS",
                                f"{len(part)}건: 1분 공백 {int((miss == 1).sum())}, 2분 이상 {int((miss >= 2).sum())}"))

    n = write_report(out, time.time() - t_all)
    print(f"\n{out}\nPASS {n['PASS']} / FAIL {n['FAIL']} / ERROR {n['ERROR']} / INFO {n['INFO']}")
    sys.exit(1 if n["FAIL"] or n["ERROR"] else 0)


if __name__ == "__main__":
    main()
