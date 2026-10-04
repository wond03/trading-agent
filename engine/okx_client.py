# 暗夜猎手 (NightHunter) · OKX客户端
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
        """返回按时间升序的【已收盘】Candle 列表; OKX 原始返回为降序, 此处反转
        字段: [ts, o, h, l, c, vol, volCcy, volCcyQuote, confirm]
        ★2026-10-03 未来函数修复: 剔除 confirm!="1" 的未收盘K线。
          OKX /market/candles 最新一根是"正在形成"的K线; 若喂进结构/流动性引擎,
          会在盘中判出 BOS/CHoCH/FVG/截取, 收盘后可能反转消失 = 信号重绘(实盘信号失真)。"""
        import sys
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from structure import Candle
        r = requests.get(f"{self.base}/api/v5/market/candles",
                         params={"instId": inst_id, "bar": bar, "limit": limit}, timeout=self.timeout)
        d = r.json()
        if d.get("code") != "0":
            raise RuntimeError(f"OKX行情失败: {d.get('code')} {d.get('msg')}")
        out = []
        for x in reversed(d["data"]):
            if len(x) > 8 and str(x[8]) != "1":
                continue                      # 丢弃未收盘K线(confirm=0)
            _ts = int(x[0])
            if _ts > 1_000_000_000_000:       # ★OKX 返回毫秒 → 统一成【秒】,
                _ts //= 1000                  #   与 Gate 备用源/回测缓存口径一致(2026-10-03)
            out.append(Candle(_ts, float(x[1]), float(x[2]), float(x[3]), float(x[4]), float(x[5])))
        return out

    # ---------- 杠杆设置 (100倍必须显式设置) ----------
    def set_leverage(self, inst_id, lever, mgn_mode="isolated", pos_side=None):
        """设置杠杆: lever=100, mgn_mode=isolated(逐仓, 100倍必配)
        双向持仓模式下需指定 pos_side(long/short)"""
        body = {"instId": inst_id, "lever": str(lever), "mgnMode": mgn_mode}
        if pos_side:
            body["posSide"] = pos_side
        return self._post("/api/v5/account/set-leverage", body)

    # ---------- 模拟盘下单 ----------
    def place_order(self, inst_id, side, sz, td_mode="isolated", ord_type="market", pos_side=None):
        """side: buy/sell; pos_side: long/short(双向持仓模式必须指定)
        开多: side=buy+pos_side=long | 开空: side=sell+pos_side=short
        平多: side=sell+pos_side=long | 平空: side=buy+pos_side=short"""
        body = {"instId": inst_id, "tdMode": td_mode, "side": side, "ordType": ord_type, "sz": str(sz)}
        if pos_side:
            body["posSide"] = pos_side
        return self._post("/api/v5/trade/order", body)

    def close_position(self, inst_id, side, sz, td_mode="isolated", pos_side=None):
        """平仓: side 与持仓方向相反 (持多->sell, pos_side仍为long)"""
        return self.place_order(inst_id, side, sz, td_mode, ord_type="market", pos_side=pos_side)

    def get_positions(self, inst_id=None):
        """查持仓(签名接口)"""
        path = "/api/v5/account/positions"
        q = f"?instId={inst_id}" if inst_id else ""
        return self._get(path, {"instId": inst_id} if inst_id else None)

    def position_tier_imr(self, inst_id, td_mode="isolated"):
        """取该合约【最小仓位档】的初始保证金率 imr(交易所口径的真实保证金率)。
        ★2026-10-04: OKX /public/position-tiers 对 SWAP 必须传 instFamily(传 instId 会报 50015)。
        返回 imr 小数(如 0.04=25倍) 或 None(查不到)。"""
        fam = "-".join(inst_id.split("-")[:2])          # XAU-USDT-SWAP -> XAU-USDT
        try:
            j = self._get("/api/v5/public/position-tiers",
                          {"instType": "SWAP", "tdMode": td_mode, "instFamily": fam})
            tiers = j.get("data") or []
            if not tiers:
                return None
            return float(tiers[0].get("imr"))           # 档位按 maxSz 升序, 首档=最小仓位
        except Exception:
            return None

    # ---------- 订单状态 / 撤单 (确认"是否真成交"用) ----------
    def get_order(self, inst_id, ord_id):
        return self._get("/api/v5/trade/order", {"instId": inst_id, "ordId": ord_id})

    def cancel_order(self, inst_id, ord_id):
        return self._post("/api/v5/trade/cancel-order", {"instId": inst_id, "ordId": ord_id})

    def get_pending_orders(self, inst_type="SWAP"):
        return self._get("/api/v5/trade/orders-pending", {"instType": inst_type})

    # ---------- 止盈止损 (策略委托, 真实挂到交易所, OKX App持仓页可见) ----------
    def get_tick(self, inst_id):
        """最小价格变动tick(缓存); 止盈止损价必须对齐tick, 否则OKX拒单"""
        if not hasattr(self, "_tick_cache"):
            self._tick_cache = {}
        if inst_id in self._tick_cache:
            return self._tick_cache[inst_id]
        t = 0.1
        try:
            d = requests.get(f"{self.base}/api/v5/public/instruments",
                             params={"instType": "SWAP", "instId": inst_id}, timeout=self.timeout).json()
            t = float(d["data"][0]["tickSz"])
        except Exception:
            pass
        self._tick_cache[inst_id] = t
        return t

    def round_tick(self, inst_id, px):
        t = self.get_tick(inst_id)
        return round(round(float(px) / t) * t, 8)

    def round_sz(self, inst_id, sz):
        """张数向下对齐 lotSz 整数倍(不低于 minSz)
        ★修复(2026-10-02) sCode 51121 "Order quantity must be a multiple of the lot size":
          部分平仓曾产生 0.295 这类非 lotSz(0.01) 整数倍的张数, 导致 TP/SL 条件单全部被拒"""
        try:
            import config as C
            spec = C.INST_SPECS.get(inst_id) or {}
        except Exception:
            spec = {}
        lot = spec.get("lotSz") or 1
        mn = spec.get("minSz") or lot
        try:
            n = int(round(float(sz) / lot, 8)) * lot
        except Exception:
            return sz
        return max(round(n, 8), mn)

    def _reduce_algo(self, inst_id, pos_side, sz, td_mode, **trig):
        """下一条 reduceOnly 条件委托 (平仓方向与持仓相反)
        ★ 实测(2026-10-02): OKX 对 closeFraction 整仓TP/SL单限制"每仓仅1条(51088)";
          改用 sz+reduceOnly 的独立条件单, 则 TP 与 SL 可同时各挂一条, 且可撤旧挂新"""
        body = {"instId": inst_id, "tdMode": td_mode,
                "side": "sell" if pos_side == "long" else "buy",
                "posSide": pos_side, "ordType": "conditional",
                "sz": str(self.round_sz(inst_id, sz)), "reduceOnly": True}
        body.update(trig)
        return self._post("/api/v5/trade/order-algo", body)

    def place_tp_order(self, inst_id, pos_side, sz, td_mode, tp):
        """挂止盈(条件单, 到价市价平仓)"""
        return self._reduce_algo(inst_id, pos_side, sz, td_mode,
                                 tpTriggerPx=str(self.round_tick(inst_id, tp)), tpOrdPx="-1")

    def place_sl_order(self, inst_id, pos_side, sz, td_mode, sl):
        """挂止损(条件单, 到价市价平仓)"""
        return self._reduce_algo(inst_id, pos_side, sz, td_mode,
                                 slTriggerPx=str(self.round_tick(inst_id, sl)), slOrdPx="-1")

    def algo_ids(self, inst_id):
        """该品种当前在挂的策略委托 id 集合(用于判断挂在不在)"""
        d = self.get_algo_pending(inst_id=inst_id).get("data") or []
        return {a.get("algoId") for a in d}

    def cancel_algo(self, inst_id, algo_id):
        return self._post("/api/v5/trade/cancel-algos", [{"instId": inst_id, "algoId": algo_id}])

    def get_algo_pending(self, inst_type="SWAP", inst_id=None):
        p = {"instType": inst_type, "ordType": "conditional"}
        if inst_id:
            p["instId"] = inst_id
        return self._get("/api/v5/trade/orders-algo-pending", p)

    def get_algo(self, inst_id, algo_id):
        return self._get("/api/v5/trade/order-algo", {"instId": inst_id, "algoId": algo_id})

    def get_fills(self, inst_type="SWAP", inst_id=None, limit=20):
        p = {"instType": inst_type, "limit": str(limit)}
        if inst_id:
            p["instId"] = inst_id
        return self._get("/api/v5/trade/fills", p)

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
