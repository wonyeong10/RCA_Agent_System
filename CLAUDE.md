# CLAUDE.md

## 규칙

- **git 명령어는 사용자의 허가 없이 절대 실행하지 않는다** (`git commit`, `git push`, `git branch`, `git reset`, `git checkout` 등 모두 포함).
- **git 작업 시 공동 저자(Co-Authored-By)에 Claude를 포함하지 않는다.** 커밋 메시지·PR 본문에 Claude 관련 attribution 줄을 넣지 않는다.
- **LLM API를 호출하는 코드에는 매 호출마다 토큰 사용량과 API 비용을 별도로 기록하는 코드를 함께 작성한다.**
  - 모든 호출은 공용 래퍼 하나를 거치게 하고, 래퍼가 기록을 담당한다 (호출부마다 기록 코드를 복붙하지 않는다).
  - 기록 항목: 시각, 모델명, 호출 목적(케이스 uuid 등), input/output 토큰 수, 비용(USD).
  - 토큰 수는 API 응답의 usage 값을 그대로 쓴다 (추정치 금지).
  - 단가는 모델별 상수 표 한 곳에 두고, 공식 가격표 기준으로 값과 출처를 주석에 남긴다.
  - 기록은 append-only 파일(예: `logs/llm_usage.jsonl`)에 남긴다.
- **LLM API 키는 루트 또는 `/Agent` 디렉토리의 `.env` 파일에 두고, LLM을 호출하는 코드는 이 `.env`를 참조한다.** 키를 코드에 하드코딩하지 않아 노출되지 않도록 한다. `.env`는 `.gitignore`에 포함되어 있다.
- **파이썬 라이브러리는 이 폴더 안의 가상환경(`.venv/`)에 설치하고, 모델 실행 등 모든 파이썬 실행은 그 가상환경에서 한다.** 전역 파이썬에 설치하지 않는다. `.venv/`는 `.gitignore`에 포함되어 있다.
- **정답 판정(채점·recall·실험 지표·근거 수준 분류)은 항상 엄격하게 한다.** groundtruth instance(리스트면 전부)와 이름이 정확히 일치해야 정답. 허용은 표기 매핑(`tidb-tikv-0` → `tikv`)뿐, pod↔service 묶기·리스트 일부만 맞아도 인정 금지. 느슨한 변형은 별도 이름의 보조 열로만 보고한다.
- **CLAUDE.md는 폴더가 추가·분화될 때마다 해당 폴더에 분산 생성한다.** 루트 CLAUDE.md의 `## 하위 CLAUDE.md 위치`에 경로와 용도를 기록하고, 관련 작업 시 해당 파일을 찾아가 참고한다.

## 하위 CLAUDE.md 위치

- `data/CLAUDE.md` — AIOps Challenge 2025 데이터셋 구조·groundtruth 필드·장애 유형·시간대. 데이터 속성을 참고할 때 읽을 것.
- `Agent/CLAUDE.md` — 에이전트 코드 구조(reader·selector)·실행 방법. Agent 코드 작업 시 읽을 것.
- `Experiments/CLAUDE.md` — 가설 검증 실험(포기 신호 등) 실행법·output 위치. LLM 실험 작성·실행 시 읽을 것.
- `Tests/CLAUDE.md` — 검증 코드 원칙(독립 oracle 대조)·실행법·output 위치. 테스트 작성·실행 시 읽을 것.
