# -*- coding: utf-8 -*-
"""腾讯自选股·练习赛组合 镜像同步器。

把本地 LX-top40 模拟组合同步到腾讯自选股模拟交易账户（100 股取整近似镜像）。
本地账本 _sim_portfolio.json 为权威，镜像仅作 App 端可视化。

模式:
  python _sim_mirror_sync.py                # 建仓镜像: 执行 _sim_mirror_plan.json 买入
  python _sim_mirror_sync.py --sync         # 全量同步: 对齐本地持仓（卖多余/买不足，调仓后用）
鉴权: 直读 WorkBuddy 连接器 OAuth 凭证（内存使用，不打印不落盘）。
注意: westock 交易接口并发会触发"订单票据无效"，必须逐笔串行 + 失败重试。
"""
import argparse
import glob
import json
import os
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _sim_engine as E

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

MCP_URL = "https://stockbuddy.qq.com/cgi/cgi-bin/openai/mcp/mcp"
CRED_GLOB = os.path.expanduser("~/.workbuddy/connectors/*/.credentials.json")
STATE_FILE = os.path.join(E.BASE, "_sim_mirror_state.json")


def load_token():
    for path in glob.glob(CRED_GLOB):
        try:
            d = json.load(open(path, encoding="utf-8"))
        except Exception:
            continue
        for k, v in (d.get("mcpOAuth") or {}).items():
            if k.startswith("westock-mcp") and v.get("accessToken"):
                return v["accessToken"]
    raise RuntimeError("找不到 westock-mcp 凭证（连接器未授权?）")


class Mcp:
    def __init__(self):
        self.tok = load_token()
        self.sid = None
        self._id = 0
        self._init()

    def _post(self, body, timeout=30):
        req = urllib.request.Request(MCP_URL, data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json",
                                              "Accept": "application/json, text/event-stream",
                                              "Authorization": "Bearer " + self.tok})
        if self.sid:
            req.add_header("mcp-session-id", self.sid)
        resp = urllib.request.urlopen(req, timeout=timeout)
        new_sid = resp.headers.get("mcp-session-id")
        if new_sid:
            self.sid = new_sid
        return resp.read().decode("utf-8", errors="replace")

    def _init(self):
        self._post({"jsonrpc": "2.0", "id": 0, "method": "initialize",
                    "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                               "clientInfo": {"name": "sim-mirror", "version": "1.0"}}})
        self._post({"jsonrpc": "2.0", "method": "notifications/initialized"})

    def call(self, tool, args, retries=2):
        self._id += 1
        body = {"jsonrpc": "2.0", "id": self._id, "method": "tools/call",
                "params": {"name": tool, "arguments": args}}
        raw = self._post(body)
        obj = self._parse(raw)
        if obj is None:
            raise RuntimeError(f"MCP 响应解析失败: {raw[:200]}")
        if "error" in obj:
            raise RuntimeError(f"MCP 错误: {obj['error']}")
        content = (obj.get("result") or {}).get("content") or []
        text = content[0].get("text", "") if content else "{}"
        try:
            return json.loads(text)
        except Exception:
            return {"raw": text}

    @staticmethod
    def _parse(raw):
        lines = [l for l in raw.splitlines() if l.startswith("data:")]
        for joiner in ("\n", ""):
            try:
                return json.loads(joiner.join(l[5:].strip() for l in lines))
            except Exception:
                continue
        try:
            return json.loads(raw)
        except Exception:
            return None


def paper_positions(mcp):
    r = mcp.call("portfolio_paper_positions", {})
    return {p["code"]: p for p in (r.get("data") or {}).get("positions", [])}


def trade(mcp, direction, code, price, qty):
    """限价单，票据错误自动重试（必要时重建会话）。返回 (ok, info)"""
    for attempt in range(4):
        try:
            r = mcp.call("portfolio_paper_trade",
                         {"code": code, "direction": direction, "price": price, "quantity": qty})
            data = r.get("data") or {}
            if r.get("ok") or data.get("orderId"):
                return True, data
            msg = str(r.get("raw") or r)
        except Exception as e:
            msg = str(e)
            try:
                mcp._init()
            except Exception:
                pass
        if "票据" in msg:
            time.sleep(1.0)
            continue
        return False, msg
    return False, msg + " (票据重试耗尽)"


def lot_qty(shares):
    return int(shares // 100) * 100


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sync", action="store_true", help="全量同步到本地持仓（调仓后用）")
    ap.add_argument("--plan", default="_sim_mirror_plan.json")
    args = ap.parse_args()

    port = E.jload(E.PORT_FILE)
    assert port and port.get("positions"), "本地无持仓，先 _sim_init.py"
    mcp = Mcp()
    quotes = E.fetch_quotes([p["tcode"] for p in port["positions"]])
    held = paper_positions(mcp)
    print(f"镜像账户现有 {len(held)} 只持仓")

    orders, results = [], []

    if args.sync:
        # 全量同步: 先卖后买，目标 = 本地持股 100 股取整
        for tc, p in held.items():
            local = next((x for x in port["positions"] if x["tcode"] == tc), None)
            target = lot_qty(local["shares"]) if local else 0
            if int(p["quantity"]) > target:
                q = int(p["quantity"]) - target
                price = round((quotes.get(tc) or {}).get("price", 0) * 0.99, 2)
                orders.append(("sell", tc, price, q))
        for p in port["positions"]:
            tc = p["tcode"]
            target = lot_qty(p["shares"])
            cur = int(held[tc]["quantity"]) if tc in held else 0
            if target > cur:
                price = round((quotes.get(tc) or {}).get("price", p["cost"]) * 1.01, 2)
                orders.append(("buy", tc, price, target - cur))
    else:
        plan = E.jload(os.path.join(E.BASE, args.plan)) or []
        for it in plan:
            tc = it["code"]
            cur = int(held[tc]["quantity"]) if tc in held else 0
            if cur >= it["qty"]:
                continue
            price = round((quotes.get(tc) or {}).get("price", it["price"]) * 1.01, 2)
            orders.append(("buy", tc, price, it["qty"] - cur))

    print(f"待执行 {len(orders)} 笔（限价=现价±1%）")
    cash_note = ""
    for i, (d, tc, price, qty) in enumerate(orders, 1):
        ok, info = trade(mcp, d, tc, price, qty)
        results.append({"direction": d, "code": tc, "price": price, "qty": qty, "ok": ok,
                        "info": str(info.get("status") or info)[:80] if isinstance(info, dict) else str(info)[:80]})
        print(f"  [{i}/{len(orders)}] {d} {tc} x{qty} @{price:.2f} -> {'OK' if ok else 'FAIL ' + str(info)[:60]}")
        if not ok and "资金" in str(info):
            cash_note = str(info)
        time.sleep(0.6)

    held2 = paper_positions(mcp)
    pf = (mcp.call("portfolio_paper_portfolio", {}).get("data") or {}).get("portfolio") or {}
    state = {"ts": time.strftime("%Y-%m-%d %H:%M:%S"), "orders": results,
             "n_positions": len(held2),
             "market_value": pf.get("marketValue"), "cash": pf.get("availableCash"),
             "total_assets": pf.get("totalAssets")}
    E.jdump(state, STATE_FILE)
    print(f"完成: 成功 {sum(1 for r in results if r['ok'])}/{len(orders)} | "
          f"镜像持仓 {len(held2)} 只 | 总资产 {pf.get('totalAssets')} | 可用 {pf.get('availableCash')}")
    if cash_note:
        print("注意:", cash_note)


if __name__ == "__main__":
    main()
