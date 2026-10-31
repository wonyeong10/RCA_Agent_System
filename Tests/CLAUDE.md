# Tests/CLAUDE.md

검증 코드. 구조는 `Agent/`를 따라간다 (`Tests/Preprocessor/reader/` ↔ `Agent/Preprocessor/reader.py`).

## 원칙

- pytest 없음 (.venv 미설치) → 단일 스크립트, 검사 하나가 실패해도 전부 실행 후 리포트.
- **독립 oracle 대조**: 대상 코드를 재사용하지 않고 원본을 따로 읽어 같은 결과가 나오는지 행 단위로 비교. oracle이 대상 코드와 같은 로직을 쓰면 같은 버그를 공유하므로 경계·필터 계산은 다른 방식으로.
- 결과는 실행마다 `output/<YYYY-MM-DD_HHMMSS>/`에 남긴다: `report.md`(PASS/FAIL 표), `cases/`(대표 케이스 실제 반환값 CSV·요약), 그 외 전수 결과.

## reader (`Preprocessor/reader/test_reader.py`)

레포 루트에서 `.venv/Scripts/python.exe Tests/Preprocessor/reader/test_reader.py [--skip-sweep]`
- `--skip-sweep` 없이 실행하면 groundtruth 400건 전수 실행 포함 (~20분, `sweep_rows.csv`: 케이스·source별 행 수·고유 분 수).
- 실패가 있으면 exit code 1.

## selector (`Preprocessor/selector/test_selector.py`)

레포 루트에서 `.venv/Scripts/python.exe Tests/Preprocessor/selector/test_selector.py [--limit N]`
- oracle 대조가 아니라 **recall 측정**: initial 조건(target=None, input 구간)에서 정답 엔티티가 metric Top-5 instance / trace 앞쪽 고유 callee 5개 / log 상위 pod 5개에 드는 비율.
- 판정은 **엄격** (루트 CLAUDE.md 규칙): 정답 이름(리스트면 전부) 정확 일치, 표기 매핑 `tidb-tikv-0` → `tikv`만 (`canon()`). `_b` 열 = service 정답에 한해 소속 pod도 인정하는 보조 변형. `*_any` 열 = Top-5 제한 없이 주인 줄 존재 (실험 근거 수준 분류용).
- 400건 ~25분. `rows.csv`(케이스별), `report.md`(엄격·b 기준 각각 전체·instance_type·fault_type별 + 근거 수준 후보 수), `cases/`(일부 케이스 출력 텍스트).
- 기준 결과: `output/2026-10-30_213210` (엄격 any_top5 29%, b 기준 43%). 2026-10-29 이전 실행(61%·67%)은 service 단위 느슨한 일치라 무효.

## Loop 채점 (`loop/score.py`)

레포 루트에서 `.venv/Scripts/python.exe Tests/loop/score.py Agent/output/<run>` (인자 없으면 assert 자체 점검)
- 생각.txt 과제3 지표 (Time 제외): Correct / Partial / Component / Fault Type. Component = instance_type + instance 리스트 정확 일치(순서 포함, 매핑 `tidb-X-N → X`만). 분모 400, 오류 = 오답.
- 보조 행 "TiDB 제외"(345건): groundtruth TiDB 형식 `[tidb-tikv-0, tidb-tikv]`는 데이터로 도출 불가라 따로 본다.
- 출력은 run 폴더에 `score.md`, `score_rows.csv`. 채점 규칙이 바뀌면 같은 출력으로 다시 돌린다.
