"""Conservative numerical equivalence within cited US-equity source evidence."""

import re
from datetime import datetime, timezone
from decimal import Decimal

_NUMBER = re.compile(
    r"(?<![\w.])(?P<sign_before>[-−])?"
    r"(?P<currency>USD|EUR|GBP|JPY|CHF|CAD|AUD|CNY|HKD|SGD|INR|KRW|\$|€|£|¥)?\s*(?P<sign_after>[-−])?"
    r"(?P<value>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
    r"\s*(?P<scale>trillion|billion|million|thousand|bn|[kmbt])?"
    r"(?P<percent>\s*%|\s+percent\b)?",
    re.I,
)
_SCALES = {
    "k": 3,
    "thousand": 3,
    "m": 6,
    "million": 6,
    "b": 9,
    "bn": 9,
    "billion": 9,
    "t": 12,
    "trillion": 12,
}
_CURRENCIES = {"$": "USD", "€": "EUR", "£": "GBP"}
_QUARTER = re.compile(r"\b(?:Q([1-4])|(first|second|third|fourth)[ -]quarter|quarter\s+([1-4]))\b", re.I)
_FISCAL_YEAR = re.compile(r"\b(?:FY\s*|fiscal(?:\s+year)?\s+)(\d{4}|\d{2})\b", re.I)


def _quantities(text: str, *, source: bool = False) -> set[tuple[Decimal, str]]:
    quantities = set()

    # Timestamp fragments must not support unrelated financial quantities.
    def timestamp_value(match: re.Match) -> str:
        quantities.add((Decimal(0), "date:" + match[0][:10]))
        if "T" in match[0]:
            try:
                value = datetime.fromisoformat(match[0].replace("Z", "+00:00"))
                if value.tzinfo is not None:
                    value = value.astimezone(timezone.utc)
                quantities.add((Decimal(0), "time:" + value.isoformat()))
            except ValueError:
                quantities.add((Decimal(0), "invalid_time:" + match[0]))
        return " "

    text = re.sub(r"\b\d{4}-\d{2}-\d{2}(?:T[\d:.]+(?:Z|[+-]\d{2}:\d{2})?)?", timestamp_value, text)

    def quarter_value(match: re.Match) -> str:
        value = (
            match[1] or match[3] or str(["first", "second", "third", "fourth"].index(match[2].lower()) + 1)
        )
        quantities.add((Decimal(value), "quarter"))
        return " "

    def fiscal_value(match: re.Match) -> str:
        year = match[1]
        quantities.add((Decimal(year if len(year) == 4 else "20" + year), "fiscal_year"))
        return " "

    text = _QUARTER.sub(quarter_value, text)
    text = _FISCAL_YEAR.sub(fiscal_value, text)
    for match in _NUMBER.finditer(text):
        value = Decimal(match["value"].replace(",", ""))
        scale = (match["scale"] or "").lower()
        # A suffix must be a complete unit, not the first letter of the next word.
        if scale and match.end("scale") < len(text) and text[match.end("scale")].isalnum():
            scale = ""
        value *= Decimal(10) ** _SCALES.get(scale, 0)
        currency = (match["currency"] or "").upper()
        unit = _CURRENCIES.get(currency, currency) or "number"
        if source and unit == "number" and re.match(r"\s+per share\b", text[match.end("value") :], re.I):
            # SEC sale evidence in this US-equity app omits the dollar symbol.
            unit = "USD"
        unit_end = match.end("scale") if scale else match.end("value")
        if unit == "number" and re.match(r"\s+shares\b", text[unit_end:], re.I):
            unit = "shares"
        if match["percent"]:
            unit = "percent" if unit == "number" else f"{unit}:percent"
        before = text[: match.start()].rstrip()
        negative = match["sign_before"] or match["sign_after"]
        # A dash between two quantities denotes a range; a unary dash denotes a loss.
        if negative and not re.search(r"\d(?:[\d,.]*)(?:\s*(?:[A-Za-z]+|%))?$", before):
            value = -value
        quantities.add((value, unit))
    return quantities


def unsupported_numbers(generated: str, evidence: str) -> list[str]:
    """Return unmatched value/unit pairs; formatting never changes their value."""
    missing = _quantities(generated) - _quantities(evidence, source=True)
    return [f"{value.normalize()} ({unit})" for value, unit in sorted(missing)]
