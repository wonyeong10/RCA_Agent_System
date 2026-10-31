# Experiments/CLAUDE.md

가설 검증 실험 (Agent 코드도, 독립 oracle 검증 테스트도 아님). LLM 호출은 전부 `Agent/util/llm.call`을 거친다 → `logs/llm_usage.jsonl`에 토큰·비용·latency 기록.
결과는 실행마다 `<실험>/output/<YYYY-MM-DD_HHMMSS>/` (gitignore).

## abstain (`abstain/run.py`) — 포기 신호 가설 v2 (생각.txt 아이디어 5)

레포 루트에서 `.venv/Scripts/python.exe Experiments/abstain/run.py [--pilot] [--n 30] [--n-short 20] [--reps 3]`
- 루트 `.env`의 `UPSTAGE_API_KEY` 필요. `--pilot` = 수준별 2건 × 1회 (20 호출), 기본 = 140 brief × 2트랙 × 3회 (840 호출).
- system card 없음 (구조 정확성 미확정).
- 근거 수준: L0(원인이 2개 이상 source에서 보임, 원본) / L1a(같은 케이스, 원인 보이는 source 1개만 남김, 인공) /
  N1(원래 1개 source만, 자연) / N0(어느 source에도 안 보임, 10분 초과, 자연) / Nshort(10분 이하, 자연).
  "보인다" = 정답 엔티티가 주인인 줄. 케이스는 recall rows.csv(`Tests/Preprocessor/selector/output/2026-10-29_195515`)로 고르고 brief로 재확인.
- 트랙: A 답변 호출(reasoning medium, status answer|insufficient) / B 결정 호출(reasoning 끔, search|finish 첫 호출만, 실행 안 함).
- 출력: `briefs/`(수준_uuid), `calls.jsonl`(호출별 응답·토큰·비용·시간), `report.md`.
- 이름 일치: service 단위 (pod → service, `tidb-tikv-0` → `tikv`), node(`aiops-k8s-NN`)는 정확 일치.
- v1(L0/L1 3 source 전부 삭제/L2 이상 줄 전부 삭제, 결과 `output/2026-10-29_202346`)은 비현실적 조작이라 교체됨.
