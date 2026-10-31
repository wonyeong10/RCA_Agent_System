"""System card: 대상 시스템(hipstershop + TiDB)의 정적 구조. LLM 시스템 프롬프트 입력용.

보류 (2026-10-27): 아키텍처 설계 후 ablation으로 선택 도입. 실험 경과는 생각.txt 아이디어 1 참고.

dict를 그대로 json.dumps 해서 프롬프트에 넣는다. 시스템이 바뀌면 이 dict만 고친다.
calls ↔ called_by, store ↔ used_by는 양쪽에 다 적는다 → 수정 시 함께 고칠 것 (__main__ assert로 확인).
값은 모델이 읽을 문장으로 쓴다 (주석은 프롬프트에 안 들어감).
시스템 사실만 넣는다 (groundtruth·장애 유형 분포 유래 내용 금지).
pod 목록·pod→node 배치·커버리지는 케이스마다 다르므로 여기 없음 (reader가 케이스별로 생성).

출처 표기: [orig] = GoogleCloudPlatform/microservices-demo v0.10.7
          [data] = 2025-06-29 (장애 없는 날) 데이터로 확인
"""

NO_SERVER_SPAN = "no server-side spans: visible only via callers' client spans"

SYSTEM_CARD = {
    "notes": [
        "hipstershop (Online Boutique) microservices on Kubernetes, namespace 'hipstershop'. TiDB cluster in namespace 'tidb'.",
        "All service-to-service calls are synchronous gRPC. A fault in a callee propagates latency/errors up to every caller, "
        "so symptoms are loudest upstream (frontend) while the cause usually sits downstream.",
        "Pod name = '<service>-<N>' (usually 3 replicas, N=0..2). One abnormal replica suggests a pod-level fault; "
        "all replicas abnormal suggests a service-level fault (or a shared node/dependency).",
        "Network faults are per call edge (caller -> callee).",
        "A node fault affects every pod scheduled on that node at the same time.",
        "'observability' lists known data gaps: missing data there means not collected, not healthy.",
    ],
    # language: [orig]. calls: [orig], 06-29 trace 24시간 전수 client 간선(15개)과 정확히 일치 [data]
    "services": {
        "frontend": {
            "role": "HTTP web server, user-facing entry point; renders pages by calling backend services",
            "language": "Go",
            "calls": ["productcatalogservice", "currencyservice", "cartservice", "recommendationservice",
                      "shippingservice", "checkoutservice", "adservice"],
            "called_by": [],
        },
        "checkoutservice": {
            "role": "places orders: reads cart, prices items, charges payment, ships, sends confirmation email",
            "language": "Go",
            "calls": ["productcatalogservice", "shippingservice", "paymentservice", "emailservice",
                      "currencyservice", "cartservice"],
            "called_by": ["frontend"],
        },
        "recommendationservice": {
            "role": "recommends products based on cart contents",
            "language": "Python",
            "calls": ["productcatalogservice"],
            "called_by": ["frontend"],
        },
        "cartservice": {
            "role": "stores and retrieves user carts",
            "language": "C#",
            "calls": ["redis-cart"],
            "called_by": ["frontend", "checkoutservice"],
        },
        "productcatalogservice": {
            "role": "product list, product lookup and search",
            "language": "Go",
            "calls": [],
            "called_by": ["frontend", "checkoutservice", "recommendationservice"],
            # 강력 후보, 확정 아님 (원본은 JSON 파일을 읽음). 근거: 06-29 tidb duration_99th 64.9초 구간 2회에
            #   productcatalog 지연만 x2800 (frontend는 그 대기로 x380), 나머지 서비스 변화 없음.
            #   span 수 상관·요청량 규모는 판별력 없어 근거에서 제외. trace에 DB span 없음 (18일)
            "store": "tidb (strong candidate, not confirmed; SQL calls are not traced)",
            "observability": "almost no logs",  # [data] 06-29 하루 ~2천 줄 (다른 서비스 수만~수백만)
        },
        "currencyservice": {
            "role": "currency conversion",
            "language": "Node.js",
            "calls": [],
            "called_by": ["frontend", "checkoutservice"],
            "observability": NO_SERVER_SPAN,  # [data]
        },
        "paymentservice": {
            "role": "charges the credit card (mock)",
            "language": "Node.js",
            "calls": [],
            "called_by": ["checkoutservice"],
            "observability": NO_SERVER_SPAN,  # [data]
        },
        "shippingservice": {
            "role": "shipping cost quote and shipment (mock)",
            "language": "Go",
            "calls": [],
            "called_by": ["frontend", "checkoutservice"],
        },
        "emailservice": {
            "role": "sends order confirmation email (mock)",
            "language": "Python",
            "calls": [],
            "called_by": ["checkoutservice"],
        },
        "adservice": {
            "role": "serves text ads",
            "language": "Java (the only JVM service)",
            "calls": [],
            "called_by": ["frontend"],
            "observability": NO_SERVER_SPAN,  # [data]
        },
        "redis-cart": {
            "role": "Redis key-value store holding cart data (stateful)",
            "language": "Redis",
            "calls": [],
            "called_by": ["cartservice"],
            "observability": "almost no logs",  # [data] 06-29 하루 ~1.3천 줄
        },
    },
    # [data] 06-29 metric: 각 계층 인스턴스 1개, trace·log에 TiDB 흔적 없음
    "datastores": {
        "tidb": {"role": "SQL layer (stateless), 1 instance", "depends_on": ["tikv", "pd"],
                 "used_by": ["productcatalogservice"]},
        "tikv": {"role": "distributed KV storage engine, 1 store", "depends_on": ["pd"], "used_by": ["tidb"]},
        "pd": {"role": "placement driver: cluster metadata, region scheduling, timestamps; 1 member (tidb-pd-0)",
               "depends_on": [], "used_by": ["tidb", "tikv"]},
    },
    "datastore_notes": [
        "TiDB/TiKV/PD are observable only through infra metrics (no traces, no logs, not in pod-level metrics).",
        "A TiKV or PD fault surfaces first as TiDB latency/failed queries, then in the services that use TiDB.",
    ],
    "nodes": "worker nodes aiops-k8s-01..08, control-plane k8s-master1..3",
}


if __name__ == "__main__":
    import json

    svcs, stores = SYSTEM_CARD["services"], SYSTEM_CARD["datastores"]
    for s, v in svcs.items():
        for c in v["calls"]:
            assert s in svcs[c]["called_by"], f"{s}->{c}: {c}.called_by에 {s} 없음"
        for c in v["called_by"]:
            assert s in svcs[c]["calls"], f"{c}->{s}: {c}.calls에 {s} 없음"
    users = [s for s, v in svcs.items() if v.get("store", "").startswith("tidb")]
    assert users == stores["tidb"]["used_by"], "store ↔ tidb.used_by 불일치"
    for d, v in stores.items():
        for dep in v["depends_on"]:
            assert d in stores[dep]["used_by"], f"{d}->{dep}: {dep}.used_by에 {d} 없음"

    text = json.dumps(SYSTEM_CARD, ensure_ascii=False)
    print(json.dumps(SYSTEM_CARD, ensure_ascii=False, indent=1))
    print(f"\n[compact {len(text)} chars, ~{len(text) // 4} tokens]")
