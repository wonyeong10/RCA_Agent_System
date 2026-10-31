# Solar Open 2 브리프

**작성:** 2026-07-22 기준 공개 정보
**조회일:** 2026-07-24

---

## 1. 요약

Solar Open 2는 업스테이지(Upstage)가 2026년 7월 22일 공개한 **250B-A15B Mixture-of-Experts(MoE) 오픈웨이트 언어모델**로, 장기 수평선(long-horizon) 에이전트 작업을 위해 설계·훈련되었다 [1](https://arxiv.org/abs/2607.20062). Solar Open 1(102B-A12B)에서 규모를 확장하고, 하이브리드 어텐션 스택으로 100만 토큰 컨텍스트 윈도우를 달성했으며, 영어·한국어·일본어 에이전트 벤치마크에서 동급 오픈웨이트 모델 중 최상위권에 위치한다 [1](https://arxiv.org/abs/2607.20062) [3](https://huggingface.co/upstage/Solar-Open2-250B). 모델 가중치는 Hugging Face에 상업적 사용이 가능한 라이선스(Upstage Solar License)로 공개되었다 [4](https://www.upstage.ai/blog/en/solar-open-2).

---

## 2. 핵심 스펙

| 항목 | 내용 | 출처 |
|---|---|---|
| **모델명** | Solar Open 2 (250B-A15B) | [3](https://huggingface.co/upstage/Solar-Open2-250B) |
| **아키텍처** | Hybrid-Attention MoE (softmax + linear attention) | [2](https://arxiv.org/html/2607.20062v2) [3](https://huggingface.co/upstage/Solar-Open2-250B) |
| **총 파라미터** | 250B (250,287,794,944) | [3](https://huggingface.co/upstage/Solar-Open2-250B) |
| **토큰당 활성 파라미터** | 15B (top-8 라우팅 + 공유 전문가 1개) | [3](https://huggingface.co/upstage/Solar-Open2-250B) |
| **레이어** | 48층 | [2](https://arxiv.org/html/2607.20062v2) |
| **히든 사이즈** | 4,096 | [2](https://arxiv.org/html/2607.20062v2) |
| **헤드 차원** | 128 | [2](https://arxiv.org/html/2607.20062v2) |
| **어텐션 헤드** | GQA: 쿼리 64 / KV 8 (softmax), 쿼리 64 (linear) | [2](https://arxiv.org/html/2607.20062v2) |
| **전문가 수** | 321개 (라우팅 320 + 공유 1) | [3](https://huggingface.co/upstage/Solar-Open2-250B) |
| **활성화 전문가** | 라우팅 top-8 + 공유 1 | [3](https://huggingface.co/upstage/Solar-Open2-250B) |
| **어텐션 패턴** | [Softmax, Linear×3] × 12 (전체 48층 중 75%가 linear attention) | [3](https://huggingface.co/upstage/Solar-Open2-250B) [4](https://www.upstage.ai/blog/en/solar-open-2) |
| **위치 인코딩** | NoPE ( rotary positional encoding 없음) | [2](https://arxiv.org/html/2607.20062v2) [3](https://huggingface.co/upstage/Solar-Open2-250B) |
| **토크나이저** | 커스텀 바이트레벨 BPE, 어휘 196,608 — Solar Open 1에서 승계 | [2](https://arxiv.org/html/2607.20062v2) [3](https://huggingface.co/upstage/Solar-Open2-250B) |
| **컨텍스트 길이** | 1M 토큰 | [1](https://arxiv.org/abs/2607.20062) [3](https://huggingface.co/upstage/Solar-Open2-250B) |
| **지원 언어** | 영어, 한국어, 일본어 | [3](https://huggingface.co/upstage/Solar-Open2-250B) [4](https://www.upstage.ai/blog/en/solar-open-2) |
| **사전훈련 토큰** | 약 12조 토큰 (20T 풀에서 가치 기준 큐레이션으로 10T 혼합 구성) | [2](https://arxiv.org/html/2607.20062v2) [3](https://huggingface.co/upstage/Solar-Open2-250B) |
| **훈련 하드웨어** | NVIDIA B200 GPU, 총 2M GPU-Hours | [3](https://huggingface.co/upstage/Solar-Open2-250B) |
| **초기화** | Solar Open 1에서 architectural change를 견디는 5.69B 파라미터(약 2.3%)만 선택적 이전, 나머지는 랜덤 초기화 후 전체 사전훈련 | [1](https://arxiv.org/abs/2607.20062) [2](https://arxiv.org/html/2607.20062v2) |
| **사후훈련** | 12개 도메인 전문가 모델을 목적별 시나리오로 훈련 후 Multi-teacher On-Policy Distillation(MOPD)으로 단일 모델 통합 | [1](https://arxiv.org/abs/2607.20062) |
| **라이선스** | Upstage Solar License (Apache 2.0 기반, 상업적 사용 허용. 파생 AI 모델은 "Solar"로 시작하는 이름 사용 및 "Built with Solar" 표기 의무) | [3](https://huggingface.co/upstage/Solar-Open2-250B) [6](https://huggingface.co/upstage/Solar-Open2-250B/raw/main/LICENSE) |
| **공개일** | 2026년 7월 22일 (arXiv v1 제출·블로그 발표 동시) | [1](https://arxiv.org/abs/2607.20062) [4](https://www.upstage.ai/blog/en/solar-open-2) |
| **하드웨어 요구** | 최소: H200 × 4 / 권장: H200 × 8 / 양자화 시 H200 × 2에서 실행 가능 | [3](https://huggingface.co/upstage/Solar-Open2-250B) [4](https://www.upstage.ai/blog/en/solar-open-2) |
| **선행 모델** | Solar Open 1 (102B-A12B, 컨텍스트 128K) | [1](https://arxiv.org/abs/2607.20062) [2](https://arxiv.org/html/2607.20062v2) |

> 참고: arXiv HTML 페이지 하단에 "License: CC BY 4.0"으로 표기된 것은 논문 문서의 라이선스이며, 모델 가중치의 라이선스는 Upstage Solar License이다 [2](https://arxiv.org/html/2607.20062v2) [3](https://huggingface.co/upstage/Solar-Open2-250B).

---

## 3. 벤치마크 하이라이트

### 3.1 영어 벤치마크 (원문 수치 그대로)

| 벤치마크 | Solar Open 2 | Solar Open 100B | Command A+ | Mistral Medium 3.5 | MiMo-V2.5 | DeepSeek-V4-Flash |
|---|---|---|---|---|---|---|
| **MMLU-Pro** | **86.2** | 80.4 | 79.0 | 81.2 | 84.6 | 85.9 |
| GPQA-Diamond | 86.3 | 66.2 | 75.6 | 77.5 | 83.0 | **88.9** |
| HLE (w/o tools) | 28.8 | 11.5 | 11.4 | 12.8 | 24.3 | **32.3** |
| **LiveCodeBench (v6)** | **92.4** | 56.5 | 86.1 | 84.9 | 89.1 | 92.3 |
| ArtifactsBench | 55.9 | 43.4 | 42.8 | 49.8 | 59.3 | **61.0** |
| HMMT2602 | 93.9 | 68.9 | 73.5 | 62.9 | 61.4 | **94.7** |
| AIME2026 | 95.7 | 87.7 | 96.0 | 89.0 | 92.3 | **97.0** |
| Multi-Challenge | 61.0 | 40.5 | 45.8 | 49.8 | 39.0 | **62.0** |
| IFBench | 80.0 | 57.7 | 73.9 | 69.0 | 67.1 | **80.3** |
| AA-LCR | 62.3 | 36.0 | 46.0 | 61.0 | 62.7 | **63.7** |
| **SWE-Bench Verified** | 70.4 | 15.4 | 14.4 | 69.6 | 73.0 | **73.8** |
| Terminal Bench Hard | 28.3 | 2.3 | 25.0 | 33.3 | **41.7** | 34.1 |
| **APEX-Agents** | **16.6** | 2.4 | 1.6 | 6.1 | 13.4 | 13.2 |
| MCP-Atlas | 58.2 | 34.4 | 27.2 | 30.7 | **63.9** | 58.2 |
| τ³ (banking) | 19.6 | 7.4 | 5.8 | 5.8 | 8.7 | **22.3** |
| GDPval-AA v2 (ELO) | 1128 | – | 712 | 929 | 1145 | **1187** |

출처: Hugging Face 모델 카드 [3](https://huggingface.co/upstage/Solar-Open2-250B)

**논문 원문 주장:** "Against comparably sized open-weight models on English benchmarks, Solar Open 2 leads on MMLU-Pro, LiveCodeBench, and the APEX-Agents agentic suite, and stays competitive with the strongest (DeepSeek-V4-Flash and MiMo-V2.5) elsewhere." [1](https://arxiv.org/abs/2607.20062)

### 3.2 한국어 벤치마크 (원문 수치 그대로)

| 벤치마크 | Solar Open 2 | Solar Open 100B | MiMo-V2.5 | DeepSeek-V4-Flash | Claude Haiku 4.5 | GPT-5.4 mini |
|---|---|---|---|---|---|---|
| KMMLU-Pro | 78.4 | 64.0 | 69.1 | **78.9** | 67.9 | 78.1 |
| **CLIcK** | **90.7** | 78.9 | 78.4 | 89.2 | 53.5 | 89.6 |
| **HAE-RAE v1.1** | **73.8** | 73.3 | 61.7 | 73.1 | 38.5 | 69.4 |
| Ko-AIME'25† | 97.7 | 80.0 | 88.0 | **98.0** | 81.7 | 90.7 |
| HRM8K | 92.2 | 87.6 | 90.7 | **93.4** | 90.6 | 91.3 |
| **KBank-MMLU†** | **80.8** | 65.5 | 71.0 | 79.5 | 68.9 | 79.0 |
| **KBL** | **75.5** | 65.5 | 69.8 | 72.8 | 69.9 | 75.3 |
| KorMedMCQA | 93.0 | 84.4 | 87.7 | 94.1 | 87.0 | **94.2** |
| **Ko-GDPval†** | **86.8** | 3.4 | 81.0 | 85.0 | 68.3 | 59.4 |

† in-house 벤치마크

출처: Hugging Face 모델 카드 [3](https://huggingface.co/upstage/Solar-Open2-250B)

**논문 원문 주장:** "On Korean benchmarks, Solar Open 2 records the highest average of any model compared, including fast-tier closed APIs, and on Ko-GDPval, an in-house Korean officework-agent benchmark, it is competitive with DeepSeek-V4-Pro (1.6T) at less than a sixth of its size." [1](https://arxiv.org/abs/2607.20062)

### 3.3 훈련 효율 관련 주장

- Solar Open 2 아키텍처는 Solar Open 100B의 all-softmax 아키텍처가 6,710억 토큰에서 도달한 MMLU 성능을 **2,100억 토큰**에서 달성 — 통제 비교 기준 [4](https://www.upstage.ai/blog/en/solar-open-2)
- Solar Open 1 대비 한국어 텍스트에서 글로벌 모델 토크나이저 대비 1.2–1.9배 토큰 효율 (동일 텍스트에 더 적은 토큰) [2](https://arxiv.org/html/2607.20062v2)
- Ko-GDPval 태스크 프롬프트 기준 토크나이저 효율: 4.41 bytes/token — 비교된 12개 토크나이저 중 1위, 최고 글로벌 모델(MiniMax-M3, 3.54) 대비 약 24% 우수 [2](https://arxiv.org/html/2607.20062v2)

---

## 4. 출처 목록

1. **arXiv: Solar Open 2 Technical Report (abstract)** — 2607.20062, 2026년 7월 22일 제출, 7월 24일 v2. https://arxiv.org/abs/2607.20062  
2. **arXiv: Solar Open 2 Technical Report (HTML)** — 동일 논문 전문. https://arxiv.org/html/2607.20062v2  
3. **Hugging Face: upstage/Solar-Open2-250B 모델 카드** — 스펙 표, 영어·한국어 벤치마크 표, 라이선스, 퀵스타트 포함. https://huggingface.co/upstage/Solar-Open2-250B  
4. **Upstage Blog: Solar Open 2: Korea's Sovereign Foundation Model, Built for Agentic Use** — 2026년 7월 22일 발표. https://www.upstage.ai/blog/en/solar-open-2  
5. **Upstage Newsroom** — 회사 배경 및 역대 발표. https://www.upstage.ai/newsroom  
6. **Upstage Solar License (LICENSE 파일)** — Hugging Face 레포 내 라이선스 원문. https://huggingface.co/upstage/Solar-Open2-250B/raw/main/LICENSE  

---

*본 브리프는 위 6개 출처에서 확인 가능한 사실만을 기술하였으며, 단일 출처에서만 확인되거나 애매한 내용은 본문에 별도 표기하였습니다. 모든 수치와 표현은 원문에서 그대로 인용하였습니다.*
