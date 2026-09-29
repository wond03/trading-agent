# OKX 客户端 —— 行情(K线) + 模拟盘下单/持仓
# 凭证来源: 环境变量(本地调试) / GitHub Secrets(云端), 代码中永不出现真实密钥
# 模拟盘: 所有请求带 header  x-simulated-trading: 1
import os, hmac, hashlib, base64, json, time, datetime
import requests

class OkxClient:
    def __init__(self, api_key=None, secret=None, passphrase=None, simulated=True, timeout=15):
        self.key = api_key or os.environ.get("OKX_API_KEY", "")
        self.secret = secret or os.environ.get("OKX_SECRET_KEY", "")
        self.passphrase = passphrase or os.environ.get("OKX_PASSPHRASE", "")
        self.simulated = simulated
        self.base = "https://www.okx.com"
        self.timeout = timeout

    # ---------- 签名 (OKX v5: base64(hmac_sha256(secret, ts+method+path+body))) ----------
    def _sign(self, ts, method, path, body=""):
        msg = f"{ts}{method}{path}{body}"
        return base64.b64encode(hmac.new(self.secret.encode(), msg.encode(), hashlib.sha256).digest()).decode()

    def _headers(self, method, path, body=""):
        ts = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        h = {"OK-ACCESS-KEY": self.key, "OK-ACCESS-SIGN": self._sign(ts, method, path, body),
             "OK-ACCESS-TIMESTAMP": ts, "OK-ACCESS-PASSPHRASE": self.passphrase,
             "Content-Type": "application/json"}
        if self.simulated:
            h["x-simulated-trading"] = "1"
        return h

    def _get(self, path, params=None):
        url = self.base + path + ("?" + "&".join(f"{k}={v}" for k, v in params.items()) if params else "")
        r = requests.get(url, headers=self._headers("GET", path + ("?" + "&".join(f"{k}={v}" for k, v in params.items()) if params else "")), timeout=self.timeout)
        return r.json()

    def _post(self, path, body: dict):
        body_str = json.dumps(body)
        r = requests.post(self.base + path, headers=self._headers("POST", path, body_str), data=body_str, timeout=self.timeout)
        return r.json()

    # ---------- 行情 (公开接口, 无需签名) ----------
    def get_candles(self, inst_id="BTC-USDT-SWAP", bar="1H", limit=300):
        """返回按时间升序的 Candle 列表; OKX 原始返回为降序, 此处反转
        字段: [ts, o, h, l, c, vol, volCcy, volCcyQuote, confirm]"""
        import sys
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from structure import Candle
        r = requests.get(f"{self.base}/api/v5/market/candles",
                         params={"instId": inst_id, "bar": bar, "limit": limit}, timeout=self.timeout)
        d = r.json()
        if d.get("code") != "0":
            raise RuntimeError(f"OKX行情失败: {d.get('code')} {d.get('msg')}")
        rows = list(reversed(d["data"]))
        return [Candle(int(x[0]), float(x[1]), float(x[2]), float(x[3]), float(x[4]), float(x[5])) for x in rows]

    # ---------- 杠杆设置 (100倍必须显式设置) ----------
    def set_leverage(self, inst_id, lever, mgn_mode="isolated"):
        """设置杠杆: lever=100, mgn_mode=isolated(逐仓, 100倍必配)"""
        return self._post("/api/v5/account/set-leverage",
                          {"instId": inst_id, "lever": str(lever), "mgnMode": mgn_mode})

    # ---------- 模拟盘下单 ----------
    def place_order(self, inst_id, side, sz, td_mode="cross", ord_type="market"):
        """side: buy/sell; sz: 数量(张/币); 市价单
        策略开多做多(buy+long), 平多(sell+long); 做空需开空仓模式, 这里用净持仓模式简化"""
        body = {"instId": inst_id, "tdMode": td_mode, "side": side, "ordType": ord_type, "sz": str(sz)}
        return self._post("/api/v5/trade/order", body)

    def close_position(self, inst_id, side, sz, td_mode="cross"):
        """平仓: side 与持仓方向相反 (持多->sell)"""
        return self.place_order(inst_id, side, sz, td_mode, ord_type="market")

    def get_positions(self, inst_id=None):
        """查持仓(签名接口)"""
        path = "/api/v5/account/positions"
        q = f"?instId={inst_id}" if inst_id else ""
        return self._get(path, {"instId": inst_id} if inst_id else None)

    def get_balance(self):
        return self._get("/api/v5/account/balance", None)

    def ping_public(self):
        """连通性自检(公开接口, 用于云端部署验证)"""
        try:
            r = requests.get(f"{self.base}/api/v5/market/ticker", params={"instId": "BTC-USDT-SWAP"}, timeout=8)
            d = r.json()
            return {"ok": d.get("code") == "0", "price": d["data"][0]["last"] if d.get("code") == "0" else None}
        except Exception as e:
            return {"ok": False, "error": str(e)}
