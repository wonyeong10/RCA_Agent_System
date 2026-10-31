# Graph Report - RCA_Agent_System  (2026-10-30)

## Corpus Check
- 12 files · ~40,632 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 111 nodes · 164 edges · 10 communities (9 shown, 1 thin omitted)
- Extraction: 96% EXTRACTED · 4% INFERRED · 0% AMBIGUOUS · INFERRED: 6 edges (avg confidence: 0.85)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `cbfd1406`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- run.py
- test_reader.py
- selector.py
- loop.py
- reader.py
- llm.py
- Research Agent Instructions
- test_selector.py
- task.md
- system_card.py

## God Nodes (most connected - your core abstractions)
1. `main()` - 8 edges
2. `job()` - 7 edges
3. `visible()` - 6 edges
4. `strip()` - 6 edges
5. `Research Agent Instructions` - 6 edges
6. `select()` - 5 edges
7. `_metric()` - 5 edges
8. `check()` - 5 edges
9. `call()` - 5 edges
10. `match()` - 5 edges

## Surprising Connections (you probably didn't know these)
- `main()` --indirect_call--> `job()`  [INFERRED]
  Agent/loop.py → Experiments/abstain/run.py

## Import Cycles
- None detected.

## Communities (10 total, 1 thin omitted)

### Community 0 - "run.py"
Cohesion: 0.17
Nodes (22): blocks(), build(), col(), job(), main(), match(), n_entities(), norm() (+14 more)

### Community 1 - "test_reader.py"
Cohesion: 0.13
Nodes (19): assert_frame_same(), assert_metric_same(), assert_no_owner_rows(), dump_case(), main(), minutes(), oracle_hourly(), oracle_metric() (+11 more)

### Community 2 - "selector.py"
Cohesion: 0.22
Nodes (12): _CNN, _log(), _metric(), selector: reader가 자른 원본에서 이상 패턴만 골라 LLM용 텍스트로 바꾼다 (OpsAgent 3.2 Training-free…, [start_time, end_time] 구간(= baseline = 관찰 구간)의 이상 패턴 텍스트., {file_key: DF} → [(entity, metric_name, 분 단위 Series)]. quirk 흡수는 여기서만., _rel(), select() (+4 more)

### Community 3 - "loop.py"
Cohesion: 0.26
Nodes (12): check(), main(), parse_input(), 메인 Loop (생각.txt 아이디어 4 "루프 (확정)"): 케이스 1건 → Tool 모델 결정 반복 → Answer 모델 json 답변.…, input 구간 + 앞뒤 확장 → ISO UTC (Z). 모델은 시각을 쓰지 않는다., 반환 (answer dict, trace dict). trace = 회차별 tool 호출·토큰·비용, history·transcript 원본., input.json 항목 → (uuid, start, end). 문장 속 ISO UTC 시각이 정확히 2개여야 함., search 인자 → 정규화 dict. 잘못되면 ValueError (메시지가 그대로 tool 결과가 됨). (+4 more)

### Community 4 - "reader.py"
Cohesion: 0.27
Nodes (10): check(), _floor_min(), _metric_files(), _parse(), reader: 원본 parquet에서 요청 구간·target의 행을 원본 그대로 잘라 시간순으로 내보낸다. 하는 일: 시간대 변환(파일명…, [start_time, end_time] (UTC ISO, 양끝 포함, 초 정밀도) 구간의 원본 행. target: None(전 엔티티) |…, read(), _read_hourly() (+2 more)

### Community 5 - "llm.py"
Cohesion: 0.33
Nodes (8): call(), client(), cost(), _key(), 공용 LLM 래퍼: 모든 호출은 call()을 거치고, 호출마다 토큰·비용·실행 시간을 logs/llm_usage.jsonl에 append.…, 모델명은 실제 버전(solar-pro4-260806)이어도 별칭 접두로 단가 조회. 표에 없으면 None., client.responses.create(**kwargs) 1회 + 기록. 반환 (response, record). 실패도 기록 후 예외…, _write()

### Community 6 - "Research Agent Instructions"
Cohesion: 0.29
Nodes (6): Hard rules, Output, Persona, Research Agent Instructions, Self-verification (run before calling `finish`), Workflow

### Community 7 - "test_selector.py"
Cohesion: 0.53
Nodes (5): hit(), main(), selector recall@K: initial 조건(target=None, input 구간 그대로)에서 정답 엔티티가 출력에 들어가는 비율.…, sections(), svc()

### Community 8 - "task.md"
Cohesion: 0.50
Nodes (3): Seed URLs (fetch_url로 조회해서 시작), 산출물, 요구사항

## Knowledge Gaps
- **8 isolated node(s):** `Persona`, `Hard rules`, `Workflow`, `Self-verification (run before calling `finish`)`, `Output` (+3 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 41 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **1 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `job()` connect `run.py` to `loop.py`?**
  _High betweenness centrality (0.018) - this node is a cross-community bridge._
- **Why does `main()` connect `loop.py` to `run.py`?**
  _High betweenness centrality (0.015) - this node is a cross-community bridge._
- **What connects `Persona`, `Hard rules`, `Workflow` to the rest of the system?**
  _8 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `test_reader.py` be split into smaller, more focused modules?**
  _Cohesion score 0.13333333333333333 - nodes in this community are weakly interconnected._