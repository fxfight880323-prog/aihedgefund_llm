"""Warren Buffett LLM agent — example LLM investor persona.

A persona is just a name + a system prompt. The LLMAgent base class
(in src/core/interfaces.py) handles all the LLM machinery.

TO ADD YOUR OWN LLM AGENT:
  1. Copy this file
  2. Change the class name, the `name` property, and the system prompt
  3. Optionally override `build_user_prompt()` to change what data the LLM sees
  4. Register in src/signals/__init__.py

The system prompt IS the strategy. Everything the LLM knows about
investing is encoded in the prompt.
"""

from __future__ import annotations

from typing import Any

from src.core.interfaces import LLMAgent
from src.core.models import Signal


class BuffettAgent(LLMAgent):
    """Reasons over fundamentals in Warren Buffett's voice."""

    @property
    def name(self) -> str:
        return "buffett"

    def get_system_prompt(self) -> str:
        return """You are Warren Buffett, evaluating a single company as a
long-term business owner, not a trader.

Work through your checklist:
1. Circle of competence — can this business be understood?
2. Competitive moat — durable high ROE, stable/improving margins, pricing power.
3. Management quality — capital allocation visible: book value compounding,
   sensible leverage, consistent free cash flow.
4. Financial strength — low debt, healthy current ratio, consistent earnings.
5. Valuation — is the price sensible relative to quality and growth?
6. Long-term prospects — would you hold this for ten years?

Signal rules:
- bullish: strong, durable business at a reasonable price
- bearish: weak/deteriorating business, or price demands perfection
- neutral: mixed evidence

Confidence scale (0-100): 90-100 exceptional; 70-89 solid; 40-69 mixed;
10-39 weak/speculative.

Respond with JSON only:
{"signal": "bullish" | "bearish" | "neutral", "confidence": <0-100>,
 "reasoning": "<2-4 sentence thesis>"}"""

    def build_user_prompt(self, ticker: str, date: str, data_client: Any) -> str:
        """Override to feed fundamentals data to the LLM."""
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
            "",
            "Financial Metrics (most recent first):",
        ]
        for m in metrics[:5]:
            lines.append(f"  Period: {m.get('period', 'N/A')}")
            for k, v in m.items():
                if k != "period" and v is not None:
                    lines.append(f"    {k}: {v}")
            lines.append("")

        return "\n".join(lines)
