"""selector: reader가 자른 원본에서 이상 패턴만 골라 LLM용 텍스트로 바꾼다 (OpsAgent 3.2 Training-free Data Processor).

OpsAgent를 그대로 따르고, 세 가지만 바꿨다 (생각.txt 아이디어 7).
- 데이터셋 차이: metric quirk('null' 문자열, kpi_key 값 열, 차원 열), trace pod·node 태그 이름, callee = span 자신의 서비스.
- 조회 구간이 바뀜: baseline = 조회 구간 전체 (OpsAgent와 동일). 구간이 넓어지면 넓어진 구간으로 다시 계산. 상태 없음.
- target 한정: target=None이면 전체 Top-5 instance, target이 있으면 그 엔티티 안에서 Top-5 metric.
  trace는 부모 span이 필요해서 target=None으로 읽은 뒤 target이 낀 span만 남긴다.
"""
import re
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from drain3 import TemplateMiner
from drain3.template_miner_config import TemplateMinerConfig

import reader

SIGMA = 3            # 논문 3σ (OpsAgent 코드는 |x-μ|/σ/2 > 1, 즉 2σ — 논문 기준을 따름)
TOP_K = 5
CNN_BEFORE, CNN_AFTER = 20, 10   # 이상 시점 앞 20 / 뒤 10 = 30포인트 (OpsAgent CNN 입력 길이 고정)
LOG_KEYWORDS = re.compile(r"fatal|error|crash|fail", re.I)
LOG_PERCENTILE = 80
TRACE_PERCENTILE = 95
MAX_METRIC_LINES, MAX_LOG_LINES, MAX_TRACE_LINES, MAX_PATHS = 30, 40, 20, 10  # ponytail: 고정 상한, 토큰 측정 후 조정
DIMS = ["type", "cf", "device", "mountpoint", "sql_type"]
SHAPES = ["Level shift up", "Level shift down", "Steady increase", "Steady decrease", "Single spike", "Single dip",
          "Transient level shift up", "Transient level shift down", "Multiple spikes", "Multiple dips", "Fluctuations"]
ANSI = re.compile(r"\x1b\[[0-9;]*m")


def select(sources, target, start_time, end_time):
    """[start_time, end_time] 구간(= baseline = 관찰 구간)의 이상 패턴 텍스트."""
    sources = list(sources)
    data = reader.read([s for s in sources if s != "trace"], target, start_time, end_time) if set(sources) - {"trace"} else {}
    if "trace" in sources:
        data["trace"] = reader.read(["trace"], None, start_time, end_time)["trace"]
    t0 = pd.Timestamp(start_time).floor("min")  # metric 시각이 분 라벨이라 같이 내림 (안 하면 +-1m)
    out = [f"조회 구간: {start_time} ~ {end_time} (기준 = 이 구간 전체, 시각 옆 +Nm은 구간 시작 분 기준)"
           + (f" / target: {target['type']} {target['name']}" if target else "")]
    for s in sources:
        out.append({"metric": _metric, "log": _log, "trace": _trace}[s](data[s], target, t0))
    return "\n\n".join(out)


def _rel(ts, t0):
    return f"{ts:%H:%M:%S} (+{int((ts - t0).total_seconds() // 60)}m)"


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


def _shape(seg):
    seg = (seg - seg.min()) / (seg.max() - seg.min())
    with torch.no_grad():
        return SHAPES[int(_cnn(torch.tensor(seg, dtype=torch.float).view(1, 1, -1)).argmax())]


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
    anomalies, n_series, n_points = [], 0, 0
    for ent, name, s in _series(metric):
        s = s.groupby(level=0).mean()
        s = s.reindex(pd.date_range(s.index.min(), s.index.max(), freq="min"))
        v = s.to_numpy(dtype=float)
        n_series += 1
        n_points = max(n_points, int(np.isfinite(v).sum()))
        mu, sd = np.nanmean(v), np.nanstd(v)
        if not np.isfinite(sd) or sd == 0:
            continue
        z = np.abs(v - mu) / sd
        hit = np.flatnonzero(z > SIGMA)
        if not len(hit):
            continue
        i = int(hit[np.nanargmax(z[hit])])  # 시리즈당 1행: 최대 점수 시점
        seg = v[i - CNN_BEFORE:i + CNN_AFTER] if i >= CNN_BEFORE else np.array([])
        shape = _shape(seg) if len(seg) == CNN_BEFORE + CNN_AFTER and np.isfinite(seg).all() and np.ptp(seg) > 0 else "판정 불가(30포인트 미만)"
        anomalies.append((ent, name, shape, s.index[int(hit[0])], s.index[i], float(z[i])))

    head = f"[metric] 시리즈 {n_series}개, 최대 {n_points}포인트, 이상 {len(anomalies)}개 (기준 {SIGMA}σ)"
    if n_points <= SIGMA ** 2 + 1:  # 모표준편차 기준 z 최댓값 = sqrt(n-1) → n ≤ 10이면 3σ를 넘을 수 없음
        head += f" — 포인트 {n_points}개로는 {SIGMA}σ 판정 불가"
    if not anomalies:
        return head
    df = pd.DataFrame(anomalies, columns=["ent", "name", "shape", "first", "peak", "score"])
    lines = [head]
    if target is None:
        top_ent = df.groupby("ent")["score"].sum().nlargest(TOP_K).index.tolist()
        lines.append(f"Top-{TOP_K} instances with largest deviations: {', '.join(top_ent)}")
        df = df[df["ent"].isin(top_ent)]
    top_metric = df.groupby("name")["score"].sum().nlargest(TOP_K).index.tolist()
    lines.append(f"Top-{TOP_K} metrics with largest deviations: {', '.join(top_metric)}")
    lines.append("Metric descriptions sorted by deviation_score:")
    for r in df.nlargest(MAX_METRIC_LINES, "score").itertuples():
        lines.append(f"- {r.ent} | {r.name} | {r.shape}: first {_rel(r.first, t0)}, peak {_rel(r.peak, t0)}, "
                     f"deviation_score ≈ {r.score:.1f}σ")
    return "\n".join(lines)


# ---------- log: 키워드 → Drain3 → TF-IDF 80% → 1분 중복 제거 ----------

def _log(log, target, t0):
    if not len(log):
        return "[log] 행 없음"
    hit = log[log["message"].str.contains(LOG_KEYWORDS, na=False)].copy()
    head = f"[log] 행 {len(log)}개, 키워드 일치 {len(hit)}개"
    if not len(hit):
        return head
    cfg = TemplateMinerConfig()
    cfg.profiling_enabled = False
    miner = TemplateMiner(config=cfg)
    hit["msg"] = hit["message"].map(lambda m: ANSI.sub("", m).strip())
    hit["tpl"] = [miner.add_log_message(m)["cluster_id"] for m in hit["msg"]]
    hit["min"] = hit["ts"].dt.floor("min")

    # TF-IDF: 문서 = 구간 안의 1분 묶음. 구간 전체에서 많이 나오되(tf) 일부 분에만 몰린(idf) 템플릿이 높음
    n_docs = hit["min"].nunique()
    tf = hit["tpl"].value_counts() / len(hit)
    idf = np.log((1 + n_docs) / (1 + hit.groupby("tpl")["min"].nunique())) + 1
    score = tf * idf
    keep = score[score >= np.percentile(score, LOG_PERCENTILE)].index
    sel = hit[hit["tpl"].isin(keep)].drop_duplicates(["tpl", "min"])  # ts 정렬 상태 → 템플릿·분마다 가장 이른 1건
    sel = sel.assign(score=sel["tpl"].map(score)).nlargest(MAX_LOG_LINES, "score").sort_values("ts")
    lines = [head + f", 템플릿 {len(score)}종 중 상위 {100 - LOG_PERCENTILE}% {len(keep)}종, 출력 {len(sel)}건",
             "Failure-indicative log entries after two-stage filtering:"]
    lines += [f"- {_rel(r.ts, t0)} <{r.k8_pod}> | {r.msg[:300]}" for r in sel.itertuples()]
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
    by_id = df.drop_duplicates("spanID").set_index("spanID")
    for c in ["svc", "pod", "node"]:
        df["p_" + c] = df["parent"].map(by_id[c])
    df["gp_svc"] = df["parent"].map(by_id["parent"]).map(by_id["svc"])

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

    # (60초, callee)별 건수·최대 지연·caller 분포. 순위 = 그 분 callee 전체 span 중 고지연 비율 (정상이면 ~5%)
    df = df.assign(min=df["ts"].dt.floor("min"))
    total = df.groupby(["min", "svc"]).size()
    rows = []
    for (m, svc), g in high.assign(min=high["ts"].dt.floor("min")).groupby(["min", "svc"]):
        callers = Counter(g["p_svc"].fillna("(root)"))
        rows.append((len(g) / total[(m, svc)], m, svc, len(g), int(g["duration"].max()),
                     ", ".join(f"{c}×{n}" for c, n in callers.most_common(3))))
    rows.sort(reverse=True)
    lines = [head, "High-latency span descriptions (rank = 그 분 callee span 중 고지연 비율):"]
    for ratio, m, svc, n, mx, callers in rows[:MAX_TRACE_LINES]:
        lines.append(f"- <{_rel(m, t0)}~+60s, Callee={svc}, Count={n} ({ratio:.0%}), MaxLatency={mx}us, Callers=[{callers}]>")
    paths = Counter(zip(high["gp_svc"].fillna("(root)"), high["p_svc"].fillna("(root)"), high["svc"]))
    lines.append("Three-hop call paths statistics:")
    lines += [f'- "{a} → {b} → {c}" has occurred {n} times in the time window' for (a, b, c), n in paths.most_common(MAX_PATHS)]
    return "\n".join(lines)


if __name__ == "__main__":
    import time

    S, E = "2025-06-05T16:10:02Z", "2025-06-05T16:31:02Z"  # 345fbe93-80 emailservice cpu stress
    t = time.time()
    text = select(reader.SOURCES, None, S, E)
    print(text, f"\n--- {time.time() - t:.1f}s, {len(text)} chars")
    assert text.startswith("조회 구간") and "[metric]" in text and "[log]" in text and "[trace]" in text
    assert "Top-5 instances" in text

    # 1분짜리 구간: metric 포인트 부족 표시
    short = select(["metric"], None, "2025-06-05T16:10:02Z", "2025-06-05T16:12:02Z")
    assert "판정 불가" in short or "이상 0개" in short, short

    # target: 그 엔티티만, instance Top-5 없음 / tikv는 trace 없음
    tt = select(reader.SOURCES, {"type": "pod", "name": "emailservice-0"}, S, E)
    assert "Top-5 instances" not in tt and "target: pod emailservice-0" in tt
    tk = select(["trace"], {"type": "tikv", "name": "tikv"}, S, E)
    assert "target 관련 0개" in tk, tk

    # 구간 공백: trace 파일 없는 시간대
    assert "[trace] 행 없음" in select(["trace"], None, "2025-06-08T17:00:00Z", "2025-06-08T17:10:00Z")
    print("ok")
