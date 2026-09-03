"""
Tests for the pure parsing/filtering functions in news_sentiment.py — no
network, no LLM calls needed.

Run with: pytest tests/test_news_sentiment.py -v
"""

from agent.tools.news_sentiment import (
    parse_rss_titles,
    filter_relevant_headlines,
    symbol_to_keywords,
)

SAMPLE_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Sample Crypto News</title>
    <item>
      <title>Bitcoin surges past $70,000 on ETF inflows</title>
      <link>https://example.com/1</link>
    </item>
    <item>
      <title>Ethereum upgrade delayed to next quarter</title>
      <link>https://example.com/2</link>
    </item>
    <item>
      <title>Local bakery wins award for best croissant</title>
      <link>https://example.com/3</link>
    </item>
  </channel>
</rss>
"""


class TestParseRssTitles:
    def test_extracts_all_titles(self):
        titles = parse_rss_titles(SAMPLE_RSS)
        assert len(titles) == 3
        assert "Bitcoin surges past $70,000 on ETF inflows" in titles

    def test_malformed_xml_returns_empty_list(self):
        titles = parse_rss_titles("<not valid xml")
        assert titles == []

    def test_empty_feed_returns_empty_list(self):
        empty_rss = '<?xml version="1.0"?><rss><channel></channel></rss>'
        assert parse_rss_titles(empty_rss) == []


class TestFilterRelevantHeadlines:
    def test_filters_to_matching_keywords_case_insensitive(self):
        headlines = [
            "Bitcoin surges past $70,000 on ETF inflows",
            "Ethereum upgrade delayed to next quarter",
            "Local bakery wins award for best croissant",
            "BITCOIN whale moves $50M to cold storage",
        ]
        result = filter_relevant_headlines(headlines, ["bitcoin", "btc"])
        assert len(result) == 2
        assert "Local bakery wins award for best croissant" not in result

    def test_no_matches_returns_empty_list(self):
        headlines = ["Local bakery wins award for best croissant"]
        result = filter_relevant_headlines(headlines, ["bitcoin", "btc"])
        assert result == []


class TestSymbolToKeywords:
    def test_btc_pair(self):
        assert symbol_to_keywords("BTCUSDT") == ["bitcoin", "btc"]

    def test_eth_pair(self):
        assert symbol_to_keywords("ETHUSDT") == ["ethereum", "eth", "ether"]

    def test_unknown_symbol_falls_back_to_lowercase_base(self):
        assert symbol_to_keywords("DOGEUSDT") == ["doge"]
