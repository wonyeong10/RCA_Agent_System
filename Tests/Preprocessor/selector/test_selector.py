"""selector recall@K: initial 조건(target=None, input 구간 그대로)에서 정답 엔티티가 출력에 들어가는 비율.

LLM 없음. groundtruth는 채점에만 쓴다.
판정 (정답 이름 하나라도 걸리면 hit, service 단위 느슨한 일치: pod 정답은 그 service, service 정답은 소속 pod도 인정)
- metric_top5 : "Top-5 instances" 줄
- metric_any  : metric 설명 줄의 엔티티
- trace_top5  : 순위순 Callee= 중 앞쪽 고유 5개 (20줄 전체로 세면 거의 모든 서비스가 걸려 의미 없음)
- log_top5    : 출력된 log의 <pod> 중 등장 횟수 상위 5개
- any_top5    : metric_top5 / trace_top5 / log_top5 중 하나

레포 루트에서 `.venv/Scripts/python.exe Tests/Preprocessor/selector/test_selector.py [--limit N]`
"""
import argparse
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "Agent" / "Preprocessor"))
import selector  # noqa: E402

OUT = Path(__file__).parent / "output" / datetime.now().strftime("%Y-%m-%d_%H%M%S")


def svc(name):
    # groundtruth TiDB 계층은 tidb-tikv-0 형식, selector는 컴포넌트명(tidb/tikv/pd)
    return re.sub(r"^tidb-(?=tidb|tikv|pd)", "", re.sub(r"-\d+$", "", name))


def hit(gt_names, found):
    gs = {svc(g) for g in gt_names}
    return any(svc(f) in gs for f in found)


def sections(text):
    parts = {}
    for block in text.split("\n\n")[1:]:
        parts[block[1:block.index("]")]] = block
    return parts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int)
    args = ap.parse_args()
    gts = [json.loads(l) for l in open(ROOT / "data/aiopschallenge2025/groundtruth.jsonl", encoding="utf-8")]
    gts = gts[:args.limit] if args.limit else gts
    (OUT / "cases").mkdir(parents=True)

    rows = []
    for n, g in enumerate(gts):
        names = g["instance"] if isinstance(g["instance"], list) else [g["instance"]]
        t = time.time()
        try:
            text = selector.select(["metric", "log", "trace"], None, g["start_time"], g["end_time"])
        except Exception as e:  # 한 건 실패해도 전수 계속
            rows.append({"uuid": g["uuid"], "fault_type": g["fault_type"], "error": repr(e)})
            continue
        s = sections(text)
        m = s.get("metric", "")
        top = re.search(r"Top-5 instances with largest deviations: (.*)", m)
        top = top.group(1).split(", ") if top else []
        m_ents = re.findall(r"^- (\S+) \|", m, re.M)
        callees = re.findall(r"Callee=([^,]+),", s.get("trace", ""))
        pods = re.findall(r"<([^>]+)> \|", s.get("log", ""))
        r = {"uuid": g["uuid"], "fault_type": g["fault_type"], "instance_type": g["instance_type"], "gt": "|".join(names),
             "minutes": (pd.Timestamp(g["end_time"]) - pd.Timestamp(g["start_time"])).total_seconds() / 60,
             "metric_top5": hit(names, top), "metric_any": hit(names, m_ents),
             "trace_top5": hit(names, list(dict.fromkeys(callees))[:5]),
             "log_top5": hit(names, pd.Series(pods, dtype=str).value_counts().index[:5]), "chars": len(text), "sec": round(time.time() - t, 1),
             "metric_no_judge": "판정 불가" in m.split("\n")[0], "error": ""}
        r["any_top5"] = r["metric_top5"] or r["trace_top5"] or r["log_top5"]
        rows.append(r)
        if n < 5 or n % 50 == 0:
            (OUT / "cases" / f"{g['uuid']}.txt").write_text(text, encoding="utf-8")
        print(f"{n + 1}/{len(gts)} {g['uuid']} any={r['any_top5']} {r['sec']}s", flush=True)

    df = pd.DataFrame(rows)
    df.to_csv(OUT / "rows.csv", index=False, encoding="utf-8-sig")
    ok = df[df["error"] == ""]
    cols = ["metric_top5", "metric_any", "trace_top5", "log_top5", "any_top5"]
    lines = [f"# selector recall (initial, {len(ok)}건, 오류 {len(df) - len(ok)}건)", "",
             "| 범위 | n | " + " | ".join(cols) + " |", "|---|---|" + "---|" * len(cols)]
    def row(label, d):
        return f"| {label} | {len(d)} | " + " | ".join(f"{d[c].mean():.0%}" for c in cols) + " |"
    lines.append(row("전체", ok))
    for k, d in ok.groupby("instance_type"):
        lines.append(row(k, d))
    for k, d in ok.groupby("fault_type"):
        lines.append(row(k, d))
    lines += ["", f"- metric 포인트 부족(≤10분)으로 3σ 판정 불가: {ok['metric_no_judge'].sum()}건",
              f"- 출력 길이: 평균 {ok['chars'].mean():.0f}자, 최대 {ok['chars'].max()}자",
              f"- 소요: 평균 {ok['sec'].mean():.1f}s, 최대 {ok['sec'].max()}s"]
    (OUT / "report.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    sys.exit(1 if len(df) != len(ok) else 0)


if __name__ == "__main__":
    main()
