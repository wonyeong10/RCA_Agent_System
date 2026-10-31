# Loop 엄격 채점 (2026-10-31_020957)

Component = instance_type + instance 리스트 정확 일치 (매핑 tidb-X-N→X만). 분모 = 전체, 오류 = 오답.

| 범위 | n | Correct | Partial | Component | Fault Type |
|---|---|---|---|---|---|
| 전체 | 400 | 0.0% | 0.0% | 0.0% | 0.0% |
| TiDB 제외 | 345 | 0.0% | 0.0% | 0.0% | 0.0% |
| TiDB만 | 55 | 0.0% | 0.0% | 0.0% | 0.0% |

## instance_type별

| 범위 | n | Correct | Partial | Component | Fault Type |
|---|---|---|---|---|---|
| node | 82 | 0.0% | 0.0% | 0.0% | 0.0% |
| pod | 123 | 0.0% | 0.0% | 0.0% | 0.0% |
| service | 195 | 0.0% | 0.0% | 0.0% | 0.0% |

## fault_type별

| 범위 | n | Correct | Partial | Component | Fault Type |
|---|---|---|---|---|---|
| code error | 21 | 0.0% | 0.0% | 0.0% | 0.0% |
| cpu stress | 22 | 0.0% | 0.0% | 0.0% | 0.0% |
| dns error | 21 | 0.0% | 0.0% | 0.0% | 0.0% |
| io fault | 28 | 0.0% | 0.0% | 0.0% | 0.0% |
| jvm cpu | 13 | 0.0% | 0.0% | 0.0% | 0.0% |
| jvm exception | 13 | 0.0% | 0.0% | 0.0% | 0.0% |
| jvm gc | 14 | 0.0% | 0.0% | 0.0% | 0.0% |
| jvm latency | 15 | 0.0% | 0.0% | 0.0% | 0.0% |
| memory stress | 20 | 0.0% | 0.0% | 0.0% | 0.0% |
| network corrupt | 27 | 0.0% | 0.0% | 0.0% | 0.0% |
| network delay | 25 | 0.0% | 0.0% | 0.0% | 0.0% |
| network loss | 21 | 0.0% | 0.0% | 0.0% | 0.0% |
| node cpu stress | 23 | 0.0% | 0.0% | 0.0% | 0.0% |
| node disk fill | 21 | 0.0% | 0.0% | 0.0% | 0.0% |
| node memory stress | 38 | 0.0% | 0.0% | 0.0% | 0.0% |
| pod failure | 45 | 0.0% | 0.0% | 0.0% | 0.0% |
| pod kill | 15 | 0.0% | 0.0% | 0.0% | 0.0% |
| target port misconfig | 18 | 0.0% | 0.0% | 0.0% | 0.0% |

- 오류/출력 없음: 399건
- 종료 사유: {'finish': 1}
- search 횟수 평균: 2.00
- 비용 합계: $0.02, 건당 평균 $0.0000
- 소요 평균: 119s