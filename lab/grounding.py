"""보고서 숫자가 도구 결과에 실제로 있는지 대조하는 결정론적 평가.

LLM 판정자 없이 계산하는 환각 지표다. 보고서에서 숫자를 뽑아 도구가 돌려준 값과
단위·반올림을 맞춰 비교한다. 값만 비교하고 그 값의 의미는 보지 않는다.

- 보고서 안에서 계산해 낸 값(예: "고점 대비 15% 하락")은 도구 결과에 그대로 없으므로
  근거 없음으로 잡힌다.
- 다른 의미의 같은 숫자가 도구 결과에 있으면 근거 있음으로 잡힌다. 그래서 날짜·시각에서
  나온 숫자는 양쪽 모두에서 빼고, ×100 환산은 퍼센트 표기에만 허용한다.
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable, Iterator
from dataclasses import asdict, dataclass
from typing import Any

_UNIT_SCALE = {"조": 1e12, "억": 1e8, "만": 1e4}

_ISO_DATE = r"\d{4}[-./]\d{1,2}[-./]\d{1,2}"
_CLOCK = r"\d{1,2}:\d{2}(?::\d{2}(?:\.\d+)?)?"
_TZ = r"(?:Z|[+-]\d{2}:?\d{2})"
_MONTH = r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?"

# 숫자와 단위를 지우기 전에 날짜·시각·기간·순서 표현을 먼저 걷어낸다. 도구 결과의 문장에도 같게 적용한다.
_STRIP_PATTERNS = [
    re.compile(rf"{_ISO_DATE}(?:[T ]{_CLOCK}{_TZ}?)?"),  # 2026-10-25, 2026-10-25T09:00:00+09:00
    re.compile(rf"{_CLOCK}(?:\s*{_TZ})?"),  # 15:30
    re.compile(rf"\b(?:\d{{1,2}}\s+{_MONTH},?\s+\d{{4}}|{_MONTH}\s+\d{{1,2}},?\s+\d{{4}})"),  # 25 Oct 2026
    re.compile(r"\d{1,2}월\s*\d{1,2}일"),
    re.compile(r"\d{4}\s*년(?:\s*\d{1,2}\s*월)?"),
    # 52주 최고가. 주식 수('1,234,567주', '100만주')는 앞에 숫자·쉼표·단위가 붙어 걸리지 않는다.
    re.compile(r"(?<![\d,.])\d{1,2}\s*주(?![식당])"),
    re.compile(
        r"\d+\s*(?:분기|개월|주일|주간|거래일|영업일|일선|일간|일|년간|년|위|단계|가지|개|명|건|회|차|시간|분)"
    ),
    re.compile(r"[QH]\d"),
    re.compile(r"(?m)^\s*(?:#+\s*)?\d+[.)]\s"),  # 목록 번호
]
# A number may start right after 조/억 ('6조5,670억원') so compound amounts can be merged, but
# never inside another number or word ('5,670' must not yield '670').
_NUMBER = re.compile(
    r"(?:(?<=[조억])|(?<![\w.,]))(?P<num>-?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?)\s*(?P<unit>%p|%|조|억|만)?(?P<won>\s*원)?"
)
_SOURCE_NUMBER = re.compile(r"^\s*(-?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?)\s*(%|조|억|만)?\s*(?:원)?\s*$")

# Words that carry the sign in Korean prose ("3.52% 하락", "1,234억원 순매도"), so the number
# itself is written without a minus. Near one of these, the comparison ignores the sign.
_DIRECTION_WORDS = (
    "하락",
    "상승",
    "감소",
    "증가",
    "순매도",
    "순매수",
    "매도",
    "매수",
    "급등",
    "급락",
    "떨어",
    "올라",
    "올랐",
    "줄었",
    "줄어",
    "늘었",
    "늘어",
    "손실",
    "적자",
    "마이너스",
    "하회",
    "상회",
    "축소",
    "확대",
    "둔화",
    "약세",
    "강세",
    "▲",
    "▼",
)
_DIRECTION_WINDOW = 15

# Text our own code writes into tool outputs (formatted summaries, failure reasons). Its numbers
# are either copies of structured fields or labels ("24시간", "S&P 500"), not source data, and
# counting them would let an invented report number match by accident.
_GENERATED_TEXT_KEYS = frozenset({"summary", "reason", "note", "error", "message", "unavailable_data"})

# Keys whose values are dates or timestamps (last_updated, pub_date, rcept_dt, recorded_at, ...).
# camelCase keys are matched after splitting ("pubDate" -> "pub_date").
_TIMESTAMP_KEY = re.compile(r"(?:^|_)(?:date|dt|time|timestamp|datetime|updated)$|_at$")
_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_COMPACT_DATE = re.compile(r"^(?P<y>\d{4})(?P<m>\d{2})(?P<d>\d{2})(?:\d{4}(?:\d{2})?)?$")
# RFC 2822 as news feeds write it: 'Mon, 27 Oct 2026 09:00:00 +0900'. Matched against the whole string.
_RFC2822 = re.compile(
    rf"(?:[A-Z][a-z]{{2}},?\s*)?\d{{1,2}}\s+{_MONTH}\s+\d{{4}}(?:\s+{_CLOCK})?(?:\s*(?:[+-]\d{{4}}|GMT|UTC))?"
)


@dataclass
class NumberMention:
    raw: str
    value: float
    tolerance: float
    is_percent: bool
    context: str
    signless: bool = False


@dataclass
class _Number:
    raw: str
    value: float
    tolerance: float
    unit: str
    digits: str
    has_comma: bool
    has_decimal: bool
    won: bool
    start: int
    end: int


def _decimals(num: str) -> int:
    return len(num.split(".")[1]) if "." in num else 0


def _strip(text: str) -> str:
    for pattern in _STRIP_PATTERNS:
        text = pattern.sub(" ", text)
    return text


def _iter_numbers(text: str) -> Iterator[_Number]:
    """숫자와 단위를 차례로 돌려준다. '6조 5,670억원'처럼 큰 단위부터 이어 쓴 값은 하나로 합친다."""
    matches = list(_NUMBER.finditer(text))
    i = 0
    while i < len(matches):
        first = matches[i]
        num, unit = first.group("num"), first.group("unit") or ""
        scale = _UNIT_SCALE.get(unit, 1.0)
        negative = num.startswith("-")
        total = abs(float(num.replace(",", ""))) * scale
        tolerance = 0.5 * 10 ** (-_decimals(num)) * scale
        end, won = first.end(), bool(first.group("won"))
        j = i + 1
        while (
            unit in ("조", "억")
            and not won
            and "." not in num
            and j < len(matches)
            and not text[end : matches[j].start()].strip()
        ):
            nxt = matches[j]
            nxt_num, nxt_unit = nxt.group("num"), nxt.group("unit") or ""
            if (
                nxt_num.startswith("-")
                or _UNIT_SCALE.get(nxt_unit, 0.0) >= scale
                or nxt_unit not in _UNIT_SCALE
            ):
                break
            scale = _UNIT_SCALE[nxt_unit]
            total += float(nxt_num.replace(",", "")) * scale
            tolerance = 0.5 * 10 ** (-_decimals(nxt_num)) * scale
            end, won, unit, num = nxt.end(), bool(nxt.group("won")), nxt_unit, nxt_num
            j += 1
        first_num = first.group("num")
        yield _Number(
            raw=text[first.start() : end].strip(),
            value=-total if negative else total,
            tolerance=tolerance,
            unit=unit,
            digits=first_num.replace(",", "").lstrip("-"),
            has_comma="," in first_num,
            has_decimal="." in first_num,
            won=won,
            start=first.start(),
            end=end,
        )
        i = j


def _has_direction_word(text: str, start: int, end: int) -> bool:
    window = text[max(0, start - _DIRECTION_WINDOW) : end + _DIRECTION_WINDOW]
    return any(word in window for word in _DIRECTION_WORDS)


def extract_report_numbers(text: str, stock_code: str | None = None) -> list[NumberMention]:
    cleaned = _strip(text)

    mentions: list[NumberMention] = []
    for number in _iter_numbers(cleaned):
        digits = number.digits
        if stock_code and digits == stock_code:
            continue
        if len(digits) == 6 and digits.startswith("0") and "." not in digits:
            continue  # 다른 종목코드
        bare = not number.unit and not number.has_decimal
        if bare and abs(number.value) <= 10:
            continue  # 개수·순번
        if (
            bare
            and not number.has_comma
            and not number.won
            and len(digits) == 4
            and 1900 <= number.value <= 2100
        ):
            continue  # 연도. '2,050'이나 '2050원'은 값으로 본다
        mentions.append(
            NumberMention(
                raw=number.raw,
                value=number.value,
                tolerance=number.tolerance,
                is_percent=number.unit in ("%", "%p"),
                context=cleaned[max(0, number.start - 30) : number.end + 30].replace("\n", " ").strip(),
                signless=_has_direction_word(cleaned, number.start, number.end),
            )
        )
    return mentions


def _is_timestamp_key(key: Any) -> bool:
    if not isinstance(key, str):
        return False
    return bool(_TIMESTAMP_KEY.search(_CAMEL_BOUNDARY.sub("_", key).lower()))


def _is_timestamp_string(text: str) -> bool:
    """문자열 전체가 날짜·시각인가 (ISO, 20261027, RFC 2822 'Mon, 27 Oct 2026 09:00:00 +0900')."""
    value = text.strip()
    if re.fullmatch(rf"{_ISO_DATE}(?:[T ]{_CLOCK}\s*{_TZ}?)?", value):
        return True
    compact = _COMPACT_DATE.fullmatch(value)
    if compact:
        return (
            1900 <= int(compact["y"]) <= 2100
            and 1 <= int(compact["m"]) <= 12
            and 1 <= int(compact["d"]) <= 31
        )
    return bool(_RFC2822.fullmatch(value))


def collect_source_numbers(outputs: Iterable[Any]) -> list[float]:
    """도구 결과(dict/list/문자열)에 들어 있는 숫자를 모은다.

    코드가 만든 요약·사유 문구, 날짜·시각 키와 날짜 문자열, 문장 속 날짜·기간 표현은 뺀다.
    """
    values: list[float] = []

    def visit(node: Any) -> None:
        if isinstance(node, bool) or node is None:
            return
        if isinstance(node, int | float):
            if math.isfinite(float(node)):
                values.append(float(node))
        elif isinstance(node, str):
            if _is_timestamp_string(node):
                return
            match = _SOURCE_NUMBER.match(node)
            if match:
                values.append(
                    float(match.group(1).replace(",", "")) * _UNIT_SCALE.get(match.group(2) or "", 1.0)
                )
            else:
                values.extend(number.value for number in _iter_numbers(_strip(node)))
        elif isinstance(node, dict):
            for key, value in node.items():
                if key not in _GENERATED_TEXT_KEYS and not _is_timestamp_key(key):
                    visit(value)
        elif isinstance(node, list | tuple):
            for value in node:
                visit(value)

    for output in outputs:
        visit(output)
    return values


def _matches(mention: NumberMention, sources: list[float]) -> bool:
    target = abs(mention.value) if mention.signless else mention.value
    allowed = max(mention.tolerance, 0.005 * abs(target))
    for source in sources:
        candidates = (source, source * 100) if mention.is_percent else (source,)
        for candidate in candidates:
            value = abs(candidate) if mention.signless else candidate
            if abs(value - target) <= allowed:
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
