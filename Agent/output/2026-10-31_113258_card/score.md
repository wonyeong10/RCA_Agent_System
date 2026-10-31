# Loop 엄격 채점 (2026-10-31_113258_card)

Component = instance_type + instance 리스트 정확 일치 (매핑 tidb-X-N→X만). 분모 = 전체, 오류 = 오답.

| 범위 | n | Correct | Partial | Component | Fault Type |
|---|---|---|---|---|---|
| 전체 | 400 | 2.2% | 18.0% | 8.5% | 14.0% |
| TiDB 제외 | 345 | 2.6% | 17.7% | 9.9% | 13.0% |
| TiDB만 | 55 | 0.0% | 20.0% | 0.0% | 20.0% |

## instance_type별

| 범위 | n | Correct | Partial | Component | Fault Type |
|---|---|---|---|---|---|
| node | 82 | 0.0% | 7.3% | 3.7% | 3.7% |
| pod | 123 | 0.8% | 21.1% | 8.9% | 13.8% |
| service | 195 | 4.1% | 20.5% | 10.3% | 18.5% |

## fault_type별

| 범위 | n | Correct | Partial | Component | Fault Type |
|---|---|---|---|---|---|
| code error | 21 | 9.5% | 28.6% | 23.8% | 23.8% |
| cpu stress | 22 | 0.0% | 0.0% | 0.0% | 0.0% |
| dns error | 21 | 0.0% | 47.6% | 0.0% | 47.6% |
| io fault | 28 | 0.0% | 21.4% | 0.0% | 21.4% |
| jvm cpu | 13 | 0.0% | 7.7% | 7.7% | 0.0% |
| jvm exception | 13 | 0.0% | 38.5% | 0.0% | 38.5% |
| jvm gc | 14 | 0.0% | 28.6% | 28.6% | 0.0% |
| jvm latency | 15 | 0.0% | 26.7% | 26.7% | 0.0% |
| memory stress | 20 | 0.0% | 20.0% | 20.0% | 0.0% |
| network corrupt | 27 | 0.0% | 0.0% | 0.0% | 0.0% |
| network delay | 25 | 0.0% | 16.0% | 0.0% | 16.0% |
| network loss | 21 | 0.0% | 19.0% | 0.0% | 19.0% |
| node cpu stress | 23 | 0.0% | 0.0% | 0.0% | 0.0% |
| node disk fill | 21 | 0.0% | 19.0% | 4.8% | 14.3% |
| node memory stress | 38 | 0.0% | 5.3% | 5.3% | 0.0% |
| pod failure | 45 | 11.1% | 26.7% | 15.6% | 33.3% |
| pod kill | 15 | 0.0% | 6.7% | 6.7% | 0.0% |
| target port misconfig | 18 | 11.1% | 27.8% | 27.8% | 22.2% |

- 오류/출력 없음: 1건
- 종료 사유: {'finish': 308, 'max_loops': 91}
- search 횟수 평균: 5.41
- 비용 합계: $8.92, 건당 평균 $0.0223
- 소요 평균: 123s