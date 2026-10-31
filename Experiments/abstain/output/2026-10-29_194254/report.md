# 포기 신호 실험

- 모델 solar-pro4, 케이스 3건, 호출 18회 (오류 2), 전체 소요 1.5분
- 제외: recall 0건 유형 = ['io fault', 'jvm cpu', 'jvm exception', 'jvm gc', 'jvm latency', 'memory stress', 'network corrupt', 'network delay', 'network loss', 'node cpu stress', 'node disk fill', 'node memory stress', 'pod failure', 'pod kill', 'target port misconfig'], 지울 근거 없음(L1=L0) 0건

## 1·2. 포기율 (A: insufficient / B: finish 없음)

| 트랙 | L0 | L1 | L2 | 민감도 L2−L0 |
|---|---|---|---|---|
| A | 50% | 50% | 100% | +50% |
| B | 67% | 67% | 100% | +33% |

## 3. B 표적성 (search를 부른 호출 중 target이 정답 엔티티)

무작위 기준선 (1 / L0 brief 엔티티 수 평균): 10%

| 수준 | search 호출 | target=정답 | target=null |
|---|---|---|---|
| L0 | 2 | 50% | 0% |
| L1 | 2 | 0% | 0% |
| L2 | 3 | 0% | 100% |

## 4. A 조건부 정답률 (answer로 답한 호출만)

| 수준 | 답한 호출 | instance | fault_type |
|---|---|---|---|
| L0 | 1 | 100% | 100% |
| L1 | 1 | 0% | 0% |
| L2 | 0 | - | - |

## 5. 비용·시간 (호출당)

| 트랙 | input | output | reasoning | 평균 latency | 최대 latency | 비용 합 |
|---|---|---|---|---|---|---|
| A | 2727 | 2349 | 2035 | 24.9s | 70.9s | $0.0247 |
| B | 3372 | 58 | 0 | 1.2s | 3.1s | $0.0097 |

총 비용 $0.0344 (usage 기준, 실패 호출 제외)

## fault_type별 포기율

| fault_type | A L0 | A L1 | A L2 | B L0 | B L1 | B L2 |
|---|---|---|---|---|---|---|
| code error | 0% | - | 100% | 100% | 100% | 100% |
| cpu stress | 100% | 100% | 100% | 100% | 0% | 100% |
| dns error | - | 0% | 100% | 0% | 100% | 100% |
