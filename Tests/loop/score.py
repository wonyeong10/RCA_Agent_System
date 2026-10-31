"""Loop 출력 엄격 채점 (생각.txt 과제3 최종 지표, Time 제외).

- Component = instance_type 일치 AND instance 리스트 정확 일치 (순서 포함, 표기 매핑 tidb-X-N → X만)
- Fault Type = fault_type 일치. Correct = 둘 다, Partial = 하나만.
- 분모 = groundtruth 전체. 출력 없음(오류)은 오답.
- 보조 열 "TiDB 제외" = groundtruth instance에 tidb-가 있는 케이스를 뺀 집합 (정답 형식 [pod, service]가 데이터로 도출 불가).

레포 루트에서 `.venv/Scripts/python.exe Tests/loop/score.py Agent/output/<run>` → 같은 폴더에 score.md, score_rows.csv
"""
import json
import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]


def canon(name):
    # 표기 매핑만: groundtruth TiDB 계층 tidb-tikv-0 → 에이전트 컴포넌트명 tikv
    return re.sub(r"^tidb-(tidb|tikv|pd)-\d+$", r"\1", name.strip())


def as_list(x):
    return x if isinstance(x, list) else [x]


def judge(gt, ans):
    if ans is None:
        return False, False
    comp = ans["instance_type"] == gt["instance_type"] and \
        [canon(n) for n in ans["instance"]] == [canon(n) for n in as_list(gt["instance"])]
    return comp, ans["fault_type"] == gt["fault_type"]


def score(run):
    gts = [json.loads(l) for l in open(ROOT / "data/aiopschallenge2025/groundtruth.jsonl", encoding="utf-8")]
    answers = {a["uuid"]: a for a in map(json.loads, open(run / "output.jsonl", encoding="utf-8"))}
    traces = {t["uuid"]: t for t in map(json.loads, open(run / "traces.jsonl", encoding="utf-8"))}
    rows = []
    for g in gts:
        a, t = answers.get(g["uuid"]), traces.get(g["uuid"], {})
        comp, ft = judge(g, a)
        rows.append({"uuid": g["uuid"], "fault_type": g["fault_type"], "instance_type": g["instance_type"],
                     "gt": "|".join(as_list(g["instance"])), "tidb": any(n.startswith("tidb-") for n in as_list(g["instance"])),
                     "ans_type": a and a["instance_type"], "ans": a and "|".join(a["instance"]), "ans_fault": a and a["fault_type"],
                     "component": comp, "fault": ft, "correct": comp and ft, "partial": comp != ft,
                     "error": t.get("error", "" if a else "출력 없음"), "stop": t.get("stop"),
                     "n_search": t.get("n_search"), "cost_usd": t.get("cost_usd", 0), "sec": t.get("total_sec")})
    df = pd.DataFrame(rows)
    df.to_csv(run / "score_rows.csv", index=False, encoding="utf-8-sig")

    cols = ["correct", "partial", "component", "fault"]
    def line(label, d):
        return f"| {label} | {len(d)} | " + " | ".join(f"{d[c].mean():.1%}" for c in cols) + " |"
    head = ["| 범위 | n | Correct | Partial | Component | Fault Type |", "|---|---|---|---|---|---|"]
    out = [f"# Loop 엄격 채점 ({run.name})", "", "Component = instance_type + instance 리스트 정확 일치 (매핑 tidb-X-N→X만). 분모 = 전체, 오류 = 오답.", "",
           *head, line("전체", df), line("TiDB 제외", df[~df.tidb]), line("TiDB만", df[df.tidb]), "",
           "## instance_type별", "", *head, *(line(k, d) for k, d in df.groupby("instance_type")), "",
           "## fault_type별", "", *head, *(line(k, d) for k, d in df.groupby("fault_type")), "",
           f"- 오류/출력 없음: {(df.error != '').sum()}건",
           f"- 종료 사유: {df.stop.value_counts().to_dict()}",
           f"- search 횟수 평균: {df.n_search.mean():.2f}",
           f"- 비용 합계: ${df.cost_usd.sum():.2f}, 건당 평균 ${df.cost_usd.mean():.4f}",
           f"- 소요 평균: {df.sec.mean():.0f}s"]
    (run / "score.md").write_text("\n".join(out), encoding="utf-8")
    print("\n".join(out))


def check():
    g = {"instance_type": "service", "instance": ["a", "b"], "fault_type": "network loss"}
    assert judge(g, {"instance_type": "service", "instance": ["a", "b"], "fault_type": "network loss"}) == (True, True)
    assert judge(g, {"instance_type": "service", "instance": ["b", "a"], "fault_type": "network loss"}) == (False, True)
    assert judge(g, {"instance_type": "service", "instance": ["a"], "fault_type": "network delay"}) == (False, False)
    assert judge(g, None) == (False, False)
    assert judge({"instance_type": "pod", "instance": "x-1", "fault_type": "pod kill"},
                 {"instance_type": "service", "instance": ["x-1"], "fault_type": "pod kill"}) == (False, True)
    assert canon("tidb-tikv-0") == "tikv" and canon("tidb-tikv") == "tidb-tikv"
    print("ok")


if __name__ == "__main__":
    check() if len(sys.argv) < 2 else score(Path(sys.argv[1]).resolve())
