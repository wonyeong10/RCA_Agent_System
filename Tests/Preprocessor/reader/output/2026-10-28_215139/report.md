# reader 검증 결과 (2026-10-28_215139)

- 대상: `Agent/Preprocessor/reader.py`
- 총 67건: PASS 63 / FAIL 0 / ERROR 0 / INFO 4
- INFO = reader 범위 밖, Agent Loop가 tool 인자를 넘기기 전에 검사할 항목 (생각.txt 아이디어 6 'Agent Loop 입력 검사')
- 소요: 176s

## 1. 입력 검증

| 검사 | 결과 | 상세 |
|---|---|---|
| sources 빈 리스트 → ValueError | ✅ PASS | ValueError: sources must be a non-empty subset of ('log', 'trace', 'metric'): [] (0.0s) |
| sources 미지원 값 → ValueError | ✅ PASS | ValueError: sources must be a non-empty subset of ('log', 'trace', 'metric'): ['logs'] (0.0s) |
| sources 문자열 → ValueError | ✅ PASS | ValueError: sources must be a non-empty subset of ('log', 'trace', 'metric'): ['m', 'e', 't', 'r', 'i', 'c'] (0.0s) |
| target type pod (제외됨) → ValueError | ✅ PASS | ValueError: target must be None or {type: ('service', 'node', 'tidb', 'tikv', 'pd'), name}: {'type': 'pod', 'name': 'car (0.0s) |
| target type 오타 → ValueError | ✅ PASS | ValueError: target must be None or {type: ('service', 'node', 'tidb', 'tikv', 'pd'), name}: {'type': 'Service', 'name':  (0.0s) |
| target name 누락 → ValueError | ✅ PASS | ValueError: target must be None or {type: ('service', 'node', 'tidb', 'tikv', 'pd'), name}: {'type': 'service'} (0.0s) |
| target name 빈 문자열 → ValueError | ✅ PASS | ValueError: target must be None or {type: ('service', 'node', 'tidb', 'tikv', 'pd'), name}: {'type': 'service', 'name':  (0.0s) |
| target name 숫자 → ValueError [Agent Loop 검사] | ℹ️ INFO | ValueError가 아니라 TypeError: decoding to str: need a bytes-like object, int found |
| target이 dict 아님 → ValueError [Agent Loop 검사] | ℹ️ INFO | ValueError가 아니라 AttributeError: 'str' object has no attribute 'get' |
| start > end → ValueError | ✅ PASS | ValueError: start_time > end_time: 2025-06-05T16:31:02Z 2025-06-05T16:10:02Z (0.0s) |
| 잘못된 ISO → ValueError [Agent Loop 검사] | ℹ️ INFO | 예외 없이 통과함 |
| 날짜 아닌 문자열 → ValueError | ✅ PASS | ValueError: Invalid isoformat string: 'yesterday' (0.0s) |
| 시간대 없는 ISO(…02)는 UTC로 처리되거나 거부 [Agent Loop 검사] | ℹ️ INFO | Z 없는 입력이 로컬 시간대로 해석됨: 행 0 vs UTC 54001 |
| +08:00 오프셋 입력 = 같은 UTC 구간 | ✅ PASS |  (0.1s) |

## 2. 원본 보존

| 검사 | 결과 | 상세 |
|---|---|---|
| log 열·값·순서·dtype = oracle | ✅ PASS | 54001행 (0.0s) |
| trace 열·값·순서·dtype = oracle (중첩 열 포함) | ✅ PASS | 56327행 (14.9s) |
| trace ts가 startTimeMillis와 ms 단위로 일치 | ✅ PASS |  (0.0s) |
| metric 전 파일 열·값·순서·dtype = oracle, kpi_name 없음 | ✅ PASS | 109개 파일 (0.1s) |
| 'null' 문자열 원본 유지 (null로 변환 안 됨) | ✅ PASS |  (0.0s) |
| trace의 pod 키(name/podName)가 없는 span 수 (모든 service target에서 빠짐) | ✅ PASS |  (0.0s) |

## 3. 시각 경계

| 검사 | 결과 | 상세 |
|---|---|---|
| log: start 초·end 초 포함, end+1초 제외 | ✅ PASS | start초 34행, end초 56행 포함 (0.2s) |
| trace: μs 양끝 경계 (start 초 첫 span, end 초 마지막 μs) | ✅ PASS | start초 48, end초 78 span (0.0s) |
| metric: 분 내림 (16:10:02 시작 → 16:10 행 포함) | ✅ PASS |  (0.0s) |
| 1초 장애 0718e0f9-92: metric 행 > 0, 전부 04:03 분 | ✅ PASS | metric 729행, log 188, trace 161 (1.2s) |
| start == end (0초 구간) = oracle | ✅ PASS | log 102, trace 100 (25.7s) |

## 4. 파일 경계

| 검사 | 결과 | 상세 |
|---|---|---|
| UTC 시 경계 (16:50~17:10): log·trace·metric = oracle | ✅ PASS | log 52639, trace 50407, metric 109파일 (23.5s) |
| CST 자정 경계 (06-06→06-07): log·trace·metric = oracle | ✅ PASS | log 55083, trace 48999, metric 111파일 (27.3s) |
| 데이터 없는 날짜(06-15 CST) → 전 source 빈 결과, 예외 없음 | ✅ PASS |  (0.0s) |

## 5. 정렬

| 검사 | 결과 | 상세 |
|---|---|---|
| 모든 반환 DF ts 단조 증가 | ✅ PASS |  (0.0s) |
| 원본 log는 실제로 비정렬 (정렬이 일을 했는지) | ✅ PASS | 원본 비정렬 확인 → 순서 일치는 2번 그룹 oracle 대조에서 검증 (0.0s) |

## 6. target 필터 / service

| 검사 | 결과 | 상세 |
|---|---|---|
| adservice: log·trace·metric = oracle (누락·초과) | ✅ PASS | log 1589, trace 0, metric 13파일 (1.7s) |
| cartservice: log·trace·metric = oracle (누락·초과) | ✅ PASS | log 22779, trace 5273, metric 13파일 (3.0s) |
| checkoutservice: log·trace·metric = oracle (누락·초과) | ✅ PASS | log 312, trace 1224, metric 11파일 (1.9s) |
| currencyservice: log·trace·metric = oracle (누락·초과) | ✅ PASS | log 17612, trace 0, metric 13파일 (1.5s) |
| emailservice: log·trace·metric = oracle (누락·초과) | ✅ PASS | log 104, trace 104, metric 13파일 (1.5s) |
| frontend: log·trace·metric = oracle (누락·초과) | ✅ PASS | log 8018, trace 30893, metric 13파일 (9.9s) |
| paymentservice: log·trace·metric = oracle (누락·초과) | ✅ PASS | log 208, trace 0, metric 13파일 (1.5s) |
| productcatalogservice: log·trace·metric = oracle (누락·초과) | ✅ PASS | log 0, trace 14298, metric 13파일 (5.5s) |
| recommendationservice: log·trace·metric = oracle (누락·초과) | ✅ PASS | log 1902, trace 3804, metric 11파일 (2.0s) |
| redis-cart: log·trace·metric = oracle (누락·초과) | ✅ PASS | log 15, trace 0, metric 11파일 (1.4s) |
| shippingservice: log·trace·metric = oracle (누락·초과) | ✅ PASS | log 1462, trace 731, metric 13파일 (1.7s) |
| cartservice에 redis span 포함, redis-cart 혼입 없음 | ✅ PASS | redis span 2742개 (0.0s) |
| (deleted) apm 파일 포함: productcatalogservice 2025-06-06 | ✅ PASS | apm/pod/pod_productcatalogservice-1 (deleted), apm/pod/pod_productcatalogservice-2 (deleted) (0.5s) |
| (deleted) apm 파일 포함: cartservice 2025-06-07 | ✅ PASS | apm/pod/pod_cartservice-2 (deleted) (0.5s) |
| 없는 서비스명 → 전 source 빈 결과, 예외 없음 | ✅ PASS |  (1.3s) |
| 정규식 문자 이름(cart.*) → 아무것도 안 잡힘 | ✅ PASS |  (1.3s) |
| 부분 이름(cart) → cartservice 안 잡힘 | ✅ PASS |  (1.2s) |

## 6. target 필터 / node

| 검사 | 결과 | 상세 |
|---|---|---|
| aiops-k8s-01: infra_node 행만 = oracle, log·trace는 읽은 뒤 빈 결과 | ✅ PASS | 16파일 (1.3s) |
| aiops-k8s-02: infra_node 행만 = oracle, log·trace는 읽은 뒤 빈 결과 | ✅ PASS | 16파일 (1.3s) |
| aiops-k8s-03: infra_node 행만 = oracle, log·trace는 읽은 뒤 빈 결과 | ✅ PASS | 16파일 (1.3s) |
| aiops-k8s-04: infra_node 행만 = oracle, log·trace는 읽은 뒤 빈 결과 | ✅ PASS | 16파일 (1.3s) |
| aiops-k8s-05: infra_node 행만 = oracle, log·trace는 읽은 뒤 빈 결과 | ✅ PASS | 16파일 (1.3s) |
| aiops-k8s-06: infra_node 행만 = oracle, log·trace는 읽은 뒤 빈 결과 | ✅ PASS | 16파일 (1.3s) |
| aiops-k8s-07: infra_node 행만 = oracle, log·trace는 읽은 뒤 빈 결과 | ✅ PASS | 16파일 (1.3s) |
| aiops-k8s-08: infra_node 행만 = oracle, log·trace는 읽은 뒤 빈 결과 | ✅ PASS | 16파일 (1.3s) |
| k8s-master1: infra_node 행만 = oracle, log·trace는 읽은 뒤 빈 결과 | ✅ PASS | 16파일 (1.3s) |
| k8s-master2: infra_node 행만 = oracle, log·trace는 읽은 뒤 빈 결과 | ✅ PASS | 16파일 (1.3s) |
| k8s-master3: infra_node 행만 = oracle, log·trace는 읽은 뒤 빈 결과 | ✅ PASS | 16파일 (1.3s) |
| ef2a4fbb-87 (aiops-k8s-03 node cpu stress) 케이스 저장 | ✅ PASS |  (1.0s) |

## 6. target 필터 / TiDB 계층

| 검사 | 결과 | 상세 |
|---|---|---|
| tidb: file_key = 'infra/infra_tidb/*' 전부 = oracle, 행 필터 없음 | ✅ PASS | 13파일 (1.3s) |
| tikv: file_key = 'other/infra_tikv_*' 전부 = oracle, 행 필터 없음 | ✅ PASS | 17파일 (1.3s) |
| pd: file_key = 'other/infra_pd_*' 전부 = oracle, 행 필터 없음 | ✅ PASS | 15파일 (1.2s) |

## 7. 빈 결과·공백

| 검사 | 결과 | 상세 |
|---|---|---|
| 파일 없는 구간: 06-08 17:00 UTC trace (06-09 CST 01시) → 빈 DF | ✅ PASS |  (0.0s) |
| 일부 공백: d0be3c58-178 trace = oracle, 19분 중 3분만 행 있음 | ✅ PASS | trace 3행, 3/19분 (3.8s) |
| 계측 없는 서비스(adservice) trace → 빈 DF, 파일은 읽음 | ✅ PASS |  (1.1s) |

## 8. 결정성

| 검사 | 결과 | 상세 |
|---|---|---|
| 같은 입력 2회 호출 결과 동일 | ✅ PASS |  (11.3s) |

## 9. 전수 sweep

| 검사 | 결과 | 상세 |
|---|---|---|
| groundtruth 400건 | ✅ PASS | 생략 (--skip-sweep) |
