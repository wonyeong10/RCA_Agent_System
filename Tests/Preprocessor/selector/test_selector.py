"""selector recall@K: initial 조건(target=None, input 구간 그대로)에서 정답 엔티티가 출력에 들어가는 비율.

LLM 없음. groundtruth는 채점에만 쓴다.
판정 = 엄격: 정답 이름(리스트면 전부)이 정확히 있어야 hit. 허용은 표기 매핑(tidb-tikv-0 → tikv)뿐.
열 이름 끝 _b = service 정답에 한해 소속 pod(<service>-N)도 인정하는 변형.
- metric_top5 : "Top-5 instances" 줄
- trace_top5  : 순위순 Callee= 중 앞쪽 고유 5개 (20줄 전체로 세면 거의 모든 서비스가 걸려 의미 없음)
- log_top5    : 출력된 log의 <pod> 중 등장 횟수 상위 5개
- any_top5    : metric_top5 / trace_top5 / log_top5 중 하나
- *_any       : Top-5 제한 없이 출력에 주인 줄이 있는지 (포기 신호 실험 근거 수준 분류용)

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


def canon(name):
    # 표기 매핑만: groundtruth TiDB 계층 tidb-tikv-0 → selector 컴포넌트명 tikv
    return re.sub(r"^tidb-(tidb|tikv|pd)-\d+$", r"\1", name.strip())


def hit(gt_names, found, itype, own_pods=False):
    """엄격: 정답 이름이 전부 found에 정확히 있어야 hit. own_pods = service 정답에 한해 소속 pod(<service>-N)도 인정 (b 기준)."""
    fs = {canon(f) for f in found}
    def ok(g):
        g = canon(g)
        return g in fs or (own_pods and itype == "service" and any(re.fullmatch(re.escape(g) + r"-\d+", f) for f in fs))
    return all(ok(g) for g in gt_names)


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
             "chars": len(text), "sec": round(time.time() - t, 1), "metric_no_judge": "3σ를 넘을 수 없음" in m.split("\n")[0], "error": ""}
        found = {"metric_top5": top, "trace_top5": list(dict.fromkeys(callees))[:5],
                 "log_top5": list(pd.Series(pods, dtype=str).value_counts().index[:5]),
                 # 근거 수준 분류용: Top-5 제한 없이 출력에 주인 줄이 있는지
                 "metric_any": m_ents, "trace_any": callees, "log_any": pods}
        for sfx, own in (("", False), ("_b", True)):
            for k, f in found.items():
                r[k + sfx] = hit(names, f, g["instance_type"], own)
            r["any_top5" + sfx] = r["metric_top5" + sfx] or r["trace_top5" + sfx] or r["log_top5" + sfx]
        rows.append(r)
        if n < 5 or n % 50 == 0:
            (OUT / "cases" / f"{g['uuid']}.txt").write_text(text, encoding="utf-8")
        print(f"{n + 1}/{len(gts)} {g['uuid']} any={r['any_top5']} {r['sec']}s", flush=True)

    df = pd.DataFrame(rows)
    df.to_csv(OUT / "rows.csv", index=False, encoding="utf-8-sig")
    ok = df[df["error"] == ""]
    lines = [f"# selector recall (initial, {len(ok)}건, 오류 {len(df) - len(ok)}건)", "",
             "엄격 = 정답 이름 전부 정확 일치 (표기 매핑 tidb-tikv-0→tikv만). _b = service 정답에 한해 소속 pod도 인정.", ""]
    for sfx, title in (("", "엄격"), ("_b", "b 기준 (service 정답 = 소속 pod 인정)")):
        cols = [c + sfx for c in ["metric_top5", "trace_top5", "log_top5", "any_top5"]]
        lines += [f"## {title}", "", "| 범위 | n | " + " | ".join(cols) + " |", "|---|---|" + "---|" * len(cols)]
        def row(label, d):
            return f"| {label} | {len(d)} | " + " | ".join(f"{d[c].mean():.0%}" for c in cols) + " |"
        lines.append(row("전체", ok))
        for k, d in ok.groupby("instance_type"):
            lines.append(row(k, d))
        for k, d in ok.groupby("fault_type"):
            lines.append(row(k, d))
        n_src = ok[[c + sfx for c in ["metric_any", "trace_any", "log_any"]]].sum(axis=1)
        lines += ["", "근거 수준 후보 (Top-5 제한 없이 주인 줄이 보이는 source 수, 10분 초과 / 이하): "
                  + ", ".join(f"{k}개 {((n_src == k) & (ok.minutes > 10)).sum()}/{((n_src == k) & (ok.minutes <= 10)).sum()}건"
                              for k in range(4)), ""]
    lines += ["", f"- metric 포인트 부족(≤10분)으로 3σ 판정 불가: {ok['metric_no_judge'].sum()}건",
              f"- 출력 길이: 평균 {ok['chars'].mean():.0f}자, 최대 {ok['chars'].max()}자",
              f"- 소요: 평균 {ok['sec'].mean():.1f}s, 최대 {ok['sec'].max()}s"]
    (OUT / "report.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    sys.exit(1 if len(df) != len(ok) else 0)


if __name__ == "__main__":
    main()
