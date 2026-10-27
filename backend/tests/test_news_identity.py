"""A roundup must identify the watched stock's analyst event, not a neighbour's."""

from app.models import WatchlistEntry
from app.services.news_identity import analyst_event_key
from app.services.news_sources import SourceItem


def test_roundup_key_ignores_other_analyst_targets():
    stock = WatchlistEntry(
        alpaca_asset_id="asset-sndk",
        symbol="SNDK",
        name="Sandisk Corporation Common Stock",
        exchange="NASDAQ",
    )
    item = SourceItem(
        "alpaca",
        "roundup",
        "https://example.com/roundup",
        "This SanDisk Analyst Begins Coverage On A Bullish Note",
        "Mizuho analyst Jane Doe initiated coverage on Other Corp (NYSE: OTHR) with a "
        "Buy rating and a price target of $2,400. Rosenblatt analyst Kevin Cassidy "
        "initiated coverage on SanDisk Corp (NASDAQ: SNDK) with a Buy rating and "
        "a price target of $2,400. Seaport analyst John Doe initiated coverage on "
        "Another Corp (NYSE: ANOT) with a Buy rating and a price target of $73. "
        "Considering buying SNDK stock? Read more.",
        None,
        ("SNDK",),
    )

    assert analyst_event_key(item, stock) == ("asset-sndk", "rosenblatt", "2400", "buy")
