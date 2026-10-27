"""Extract conservative event identities from attributed news evidence."""

import re

from ..models import WatchlistEntry
from .news_sources import SourceItem

_ACTION = re.compile(r"\b(?:initiat\w*|start\w* coverage|begin\w* coverage)\b", re.I)
_FIRM = re.compile(
    r"\b(?P<firm>[A-Z][A-Za-z&-]+(?:\s+[A-Z][A-Za-z&-]+){0,2})\s+"
    r"(?:(?:analyst\s+)(?:[A-Z][a-z]+\s+){1,3})?"
    r"(?:[Ii]nitiat\w*|[Ss]tart\w* coverage|[Bb]egin\w* coverage)\b"
)
_TARGET = re.compile(r"\$\s?(\d[\d,]*(?:\.\d+)?)")
_RATING = re.compile(r"\b(?:at|with|a)\s+(buy|sell|hold|neutral)\b", re.I)
_SENTENCE_BREAK = re.compile(r"\.\s+[A-Z]")
_TARGET_ACTIONS = {
    "raise": re.compile(r"\b(?:rais\w*|increas\w*|boost\w*|lift\w*|hik\w*)\b", re.I),
    "cut": re.compile(r"\b(?:cut\w*|lower\w*|reduc\w*|slash\w*)\b", re.I),
    "reiterate": re.compile(r"\b(?:reiterat\w*|maintain\w*|reaffirm\w*)\b", re.I),
}
_DOLLAR_VALUE = re.compile(r"\$\s?(\d[\d,]*(?:\.\d+)?)")
_RATING_ACTION = re.compile(
    r"\b(?:at|with|a|keeps?|reiterates?|maintains?|reaffirms?)\s+"
    r"(?P<rating>buy|sell|hold|neutral|overweight|underweight|equal[- ]weight)\b",
    re.I,
)
_FIRM_ALIASES = {
    "bank of america securities": "bank of america",
    "b of a securities": "bank of america",
    "bank of america": "bank of america",
    "bofa": "bank of america",
    "b of a": "bank of america",
    "cantor fitzgerald": "cantor fitzgerald",
    "td cowen": "td cowen",
    "rosenblatt": "rosenblatt",
    "piper sandler": "piper sandler",
    "goldman sachs": "goldman sachs",
    "morgan stanley": "morgan stanley",
    "jpmorgan": "jpmorgan",
    "j.p. morgan": "jpmorgan",
    "jefferies": "jefferies",
    "mizuho": "mizuho",
    "needham": "needham",
    "opco": "opco",
    "oppenheimer": "oppenheimer",
    "raymond james": "raymond james",
    "ubs": "ubs",
    "wedbush": "wedbush",
}


def analyst_event_key(item: SourceItem, entry: WatchlistEntry) -> tuple[str, str, str, str] | None:
    """Key a rated initiation only when firm, action and target appear in stock-local evidence."""
    text = f"{item.title}. {item.excerpt[:3000]}"
    names = sorted({entry.symbol, entry.name.split()[0]}, key=lambda value: (-len(value), value))
    stock_pattern = re.compile(r"\b(?:" + "|".join(map(re.escape, names)) + r")\b", re.I)
    for stock in stock_pattern.finditer(text):
        start = max(0, stock.start() - 120)
        window = text[start : stock.end() + 260]
        stock_start, stock_end = stock.start() - start, stock.end() - start
        targets = [
            match
            for match in _TARGET.finditer(window)
            if match.start() >= stock_end
            and not match.group(1).endswith(",")
            and not _SENTENCE_BREAK.search(window[stock_end : match.start()])
        ]
        if not targets:
            continue
        target = targets[0]
        firms = [
            match
            for match in _FIRM.finditer(window[: target.start()])
            if (
                match.end() <= stock_start
                and stock_start - match.end() <= 120
                and not _SENTENCE_BREAK.search(window[match.end() : stock_start])
                or match.start() >= stock_end
                and match.start() - stock_end <= 100
                and not _SENTENCE_BREAK.search(window[stock_end : match.start()])
            )
        ]
        if not firms:
            continue
        firm = min(
            firms, key=lambda match: min(abs(match.end() - stock_start), abs(match.start() - stock_end))
        )
        if not _ACTION.search(window[firm.start() : target.end()]):
            continue
        firm_name = firm.group("firm").lower().removesuffix(" securities")
        rating = _RATING.search(window[firm.start() : target.end()])
        return (
            entry.alpaca_asset_id,
            firm_name,
            target.group(1).replace(",", ""),
            rating.group(1).lower() if rating else "",
        )
    return None


def analyst_target_action_key(
    item: SourceItem, entry: WatchlistEntry
) -> tuple[str, str, str, str, str] | None:
    """Identify a stock-specific target action from a publisher title or article excerpt."""
    text = f"{item.title}. {item.excerpt[:3000]}"
    stock_names = sorted({entry.symbol, entry.name.split()[0]}, key=lambda value: (-len(value), value))
    stock_pattern = re.compile(r"\b(?:" + "|".join(map(re.escape, stock_names)) + r")\b", re.I)
    stock_mentions = list(stock_pattern.finditer(text))
    if not stock_mentions:
        return None

    lowered = text.lower()
    firms = sorted(_FIRM_ALIASES.items(), key=lambda pair: -len(pair[0]))
    for action, pattern in _TARGET_ACTIONS.items():
        for match in pattern.finditer(text):
            nearby_stocks = [stock for stock in stock_mentions if abs(stock.start() - match.start()) <= 220]
            if not nearby_stocks:
                continue
            stock = min(nearby_stocks, key=lambda value: abs(value.start() - match.start()))
            between_start = min(stock.end(), match.end())
            between_end = max(stock.start(), match.start())
            if _SENTENCE_BREAK.search(text[between_start:between_end]):
                continue

            target_window = text[match.end() : min(len(text), match.end() + 180)]
            target_context = text[max(0, match.start() - 80) : match.end() + 100]
            if not re.search(r"\b(?:price\s+)?target\b", target_context, re.I):
                continue
            values = list(_DOLLAR_VALUE.finditer(target_window))
            if not values:
                continue
            # In "raised from $620 to $720", the new target is the last value.
            # In "raised the target to $720 from $620", it is the value after "to".
            new_target = values[-1]
            for value in values:
                prefix = target_window[max(0, value.start() - 12) : value.start()].lower()
                if re.search(r"\bto\s*$", prefix):
                    new_target = value
                    break

            search_start = max(0, min(stock.start(), match.start()) - 130)
            search_end = min(len(text), max(stock.end(), match.end()) + 130)
            neighborhood = lowered[search_start:search_end]
            firm = next(
                (
                    canonical
                    for alias, canonical in firms
                    if re.search(rf"\b{re.escape(alias)}\b", neighborhood)
                ),
                None,
            )
            if firm is None:
                continue
            rating_match = _RATING_ACTION.search(neighborhood)
            return (
                entry.alpaca_asset_id,
                firm,
                action,
                new_target.group(1).replace(",", ""),
                rating_match.group("rating").lower().replace(" ", "-") if rating_match else "",
            )
    return None


def same_analyst_event(left: SourceItem, right: SourceItem, assets: list[WatchlistEntry]) -> bool:
    for asset in assets:
        one = analyst_event_key(left, asset)
        two = analyst_event_key(right, asset)
        if one and two and one[:3] == two[:3] and (not one[3] or not two[3] or one[3] == two[3]):
            return True
        one_action = analyst_target_action_key(left, asset)
        two_action = analyst_target_action_key(right, asset)
        if (
            one_action
            and two_action
            and one_action[:4] == two_action[:4]
            and (not one_action[4] or not two_action[4] or one_action[4] == two_action[4])
        ):
            return True
    return False
