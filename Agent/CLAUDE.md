# Agent/CLAUDE.md

RCA 에이전트 코드. 전체 흐름·설계 결정은 루트 `생각.txt` 아이디어 4·6(reader)·7(selector) 참고.

## 구조

- `Preprocessor/reader.py` — 원본 parquet에서 (sources, target, 구간)의 행을 **원본 그대로** 잘라 ts 정렬해 반환. 반환 = `{"log": DF, "trace": DF, "metric": {file_key: DF}}` (요청 source만).
  - 추가 열 `ts`(UTC) 하나, 빼는 열 `kpi_name` 하나. 열 통일·값 변환·quirk 해석은 하지 않는다 (selector 몫).
  - target: `None` | `{"type": pod|service|node|tidb|tikv|pd, "name"}`. 확장 없음, 모두 자기 데이터만 (service = apm service 집계 파일, 하위 pod 안 따라감).
  - 모든 source에 같은 규칙: 행 주인(log `k8_pod`, trace pod 태그, apm 파일명, infra `pod`/`kubernetes_node`)이 target 이름과 같으면 남긴다. 관계(service↔pod, pod→node)나 "어떤 엔티티에 어떤 source가 있는지"는 판단하지 않는다 (그 지식은 system card).
  - 수집 상태(coverage)는 판정하지 않는다. 빈 DataFrame = 행 없음, 해석은 프롬프트 규칙("행 0 = 정상 근거 아님")과 selector 몫.
  - metric은 파일마다 스키마가 달라 `{file_key: DataFrame}`로 반환.
- `Preprocessor/selector.py` — reader 출력에서 이상 패턴만 골라 LLM용 텍스트로. `select(sources, target, start, end) -> str`. **OpsAgent 공개 코드(`참고 구현/OpsAgent-CCC0`)를 따르고, 논문과 코드가 다르면 논문** (생각.txt 아이디어 7).
  - 조회 구간 = 요청 구간 그대로, 기준 = 그 구간 전체. OpsAgent process_data의 구간 확장(쿼리 30분 고정, metric 앞 20분·뒤 10분)은 baseline 성능 측정 후로 보류. 상태·캐시 없음 (재검색 = 넓힌 구간으로 다시 호출).
  - metric: 3σ(표본 표준편차)를 넘은 모든 시점이 이상 → 시점마다 CNN 모양(`patterncla.pt`, 30포인트, 끝이면 반대쪽으로 채움, 못 채우면 "판정 불가(30포인트 미만)") → Top-5 instance(이상 시점 z 합, target=None일 때만) + Top-5 metric(Top-5 instance 안) + (엔티티, 지표, 모양) 묶음 설명 최대 편차순 24줄. 결측 0 채우기는 안 따름.
  - log: 키워드 → 걸린 로그 Drain3 템플릿 → TF-IDF(sklearn, 줄 단위 평균) 80 분위 이상 → 분·템플릿 첫 1건, 원문 전체 출력 (상한 없음).
  - trace: 호출 유형(서비스, operation)별 p95 초과 = 고지연 → (60초, callee pod)별 건수·최대 지연·caller(부모 없으면 자신), 건수순 24줄 + 3-hop 경로(조부모 있는 것, 2회 이상) 24개. target이 있어도 부모 span이 필요해 전체를 읽고 target이 낀 span만 남김.
  - source마다 헤더 한 줄: 행 수 / "행 없음" / metric 포인트 ≤10이면 "3σ 판정 불가".
  - 알려진 한계: 구간 전체가 장애라 기준이 오염됨 (OpsAgent도 기준 범위에 장애 포함, 지속형 장애가 범위의 10% 이상이면 3σ를 넘기 어려움), 10분 이하 구간은 3σ 불가, 30분 미만 구간은 CNN 모양 "판정 불가".
  - 엔티티 이름: TiDB 계층은 컴포넌트명(tidb/tikv/pd). groundtruth 형식(tidb-tikv-0)으로의 매핑은 출력 단계 몫.
- `loop.py` — 메인 Loop (생각.txt 아이디어 4 "루프 (확정)"). `run_case(uuid, start, end) -> (answer, trace)`, 입력 형식(input.json 파싱)은 `parse_input`·`__main__` 쪽.
  - initial brief = `selector.select(전체 source, None, 입력 구간)` → Tool 모델(`TOOL_MODEL`, reasoning 끔, tool_choice=required, search|finish) 최대 `MAX_LOOPS`(5)회 → Answer 모델(`ANSWER_MODEL`, reasoning medium, json_schema strict, reason 마지막, 실패 시 1회 재시도).
  - history: 케이스별 지역 리스트, append-only로 매 호출 통째 전달. 모든 function_call에 function_call_output (검증 오류·중복 조회도 문자열, 회차 소모). finish가 search와 섞이면 finish 우선. Answer 모델엔 tool item 대신 텍스트 transcript.
  - 모델은 시각을 안 씀: window{before_min, after_min}(0~60) → 코드가 ISO Z로 계산. 인자 검사는 `validate` (reader 앞단, 아이디어 6).
  - 출력 instance는 항상 리스트. TiDB 계층은 컴포넌트명(tikv 등) 그대로, groundtruth 형식 매핑은 채점 쪽.
  - 선택지: search target = 케이스별 `selector.entities(입력 ±60분)`, 답변 instance = 상수 `ANSWER_NAMES`(전체 날짜 원본 합집합, `(deleted)`·`example-ant-*` 제외, groundtruth 미사용) — 프롬프트 ANSWER_TASK에 목록 표시.
- `util/llm.py` — 공용 LLM 래퍼. 모든 LLM 호출은 `llm.call(purpose, **responses_create_kwargs) -> (response, record)`를 거친다.
  - Upstage Responses API (OpenAI SDK, `base_url=https://api.upstage.ai/v1`), 키는 루트 `.env` → `Agent/.env`의 `UPSTAGE_API_KEY`.
  - 호출마다 `logs/llm_usage.jsonl`에 append: ts, model(응답의 실제 버전), purpose, input/cached/output/reasoning 토큰(usage 그대로), cost_usd, latency_sec. 실패 호출도 `error`로 기록.
  - 단가는 `PRICES` 한 곳 (upstage.ai/pricing). 별칭 접두로 조회.

## 실행

레포 루트에서 `.venv` 파이썬으로: `.venv/Scripts/python.exe Agent/Preprocessor/reader.py` → `__main__` assert 자체 점검 (`ok` 출력). selector·`util/llm.py`(비용 계산 점검, API 호출 없음)도 같은 방식 (`Agent/Preprocessor/selector.py`, 의존성 drain3·torch CPU).

Loop: `.venv/Scripts/python.exe Agent/loop.py [--uuid U ...] [--limit N] [--workers 4]` (루트 `.env`의 `UPSTAGE_API_KEY` 필요), API 없는 점검은 `--check`.
출력 `Agent/output/<YYYY-MM-DD_HHMMSS>/` (gitignore): `output.jsonl`(uuid, instance_type, instance[], fault_type, reason), `traces.jsonl`(회차별 tool 호출·input/cached 토큰·비용·latency, 종료 사유), `histories/{uuid}.json`(history·transcript 원본).
