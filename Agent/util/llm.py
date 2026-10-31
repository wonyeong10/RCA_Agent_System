"""공용 LLM 래퍼: 모든 호출은 call()을 거치고, 호출마다 토큰·비용·실행 시간을 logs/llm_usage.jsonl에 append.

키는 루트 .env → Agent/.env 순으로 읽는다 (코드·로그에 키를 남기지 않음).
Upstage Responses API는 상태 저장 안 함 → history는 호출자가 매번 통째로 전달 (생각.txt 아이디어 2).
"""
import json
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOG = ROOT / "logs" / "llm_usage.jsonl"
BASE_URL = "https://api.upstage.ai/v1"

# USD / 1M 토큰 (VAT 별도). 출처: https://www.upstage.ai/pricing (2026-10-27 확인, 생각.txt 아이디어 2)
PRICES = {
    "solar-pro4": {"input": 0.30, "cached": 0.06, "output": 1.20},
    "solar-mini4": {"input": 0.10, "cached": 0.01, "output": 0.40},
}

_lock = threading.Lock()
_client = None


def _key():
    for p in (ROOT / ".env", ROOT / "Agent" / ".env"):
        if p.exists():
            for line in p.read_text(encoding="utf-8").splitlines():
                k, _, v = line.partition("=")
                if k.strip() == "UPSTAGE_API_KEY" and v.strip():
                    return v.strip().strip('"\'')
    if os.environ.get("UPSTAGE_API_KEY"):
        return os.environ["UPSTAGE_API_KEY"]
    raise RuntimeError("UPSTAGE_API_KEY가 없음: 루트 .env에 입력할 것")


def client():
    global _client
    if _client is None:
        from openai import OpenAI
        _client = OpenAI(base_url=BASE_URL, api_key=_key())
    return _client


def cost(model, input_tokens, cached_tokens, output_tokens):
    """모델명은 실제 버전(solar-pro4-260806)이어도 별칭 접두로 단가 조회. 표에 없으면 None."""
    p = next((v for k, v in PRICES.items() if model.startswith(k)), None)
    if p is None:
        return None
    return ((input_tokens - cached_tokens) * p["input"] + cached_tokens * p["cached"] + output_tokens * p["output"]) / 1e6


def _write(rec):
    LOG.parent.mkdir(exist_ok=True)
    with _lock, open(LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def call(purpose, **kwargs):
    """client.responses.create(**kwargs) 1회 + 기록. 반환 (response, record). 실패도 기록 후 예외 다시 던짐."""
    rec = {"ts": datetime.now(timezone.utc).isoformat(), "model": kwargs.get("model"), "purpose": purpose}
    t = time.perf_counter()
    try:
        r = client().responses.create(**kwargs)
    except Exception as e:
        rec.update(latency_sec=round(time.perf_counter() - t, 3), input_tokens=0, cached_tokens=0, output_tokens=0,
                   reasoning_tokens=0, cost_usd=0.0, error=repr(e)[:500])
        _write(rec)
        raise
    u = r.usage  # 토큰은 API usage 값 그대로 (추정 금지)
    cached = getattr(getattr(u, "input_tokens_details", None), "cached_tokens", 0) or 0
    reasoning = getattr(getattr(u, "output_tokens_details", None), "reasoning_tokens", 0) or 0
    rec.update(model=r.model, latency_sec=round(time.perf_counter() - t, 3), input_tokens=u.input_tokens,
               cached_tokens=cached, output_tokens=u.output_tokens, reasoning_tokens=reasoning,
               cost_usd=cost(r.model, u.input_tokens, cached, u.output_tokens))
    _write(rec)
    return r, rec


if __name__ == "__main__":  # API 호출 없는 비용 계산 점검
    assert abs(cost("solar-pro4-260806", 1_000_000, 0, 0) - 0.30) < 1e-12
    assert abs(cost("solar-pro4", 1_000_000, 500_000, 1_000_000) - (0.15 + 0.03 + 1.20)) < 1e-12
    assert abs(cost("solar-mini4-260922", 0, 0, 1_000_000) - 0.40) < 1e-12
    assert cost("gpt-x", 1, 0, 1) is None
    print("ok")
