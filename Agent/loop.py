"""메인 Loop (생각.txt 아이디어 4 "루프 (확정)"): 케이스 1건 → Tool 모델 결정 반복 → Answer 모델 json 답변.

- run_case(uuid, start, end): 입력 형식과 무관. input.json 파싱·병렬 실행·출력 쓰기는 __main__ 쪽.
- Tool 모델: reasoning 끔, tool_choice=required, search | finish. MAX_LOOPS 소진 시 강제 답변.
- history: API가 stateless라 케이스마다 지역 리스트를 append-only로 쌓아 매 호출 통째로 전달.
  모든 function_call에 function_call_output을 붙인다 (검증 오류·중복 조회도 문자열로, 회차 소모).
- Answer 모델: history를 텍스트 transcript로 렌더링해 1회 호출 (tool item 안 넘김), json_schema strict, 실패 시 1회 재시도.
- 모델은 시각을 쓰지 않는다. window{before_min, after_min}만 받고 시각은 코드가 계산 (아이디어 6 입력 검사).
- 모든 LLM 호출은 util.llm.call (purpose = loop:{uuid}:tool{n} | answer{k}) → 회차별 input 토큰이 logs/llm_usage.jsonl에.

레포 루트에서 `.venv/Scripts/python.exe Agent/loop.py [--uuid U ...] [--limit N] [--workers 4]`, API 없는 점검은 `--check`.
"""
import argparse
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "Agent" / "Preprocessor"), str(ROOT / "Agent")]
import selector  # noqa: E402
from util import llm  # noqa: E402

TOOL_MODEL = "solar-pro4"
ANSWER_MODEL = "solar-pro4"
MAX_LOOPS = 5      # Tool 결정 호출 상한 (abstain 실험 B: 근거와 무관하게 첫 호출 82%가 search)
MAX_WINDOW = 60    # window 확장 상한(분)
INPUT = ROOT / "data" / "aiopschallenge2025" / "input.json"
TIME_RE = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ")
SOURCES = ["metric", "log", "trace"]
TARGET_TYPES = ["pod", "service", "node", "tidb", "tikv", "pd"]
FAULT_TYPES = ["code error", "cpu stress", "dns error", "io fault", "jvm cpu", "jvm exception", "jvm gc", "jvm latency",
               "memory stress", "network corrupt", "network delay", "network loss", "node cpu stress", "node disk fill",
               "node memory stress", "pod failure", "pod kill", "target port misconfig"]
# 답변 instance 선택지 = 전체 날짜(06-04~06-29) 원본 metric 행 주인 합집합 (selector.entities를 날짜별 하루 구간으로, groundtruth 미사용).
# 제외: "(deleted)" 접미사 파일(같은 pod의 재생성 흔적), example-ant-* (hipstershop 아닌 cronjob pod). 케이스별 search 선택지는 따로(names).
ANSWER_SERVICES = ['adservice', 'cartservice', 'checkoutservice', 'currencyservice', 'emailservice', 'frontend', 'paymentservice', 'productcatalogservice', 'recommendationservice', 'redis-cart', 'shippingservice']
ANSWER_NAMES = {"service": ANSWER_SERVICES,
                "pod": [f"{s}-{i}" for s in ANSWER_SERVICES if s != "redis-cart" for i in range(3)] + ["redis-cart-0"],
                "node": [f"aiops-k8s-0{i}" for i in range(1, 9)] + ["k8s-master1", "k8s-master2", "k8s-master3"],
                "tidb": ["tidb"], "tikv": ["tikv"], "pd": ["pd"]}

SYSTEM = """너는 마이크로서비스 시스템(hipstershop 11개 서비스 + TiDB 계층 tidb/tikv/pd, k8s node aiops-k8s-NN)의 장애 근본 원인 분석가다.
입력 brief는 장애 구간의 metric·log·trace에서 이상 패턴만 골라낸 요약이다 (기준 = 조회 구간 전체, +Nm = 구간 시작 기준 상대 시각).
목표: 장애 위치(instance_type: service | pod | node, instance 이름)와 fault_type을 찾는다.
fault_type은 다음 중 하나: """ + ", ".join(FAULT_TYPES) + """
규칙: source 행 0개 = 수집 안 됨 또는 해당 데이터 없음. 정상의 근거로 쓰지 말 것."""

TOOL_TASK = """다음 행동을 tool로 고른다.
- 근거가 충분해 최종 답변으로 넘어가도 되면 finish (단독 호출)
- 판단에 더 필요한 데이터가 있으면 search (sources, target, window를 지정). 여러 개를 한 번에 병렬로 불러도 된다.
- window는 입력 구간을 앞(before_min)·뒤(after_min)로 넓히기만 한다 (0~""" + str(MAX_WINDOW) + """분, 음수 불가, 구간 축소 불가). 0/0 = 입력 구간 그대로.
- target.name은 아래 "조회 가능한 target" 목록의 이름만 쓴다 (IP·포트·주소 불가). 전체 엔티티는 target=null.
- search 결과는 그 조회 구간 전체를 기준으로 다시 계산한 이상 패턴이다. 같은 인자로 다시 부르면 이전 결과를 참고하라는 답만 온다.
- 결정 호출은 최대 """ + str(MAX_LOOPS) + "회, 소진되면 지금까지의 근거로 바로 최종 답변한다."

ANSWER_TASK = """지금까지 수집한 근거(initial brief와 search 결과)로 최종 답변을 낸다. 반드시 답한다.
instance는 아래 "답변 선택지" 목록의 이름만 리스트로 쓴다 (예: ["checkoutservice"], ["checkoutservice-1"], ["aiops-k8s-03"], ["tikv"]). IP·주소 불가.
네트워크 장애는 [source, destination], 여러 pod가 대상이면 모두. 설명은 reason에.
reason에는 근거가 된 지표 이름(kpi_key 등)을 그대로 쓴다.
## 답변 선택지 (type: 이름)
""" + "\n".join(f"- {t}: {', '.join(v)}" for t, v in ANSWER_NAMES.items())

def tools(names):
    """케이스별 tool 스키마. name enum = 전체 이름 합집합 (type별 짝은 validate가 검사, 중첩 anyOf 회피)."""
    return [
        {"type": "function", "name": "search", "strict": True,
         "description": "데이터를 더 수집한다. 결과는 같은 형식의 이상 패턴 요약.",
         "parameters": {"type": "object", "additionalProperties": False, "required": ["sources", "target", "window"], "properties": {
             "sources": {"type": "array", "items": {"type": "string", "enum": SOURCES}},
             "target": {"type": ["object", "null"], "additionalProperties": False, "required": ["type", "name"],
                        "description": "null이면 전체 엔티티", "properties": {
                            "type": {"type": "string", "enum": TARGET_TYPES},
                            "name": {"type": "string", "enum": sorted({n for v in names.values() for n in v})}}},
             "window": {"type": "object", "additionalProperties": False, "required": ["before_min", "after_min"],
                        "description": f"입력 구간 앞뒤 확장(분, 0~{MAX_WINDOW}, 음수 불가), 0/0 = 입력 구간", "properties": {
                            "before_min": {"type": "integer"}, "after_min": {"type": "integer"}}}}}},
        {"type": "function", "name": "finish", "strict": True, "description": "근거 수집을 끝내고 최종 답변 단계로 넘어간다.",
         "parameters": {"type": "object", "additionalProperties": False, "properties": {}, "required": []}},
    ]


def answer_schema():
    # reason(긴 문자열)은 마지막: 앞에 두면 공백 반복 퇴화로 다음 키 누락 (abstain 파일럿)
    return {"type": "object", "additionalProperties": False,
            "required": ["instance_type", "instance", "fault_type", "reason"],
            "properties": {"instance_type": {"type": "string", "enum": ["service", "pod", "node"]},
                           "instance": {"type": "array", "items": {"type": "string",
                                                                   "enum": sorted({n for v in ANSWER_NAMES.values() for n in v})}},
                           "fault_type": {"type": "string", "enum": FAULT_TYPES},
                           "reason": {"type": "string"}}}


def names_text(names):
    return "## 조회 가능한 target (type: 이름)\n" + "\n".join(f"- {t}: {', '.join(v)}" for t, v in names.items())
USAGE_KEYS = ["model", "input_tokens", "cached_tokens", "output_tokens", "reasoning_tokens", "cost_usd", "latency_sec"]


# ---------- 입력 ----------

def parse_input(item):
    """input.json 항목 → (uuid, start, end). 문장 속 ISO UTC 시각이 정확히 2개여야 함."""
    times = TIME_RE.findall(item["Anomaly Description"])
    if len(times) != 2:
        raise ValueError(f"{item['uuid']}: 시각 {len(times)}개")
    return item["uuid"], *sorted(times)


# ---------- tool 인자 검사 (reader 앞단, 아이디어 6) ----------

def validate(name, raw, names):
    """search 인자 → 정규화 dict. names = 조회 가능한 target {type: [name]}. 잘못되면 ValueError (메시지가 그대로 tool 결과가 됨)."""
    if name != "search":
        raise ValueError(f"알 수 없는 tool: {name}")
    try:
        a = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"arguments JSON 파싱 실패 ({e})") from None
    if not isinstance(a, dict):
        raise ValueError("arguments는 object여야 함")
    src = a.get("sources")
    if not isinstance(src, list) or not src or any(s not in SOURCES for s in src):
        raise ValueError(f"sources는 {SOURCES} 중 1개 이상")
    t = a.get("target")
    if t is not None and not (isinstance(t, dict) and t.get("type") in TARGET_TYPES
                              and isinstance(t.get("name"), str) and t["name"].strip()):
        raise ValueError(f"target은 null 또는 {{type: {TARGET_TYPES} 중 하나, name: 비어 있지 않은 문자열}}")
    if t is not None and t["name"].strip() not in names.get(t["type"], []):
        raise ValueError(f"{t['type']} '{t['name']}'은 조회 가능한 target 목록에 없음: {names.get(t['type'], [])}")
    w = a.get("window")
    if not (isinstance(w, dict) and all(type(w.get(k)) is int and 0 <= w[k] <= MAX_WINDOW for k in ("before_min", "after_min"))):
        raise ValueError(f"window는 {{before_min, after_min}} 정수 0~{MAX_WINDOW}")
    return {"sources": sorted(set(src), key=SOURCES.index),
            "target": t and {"type": t["type"], "name": t["name"].strip()},
            "window": {"before_min": w["before_min"], "after_min": w["after_min"]}}


def window(start, end, w):
    """input 구간 + 앞뒤 확장 → ISO UTC (Z). 모델은 시각을 쓰지 않는다."""
    fmt = "%Y-%m-%dT%H:%M:%SZ"
    return ((pd.Timestamp(start) - pd.Timedelta(minutes=w["before_min"])).strftime(fmt),
            (pd.Timestamp(end) + pd.Timedelta(minutes=w["after_min"])).strftime(fmt))


def search(a, start, end):
    try:
        return selector.select(a["sources"], a["target"], *window(start, end, a["window"]))
    except Exception as e:  # 조회 실패도 tool 결과로 돌려줌 (루프는 계속)
        return f"오류: 조회 실패 ({e!r:.300})"


# ---------- Loop ----------

def run_case(uuid, start, end):
    """반환 (answer dict, trace dict). trace = 회차별 tool 호출·토큰·비용, history·transcript 원본."""
    t0 = time.perf_counter()
    brief = selector.select(SOURCES, None, start, end)
    # 선택지는 넓은 구간에서 (pod failure면 입력 구간 안에서 pod가 사라짐, 아이디어 6)
    names = selector.entities(*window(start, end, {"before_min": MAX_WINDOW, "after_min": MAX_WINDOW}))
    tool_specs = tools(names)
    history = [{"role": "user", "content": names_text(names) + "\n\n" + brief}]   # append-only, 앞 항목 수정 금지 (프리픽스 캐시)
    blocks = [names_text(names), f"## initial (조회 구간 = 입력 구간, target 없음)\n{brief}"]
    seen, rounds, stop = {}, [], "max_loops"

    for n in range(1, MAX_LOOPS + 1):
        r, rec = llm.call(f"loop:{uuid}:tool{n}", model=TOOL_MODEL, instructions=SYSTEM + "\n\n" + TOOL_TASK,
                          input=history, tools=tool_specs, tool_choice="required", max_output_tokens=4000)
        calls = [o for o in r.output if o.type == "function_call"]
        rnd = {"round": n, **{k: rec[k] for k in USAGE_KEYS},
               "calls": [{"name": c.name, "arguments": c.arguments} for c in calls]}
        rounds.append(rnd)
        if any(c.name == "finish" for c in calls):   # search와 섞여도 finish 우선, search는 실행 안 함
            stop = "finish"
            break
        if not calls:   # tool_choice=required인데 호출 없음: 응답을 기록하고 다시 요구 (회차 소모)
            rnd["no_call_output"] = json.dumps([o.model_dump(exclude_none=True) for o in r.output], ensure_ascii=False)[:2000]
            history.append({"role": "user", "content": "응답에 tool 호출이 없었다. search 또는 finish를 호출할 것."})
            continue

        plans = []   # (call, 정규화 인자, 미리 정해진 결과) — 중복 판정은 병렬 실행 전에 순서대로
        for c in calls:
            try:
                a = validate(c.name, c.arguments, names)
            except ValueError as e:
                plans.append((c, None, f"오류: {e}"))
                continue
            key = json.dumps(a, sort_keys=True, ensure_ascii=False)
            if key in seen:
                plans.append((c, a, f"이미 조회함: {seen[key]}회차 결과 참고"))
                continue
            seen[key] = n
            plans.append((c, a, None))
        with ThreadPoolExecutor(max(len(plans), 1)) as ex:
            outs = list(ex.map(lambda p: p[2] or search(p[1], start, end), plans))

        history += [{"type": "function_call", "call_id": c.call_id, "name": c.name, "arguments": c.arguments} for c, _, _ in plans]
        history += [{"type": "function_call_output", "call_id": c.call_id, "output": out} for (c, _, _), out in zip(plans, outs)]
        blocks += [f"## {n}회차 search {c.arguments}\n{out}" for (c, _, _), out in zip(plans, outs)]
        rnd["output_chars"] = [len(o) for o in outs]

    transcript = "\n\n".join(blocks)
    answer, answer_recs = None, []
    for k in (1, 2):   # 잘림·파싱 실패 1회 재시도 (history엔 안 넣음)
        r, rec = llm.call(f"loop:{uuid}:answer{k}", model=ANSWER_MODEL, instructions=SYSTEM + "\n\n" + ANSWER_TASK,
                          input=transcript, reasoning={"effort": "medium"}, max_output_tokens=32000,
                          text={"format": {"type": "json_schema", "name": "rca_answer", "schema": answer_schema(), "strict": True}})
        answer_recs.append({k2: rec[k2] for k2 in USAGE_KEYS})
        try:
            if r.status != "completed":
                raise ValueError(f"status={r.status}")
            answer = json.loads(r.output_text)
            if not answer["instance"]:
                raise ValueError("instance 비어 있음")
            break
        except (ValueError, KeyError) as e:
            answer_recs[-1]["error"] = repr(e)[:300]
            answer = None
    if answer is None:
        raise RuntimeError(f"답변 실패: {answer_recs[-1]['error']}")

    recs = rounds + answer_recs
    trace = {"uuid": uuid, "start": start, "end": end, "stop": stop, "n_rounds": len(rounds),
             "n_search": sum(c["name"] == "search" for r_ in rounds for c in r_["calls"]),
             "cost_usd": sum(x["cost_usd"] or 0 for x in recs), "llm_sec": sum(x["latency_sec"] for x in recs),
             "total_sec": round(time.perf_counter() - t0, 3), "rounds": rounds, "answer_calls": answer_recs,
             "history": history, "transcript": transcript}
    return {"uuid": uuid, **answer}, trace


# ---------- 실행 ----------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--uuid", nargs="*", help="이 uuid만")
    ap.add_argument("--limit", type=int, help="앞에서 N건")
    ap.add_argument("--workers", type=int, default=4)  # 분당 100요청 한도 안
    ap.add_argument("--check", action="store_true", help="API 없는 자체 점검")
    ap.add_argument("--system-card", action="store_true", help="SYSTEM에 루트 system_card.py 주입 (ablation, 생각.txt 아이디어 1)")
    args = ap.parse_args()
    if args.system_card:
        global SYSTEM
        sys.path.insert(0, str(ROOT))
        from system_card import SYSTEM_CARD
        SYSTEM += "\n\n## 시스템 구조 (system card)\n" + json.dumps(SYSTEM_CARD, ensure_ascii=False)
    if args.check:
        return check()

    items = [parse_input(x) for x in json.loads(INPUT.read_text(encoding="utf-8"))]
    if args.uuid:
        items = [x for x in items if x[0] in set(args.uuid)]
    items = items[:args.limit] if args.limit else items
    llm.client()  # 키 없으면 selector 돌리기 전에 바로 실패
    out = ROOT / "Agent" / "output" / (datetime.now().strftime("%Y-%m-%d_%H%M%S") + ("_card" if args.system_card else ""))
    (out / "histories").mkdir(parents=True)

    def job(item):
        try:
            return run_case(*item)
        except Exception as e:  # 한 건 실패해도 계속 (llm.call이 실패 호출도 usage 로그에 기록)
            return None, {"uuid": item[0], "error": repr(e)[:500]}

    t0, n_err, cost = time.time(), 0, 0.0
    with ThreadPoolExecutor(args.workers) as ex, open(out / "output.jsonl", "w", encoding="utf-8") as fo, \
            open(out / "traces.jsonl", "w", encoding="utf-8") as ft:
        for i, (ans, tr) in enumerate(ex.map(job, items), 1):   # 파일은 메인 스레드만 씀
            if ans:
                fo.write(json.dumps(ans, ensure_ascii=False) + "\n")
                (out / "histories" / f"{tr['uuid']}.json").write_text(
                    json.dumps({"history": tr.pop("history"), "transcript": tr.pop("transcript")}, ensure_ascii=False, indent=1),
                    encoding="utf-8")
                cost += tr["cost_usd"]
            else:
                n_err += 1
            ft.write(json.dumps(tr, ensure_ascii=False) + "\n")
            fo.flush(), ft.flush()
            print(f"{i}/{len(items)} {tr['uuid']} " + (f"{tr['stop']} rounds={tr['n_rounds']} search={tr['n_search']} "
                  f"${tr['cost_usd']:.4f} {tr['total_sec']:.0f}s → {ans['instance_type']} {ans['instance']} {ans['fault_type']}"
                  if ans else f"ERROR {tr['error']}"), flush=True)
    print(f"\n{len(items)}건, 오류 {n_err}, 비용 ${cost:.4f}, {(time.time() - t0) / 60:.1f}분 → {out}")


def check():
    assert parse_input({"uuid": "u", "Anomaly Description": "from 2025-06-05T16:10:02Z to 2025-06-05T16:31:02Z."}) \
        == ("u", "2025-06-05T16:10:02Z", "2025-06-05T16:31:02Z")
    names = {"pod": ["a-1"], "service": ["a"], "node": ["aiops-k8s-01"]}
    ok = validate("search", '{"sources":["trace","metric","trace"],"target":{"type":"pod","name":" a-1 "},'
                            '"window":{"before_min":10,"after_min":0}}', names)
    assert ok == {"sources": ["metric", "trace"], "target": {"type": "pod", "name": "a-1"},
                  "window": {"before_min": 10, "after_min": 0}}
    assert validate("search", '{"sources":["log"],"target":null,"window":{"before_min":0,"after_min":0}}', names)["target"] is None
    for name, raw in [("search", "{bad"), ("search", "[]"), ("foo", "{}"),
                      ("search", '{"sources":[],"target":null,"window":{"before_min":0,"after_min":0}}'),
                      ("search", '{"sources":["x"],"target":null,"window":{"before_min":0,"after_min":0}}'),
                      ("search", '{"sources":["log"],"target":{"type":"pod","name":""},"window":{"before_min":0,"after_min":0}}'),
                      ("search", '{"sources":["log"],"target":{"type":"db","name":"a"},"window":{"before_min":0,"after_min":0}}'),
                      ("search", '{"sources":["log"],"target":{"type":"pod","name":"a"},"window":{"before_min":0,"after_min":0}}'),
                      ("search", '{"sources":["log"],"target":{"type":"node","name":"10.233.27.213"},"window":{"before_min":0,"after_min":0}}'),
                      ("search", '{"sources":["log"],"target":"a","window":{"before_min":0,"after_min":0}}'),
                      ("search", '{"sources":["log"],"target":null,"window":{"before_min":-1,"after_min":0}}'),
                      ("search", '{"sources":["log"],"target":null,"window":{"before_min":61,"after_min":0}}'),
                      ("search", '{"sources":["log"],"target":null,"window":{"before_min":true,"after_min":0}}'),
                      ("search", '{"sources":["log"],"target":null,"window":{"before_min":1.5,"after_min":0}}')]:
        try:
            validate(name, raw, names)
            raise AssertionError(f"통과하면 안 됨: {name} {raw}")
        except ValueError:
            pass
    assert window("2025-06-05T16:10:02Z", "2025-06-05T16:31:02Z", {"before_min": 15, "after_min": 30}) \
        == ("2025-06-05T15:55:02Z", "2025-06-05T17:01:02Z")
    assert window("2025-06-05T23:50:00Z", "2025-06-05T23:55:00Z", {"before_min": 0, "after_min": 10})[1] == "2025-06-06T00:05:00Z"
    assert all(len(TIME_RE.findall(x["Anomaly Description"])) == 2 for x in json.loads(INPUT.read_text(encoding="utf-8")))
    print("ok")


if __name__ == "__main__":
    main()
