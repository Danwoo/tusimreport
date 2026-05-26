"""LLM 호출 비용/토큰 카운트 헬퍼.

목적: "한 번의 분석이 LLM 토큰 몇 개를 쓰는가?"라는 시니어 질문에 답할
수 있도록 호출 단위 비용을 가시화한다. 토큰 단가는 빠르게 변하니 한
곳에서 관리.

설계:
- `count_tokens(text, model)` — tiktoken으로 정확 카운트. tiktoken은 OpenAI
  토크나이저라 Gemini에는 근사값이지만, 같은 텍스트에 일관된 결과를 주므로
  '추세'를 보는 용도로는 충분.
- `estimate_cost_usd(prompt_tokens, completion_tokens, model)` — 단가표로
  USD 비용 계산. 표는 2025년 11월 기준이며 갱신 책임은 호출자에게 명시.
- `track_llm_call(...)` — 위 두 헬퍼를 묶어 로그 라인 한 줄을
  `[s=<sid> c=<symbol>] llm_call model=... in_tok=N out_tok=N cost_usd=...`
  형태로 남긴다. 별도 메트릭 백엔드 없이도 grep으로 일/주 단위 집계 가능.

미래 작업:
- Prometheus exporter / OpenTelemetry trace는 별도 PR. 지금은 로그가
  유일한 시그널.
- 동시 호출 누적 카운트가 필요해지면 contextvars 기반 카운터 추가.
"""

from __future__ import annotations

import logging
from typing import Final

logger = logging.getLogger(__name__)


# 1K 토큰당 USD 단가. 2025년 11월 기준 공개가.
# 모델 이름은 build_llm이 반환하는 model_name 그대로 사용.
# 미등록 모델은 fallback 단가 적용 + 경고.
_PRICING_PER_1K_TOKENS_USD: Final[dict[str, dict[str, float]]] = {
    # OpenAI
    "gpt-4.1-nano": {"input": 0.0001, "output": 0.0004},
    "gpt-4o": {"input": 0.0025, "output": 0.01},
    "gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
    # Google
    "gemini-2.0-flash-lite": {"input": 0.000075, "output": 0.0003},
    "gemini-2.0-flash": {"input": 0.00015, "output": 0.0006},
}

_FALLBACK_PRICING: Final[dict[str, float]] = {"input": 0.001, "output": 0.003}


def count_tokens(text: str, model: str = "gpt-4o-mini") -> int:
    """tiktoken으로 정확한 토큰 수 계산. tiktoken 미설치/미지원 모델이면
    문자열 길이 / 4 휴리스틱으로 근사 (영문 기준, 한글은 약간 과소평가).
    """
    try:
        import tiktoken

        try:
            enc = tiktoken.encoding_for_model(model)
        except KeyError:
            enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except Exception:  # tiktoken 자체가 import 실패
        return max(1, len(text) // 4)


def estimate_cost_usd(prompt_tokens: int, completion_tokens: int, model: str) -> float:
    """`model`의 등록 단가로 USD 비용 산출.

    Args:
        prompt_tokens: 입력 토큰 수 (count_tokens 또는 LLM 응답 metadata).
        completion_tokens: 출력 토큰 수.
        model: build_llm이 반환한 model_name.

    Returns:
        USD float. 미등록 모델이면 _FALLBACK_PRICING으로 계산 (warning 로그).
    """
    pricing = _PRICING_PER_1K_TOKENS_USD.get(model)
    if pricing is None:
        logger.warning(
            "cost.estimate_cost_usd: unknown model %r — using fallback pricing %r",
            model,
            _FALLBACK_PRICING,
        )
        pricing = _FALLBACK_PRICING

    return prompt_tokens / 1000 * pricing["input"] + completion_tokens / 1000 * pricing["output"]


def track_llm_call(
    *,
    model: str,
    prompt: str,
    response: str,
    agent: str | None = None,
) -> dict[str, float | int | str]:
    """한 번의 LLM 호출 비용을 계산하고 구조화된 로그를 남긴다.

    호출 패턴:

        result = llm.invoke(prompt)
        track_llm_call(
            model=model_name,
            prompt=prompt,
            response=result.content,
            agent="sentiment_expert",
        )

    Returns:
        dict 형태 {prompt_tokens, completion_tokens, cost_usd, model, agent} —
        호출자가 결과 dict에 attach하고 싶을 때 사용.
    """
    pt = count_tokens(prompt, model)
    ct = count_tokens(response, model)
    cost = estimate_cost_usd(pt, ct, model)

    logger.info(
        "llm_call agent=%s model=%s in_tok=%d out_tok=%d cost_usd=%.6f",
        agent or "-",
        model,
        pt,
        ct,
        cost,
    )

    return {
        "prompt_tokens": pt,
        "completion_tokens": ct,
        "cost_usd": cost,
        "model": model,
        "agent": agent or "",
    }
