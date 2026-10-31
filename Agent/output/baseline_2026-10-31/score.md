# Loop 엄격 채점 (baseline_2026-10-31)

Component = instance_type + instance 리스트 정확 일치 (매핑 tidb-X-N→X만). 분모 = 전체, 오류 = 오답.

| 범위 | n | Correct | Partial | Component | Fault Type |
|---|---|---|---|---|---|
| 전체 | 400 | 1.8% | 17.8% | 8.0% | 13.2% |
| TiDB 제외 | 345 | 2.0% | 18.0% | 9.3% | 12.8% |
| TiDB만 | 55 | 0.0% | 16.4% | 0.0% | 16.4% |

## instance_type별

| 범위 | n | Correct | Partial | Component | Fault Type |
|---|---|---|---|---|---|
| node | 82 | 0.0% | 4.9% | 4.9% | 0.0% |
| pod | 123 | 1.6% | 23.6% | 13.8% | 13.0% |
| service | 195 | 2.6% | 19.5% | 5.6% | 19.0% |

## fault_type별

| 범위 | n | Correct | Partial | Component | Fault Type |
|---|---|---|---|---|---|
| code error | 21 | 4.8% | 38.1% | 4.8% | 42.9% |
| cpu stress | 22 | 0.0% | 9.1% | 4.5% | 4.5% |
| dns error | 21 | 4.8% | 47.6% | 9.5% | 47.6% |
| io fault | 28 | 0.0% | 17.9% | 0.0% | 17.9% |
| jvm cpu | 13 | 0.0% | 7.7% | 7.7% | 0.0% |
| jvm exception | 13 | 0.0% | 23.1% | 15.4% | 7.7% |
| jvm gc | 14 | 0.0% | 28.6% | 28.6% | 0.0% |
| jvm latency | 15 | 0.0% | 26.7% | 26.7% | 0.0% |
| memory stress | 20 | 0.0% | 15.0% | 10.0% | 5.0% |
| network corrupt | 27 | 0.0% | 0.0% | 0.0% | 0.0% |
| network delay | 25 | 0.0% | 28.0% | 0.0% | 28.0% |
| network loss | 21 | 0.0% | 19.0% | 0.0% | 19.0% |
| node cpu stress | 23 | 0.0% | 4.3% | 4.3% | 0.0% |
| node disk fill | 21 | 0.0% | 0.0% | 0.0% | 0.0% |
| node memory stress | 38 | 0.0% | 7.9% | 7.9% | 0.0% |
| pod failure | 45 | 8.9% | 24.4% | 13.3% | 28.9% |
| pod kill | 15 | 0.0% | 13.3% | 13.3% | 0.0% |
| target port misconfig | 18 | 5.6% | 16.7% | 16.7% | 11.1% |

- 오류/출력 없음: 0건
- 종료 사유: {'finish': 323, 'max_loops': 77}
- search 횟수 평균: 4.93
- 비용 합계: $7.39, 건당 평균 $0.0185
- 소요 평균: 93s