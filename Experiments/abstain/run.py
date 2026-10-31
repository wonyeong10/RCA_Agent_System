"""포기 신호 가설 실험 v2 (생각.txt 아이디어 5): Solar가 근거가 부족할 때 답을 포기하는가(A), 재검색 tool을 부르는가(B).

v1(output/2026-10-29_202346)의 L1(원인을 3 source 전부에서 삭제)·L2(이상 줄 전부 삭제)는 현실에 거의 없는 조건이라 교체.
근거 수준 (system card 없음 — 구조가 맞다는 보장이 아직 없어 제외)
- L0      : 원인이 2개 이상 source에서 보이는 케이스 원본 (근거 충분)
- L1a     : 같은 케이스에서 원인이 보이는 source 1개만 남기고 나머지 source의 원인 줄 삭제 (인공, 단일 source 근거)
- N1      : 원래 원인이 1개 source에서만 보이는 케이스 (자연)
- N0      : 원인이 어느 source에도 안 보이는 케이스, 구간 10분 초과 (자연, selector가 놓친 케이스)
- Nshort  : 구간 10분 이하 (자연, metric 3σ 판정 불가)
"보인다" = 정답 엔티티가 주인인 줄 (metric `- X |`, log `<X>`, trace `Callee=X`). 호출자·로그 메시지 속 언급은 셈하지 않음.
트랙
- A 답변 호출: reasoning medium, json_schema {status: answer|insufficient, ...} → 포기 = insufficient
- B 결정 호출: reasoning 끔, tool_choice=required, search|finish 첫 호출만 → 포기 = finish 없음
groundtruth는 케이스 선택·채점에만 쓴다. 모든 호출은 Agent/util/llm.call (토큰·비용·시간 기록).

레포 루트에서 `.venv/Scripts/python.exe Experiments/abstain/run.py [--pilot] [--n 30] [--n-short 20] [--reps 3]`
"""
import argparse
import json
import random
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "Agent" / "Preprocessor"), str(ROOT / "Agent")]
import selector  # noqa: E402
from util import llm  # noqa: E402

MODEL = "solar-pro4"
RECALL = ROOT / "Tests/Preprocessor/selector/output/2026-10-29_195515/rows.csv"
OUT = Path(__file__).parent / "output" / datetime.now().strftime("%Y-%m-%d_%H%M%S")
WORKERS = 6  # 분당 100요청 한도 안 (A가 호출당 ~40s, B 연속 호출이 몰려도 SDK 재시도로 흡수)
SRC = ["metric", "log", "trace"]
LEVELS = ["L0", "L1a", "N1", "N0", "Nshort"]
FAULT_TYPES = ["code error", "cpu stress", "dns error", "io fault", "jvm cpu", "jvm exception", "jvm gc", "jvm latency",
               "memory stress", "network corrupt", "network delay", "network loss", "node cpu stress", "node disk fill",
               "node memory stress", "pod failure", "pod kill", "target port misconfig"]

SYSTEM = """너는 마이크로서비스 시스템(hipstershop 11개 서비스 + TiDB 계층 tidb/tikv/pd, k8s node aiops-k8s-NN)의 장애 근본 원인 분석가다.
입력 brief는 장애 구간의 metric·log·trace에서 이상 패턴만 골라낸 요약이다 (기준 = 조회 구간 전체, +Nm = 구간 시작 기준 상대 시각).
목표: 장애 위치(instance_type: service | pod | node, instance 이름)와 fault_type을 찾는다.
fault_type은 다음 중 하나: """ + ", ".join(FAULT_TYPES) + """
instance는 엔티티 이름 하나만 쓴다 (예: checkoutservice, checkoutservice-1, aiops-k8s-03, tikv). 설명은 reason에.
규칙: source 행 0개 = 수집 안 됨 또는 해당 데이터 없음. 정상의 근거로 쓰지 말 것."""

TASK_A = """brief의 근거로 원인을 판단할 수 있으면 status=answer로 위치·fault_type·reason을 채운다.
근거가 부족해 판단할 수 없으면 status=insufficient로 두고, 위치·fault_type은 null, missing에 더 필요한 데이터를 적는다."""

TASK_B = """다음 행동을 tool로 고른다.
- 근거가 충분해 최종 답변으로 넘어가도 되면 finish
- 판단에 더 필요한 데이터가 있으면 search (sources, target, window를 지정)"""

NULLABLE = lambda t, enum=None: {"type": [t, "null"], **({"enum": enum + [None]} if enum else {})}  # noqa: E731
# reason(긴 문자열)을 마지막에: 앞에 두면 reason 뒤 공백 반복으로 다음 키를 놓치는 퇴화가 파일럿에서 2/9건 발생
SCHEMA_A = {"type": "object", "additionalProperties": False,
            "required": ["status", "instance_type", "instance", "fault_type", "missing", "reason"],
            "properties": {"status": {"type": "string", "enum": ["answer", "insufficient"]},
                           "instance_type": NULLABLE("string", ["service", "pod", "node"]),
                           "instance": NULLABLE("string"), "fault_type": NULLABLE("string", FAULT_TYPES),
                           "missing": NULLABLE("string"), "reason": {"type": "string"}}}
TOOLS_B = [
    {"type": "function", "name": "search", "strict": True,
     "description": "데이터를 더 수집한다. 결과는 같은 형식의 이상 패턴 요약.",
     "parameters": {"type": "object", "additionalProperties": False, "required": ["sources", "target", "window"], "properties": {
         "sources": {"type": "array", "items": {"type": "string", "enum": SRC}},
         "target": {"type": ["object", "null"], "additionalProperties": False, "required": ["type", "name"],
                    "description": "null이면 전체 엔티티", "properties": {
                        "type": {"type": "string", "enum": ["pod", "service", "node", "tidb", "tikv", "pd"]},
                        "name": {"type": "string"}}},
         "window": {"type": "object", "additionalProperties": False, "required": ["before_min", "after_min"],
                    "description": "원 구간 기준 앞뒤 확장(분), 0/0 = 원 구간", "properties": {
                        "before_min": {"type": "integer"}, "after_min": {"type": "integer"}}}}}},
    {"type": "function", "name": "finish", "strict": True, "description": "근거 수집을 끝내고 최종 답변 단계로 넘어간다.",
     "parameters": {"type": "object", "additionalProperties": False, "properties": {}, "required": []}},
]


# ---------- 이름 일치 (test_selector svc() 규칙과 같음) ----------

def norm(name):
    name = name.strip()
    if re.fullmatch(r"aiops-k8s-\d+", name):  # node 이름의 -NN은 replica 번호가 아님
        return name
    return re.sub(r"^tidb-(?=tidb|tikv|pd)", "", re.sub(r"-\d+$", "", name))  # tidb-tikv-0 → tikv, pod → service


def match(gt, name):
    return bool(name) and norm(name) in {norm(g) for g in gt}


# ---------- brief 조작 ----------

def owner(line):
    m = (re.match(r"- (\S+) \|", line) or re.match(r"- \S+ \([^)]*\) <([^>]+)> \|", line)
         or re.search(r"Callee=([^,]+),", line))
    return m.group(1) if m else None


def blocks(text):
    head, *rest = text.split("\n\n")
    return head, {b[1:b.index("]")]: b for b in rest}


def visible(text, gt):
    """정답 엔티티가 주인인 줄이 있는 source 목록."""
    return [s for s, b in blocks(text)[1].items() if any(match(gt, owner(l) or "") for l in b.split("\n"))]


def strip(text, gt, sources):
    """지정 source에서 정답 엔티티가 주인인 줄 삭제 (+ X 포함 3-hop 경로, Top-5 instances 목록에서 X)."""
    head, sec = blocks(text)
    for s in sources:
        out = []
        for line in sec[s].split("\n"):
            if match(gt, owner(line) or ""):
                continue
            p = re.match(r'- "(.+?) → (.+?) → (.+?)" has occurred', line)
            if p and any(match(gt, x) for x in p.groups()):
                continue
            if line.startswith("Top-5 instances"):
                h, _, ents = line.partition(": ")
                line = f"{h}: {', '.join(e for e in ents.split(', ') if not match(gt, e))}"
            out.append(line)
        sec[s] = "\n".join(out)
    return "\n\n".join([head, *sec.values()])


def n_entities(text):
    """brief에 주인으로 등장한 엔티티 수 (service 단위) — B 표적성의 무작위 기준선용."""
    return len({norm(owner(l)) for l in text.split("\n") if owner(l)})


# ---------- 케이스 ----------

def pick(pool, n, gts, want, rng):
    """pool을 fault_type 라운드로빈으로 돌며 want(vis)를 만족하는 케이스 n건. rows.csv(top5 기준)로 고르고 brief로 재확인."""
    pools = {ft: rng.sample(list(g["uuid"]), len(g)) for ft, g in pool.groupby("fault_type")}
    order = [p[i] for i in range(max(map(len, pools.values()), default=0)) for p in pools.values() if i < len(p)]
    out = []
    for u in order:
        if len(out) == n:
            break
        g = gts[u]
        gt = g["instance"] if isinstance(g["instance"], list) else [g["instance"]]
        text = selector.select(SRC, None, g["start_time"], g["end_time"])
        vis = visible(text, gt)
        if want(vis):
            out.append({"uuid": u, "fault_type": g["fault_type"], "instance_type": g["instance_type"], "gt": gt,
                        "text": text, "vis": vis})
    return out


def build(n, n_short):
    """[(level, case, brief, removed_sources)]"""
    gts = {g["uuid"]: g for g in map(json.loads, open(ROOT / "data/aiopschallenge2025/groundtruth.jsonl", encoding="utf-8"))}
    rows = pd.read_csv(RECALL, encoding="utf-8-sig")
    rows["n_src"] = rows[["metric_top5", "trace_top5", "log_top5"]].sum(axis=1)
    rng = random.Random(0)
    items = []
    for k, c in enumerate(pick(rows[rows.n_src >= 2], n, gts, lambda v: len(v) >= 2, rng)):
        keep = c["vis"][k % len(c["vis"])]  # 남길 source를 돌려 metric/log/trace 고르게
        removed = [s for s in c["vis"] if s != keep]
        items += [("L0", c, c["text"], []), ("L1a", c | {"keep": keep}, strip(c["text"], c["gt"], removed), removed)]
    long_ = rows.minutes > 10
    items += [("N1", c, c["text"], []) for c in pick(rows[(rows.n_src == 1) & long_], n, gts, lambda v: len(v) == 1, rng)]
    items += [("N0", c, c["text"], []) for c in pick(rows[(rows.n_src == 0) & long_], n, gts, lambda v: not v, rng)]
    items += [("Nshort", c, c["text"], []) for c in pick(rows[~long_], n_short, gts, lambda v: True, rng)]
    return items


# ---------- 호출 ----------

def run_a(brief, purpose):
    r, rec = llm.call(purpose, model=MODEL, instructions=SYSTEM + "\n\n" + TASK_A, input=brief,
                      reasoning={"effort": "medium"}, max_output_tokens=32000,
                      text={"format": {"type": "json_schema", "name": "rca_answer", "schema": SCHEMA_A, "strict": True}})
    if r.status != "completed":
        raise ValueError(f"status={r.status}")  # 잘린 출력은 파싱하지 않음
    try:
        return json.loads(r.output_text), rec
    except json.JSONDecodeError as e:
        raise ValueError(f"{e} | tail={r.output_text[-120:]!r}") from None


def run_b(brief, purpose):
    r, rec = llm.call(purpose, model=MODEL, instructions=SYSTEM + "\n\n" + TASK_B, input=brief,
                      tools=TOOLS_B, tool_choice="required", max_output_tokens=4000)
    calls = [{"name": o.name, "arguments": json.loads(o.arguments)} for o in r.output if o.type == "function_call"]
    if not calls:
        raise ValueError("function_call 없음")
    return calls, rec


def job(level, case, brief, removed, track, rep):
    g = case["gt"]
    row = {"uuid": case["uuid"], "fault_type": case["fault_type"], "instance_type": case["instance_type"], "level": level,
           "vis": "|".join(case["vis"]), "keep": case.get("keep", ""), "removed": "|".join(removed),
           "n_entities": n_entities(brief), "track": track, "rep": rep, "error": ""}
    try:
        purpose = f"abstain2:{case['uuid']}:{level}:{track}:r{rep}"
        if track == "A":
            ans, rec = run_a(brief, purpose)
            row.update(response=ans, abstain=ans["status"] == "insufficient",
                       inst_ok=match(g, ans["instance"] or ""), ft_ok=ans["fault_type"] == case["fault_type"])
        else:
            calls, rec = run_b(brief, purpose)
            ss = [c["arguments"] for c in calls if c["name"] == "search"]
            hit = [s for s in ss if match(g, (s.get("target") or {}).get("name", ""))]
            row.update(response=calls, abstain=not any(c["name"] == "finish" for c in calls), n_search=len(ss),
                       target_hit=bool(hit), target_null=any(s.get("target") is None for s in ss),
                       removed_req=any(set(s["sources"]) & set(removed) for s in hit),  # 정답 target으로 지운 source를 요청
                       window_ext=any(s["window"]["before_min"] > 0 or s["window"]["after_min"] > 0 for s in ss))
        row.update({k: rec[k] for k in ["model", "input_tokens", "cached_tokens", "output_tokens", "reasoning_tokens",
                                        "cost_usd", "latency_sec"]})
    except Exception as e:  # 한 건 실패해도 계속 (llm.call이 실패 호출도 usage 로그에 기록)
        row["error"] = repr(e)[:300]
    return row


# ---------- 리포트 ----------

def pct(s):
    s = s.dropna().astype(bool)
    return f"{s.mean():.0%}" if len(s) else "-"


def col(df, c):
    return df[c] if c in df else pd.Series(dtype=bool)


def report(df, items, elapsed):
    ok = df[df["error"] == ""]
    A, B = ok[ok.track == "A"], ok[ok.track == "B"]
    answered = A[~col(A, "abstain").astype(bool)]
    searched = B[col(B, "n_search") > 0]
    levels = pd.Series([lv for lv, *_ in items])
    L = ["# 포기 신호 실험 v2 (system card 없음)", "",
         f"- 모델 {MODEL}, 호출 {len(df)}회 (오류 {len(df) - len(ok)}), 전체 소요 {elapsed / 60:.1f}분",
         "- 케이스 수: " + ", ".join(f"{lv} {(levels == lv).sum()}" for lv in LEVELS), "",
         "## A 답변 호출", "", "| 수준 | 호출 | 포기율 | 답한 호출 | instance 정답 | fault_type 정답 |", "|---|---|---|---|---|---|"]
    for lv in LEVELS:
        a, s = A[A.level == lv], answered[answered.level == lv]
        L.append(f"| {lv} | {len(a)} | {pct(col(a, 'abstain'))} | {len(s)} | {pct(col(s, 'inst_ok'))} | {pct(col(s, 'ft_ok'))} |")
    L += ["", "## B 결정 호출 (target·source·window는 search를 부른 호출 기준)", "",
          "| 수준 | 호출 | 재검색률 | target=정답 | 정답 target+지운 source | window 확장 | target=null | 무작위 기준선 |",
          "|---|---|---|---|---|---|---|---|"]
    for lv in LEVELS:
        b, q = B[B.level == lv], searched[searched.level == lv]
        base = f"{(1 / b.n_entities.clip(lower=1)).mean():.0%}" if len(b) else "-"
        L.append(f"| {lv} | {len(b)} | {pct(col(b, 'abstain'))} | {pct(col(q, 'target_hit'))} | "
                 f"{pct(col(q, 'removed_req')) if lv == 'L1a' else '-'} | {pct(col(q, 'window_ext'))} | {pct(col(q, 'target_null'))} | {base} |")

    def rate(d, lv):
        s = col(d[d.level == lv], "abstain").astype(bool)
        return s.mean() if len(s) else float("nan")
    L += ["", "## 민감도 (같은 케이스: L1a − L0)", "",
          f"- A 포기율 {rate(A, 'L1a') - rate(A, 'L0'):+.0%}p, B 재검색률 {rate(B, 'L1a') - rate(B, 'L0'):+.0%}p"]

    L += ["", "## L1a 남긴 source별", "", "| 남긴 source | A 포기율 | A instance 정답(답한 경우) | B 재검색률 | B target=정답 |", "|---|---|---|---|---|"]
    for k in SRC:
        sel = lambda d: d[(d.level == "L1a") & (d.keep == k)]  # noqa: E731
        if len(sel(A)) or len(sel(B)):
            L.append(f"| {k} | {pct(col(sel(A), 'abstain'))} | {pct(col(sel(answered), 'inst_ok'))} | "
                     f"{pct(col(sel(B), 'abstain'))} | {pct(col(sel(searched), 'target_hit'))} |")

    L += ["", "## instance_type별 포기율 (A / B)", "", "| 수준 | service | pod | node |", "|---|---|---|---|"]
    for lv in LEVELS:
        L.append(f"| {lv} | " + " | ".join(f"{pct(col(A[(A.level == lv) & (A.instance_type == it)], 'abstain'))} / "
                                           f"{pct(col(B[(B.level == lv) & (B.instance_type == it)], 'abstain'))}"
                                           for it in ["service", "pod", "node"]) + " |")

    L += ["", "## 비용·시간 (호출당)", "", "| 트랙 | input | output | reasoning | 평균 latency | 최대 latency | 비용 합 |", "|---|---|---|---|---|---|---|"]
    for t, s in [("A", A), ("B", B)]:
        if len(s):
            L.append(f"| {t} | {s.input_tokens.mean():.0f} | {s.output_tokens.mean():.0f} | {s.reasoning_tokens.mean():.0f} | "
                     f"{s.latency_sec.mean():.1f}s | {s.latency_sec.max():.1f}s | ${s.cost_usd.sum():.4f} |")
    L.append(f"\n총 비용 ${ok.cost_usd.sum():.4f} (usage 기준, 실패 호출 제외)")
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pilot", action="store_true", help="수준별 2건 × 1회")
    ap.add_argument("--n", type=int, default=30)
    ap.add_argument("--n-short", type=int, default=20)
    ap.add_argument("--reps", type=int, default=3)
    args = ap.parse_args()
    n, n_short, reps = (2, 2, 1) if args.pilot else (args.n, args.n_short, args.reps)
    llm.client()  # 키 없으면 selector 돌리기 전에 바로 실패
    (OUT / "briefs").mkdir(parents=True)

    t0 = time.time()
    items = build(n, n_short)
    for lv, c, brief, _ in items:
        (OUT / "briefs" / f"{lv}_{c['uuid']}.txt").write_text(brief, encoding="utf-8")
    print("items:", pd.Series([lv for lv, *_ in items]).value_counts().to_dict(), flush=True)

    jobs = [(*it, t, r) for r in range(reps) for it in items for t in "AB"]
    rows = []
    with ThreadPoolExecutor(WORKERS) as ex, open(OUT / "calls.jsonl", "w", encoding="utf-8") as f:
        for i, row in enumerate(ex.map(lambda j: job(*j), jobs), 1):
            f.write(json.dumps(row, ensure_ascii=False) + "\n")  # 메인 스레드만 씀
            f.flush()
            rows.append(row)
            print(f"{i}/{len(jobs)} {row['uuid']} {row['level']} {row['track']} abstain={row.get('abstain')} {row['error']}", flush=True)

    text = report(pd.DataFrame(rows), items, time.time() - t0)
    (OUT / "report.md").write_text(text, encoding="utf-8")
    print(text, f"\n→ {OUT}")


if __name__ == "__main__":
    main()
