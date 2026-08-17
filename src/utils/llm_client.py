"""LLM client wrappers for the framework.

The LLMAgent base class (src/core/interfaces.py) expects a client with a
single method:

    client.complete(system_prompt: str, user_prompt: str) -> str

This module provides a Zhipu AI client that uses its OpenAI-compatible
endpoint via langchain-openai. To use a different provider, add a new
class with the same `complete()` signature.
"""

from __future__ import annotations

import os
from typing import Any


def _require_env(key: str) -> str:
    value = os.environ.get(key, "").strip()
    if not value:
        raise ValueError(f"{key} is not set. Add it to your .env file or environment.")
    return value


class ZhipuLLMClient:
    """Zhipu AI (智谱) LLM client using the OpenAI-compatible endpoint.

    Configuration:
        ZHIPU_API_KEY   required
        ZHIPU_MODEL     optional, default "glm-4"
        ZHIPU_BASE_URL  optional, default "https://open.bigmodel.cn/api/paas/v4"
        ZHIPU_TEMPERATURE optional, default 0.7

    Usage:
        from src.utils.llm_client import ZhipuLLMClient
        client = ZhipuLLMClient()
        response = client.complete(system, user)
    """

    DEFAULT_BASE_URL = "https://open.bigmodel.cn/api/paas/v4"
    DEFAULT_MODEL = "glm-4"
    DEFAULT_TEMPERATURE = 0.7

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        temperature: float | None = None,
        trust_env: bool | None = None,
        **kwargs: Any,
    ):
        import httpx
        from langchain_openai import ChatOpenAI

        self.api_key = api_key or _require_env("ZHIPU_API_KEY")
        self.model = model or os.environ.get("ZHIPU_MODEL", self.DEFAULT_MODEL)
        self.base_url = base_url or os.environ.get(
            "ZHIPU_BASE_URL", self.DEFAULT_BASE_URL
        )
        self.temperature = (
            temperature
            if temperature is not None
            else float(os.environ.get("ZHIPU_TEMPERATURE", self.DEFAULT_TEMPERATURE))
        )

        # bigmodel.cn 是国内 API，直连即可。默认绕过系统代理（Windows 注册表
        # 代理可能指向未运行的本地代理如 Clash，会阻断连接）——与
        # MXMCPClient 的 trust_env=False 同一模式。设 ZHIPU_TRUST_ENV=1
        # 可恢复走代理（企业网络等场景）。
        if trust_env is None:
            trust_env = os.environ.get("ZHIPU_TRUST_ENV", "").strip() == "1"
        client_kwargs = dict(kwargs)
        if not trust_env and "http_client" not in client_kwargs:
            client_kwargs["http_client"] = httpx.Client(
                trust_env=False, timeout=120.0
            )

        self._chat = ChatOpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            model=self.model,
            temperature=self.temperature,
            **client_kwargs,
        )

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        """Call the LLM and return the raw text response."""
        messages = [
            ("system", system_prompt),
            ("human", user_prompt),
        ]
        response = self._chat.invoke(messages)
        return str(response.content)


def get_default_llm_client() -> ZhipuLLMClient | None:
    """Return a default Zhipu client if ZHIPU_API_KEY is configured.

    Returns None if the key is missing so that quant-only funds can run
    without LLM configuration.
    """
    if os.environ.get("ZHIPU_API_KEY", "").strip():
        return ZhipuLLMClient()
    return None
