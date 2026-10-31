# data/CLAUDE.md

AIOps Challenge 2025 데이터셋 정리. 원문(영어 번역본): `aiopschallenge2025/README.md`.

마이크로서비스 시스템에 장애를 주입하고 로그·메트릭·트레이스를 수집한 RCA 데이터셋. 장애 사례 400건 + 정답.

## 핵심 이슈 요약 (데이터 검토 결론)

상세 근거는 아래 각 섹션 참고.

1. **[최우선] 시간 채점 불가** — input의 시각이 groundtruth `start_time`/`end_time`과 400건 전부 동일. 과제가 time 채점을 요구하면 성립 안 함 → 과제 수정 요청 필요. 대안: (A) 입력에서 시각 제거·탐지 포함, 구간 겹침(IoU)으로 채점 (B) 넓은 범위(1~2h)만 주고 실제 구간을 찾게 함 (C) 시간 채점 제외, 위치·유형·reason만 채점 (원 대회 방식)
2. **시간대 변환 필수** — 파일명 CST(UTC+8), log/metric 내부 UTC, trace ms. 로더 한 곳에서 통일
3. **장애 구간 데이터 누락** — log 없음 21건, trace 없음 40건, trace 일부만 7건. 일 단위 누락(06-15·16·22·23·25·26)은 장애 0건이라 무관. 에이전트는 소스별 커버리지를 먼저 계산해 넘길 것 ("trace 0%" ≠ "trace 정상")
4. **정렬** — 원본 파일 자체가 비정렬(뷰어 문제 아님, pyarrow는 저장 순서대로 읽음). log: 1시간 파일 내 최대 ~60분 뒤섞임(중앙값 ~20분) → 시각 필터+정렬 필수. trace: 30초 이내. metric: 전 2,035개 파일 완전 정렬. 파일 밖 시간대 행은 0건이라 파일 선택은 안전
5. **라벨 이름이 README와 다름** — 실제 `fault_type` 18종(공백 구분, `node memory stress` 포함). 출력 라벨은 groundtruth 기준으로 고정
6. **`instance`가 문자열/리스트 혼재** (179건 리스트) — 네트워크 `[src, dst]`, pod 장애 다중 대상. 출력 형식·채점(부분 일치 처리) 결정 필요
7. **같은 유형이 pod/service 양쪽 레벨에 존재** — 영향 범위(pod 하나 vs 서비스 전체) 판별 필요
8. **정답 유출·과적합 주의** — groundtruth의 `key_observations`/`key_metrics`가 에이전트 입력·프롬프트에 섞이면 안 됨. 개발용/평가용 케이스 분리 권장
9. **원본을 LLM에 그대로 못 넣음** — 하루 log ~210MB(~700만 행), trace ~480MB. 코드로 필터·집계·이상치 추출 후 LLM 전달
10. **log `message` 형식 이질적** — 서비스별 평문/JSON 혼재
11. **정합성 처리** — infra 값 컬럼명=`kpi_key`(파일마다 다름), 노드명 위치 불일치(`instance` vs `kubernetes_node`)
12. **pod 구성이 날짜마다 다름** — apm pod 파일 20~31개, `(deleted)` 접미사 파일 존재 → pod 목록 하드코딩 금지
13. **매우 짧은 장애** — 최소 1초. 1분 metric에 흔적이 약할 수 있음 → `end_time` 이후 구간도 볼 것
14. **정상 구간(baseline) 확보** — 하루 21~24건, 샘플상 매시 :10 전후 시작(전체 규칙인지 미확인). 장애 직전 구간 vs 장애 없는 06-29 중 baseline 방식 결정 필요
15. **유형 불균형** — 45건(pod failure) ~ 13건(jvm cpu/exception). 유형별 정확도도 함께 볼 것
16. **중국어 → `kpi_name` 조회 금지** — 에이전트 모델이 중국어 미지원. 데이터셋에서 중국어는 metric infra/other의 `kpi_name`에만 있음 (log·trace 샘플, apm, input/groundtruth, 파일명엔 없음). **로더·에이전트 설계 시 `kpi_name`은 읽지 않고 `kpi_key`만 사용**한다. 근거: `kpi_key`↔`kpi_name` 1:1(71개)이라 정보 손실 없음 / 채점 `key_metrics`도 `kpi_key` 이름 기준 / `kpi_name`은 오류 있음(`node_filesystem_free_bytes`↔`size_bytes` 설명 뒤바뀜, `{{device}}` 템플릿 미치환). 의미가 모호한 키(`leader_primary`, `witness_count` 등) 해석이 실제 문제가 되면 그때 영어 설명 dict 추가

## 구성 파일 (`aiopschallenge2025/`)

| 파일 | 내용 |
|---|---|
| `input.json` | 400건 장애의 시작·종료 시각. 에이전트 입력. `[{"Anomaly Description": "<자연어 문장>", "uuid"}]` — 문장 표현은 매번 다르지만 ISO UTC 시각(`\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ`)이 정확히 2개씩 있음 → 정규식 추출. groundtruth 시각·uuid와 400건 전부 일치 |
| `groundtruth.jsonl` | 400건 정답 (원인, 장애 위치, 지속 시간, 핵심 근거) |
| `2025-MM-DD/` | 날짜별 원시 데이터 (아래 구조) |
| `*.tar.gz`, `checksums.md5` | 날짜별 압축 원본 + MD5 (`md5sum -c checksums.md5`) |

로컬 보유 날짜: 18일치, 06-06 ~ 06-29 (06-15·16, 06-22·23, 06-25·26 없음).

## 대상 시스템

- hipstershop (Google Online Boutique) 마이크로서비스, Kubernetes 위에서 동작. 네임스페이스 `hipstershop`
- 서비스 11개: adservice, cartservice, checkoutservice, currencyservice, emailservice, frontend, paymentservice, productcatalogservice, recommendationservice, redis-cart, shippingservice
- pod명 `<service>-<N>` (보통 0~2). service = pod명에서 `-N` 제거
- 노드: `aiops-k8s-01` ~ `aiops-k8s-08`, `k8s-master*` (infra_node 기준 11대)
- DB: TiDB(SQL 계층) / TiKV(저장) / PD(클러스터 관리), 네임스페이스 `tidb`

## Raw data 구조 (2025-06-06 기준)

parquet 읽기: `pyarrow` 사용. 대용량이므로 `ParquetFile(...).metadata` / `iter_batches(batch_size=n)` / `columns=[...]`로 필요한 부분만 읽을 것.

### 하루 규모

| 종류 | 경로 | 파일 단위 | 파일 수 | 용량 | 행 수 |
|---|---|---|---|---|---|
| log | `log-parquet/log_filebeat-server_YYYY-MM-DD_HH-00-00.parquet` | 1시간 | 24 | 211 MB | ~15.7만 / 시간 |
| trace | `trace-parquet/trace_jaeger-span_YYYY-MM-DD_HH-00-00.parquet` | 1시간 | 24 | 501 MB | ~16.3만 span / 시간 |
| metric | `metric-parquet/{apm,infra,other}/` | 1일, 지표 1개 = 파일 1개 | 113 | ~2 MB | 1,439 ~ 4.4만 / 파일 |

파일명 시각은 CST, 데이터 내부 시각은 UTC (아래 "시간대 주의").

### log (filebeat)

| 컬럼 | 예시 |
|---|---|
| `@timestamp` | `2025-06-05T16:00:29.045Z` (UTC) |
| `k8_namespace` | `hipstershop` |
| `k8_pod` | `cartservice-1` |
| `k8_node_name` | `aiops-k8s-08` |
| `agent_name` | `filebeat-filebeat-htfz4` (수집기, 분석엔 불필요) |
| `message` | 로그 본문 |

- `message` 형식이 서비스마다 다름: cartservice 평문(`Request starting HTTP/2 POST .../GetCart`), frontend JSON(`http.req.path`, `http.resp.status`, `http.resp.took_ms`, `severity`), currencyservice 별도 JSON(`severity`, `message`, `hostname`) → 서비스별 파싱 또는 키워드 검색 필요
- 행이 시간순 정렬 아님 — 원본 자체가 비정렬. 1시간 파일 안에서 최대 ~60분(중앙값 ~20분) 뒤섞임 → 반드시 `@timestamp`로 필터 후 정렬 (trace는 30초 이내, metric은 완전 정렬)

### trace (jaeger)

한 행 = span 하나. 중첩 컬럼(list/struct) 포함.

| 컬럼 | 내용 |
|---|---|
| `traceID` / `spanID` | 요청 전체 ID / 구간 ID |
| `references` | `[{refType: CHILD_OF, spanID, traceID}]` 부모 span → 호출 트리 복원 |
| `operationName` | `hipstershop.ProductCatalogService/GetProduct` |
| `startTime` / `startTimeMillis` | μs / ms Unix 시간 |
| `duration` | **μs** (14,346 = 14ms) |
| `tags` | `[{key,type,value}]`: `rpc.service`, `rpc.method`, `net.peer.ip`(호출 대상), `net.peer.port`, `status.code`(0=정상), `status.message`, `span.kind`(client/server) |
| `process` | `serviceName`(예: frontend) + tags: `name`(pod명), `node_name`, `ip`, `namespace` |
| `logs` | span 내 이벤트 (gRPC 메시지 SENT/RECEIVED 등) |
| `flags` | 1.0 (분석엔 불필요) |

- 호출 방향: 호출하는 쪽 `process.serviceName` → 호출받는 쪽 `tags.rpc.service` (네트워크 장애 source→destination 특정에 사용)
- 실패: `status.code != 0`
- span마다 pod·node가 바로 나옴

### metric (a) apm — 넓은 형식

- 파일 1개 = 대상 1개, 1분 1행, 1,439행
- `apm/pod/pod_<pod>_DATE` (30개, 일부 pod 파일 없음 — 예: checkoutservice는 `-2`만), `apm/service/service_<svc>_DATE` (11개), `apm/pod_ns_hipstershop_DATE` (1개)
- 컬럼: `time`, `request`, `response`, `rrt`(평균 응답시간), `rrt_max`, `error`, `error_ratio`, `client_error(_ratio)`, `server_error(_ratio)`, `timeout`, `object_id`(pod명/서비스명/`hipstershop`), `object_type`(`pod`/`service`/`pod_ns`)
- 집계 계층: `pod_ns` ⊇ `service` ⊇ `pod`
  - `pod_ns`의 request·error = 서비스 11개 합 (request 1356/1439행, error 1432/1439행 정확히 일치. 나머지는 집계 시점 차이로 추정)
  - `pod_ns`의 rrt = 서비스 rrt의 request 가중평균 (단순평균 아님)
  - pod 합이 서비스 합보다 수십 건 큼 — 원인 미확인
- RCA 활용: pod_ns로 이상 시점 → service로 서비스 특정 → pod로 인스턴스 특정

### metric (b) infra / other — 긴 형식

- 파일 1개 = 지표 1개, 대상(pod/node 등)은 행으로 쌓임. 14개 공통 컬럼:

| 컬럼 | 설명 |
|---|---|
| `time` | 분 단위, UTC |
| `kpi_key` | 지표명 = **값이 든 컬럼명** (예: `pod_cpu_usage`, `node_cpu_usage_rate`, `qps`, `store_size`) |
| `kpi_name` | 중국어 설명 (`CPU使用率`, `请求数量`, `已用存储容量`) — **사용 금지**, 핵심 이슈 16 참고 |
| `object_type` | `pod` / `node` / `tidb` / `tikv` 등 |
| `instance` | pod 지표: **노드명** / node 지표: IP / tidb·tikv: `IP:port` |
| `kubernetes_node` | 노드명 (node 지표에서만 채워짐) |
| `pod`, `namespace` | 대상 pod, 네임스페이스 |
| `type` | 하위 구분 (예: tidb qps의 `Begin`/`Use`/`Commit`) |
| `cf`, `device`, `mountpoint`, `sql_type` | 일부 지표에서만 사용, 대부분 null |

| 대표 파일 | 행 수 | 구성 |
|---|---|---|
| `infra/infra_pod/infra_pod_pod_cpu_usage` | 44,486 | pod ~31개 × 1,439분 |
| `infra/infra_node/infra_node_node_cpu_usage_rate` | 15,829 | 노드 11대 × 1,439분 |
| `infra/infra_tidb/infra_tidb_qps` | 12,951 | SQL `type`별 |
| `other/infra_tikv_store_size` | 1,439 | TiKV 1개 |

- 여러 파일을 합칠 때 `kpi_key` 이름의 값 컬럼을 공통 이름(예: `value`)으로 바꿀 것
- 노드명이 pod 지표에선 `instance`, node 지표에선 `kubernetes_node` — 합칠 때 맞춰야 함

### 공통 조인 키

| 키 | log | trace | apm | infra |
|---|---|---|---|---|
| 시간 | `@timestamp` (UTC ISO) | `startTimeMillis` (ms) | `time` (UTC, 분) | `time` (UTC, 분) |
| pod | `k8_pod` | `process.tags.name` | `object_id` | `pod` |
| node | `k8_node_name` | `process.tags.node_name` | – | `instance` / `kubernetes_node` |
| service | pod명에서 `-N` 제거 | `process.serviceName` | `object_id` | pod명에서 `-N` 제거 |

## 전체 날짜 특이사항 (18일 메타데이터 스캔)

### log / trace 시간대 파일 누락 (CST 시)

| 날짜 | log 누락 | trace 누락 |
|---|---|---|
| 06-08 | 20, 23 | 21–23 |
| 06-09 | 20–23 | 0–5, 19–23 |
| 06-10 | 0 | 0–4 |
| 06-12 | 20–23 | 20–23 |
| 06-13 | 19–23 | 0, 20–23 |
| 06-14 | – | 0, 23 |
| 06-17 | 4–9 | 0, 4–9 |
| 06-18 | – | 20–23 |
| 06-19 | – | 0 |

나머지 9일은 24개 완비. metric은 일 단위 파일이라 파일 누락 없음.

### log / trace 파일 내부 분 단위 공백

파일이 있어도 해당 1시간 중 행이 없는 분이 있음 (log 410개·trace 390개 파일 시간 컬럼 전수 확인). 자기 시간대 밖 시각의 행은 0건 — 파일은 시간 경계로 정확히 나뉨.

- log: 2개 파일만 — `06-12 19시` 42–59분, `06-19 18시` 29분
- trace: 149개 파일, 총 481분
  - **매시 `:00`분 공백** (~120개 파일): 이전 시간 파일로 넘어간 것도 아님. 수집·export 단계 현상으로 추정, 영향 작음
  - **큰 공백**: 06-13 19시 13–59, 06-17 03시 12–59, 06-14 22시 19–59, 06-18 19시 43–59, 06-12 19시 42–59 (뒷부분 잘림 — 대개 다음 시간 파일도 없음, 수집 중단 추정) / 06-09 06시, 06-10 05시, 06-17 10시, 06-18 14–15시 (분 단위 듬성듬성 — 06-09·06-10은 파일 통째 누락 직후, 수집 재개 시점 추정) / 06-08 20시 58–59, 06-09 18시 55–59

### 장애 구간 데이터 커버리지 (파일 누락 + 내부 공백 합산)

| | 데이터 전혀 없음 | 일부만 있음 |
|---|---|---|
| log | 21건 | 0건 |
| trace | 40건 | 7건 (예: `d0be3c58-178` 3/19분, `757fa56f-263` 2/24분, `c0cdda5e-314` 2/11분) |

→ "trace에 에러 없음"이 정상 의미가 아니라 데이터 부재일 수 있음. 에이전트는 장애 구간마다 소스별 커버리지를 먼저 확인하고 추론에 반영할 것.

### 기타

- CST 자정을 넘는 장애 0건 → 장애 1건 = 날짜 폴더 1개
- 날짜별 장애 21~24건 (06-06 ~ 06-28). **06-29는 장애 0건**인데 데이터가 가장 큼 (log 10M행, trace 9.9M span), redis-cart apm service 파일 없음, apm pod 20개뿐
- apm pod 파일 수 날짜별 20~31개. 일부 pod는 일부 날짜에만 있음 (checkoutservice-1 7일, recommendationservice-0 11일) → apm pod 데이터 부재 처리 필요
- `cartservice-2 (deleted)`, `productcatalogservice-1 (deleted)`, `productcatalogservice-2 (deleted)` 이름의 apm pod 파일이 각 1일씩 존재 (pod 재생성 흔적으로 추정). 파일명에서 pod명 파싱 시 주의
- infra_tidb `slow_query` 지표는 10일에만 존재 (파일 13~14개)
- 스키마: log·apm·infra는 18일 동일. trace는 2개 파일(06-18, 06-27)에서 `flags` 컬럼 순서만 다름 — 컬럼명으로 읽으면 무관

### 미확인

- apm `rrt` 단위 — trace `duration`이 μs이고 값 크기(~11,000)로 보아 μs 추정
- apm pod 합 > 서비스 합인 이유
- metric 파일 내부의 분 단위 결측 (apm 파일이 하루 1,440분인데 1,439행 — 어느 분이 빠지는지 미확인)

## groundtruth 필드

- **장애 위치**: `instance_type`(pod / service / node), `service`, `instance`. 네트워크 장애는 `source` → `destination`
- **장애 종류**: `fault_category`(대분류), `fault_type`(세부)
- **시간**: `start_time`, `end_time` (지속 시간 = 차이)
- **근거**: `key_observations` — log / metric / trace별 핵심 지표
- **채점용** (에이전트 출력의 `reason` 필드 채점):
  - `key_metrics` — 키워드 채점, 해당 키워드 포함 시 정답 (Track 1)
  - `fault_description` — 의미 유사도 채점, 최고 유사도 사용
- 중점 필드: `fault_type`, `instance_type`, `instance`, `start_time`, `end_time`, `key_observations`
- **`instance`는 문자열 또는 리스트** (리스트 179건: 길이 2 122건, 1 51건, 3 6건)
  - 네트워크 장애(73건): `[source, destination]` (예: `['checkoutservice', 'shippingservice']`)
  - pod 레벨 장애(pod failure, io fault, memory stress, jvm 계열 등): 여러 pod 동시 장애
- `instance_type` 분포: service 195 / pod 123 / node 82
- 장애 지속 시간: 최소 1초, 중앙값 16분, 최대 25분

### 실제 라벨 값 (README 표와 다름 — 출력은 이 값 기준)

`fault_type` 18종, 공백 구분 소문자:

| fault_type | 건수 | fault_type | 건수 |
|---|---|---|---|
| pod failure | 45 | dns error | 21 |
| node memory stress | 38 | memory stress | 20 |
| io fault | 28 | target port misconfig | 18 |
| network corrupt | 27 | pod kill | 15 |
| network delay | 25 | jvm latency | 15 |
| node cpu stress | 23 | jvm gc | 14 |
| cpu stress | 22 | jvm cpu | 13 |
| node disk fill | 21 | jvm exception | 13 |
| network loss | 21 | code error | 21 |

README 표와의 차이: `node_cpu`→`node cpu stress`, `node_disk`→`node disk fill`, `erroneous-code`→`code error`, `jvm-cpu-stress`→`jvm cpu`. `node memory stress`는 README 표에 없음. `node_network_loss/delay`는 실제 라벨에 없음.

`fault_category` 9종: node fault 82, network attack 73, pod fault 60, jvm fault 55, stress test 42, io fault 28, erroneous change 21, dns fault 21, misconfiguration 18.

## 장애 유형 (README 표 기준 — 실제 라벨은 위 "실제 라벨 값" 참고)

| 레벨 | 유형 | 주로 드러나는 신호 |
|---|---|---|
| SERVICE | network_delay / network_loss / network_corrupt | 메트릭, 트레이스 |
| POD·SERVICE | cpu_stress, memory_stress | 메트릭 |
| POD·SERVICE | pod_failure, pod_kill, dns-error | 메트릭, 트레이스, 로그 |
| POD·SERVICE | jvm-exception / jvm-gc / jvm-latency / jvm-cpu-stress | 메트릭, 로그 |
| NODE | node_cpu, node_disk, node_network_loss, node_network_delay | 메트릭 |
| SERVICE | target_port_misconfig, erroneous-code | 메트릭, 트레이스, 로그 |
| POD | io-fault | 메트릭, 로그 |

같은 유형이 POD·SERVICE 양쪽에 존재 → 유형뿐 아니라 영향 범위(파드 하나 vs 서비스 전체)도 구분해야 함.

## 시간대 주의

| 위치 | 형식 | 시간대 |
|---|---|---|
| 파일명 | `..._2025-06-06_00-00-00.parquet` | **CST (UTC+8)** |
| 로그 | `2025-06-05T16:00:29.045Z` | UTC |
| 메트릭 | `2025-06-05T16:00:00Z` | UTC |
| 트레이스 `startTimeMillis` | `1749139200377` | Unix ms |

파일명과 데이터 내부 시각은 **8시간** 차이. 장애 구간에 맞는 파일을 고를 때 변환 필요. 짧은 장애가 있으므로 `end_time` 이후 일정 구간도 볼 것.

## RCA 에이전트 설계 시사점

- 출력은 groundtruth 형식을 따름: 장애 위치(`instance_type`/`instance`), `fault_type`, `reason`
- `reason`은 키워드 + 의미 유사도로 채점 → `key_metrics`에 해당하는 지표명을 명시적으로 쓰는 게 유리
- 유형별로 드러나는 신호가 다름 (NODE·CPU/메모리 → 메트릭만, JVM → 메트릭+로그) → 후보 유형에 따라 조회할 소스 선택
- CST↔UTC 변환 유틸은 하나로 통일
- 데이터 로더: 시간대 변환 → 시각 필터·정렬 → 소스별 커버리지 계산 → 집계·요약 후 LLM 전달
- 출력 라벨·instance 형식은 groundtruth 실제 값 기준 (README 표 아님)
- 장애 구간 판단에 데이터 부재를 명시적으로 반영

## 라이선스

CC BY-NC 4.0 (Dan Pei). 비상업적 용도만, 출처 표시 필요.
