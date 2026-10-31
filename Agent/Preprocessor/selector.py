"""selector: reader가 자른 원본에서 이상 패턴만 골라 LLM용 텍스트로 바꾼다 (OpsAgent 3.2 Training-free Data Processor).

OpsAgent 공개 코드(참고 구현/OpsAgent-CCC0, utils/data_processer.py)를 따른다.
논문과 코드가 다른 곳(log 상위 분위 0.8 vs 0.98, trace p95 vs p98, log 출력 원문 vs 템플릿)은 논문을 따른다.
- 조회 구간 = 요청 구간 그대로, 기준(평균·표준편차, 분위) = 그 구간 전체.
  OpsAgent process_data는 쿼리를 start+30분으로 고정하고 metric을 앞 20분·뒤 10분 더 읽지만,
  baseline 성능 측정 전까지는 연구실 보고대로 input 구간만 쓰고 부족하면 "판정 불가"로 표시한다 (생각.txt 아이디어 7).
- 데이터셋 차이: metric quirk('null' 문자열, kpi_key 값 열, 차원 열), trace pod·node 태그 이름,
  callee = span 자신의 pod (redis client span은 "redis"), 호출 유형(p95 기준)은 (서비스, operation).
  결측은 0으로 채우지 않는다 (OpsAgent는 fillna(0) — 가짜 dip이 생겨 따르지 않음).
- target 한정 (Loop 재검색): target=None이면 전체 Top-5 instance, target이 있으면 그 엔티티 안에서 Top-5 metric.
  trace는 부모 span이 필요해서 target=None으로 읽은 뒤 target이 낀 span만 남긴다.
"""
import re
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from drain3 import TemplateMiner
from drain3.template_miner_config import TemplateMinerConfig
from sklearn.feature_extraction.text import TfidfVectorizer

import reader

SIGMA = 3
TOP_K = 5
CNN_BEFORE, CNN_AFTER = 20, 10   # 이상 시점 앞 20 / 뒤 10 = 30포인트 (OpsAgent CNN 입력 길이 고정)
LOG_KEYWORDS = ["failure", "fail", "failed", "error", "fatal", "crash"]   # OpsAgent extract_log_features 기본값
LOG_PERCENTILE = 80     # 논문 (OpsAgent 코드 호출값은 0.98)
TRACE_PERCENTILE = 95   # 논문 (OpsAgent 코드는 0.98)
MAX_METRIC_LINES, MAX_TRACE_LINES, MAX_PATHS = 24, 24, 24   # OpsAgent 코드 상한 (log는 상한 없음)
METRIC_SKIP_PEAKS, METRIC_SKIP_DEV = 10, 6   # OpsAgent: 10회 넘게 반복되고 최대 6σ 미만인 묶음은 출력 안 함
DIMS = ["type", "cf", "device", "mountpoint", "sql_type"]
SHAPES = ["Level shift up", "Level shift down", "Steady increase", "Steady decrease", "Single spike", "Single dip",
          "Transient level shift up", "Transient level shift down", "Multiple spikes", "Multiple dips", "Fluctuations"]
ANSI = re.compile(r"\x1b\[[0-9;]*m")


def select(sources, target, start_time, end_time):
    """[start_time, end_time] 구간(= baseline = 관찰 구간)의 이상 패턴 텍스트."""
    sources = list(sources)
    data = {s: reader.read([s], None if s == "trace" else target, start_time, end_time)[s] for s in sources}
    t0 = pd.Timestamp(start_time).floor("min")  # metric 시각이 분 라벨이라 같이 내림 (안 하면 +-1m)
    out = [f"조회 구간: {start_time} ~ {end_time} (기준 = 이 구간 전체, 시각 옆 +Nm은 구간 시작 분 기준)"
           + (f" / target: {target['type']} {target['name']}" if target else "")]
    for s in sources:
        out.append({"metric": _metric, "log": _log, "trace": _trace}[s](data[s], target, t0))
    return "\n\n".join(out)


def entities(start_time, end_time):
    """구간 metric의 행 주인 = 조회 가능한 target 이름 {type: [name]} (Loop tool 선택지, 생각.txt 아이디어 6)."""
    out = {t: set() for t in ["pod", "service", "node", "tidb", "tikv", "pd"]}
    for key, df in reader.read(["metric"], None, start_time, end_time)["metric"].items():
        if df.empty:
            continue
        typ = df["object_type"].iloc[0]
        if key.startswith("apm/"):
            if typ in ("pod", "service"):
                out[typ].update(df["object_id"])
        elif typ in ("pod", "node"):
            out[typ].update(df[{"pod": "pod", "node": "kubernetes_node"}[typ]])
        elif typ in out:  # TiDB 계층은 컴포넌트 단위
            out[typ].add(typ)
    return {t: sorted(v - {"null", ""}) for t, v in out.items() if v - {"null", ""}}


def _rel(ts, t0):
    return f"{ts:%H:%M:%S} ({int((ts - t0).total_seconds() // 60):+d}m)"


# ---------- metric: 3σ → CNN 모양 → Top-5 ----------

class _CNN(nn.Module):  # OpsAgent metric_anomaly.py CNN과 같은 구조 (가중치 patterncla.pt 로드용)
    def __init__(self, classes=11):
        super().__init__()
        self.conv1 = nn.Sequential(nn.Conv1d(1, 64, 5, 1, 1), nn.ReLU(), nn.MaxPool1d(2))
        self.conv2 = nn.Sequential(nn.Conv1d(64, 128, 5, 1, 1, bias=False), nn.ReLU(), nn.MaxPool1d(2))
        self.conv3 = nn.Sequential(nn.Conv1d(128, 256, 5, 1, 1, bias=False), nn.ReLU(), nn.MaxPool1d(2))
        self.flatten = nn.Sequential(nn.Linear(512, 64), nn.BatchNorm1d(64), nn.ReLU())
        self.out = nn.Linear(64, classes)

    def forward(self, x):
        x = self.conv3(self.conv2(self.conv1(x)))
        return self.out(self.flatten(x.view(x.size(0), -1)))


_cnn = _CNN()
# 출처: OpsAgent 공개 저장소 patterncla.pt (https://anonymous.4open.science/r/OpsAgent-CCC0)
_cnn.load_state_dict(torch.load(Path(__file__).with_name("patterncla.pt"), map_location="cpu"))
_cnn.eval()


def _shapes(segs):
    """30포인트 구간들 → 모양 이름 (min-max 정규화, 한 번에 추론)."""
    if not segs:
        return []
    x = np.stack(segs)
    x = (x - x.min(axis=1, keepdims=True)) / np.ptp(x, axis=1, keepdims=True)
    with torch.no_grad():
        return [SHAPES[i] for i in _cnn(torch.tensor(x, dtype=torch.float).unsqueeze(1)).argmax(1).tolist()]


def _series(metric):
    """{file_key: DF} → [(entity, metric_name, 분 단위 Series)]. quirk 흡수는 여기서만."""
    for key, df in metric.items():
        if key.startswith("apm/"):  # 넓은 형식: 숫자 열마다 지표 하나, 행 주인 = object_id
            for col in df.columns.drop(["time", "ts", "object_id", "object_type"]):
                for ent, g in df.groupby("object_id"):
                    yield ent, col, pd.to_numeric(g.set_index("ts")[col], errors="coerce")
            continue
        kpi = df["kpi_key"].iloc[0]
        typ = df["object_type"].iloc[0]
        ent_col = {"pod": "pod", "node": "kubernetes_node"}.get(typ)
        # TiDB 계층 instance는 엔티티 이름이 아니라 같은 컴포넌트 안의 여러 행을 가르는 차원 (생각.txt 아이디어 6)
        dims = [d for d in DIMS + ([] if ent_col else ["instance"]) if (df[d] != "null").any()]
        for keys, g in df.groupby(([ent_col] if ent_col else []) + dims if (ent_col or dims) else lambda _: 0):
            keys = keys if isinstance(keys, tuple) else (keys,)
            ent = keys[0] if ent_col else typ
            label = kpi + ("{" + ",".join(f"{d}={v}" for d, v in zip(dims, keys[1 if ent_col else 0:])) + "}" if dims else "")
            yield ent, label, pd.to_numeric(g.set_index("ts")[kpi], errors="coerce")


def _metric(metric, target, t0):
    if not metric:
        return "[metric] 행 없음"
    # OpsAgent extract_metric_features: 3σ를 넘은 모든 시점이 이상, 시점마다 CNN 모양
    points, segs, n_series, n_points = [], [], 0, 0   # points = (ent, name, ts, z), segs[k] = points[k]의 30포인트 (없으면 None)
    for ent, name, s in _series(metric):
        s = s.groupby(level=0).mean()
        s = s.reindex(pd.date_range(s.index.min(), s.index.max(), freq="min"))
        v = s.to_numpy(dtype=float)
        n_series += 1
        n_points = max(n_points, int(np.isfinite(v).sum()))
        mu, sd = np.nanmean(v), np.nanstd(v, ddof=1)   # pandas std와 같은 표본 표준편차
        if not np.isfinite(sd) or sd == 0:
            continue
        z = np.abs(v - mu) / sd
        n = len(v)
        for i in np.flatnonzero(z > SIGMA):
            st, en = max(0, i - CNN_BEFORE), min(n, i + CNN_AFTER)
            if en - st < CNN_BEFORE + CNN_AFTER:   # 끝에 붙으면 반대쪽으로 늘려 30포인트를 채움 (OpsAgent와 같음)
                pad = CNN_BEFORE + CNN_AFTER - (en - st)
                st, en = (st - pad, en) if st > pad else (st, min(n, en + pad))
            seg = v[st:en]
            points.append((ent, name, s.index[i], float(z[i])))
            segs.append(seg if len(seg) < CNN_BEFORE + CNN_AFTER   # 길이 부족은 그대로 넘겨 이유를 구분
                        else seg if np.isfinite(seg).all() and np.ptp(seg) > 0 else None)

    need = CNN_BEFORE + CNN_AFTER
    head = f"[metric] 시리즈 {n_series}개, 최대 {n_points}포인트(1분 1포인트), 이상 시점 {len(points)}개 (기준 {SIGMA}σ)"
    if n_points <= SIGMA ** 2 + 1:  # 표본 표준편차 기준 z 최댓값 = (n-1)/sqrt(n) → n ≤ 10이면 3σ를 넘을 수 없음
        head += (f" — 조회 구간이 짧아 포인트 {n_points}개로는 {SIGMA}σ를 넘을 수 없음 (이상 0개 ≠ 정상). "
                 f"{SIGMA ** 2 + 2}포인트 이상이 되도록 구간을 넓히면 판정 가능")
    elif n_points < need:
        head += (f" — 조회 구간이 짧아 모양(CNN) 판정에 필요한 {need}포인트를 못 채움 → 모양 '판정 불가(구간 짧음)'. "
                 f"{need}포인트 이상이 되도록 구간을 넓히면 판정 가능")
    if not points:
        return head
    df = pd.DataFrame(points, columns=["ent", "name", "ts", "score"])
    lines = [head]
    if target is None:
        top_ent = df.groupby("ent")["score"].sum().nlargest(TOP_K).index.tolist()   # 이상 시점 z 합
        lines.append(f"Top-{TOP_K} instances with largest deviations: {', '.join(top_ent)}")
        top_metric = df[df["ent"].isin(top_ent)].groupby("name")["score"].sum().nlargest(TOP_K).index.tolist()
    else:
        top_metric = df.groupby("name")["score"].sum().nlargest(TOP_K).index.tolist()
    lines.append(f"Top-{TOP_K} metrics with largest deviations: {', '.join(top_metric)}")

    # 설명 줄 = (엔티티, 지표, 모양) 묶음, 최대 편차순 (Top-5 instance로 거르지 않음).
    # 30포인트를 못 채운 시점은 OpsAgent처럼 버리지 않고 "판정 불가"로 남긴다 (조회 구간이 input 그대로라 짧음)
    idx = [k for k, sg in enumerate(segs) if sg is not None and len(sg) == need]
    shape_of = dict(zip(idx, _shapes([segs[k] for k in idx])))
    groups = defaultdict(list)
    for k, (ent, name, ts, z) in enumerate(points):
        shape = shape_of.get(k) or ("판정 불가(결측·평탄)" if segs[k] is None else "판정 불가(구간 짧음)")
        groups[(ent, name, shape)].append((ts, z))
    lines.append("Metric descriptions sorted by deviation_score:")
    for (ent, name, shape), tz in sorted(groups.items(), key=lambda g: -max(z for _, z in g[1]))[:MAX_METRIC_LINES]:
        tz.sort()
        mx = max(z for _, z in tz)
        if len(tz) > METRIC_SKIP_PEAKS and mx < METRIC_SKIP_DEV:
            continue
        when = (f"{_rel(tz[0][0], t0)} ~ {_rel(tz[-1][0], t0)} ({len(tz)} times)" if len(tz) >= 3
                else ", ".join(_rel(t, t0) for t, _ in tz))
        lines.append(f"- {ent} | {name} | {shape}: {when}, max deviation ≈ {mx:.1f}σ")
    return "\n".join(lines)


# ---------- log: 키워드 → Drain3 → TF-IDF 80% → 1분 중복 제거 ----------

def _log(log, target, t0):
    if not len(log):
        return "[log] 행 없음"
    # 논문 순서: 키워드 필터 → 걸린 로그를 Drain3 템플릿으로 → 템플릿 TF-IDF(줄 단위 평균, OpsAgent 코드 설정) → 상위 분위 → 분·템플릿 중복 제거.
    # OpsAgent 코드는 Drain3를 전체 로그에 돌리지만 없는 키(log_template)를 읽어 실제로는 원문을 씀 → 논문을 따름
    msg = log["message"].fillna("").map(lambda m: ANSI.sub("", m).strip())
    hit = log.assign(msg=msg)[msg.str.contains("|".join(map(re.escape, LOG_KEYWORDS)), case=False)]
    head = f"[log] 행 {len(log)}개, 키워드 일치 {len(hit)}개"
    if not len(hit):
        return head
    cfg = TemplateMinerConfig()
    cfg.profiling_enabled = False
    miner = TemplateMiner(config=cfg)
    ids = [miner.add_log_message(m)["cluster_id"] for m in hit["msg"]]
    final = {c.cluster_id: c.get_template() for c in miner.drain.clusters}   # 학습이 끝난 뒤의 템플릿
    hit = hit.assign(tpl=[final[i] for i in ids])
    vec = TfidfVectorizer(use_idf=True, binary=True, smooth_idf=True, norm=None, stop_words="english")
    try:
        priority = np.asarray(vec.fit_transform(hit["tpl"]).mean(axis=1)).ravel()
    except ValueError:   # 템플릿이 전부 불용어·숫자뿐이면 어휘가 비어 fit 실패 → 우선순위 동일
        priority = np.zeros(len(hit))
    hit = hit.assign(priority=priority)
    sel = hit[hit["priority"] >= hit["priority"].quantile(LOG_PERCENTILE / 100)]
    sel = sel.assign(min=sel["ts"].dt.floor("min")).sort_values("ts").drop_duplicates(["min", "tpl"])
    lines = [head + f", 상위 {100 - LOG_PERCENTILE}% 분위 이상·분당 템플릿 1건 {len(sel)}건",
             "Failure-indicative log entries after two-stage filtering:"]
    lines += [f"- {_rel(r.ts, t0)} <{r.k8_pod}> | {r.msg}" for r in sel.itertuples()]
    return "\n".join(lines)


# ---------- trace: 호출 유형별 p95 → (60초, callee) 집계 + 3-hop 경로 ----------

def _span_info(process):
    tags = {t["key"]: t["value"] for t in process["tags"]}  # cartservice·redis는 podName/nodeName
    return process["serviceName"], tags.get("name") or tags.get("podName"), tags.get("node_name") or tags.get("nodeName")


def _trace(trace, target, t0):
    if not len(trace):
        return "[trace] 행 없음"
    info = pd.DataFrame(trace["process"].map(_span_info).tolist(), columns=["svc", "pod", "node"])
    df = pd.concat([trace[["spanID", "operationName", "duration", "ts"]].reset_index(drop=True), info], axis=1)
    df["parent"] = trace["references"].map(lambda r: r[0]["spanID"] if len(r) else None).to_numpy()
    # 출력 단위 = 인스턴스(pod), OpsAgent 예시 Callee=IG01(인스턴스 ID)과 같은 단위.
    # redis span은 cartservice pod에서 실행되는 redis client span이라 pod가 아니라 "redis"로 둔다
    df["ent"] = [p if isinstance(p, str) and p.startswith(s + "-") else s for s, p in zip(df["svc"], df["pod"])]
    by_id = df.drop_duplicates("spanID").set_index("spanID")
    for c in ["svc", "pod", "node", "ent"]:
        df["p_" + c] = df["parent"].map(by_id[c])
    df["gp_ent"] = df["parent"].map(by_id["parent"]).map(by_id["ent"])

    # 호출 유형 = (callee 서비스, operation). 임계값은 조회 구간 전체에서 (OpsAgent와 동일)
    df["thr"] = df.groupby(["svc", "operationName"])["duration"].transform(lambda d: np.percentile(d, TRACE_PERCENTILE))
    df["high"] = df["duration"] > df["thr"]
    if target is not None:
        col = {"pod": "pod", "service": "svc", "node": "node"}.get(target["type"])
        df = df[(df[col] == target["name"]) | (df["p_" + col] == target["name"])] if col else df.iloc[:0]
    head = f"[trace] span {len(trace)}개" + (f", target 관련 {len(df)}개" if target else "")
    high = df[df["high"]]
    if not len(high):
        return head + ", 고지연 0건"
    head += f", 호출 유형별 p{TRACE_PERCENTILE} 초과 {len(high)}건"

    # OpsAgent generate_trace_descriptions: (60초, callee)별 고지연 건수·최대 지연·caller 분포, 건수 → 최대 지연순.
    # caller는 부모 span의 주인, 부모가 데이터에 없으면 callee 자신
    high = high.assign(min=high["ts"].dt.floor("min"), caller=high["p_ent"].fillna(high["ent"]))
    rows = []
    for (m, ent), g in high.groupby(["min", "ent"]):
        callers = ", ".join(f"{c}×{n}" for c, n in sorted(Counter(g["caller"]).items()))
        rows.append((len(g), int(g["duration"].max()), m, ent, callers))
    rows.sort(key=lambda r: (-r[0], -r[1]))
    lines = [head, "High-latency span descriptions:"]
    for n, mx, m, ent, callers in rows[:MAX_TRACE_LINES]:
        lines.append(f"- <{_rel(m, t0)}~+60s, Callee={ent}, Count={n}, MaxLatency={mx}us, Callers=[{callers}]>")
    # 3-hop 경로: 조부모까지 데이터에 있는 것만, 2회 이상
    known = high[high["gp_ent"].notna()]
    paths = Counter(zip(known["gp_ent"], known["caller"], known["ent"]))
    lines.append("Three-hop call paths statistics:")
    lines += [f'- "{a} → {b} → {c}" has occurred {n} times in the time window'
              for (a, b, c), n in paths.most_common() if n >= 2][:MAX_PATHS]
    return "\n".join(lines)


if __name__ == "__main__":
    import time

    S, E = "2025-06-05T16:10:02Z", "2025-06-05T16:31:02Z"  # 345fbe93-80 emailservice cpu stress
    t = time.time()
    text = select(reader.SOURCES, None, S, E)
    print(text, f"\n--- {time.time() - t:.1f}s, {len(text)} chars")
    assert text.startswith("조회 구간") and "[metric]" in text and "[log]" in text and "[trace]" in text
    assert "Top-5 instances" in text and "판정 불가(구간 짧음)" in text and "구간을 넓히면" in text   # 21분 → CNN 30포인트 못 채움

    # 1분짜리 구간: metric 포인트 부족 표시
    short = select(["metric"], None, "2025-06-05T16:10:02Z", "2025-06-05T16:12:02Z")
    assert "판정 불가" in short or "이상 시점 0개" in short, short

    # target: 그 엔티티만, instance Top-5 없음 / tikv는 trace 없음
    tt = select(reader.SOURCES, {"type": "pod", "name": "emailservice-0"}, S, E)
    assert "Top-5 instances" not in tt and "target: pod emailservice-0" in tt
    tk = select(["trace"], {"type": "tikv", "name": "tikv"}, S, E)
    assert "target 관련 0개" in tk, tk

    # 구간 공백: trace 파일 없는 시간대
    assert "[trace] 행 없음" in select(["trace"], None, "2025-06-08T17:00:00Z", "2025-06-08T17:10:00Z")
    print("ok")
