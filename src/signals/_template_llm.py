"""TEMPLATE: Custom LLM Investor Agent
============================================================================

Copy this file, rename it, and create your own AI investor persona.

The system prompt IS the investment philosophy. Everything the LLM knows
about how to evaluate stocks is encoded in the prompt.

IDEAS FOR LLM AGENTS:
  - Cathie Wood: disruptive innovation, exponential growth
  - Michael Burry: contrarian, deep value, short seller
  - Bill Ackman: activist investor, concentrated bets
  - Aswath Damodaran: intrinsic valuation, DCF
  - Phil Fisher: scuttlebutt, qualitative growth
  - Mohnish Pabrai: clones Buffett, few bets
  - Nassim Taleb: tail risk, antifragility
  - Rakesh Jhunjhunwala: Indian growth investing
  - YOUR OWN THEORY: encode your personal investment philosophy

REGISTRATION:
  In src/signals/__init__.py, add:
    from src.signals.my_agent import MyAgent
    ALPHA_MODEL_REGISTRY["my_agent"] = MyAgent
"""

from __future__ import annotations

from typing import Any

from src.core.interfaces import LLMAgent
from src.core.models import Signal


class TemplateLLMAgent(LLMAgent):
    """BLANK TEMPLATE — implement your own LLM investor persona.

    The persona is ONLY a system prompt. All machinery lives in LLMAgent
    (src/core/interfaces.py). All data comes from the data_client.

    TO CUSTOMIZE:
      1. Change `name` to your persona's identifier
      2. Write your investment philosophy in `get_system_prompt()`
      3. Optionally override `build_user_prompt()` to change what data the LLM sees
    """

    @property
    def name(self) -> str:
        """This must match the key in ALPHA_MODEL_REGISTRY."""
        return "my_agent"  # TODO: Rename

    def get_system_prompt(self) -> str:
        """YOUR INVESTMENT PHILOSOPHY GOES HERE.

        This prompt defines everything about how this agent evaluates stocks.
        Be specific about:
          - What matters to you (growth? value? momentum? quality?)
          - Your decision criteria
          - Your confidence calibration
          - What data to focus on

        The LLM will follow this prompt literally. Make it count.
        """

        # TODO: Replace with your own investment philosophy
        return """You are [YOUR PERSONA], evaluating a single company.

YOUR INVESTMENT PHILOSOPHY:
[Describe your investment approach here. What do you look for? What do you
avoid? What's your edge?]

YOUR CHECKLIST:
1. [First criterion]
2. [Second criterion]
3. [Third criterion]
4. ...

SIGNAL RULES:
- bullish: [when to be bullish]
- bearish: [when to be bearish]
- neutral: [when to abstain]

CONFIDENCE SCALE (0-100):
- 90-100: [exceptional conviction criteria]
- 70-89: [solid conviction criteria]
- 40-69: [mixed evidence criteria]
- 10-39: [weak/speculative criteria]

Respond with JSON only:
{"signal": "bullish" | "bearish" | "neutral", "confidence": <0-100>,
 "reasoning": "<2-4 sentence thesis in your voice>"}"""

    def build_user_prompt(self, ticker: str, date: str, data_client: Any) -> str:
        """What data does your persona need to make a decision?

        Default: fetches financial metrics + company facts.
        Override to add news, alternative data, custom research, etc.

        Examples of what you can fetch:
          - data_client.get_prices(ticker, start, date)        # price history
          - data_client.get_financial_metrics(ticker, date)    # fundamentals
          - data_client.get_company_facts(ticker)              # company info
          - data_client.get_earnings(ticker)                   # earnings data

        Or use a custom data client for alternative data:
          - sentiment scores
          - insider trading
          - social media mentions
          - satellite data
        """
        # ---- DEFAULT: Fetch fundamentals + company facts ----
        metrics = []
        try:
            metrics = data_client.get_financial_metrics(ticker, date, limit=5)
        except Exception:
            pass

        facts = {}
        try:
            facts = data_client.get_company_facts(ticker) or {}
        except Exception:
            pass

        lines = [
            f"Company: {ticker}",
            f"As of: {date}",
            f"Sector: {facts.get('sector', 'N/A')}",
            f"Industry: {facts.get('industry', 'N/A')}",
            f"Description: {facts.get('description', 'N/A')[:500]}",
            "",
            "Financial Metrics:",
        ]
        for m in metrics[:5]:
            lines.append(f"  Period: {m.get('period', 'N/A')}")
            for k, v in m.items():
                if k != "period" and v is not None:
                    lines.append(f"    {k}: {v}")
            lines.append("")

        # ---- OPTIONAL: Add price history ----
        # from datetime import timedelta
        # from datetime import datetime
        # as_of = datetime.strptime(date[:10], "%Y-%m-%d").date()
        # start = (as_of - timedelta(days=365)).isoformat()
        # prices = data_client.get_prices(ticker, start, date)
        # if prices:
        #     closes = [p["close"] for p in prices]
        #     lines.append(f"Current Price: {closes[-1]:.2f}")
        #     lines.append(f"52w High: {max(closes):.2f}")
        #     lines.append(f"52w Low: {min(closes):.2f}")
        #     lines.append(f"1Y Return: {(closes[-1]/closes[0]-1)*100:.1f}%")
        #     lines.append("")

        # ---- OPTIONAL: Add alternative data ----
        # sentiment = my_alt_client.get_sentiment(ticker, date)
        # lines.append(f"Sentiment Score: {sentiment:.2f}")

        return "\n".join(lines)
