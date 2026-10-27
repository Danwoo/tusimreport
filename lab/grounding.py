"""보고서 숫자가 도구 결과에 실제로 있는지 대조하는 결정론적 평가.

LLM 판정자 없이 계산하는 환각 지표다. 보고서에서 숫자를 뽑아 도구가 돌려준 값과
단위·반올림을 맞춰 비교한다. 보고서 안에서 계산해 낸 값(예: "고점 대비 15% 하락")은
도구 결과에 그대로 없으므로 근거 없음으로 잡힌다. 그래서 이 비율은 보수적 하한이다.
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from typing import Any

_UNIT_SCALE = {"조": 1e12, "억": 1e8, "만": 1e4}

# 숫자와 단위를 지우기 전에 날짜·기간·순서 표현을 먼저 걷어낸다.
_STRIP_PATTERNS = [
    re.compile(r"\d{4}[-./]\d{1,2}[-./]\d{1,2}"),  # 2026-10-25
    re.compile(r"\d{1,2}월\s*\d{1,2}일"),
    re.compile(r"\d{4}\s*년(?:\s*\d{1,2}\s*월)?"),
    re.compile(
        r"\d+\s*(?:분기|개월|주일|주간|거래일|영업일|일선|일간|일|년간|년|위|단계|가지|개|명|건|회|차|시간|분)"
    ),
    re.compile(r"[QH]\d"),
    re.compile(r"(?m)^\s*(?:#+\s*)?\d+[.)]\s"),  # 목록 번호
]
_NUMBER = re.compile(
    r"(?<![\w.])(?P<num>-?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?)\s*(?P<unit>%p|%|조|억|만)?(?:\s*원)?"
)
_SOURCE_NUMBER = re.compile(r"^\s*(-?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?)\s*(%|조|억|만)?\s*(?:원)?\s*$")

# Text our own code writes into tool outputs (formatted summaries, failure reasons). Its numbers
# are either copies of structured fields or labels ("24시간", "S&P 500"), not source data, and
# counting them would let an invented report number match by accident.
_GENERATED_TEXT_KEYS = frozenset({"summary", "reason", "note", "error", "message", "unavailable_data"})


@dataclass
class NumberMention:
    raw: str
    value: float
    tolerance: float
    is_percent: bool
    context: str


def _decimals(num: str) -> int:
    return len(num.split(".")[1]) if "." in num else 0


def extract_report_numbers(text: str, stock_code: str | None = None) -> list[NumberMention]:
    cleaned = text
    for pattern in _STRIP_PATTERNS:
        cleaned = pattern.sub(" ", cleaned)

    mentions: list[NumberMention] = []
    for match in _NUMBER.finditer(cleaned):
        num, unit = match.group("num"), match.group("unit") or ""
        digits = num.replace(",", "").lstrip("-")
        if stock_code and digits == stock_code:
            continue
        if len(digits) == 6 and digits.startswith("0") and "." not in digits:
            continue  # 다른 종목코드
        value = float(num.replace(",", ""))
        if not unit and "." not in num and abs(value) <= 10:
            continue  # 개수·순번
        if not unit and "." not in num and 1900 <= value <= 2100:
            continue  # 연도
        scale = _UNIT_SCALE.get(unit, 1.0)
        tolerance = 0.5 * 10 ** (-_decimals(num)) * scale
        start, end = match.span()
        mentions.append(
            NumberMention(
                raw=match.group(0).strip(),
                value=value * scale,
                tolerance=tolerance,
                is_percent=unit in ("%", "%p"),
                context=cleaned[max(0, start - 30) : end + 30].replace("\n", " ").strip(),
            )
        )
    return mentions


def collect_source_numbers(outputs: Iterable[Any]) -> list[float]:
    """도구 결과(dict/list/문자열)에 들어 있는 숫자를 모은다. 코드가 만든 요약·사유 문구는 뺀다."""
    values: list[float] = []

    def visit(node: Any) -> None:
        if isinstance(node, bool) or node is None:
            return
        if isinstance(node, int | float):
            if math.isfinite(float(node)):
                values.append(float(node))
        elif isinstance(node, str):
            match = _SOURCE_NUMBER.match(node)
            if match:
                values.append(
                    float(match.group(1).replace(",", "")) * _UNIT_SCALE.get(match.group(2) or "", 1.0)
                )
            else:
                for inner in _NUMBER.finditer(node):
                    scale = _UNIT_SCALE.get(inner.group("unit") or "", 1.0)
                    values.append(float(inner.group("num").replace(",", "")) * scale)
        elif isinstance(node, dict):
            for key, value in node.items():
                if key not in _GENERATED_TEXT_KEYS:
                    visit(value)
        elif isinstance(node, list | tuple):
            for value in node:
                visit(value)

    for output in outputs:
        visit(output)
    return values


def _matches(mention: NumberMention, sources: list[float]) -> bool:
    target = mention.value
    allowed = max(mention.tolerance, 0.005 * abs(target))
    for source in sources:
        candidates = (source, source * 100) if mention.is_percent else (source, source * 100, source / 100)
        if any(abs(candidate - target) <= allowed for candidate in candidates):
            return True
    return False


@dataclass
class GroundingResult:
    checked: int
    grounded: int
    ratio: float | None
    ungrounded: list[dict[str, str]]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def numeric_grounding(
    report: str, tool_outputs: Iterable[Any], stock_code: str | None = None, max_examples: int = 20
) -> GroundingResult:
    mentions = extract_report_numbers(report or "", stock_code)
    sources = collect_source_numbers(tool_outputs)
    grounded = 0
    ungrounded: list[dict[str, str]] = []
    for mention in mentions:
        if _matches(mention, sources):
            grounded += 1
        elif len(ungrounded) < max_examples:
            ungrounded.append({"number": mention.raw, "context": mention.context})
    ratio = grounded / len(mentions) if mentions else None
    return GroundingResult(checked=len(mentions), grounded=grounded, ratio=ratio, ungrounded=ungrounded)
