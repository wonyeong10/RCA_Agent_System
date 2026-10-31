# selector recall (initial, 400건, 오류 0건)

엄격 = 정답 이름 전부 정확 일치 (표기 매핑 tidb-tikv-0→tikv만). _b = service 정답에 한해 소속 pod도 인정.

## 엄격

| 범위 | n | metric_top5 | trace_top5 | log_top5 | any_top5 |
|---|---|---|---|---|---|
| 전체 | 400 | 15% | 12% | 4% | 29% |
| node | 82 | 29% | 0% | 0% | 29% |
| pod | 123 | 19% | 0% | 13% | 28% |
| service | 195 | 6% | 24% | 0% | 30% |
| code error | 21 | 0% | 38% | 0% | 38% |
| cpu stress | 22 | 18% | 23% | 0% | 41% |
| dns error | 21 | 19% | 43% | 5% | 62% |
| io fault | 28 | 0% | 0% | 0% | 0% |
| jvm cpu | 13 | 31% | 0% | 15% | 46% |
| jvm exception | 13 | 31% | 0% | 15% | 46% |
| jvm gc | 14 | 57% | 0% | 29% | 57% |
| jvm latency | 15 | 20% | 0% | 27% | 40% |
| memory stress | 20 | 40% | 15% | 15% | 70% |
| network corrupt | 27 | 0% | 22% | 0% | 22% |
| network delay | 25 | 0% | 28% | 0% | 28% |
| network loss | 21 | 0% | 10% | 0% | 10% |
| node cpu stress | 23 | 13% | 0% | 0% | 13% |
| node disk fill | 21 | 19% | 0% | 0% | 19% |
| node memory stress | 38 | 45% | 0% | 0% | 45% |
| pod failure | 45 | 0% | 7% | 0% | 7% |
| pod kill | 15 | 0% | 13% | 0% | 13% |
| target port misconfig | 18 | 0% | 11% | 0% | 11% |

근거 수준 후보 (Top-5 제한 없이 주인 줄이 보이는 source 수, 10분 초과 / 이하): 0개 213/48건, 1개 122/11건, 2개 6/0건, 3개 0/0건

## b 기준 (service 정답 = 소속 pod 인정)

| 범위 | n | metric_top5_b | trace_top5_b | log_top5_b | any_top5_b |
|---|---|---|---|---|---|
| 전체 | 400 | 29% | 12% | 13% | 43% |
| node | 82 | 29% | 0% | 0% | 29% |
| pod | 123 | 19% | 0% | 13% | 28% |
| service | 195 | 35% | 24% | 19% | 59% |
| code error | 21 | 33% | 38% | 48% | 81% |
| cpu stress | 22 | 36% | 23% | 0% | 45% |
| dns error | 21 | 33% | 43% | 14% | 62% |
| io fault | 28 | 0% | 0% | 0% | 0% |
| jvm cpu | 13 | 54% | 0% | 92% | 100% |
| jvm exception | 13 | 54% | 0% | 77% | 85% |
| jvm gc | 14 | 86% | 0% | 64% | 86% |
| jvm latency | 15 | 33% | 0% | 33% | 53% |
| memory stress | 20 | 65% | 15% | 20% | 95% |
| network corrupt | 27 | 22% | 22% | 0% | 44% |
| network delay | 25 | 8% | 28% | 0% | 36% |
| network loss | 21 | 10% | 10% | 0% | 19% |
| node cpu stress | 23 | 13% | 0% | 0% | 13% |
| node disk fill | 21 | 19% | 0% | 0% | 19% |
| node memory stress | 38 | 45% | 0% | 0% | 45% |
| pod failure | 45 | 9% | 7% | 0% | 16% |
| pod kill | 15 | 0% | 13% | 0% | 13% |
| target port misconfig | 18 | 61% | 11% | 0% | 67% |

근거 수준 후보 (Top-5 제한 없이 주인 줄이 보이는 source 수, 10분 초과 / 이하): 0개 164/48건, 1개 130/11건, 2개 45/0건, 3개 2/0건


- metric 포인트 부족(≤10분)으로 3σ 판정 불가: 43건
- 출력 길이: 평균 9072자, 최대 21046자
- 소요: 평균 3.6s, 최대 10.5s