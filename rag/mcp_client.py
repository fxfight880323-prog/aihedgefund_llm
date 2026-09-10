# -*- coding: utf-8 -*-
"""通用 streamable-http MCP 客户端 —— 供 RAG ingest 无人值守直连研报源。

设计:
- 读取 ~/.workbuddy/mcp.json 中的服务器配置(url + headers), 不复制 token 到本仓库
- SSE 响应统一 r.content.decode('utf-8') 解析(requests r.text 会用 ISO-8859-1 污染中文)
- csc 服务器为旧 TLS 实现(unsafe legacy renegotiation), 用 urllib3 自定义 SSLContext
- 幂等: call_tool 每次重新 initialize(无状态短会话), 每次调用独立超时与重试

实测(2026-09-10): juzi-mcp / csc-mcp 均可直连。
"""
from __future__ import annotations

import json
import os
import ssl
import time
from typing import Any

import requests
from requests.adapters import HTTPAdapter

MCP_CONFIG_PATH = os.path.join(os.path.expanduser("~"), ".workbuddy", "mcp.json")

# protocolVersion 按服务器支持顺序尝试(实测 2025-03-26 两者都接受)
_PROTOCOLS = ["2025-03-26", "2024-11-05"]


class _LegacySSLAdapter(HTTPAdapter):
    """允许 SSL_OP_LEGACY_SERVER_CONNECT —— csc 旧版 TLS renegotiation 需要。"""

    def init_poolmanager(self, *args, **kwargs):
        ctx = ssl.create_default_context()
        ctx.options |= 0x4  # SSL_OP_LEGACY_SERVER_CONNECT
        kwargs["ssl_context"] = ctx
        return super().init_poolmanager(*args, **kwargs)


class McpClient:
    def __init__(self, server_name: str, timeout: int = 60):
        os.environ.setdefault("NO_PROXY", "*")  # Windows 系统代理会拦直连
        cfg = json.load(open(MCP_CONFIG_PATH, encoding="utf-8"))["mcpServers"]
        if server_name not in cfg:
            raise KeyError(f"MCP server '{server_name}' not in {MCP_CONFIG_PATH}; have {list(cfg)}")
        self.name = server_name
        self.url = cfg[server_name]["url"]
        self.timeout = timeout
        self._headers = dict(cfg[server_name].get("headers", {}))
        self._session = requests.Session()
        self._ready = False
        if server_name == "csc-mcp":
            self._session.mount("https://", _LegacySSLAdapter())

    # ---------- 底层 ----------
    def _post(self, payload: dict) -> dict | None:
        h = dict(self._headers)
        h.update({"Content-Type": "application/json",
                  "Accept": "application/json, text/event-stream"})
        r = self._session.post(self.url, headers=h, json=payload, timeout=self.timeout)
        r.raise_for_status()
        return self._parse(r.content.decode("utf-8", errors="replace"))

    @staticmethod
    def _parse(body: str) -> dict | None:
        try:
            return json.loads(body)
        except Exception:
            pass
        for line in body.splitlines():
            if line.startswith("data:"):
                try:
                    return json.loads(line[5:].strip())
                except Exception:
                    continue
        return None

    def _initialize(self) -> bool:
        """发送 initialize(会话首次)。返回是否成功。"""
        for pv in _PROTOCOLS:
            resp = self._post({
                "jsonrpc": "2.0", "id": 1, "method": "initialize",
                "params": {"protocolVersion": pv, "capabilities": {},
                           "clientInfo": {"name": "ai-fund-rag", "version": "0.1"}}})
            if resp and "result" in resp:
                try:
                    self._session.post(self.url, headers=self._headers,
                                       json={"jsonrpc": "2.0", "method": "notifications/initialized"},
                                       timeout=15)
                except Exception:
                    pass
                self._ready = True
                return True
        raise RuntimeError(f"[{self.name}] initialize failed on all protocol versions")

    # ---------- 公共 API ----------
    def list_tools(self) -> list[dict]:
        self._initialize()
        resp = self._post({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        return (resp or {}).get("result", {}).get("tools", [])

    def call_tool(self, tool: str, arguments: dict | None = None,
                  retries: int = 2) -> Any:
        """调用工具并返回 content 里的 JSON/text。

        juzi 返回 {"ok":true,"data":...}; csc 返回 {"status":"ok","items":[...]}
        或 JSON 字符串(带 【工具编号】 前缀说明)。这里做尽力解析, 失败返回原始文本。
        """
        arguments = arguments or {}
        last_err = None
        for attempt in range(retries + 1):
            try:
                if not self._ready:
                    self._initialize()
                resp = self._post({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                                   "params": {"name": tool, "arguments": arguments}})
                if resp is None:
                    raise RuntimeError("empty response")
                if "error" in resp:
                    raise RuntimeError(f"rpc error: {resp['error']}")
                content = resp.get("result", {}).get("content", [])
                if not content:
                    return None
                text_parts = [c.get("text", "") for c in content if c.get("type") == "text"]
                if not text_parts:
                    return content
                raw = "\n".join(text_parts)
                try:
                    return json.loads(raw)
                except Exception:
                    return raw
            except Exception as e:  # noqa: BLE001
                last_err = e
                self._ready = False  # 会话可能失效, 下轮重新 initialize
                time.sleep(1.5 * (attempt + 1))
        raise RuntimeError(f"[{self.name}] call_tool({tool}) failed after retries: {last_err}")


if __name__ == "__main__":
    import sys
    for name in (sys.argv[1:] or ["juzi-mcp", "csc-mcp"]):
        try:
            c = McpClient(name)
            tools = c.list_tools()
            names = [t["name"].split("__")[-1] for t in tools]
            print(f"✅ {name}: {len(tools)} tools")
            for n in names[:5]:
                print("   -", n)
        except Exception as e:  # noqa: BLE001
            print(f"❌ {name}: {type(e).__name__}: {e}")
