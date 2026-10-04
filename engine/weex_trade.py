# 暗夜猎手 (NightHunter) · WEEX 模拟盘(Paper Trading) 交易客户端
# ★2026-10-04 用户裁定: 下单整体从 OKX 切到 WEEX 模拟盘, 不再保留 OKX
#
# 官方【仅 4 个】sim 接口(实测确认):
#   GET  /capi/v3/sim/balance              账户余额(资产 SUSDT)
#   GET  /capi/v3/sim/position/allPosition 全部持仓(对冲模式)
#   POST /capi/v3/sim/order                下单(可一次内联带 止盈+止损)
#   GET  /capi/v3/sim/order/history        历史委托
# 没有撤单 / 订单详情 / 设置杠杆接口 → 平仓一律用"反向市价单", 成交判定靠轮询持仓。
#
# 签名(=OKX 同款): ACCESS-SIGN = base64(HMAC_SHA256(secret,
#        timestamp + method大写 + requestPath + ("?"+queryString 若有) + body))
#   ACCESS-TIMESTAMP 毫秒, 与服务器时差须 ≤30s → 用 /capi/v3/market/time 校准。
#
# 交易对命名: 模拟盘 = `<BASE>SUSDT`(BTCSUSDT / XAUTSUSDT);
#             行情/规格 = 真实符号(BTCUSDT / XAUTUSDT)与 cmt_* 不同, 不可混用。
import base64
import hashlib
import hmac
import json
import os
import time
import urllib.parse

import requests

BASE = "https://api-contract.weex.com"

# 内部品种名 → (模拟盘下单符号, 规格符号/真实合约)
SYMBOL_MAP = {
    "BTC-USDT-SWAP": ("BTCSUSDT", "BTCUSDT"),
    "XAU-USDT-SWAP": ("XAUTSUSDT", "XAUTUSDT"),
}

# ★2026-10-05: 条件单接口【不带 /sim/ 前缀】, 但用模拟盘密钥调用时作用在模拟盘账户上
#   (实测: GET openAlgoOrders 返回的正是模拟盘持仓对应的条件单) → 加入签名白名单。
ALGO_PATHS = (
    "/capi/v3/openAlgoOrders",     # 查当前条件单
    "/capi/v3/algoOrder",          # 下条件单(POST) / 撤条件单(DELETE)
    "/capi/v3/algoOpenOrders",     # 撤全部条件单(DELETE)
    "/capi/v3/modifyTpSlOrder",    # 改止盈止损触发价(POST)
)


class WeexTrade:
    """WEEX 合约模拟盘客户端(仅下单/持仓/余额/历史; 无撤单)"""

    def __init__(self, api_key=None, secret=None, passphrase=None, timeout=20):
        self.key = api_key or os.environ.get("WEEX_API_KEY", "")
        self.secret = secret or os.environ.get("WEEX_API_SECRET", "")
        self.passphrase = passphrase or os.environ.get("WEEX_API_PASSPHRASE", "")
        self.timeout = timeout
        self._spec = {}          # 真实符号 → 规格 dict
        self._t_off = 0          # 本地与服务器时差(ms)
        self._last_err = ""

    # ================= 基础 =================
    @property
    def configured(self):
        return bool(self.key and self.secret and self.passphrase)

    def _headers(self, ts, method, path, query, body_str):
        msg = str(ts) + method.upper() + path
        if query:
            msg += "?" + query
        if body_str:
            msg += body_str
        sign = base64.b64encode(
            hmac.new(self.secret.encode(), msg.encode(), hashlib.sha256).digest()).decode()
        return {"ACCESS-KEY": self.key, "ACCESS-SIGN": sign, "ACCESS-PASSPHRASE": self.passphrase,
                "ACCESS-TIMESTAMP": str(ts), "Content-Type": "application/json",
                "User-Agent": "nighthunter/1.0"}

    def _call(self, method, path, params=None, body=None, signed=True, retry=2):
        """统一请求。★安全守卫: 签名请求只允许打 /sim/ 路径或条件单白名单(绝不可能误触真实盘)"""
        if signed and "/sim/" not in path and path not in ALGO_PATHS:
            raise RuntimeError(f"拒绝: 签名请求路径必须是 sim 接口或条件单白名单, 收到 {path}")
        query = urllib.parse.urlencode(params) if params else ""
        body_str = json.dumps(body, separators=(",", ":")) if body is not None else ""
        url = BASE + path + (("?" + query) if query else "")
        last = None
        for _ in range(retry + 1):
            try:
                if signed:
                    ts = int(time.time() * 1000) + self._t_off
                    h = self._headers(ts, method, path, query, body_str)
                else:
                    h = {"Content-Type": "application/json", "User-Agent": "nighthunter/1.0"}
                _m = method.upper()
                if _m == "GET":
                    r = requests.get(url, headers=h, timeout=self.timeout)
                elif _m == "DELETE":
                    r = requests.delete(url, headers=h, timeout=self.timeout, data=body_str)
                else:
                    r = requests.post(url, headers=h, timeout=self.timeout, data=body_str)
                try:
                    return r.status_code, r.json()
                except Exception:
                    return r.status_code, {"_raw": r.text[:300]}
            except Exception as e:
                last = e
                time.sleep(1.0)
        return -1, {"_err": f"{type(last).__name__}: {last}"}

    # ================= 时间同步 =================
    def sync_time(self):
        try:
            r = requests.get(BASE + "/capi/v3/market/time", timeout=self.timeout)
            st = int(r.json().get("serverTime", 0))
            if st:
                self._t_off = st - int(time.time() * 1000)
                return self._t_off
        except Exception:
            pass
        return 0

    # ================= 合约规格(公开) =================
    def load_specs(self, force=False):
        if self._spec and not force:
            return self._spec
        try:
            r = requests.get(BASE + "/capi/v3/market/exchangeInfo", timeout=self.timeout)
            for s in (r.json().get("symbols") or []):
                self._spec[s.get("symbol")] = s
        except Exception as e:
            self._last_err = f"exchangeInfo 失败 {type(e).__name__}"
        return self._spec

    def spec(self, inst_id):
        """按内部品种名取规格(真实合约): {pricePrecision, quantityPrecision, minOrderSize, maxLeverage, takerFeeRate...}"""
        self.load_specs()
        _, real = SYMBOL_MAP.get(inst_id, (None, None))
        return self._spec.get(real) or {}

    def trade_symbol(self, inst_id):
        return SYMBOL_MAP.get(inst_id, (None, None))[0]

    def round_qty(self, inst_id, qty):
        """数量按 quantityPrecision 向下取整, 不低于 minOrderSize"""
        sp = self.spec(inst_id)
        p = int(sp.get("quantityPrecision", 4))
        mn = float(sp.get("minOrderSize") or 0)
        step = 10 ** (-p)
        v = int(float(qty) / step) * step
        v = round(v, p)
        if v < mn:
            v = mn
        return v

    def round_px(self, inst_id, px):
        sp = self.spec(inst_id)
        p = int(sp.get("pricePrecision", 1))
        return round(float(px), p)

    # ★2026-10-04 实测: 黄金(TRADIFI_PERPETUAL/Metals)的【止盈止损触发价】必须对齐 0.1,
    #   比 exchangeInfo 里的 pricePrecision=2 更粗 → 报 -1054 "matches the stepSize '0.1' requirement"
    TRIGGER_PRECISION = {"XAUTUSDT": 1, "XAUTSUSDT": 1}

    def round_trigger(self, inst_id, px):
        """止盈/止损触发价的取整精度(比下单价更保守)"""
        _, real = SYMBOL_MAP.get(inst_id, (None, None))
        if real in self.TRIGGER_PRECISION:
            return round(float(px), self.TRIGGER_PRECISION[real])
        return round(float(px), int((self.spec(inst_id) or {}).get("pricePrecision", 1)))

    # ================= 查询 =================
    def get_balance(self):
        return self._call("GET", "/capi/v3/sim/balance")

    def balance_asset(self, asset="SUSDT"):
        st, j = self.get_balance()
        rows = j if isinstance(j, list) else (j.get("data") or [])
        for x in rows:
            if (x.get("asset") or "").upper() == asset.upper():
                return x
        return {}

    def get_positions(self):
        """返回 [{symbol, positionSide, size, avgPrice?, marginSize, leverage, unrealizePnl, liquidatePrice, ...}]
        注意: 官方返回字段为 side(而非 positionSide)、size、marginSize、unrealizePnl、liquidatePrice"""
        st, j = self.get_positions_raw()
        rows = j if isinstance(j, list) else (j.get("data") or [])
        out = []
        for x in rows:
            try:
                if abs(float(x.get("size") or 0)) > 0:
                    out.append(x)
            except Exception:
                continue
        return out

    def get_positions_raw(self):
        return self._call("GET", "/capi/v3/sim/position/allPosition")

    def pos_of(self, inst_id):
        """取该内部品种名的持仓记录(无则 None)"""
        sym = self.trade_symbol(inst_id)
        for x in self.get_positions():
            if (x.get("symbol") or "").upper() == (sym or "").upper():
                return x
        return None

    def get_order_history(self, inst_id=None, limit=50):
        p = {"limit": str(limit)}
        if inst_id:
            p["symbol"] = self.trade_symbol(inst_id)
        return self._call("GET", "/capi/v3/sim/order/history", params=p)

    # ================= 条件单(止盈/止损) ★2026-10-05 =================
    #   内联的 tp/sl 会在交易所生成 2 张条件单, 其 clientAlgoId = 下单的 newClientOrderId + "sl"/"tp"。
    #   下面 4 个接口可直接【读回 / 补挂 / 改价 / 撤销】(全部走 ALGO_PATHS 白名单)。
    def real_symbol(self, inst_id):
        return SYMBOL_MAP.get(inst_id, (None, None))[1]

    def algo_orders(self, inst_id=None, limit=100):
        """当前条件单列表。
        ★实测: 该接口传 symbol 会被拒/过滤成空(-1142, 且 sim/real 名都不认) → 一律【不传 symbol】,
          拉全量后本地按真实合约名筛; 否则会误判成"没有保护单"→重复补挂。"""
        st, j = self._call("GET", "/capi/v3/openAlgoOrders", params={"page": "1", "limit": str(limit)})
        if isinstance(j, list):
            rows = j
        elif isinstance(j, dict):
            rows = j.get("data") or []
        else:
            rows = []
        if inst_id:
            # ★返回的 symbol 是【模拟盘名】(BTCSUSDT), 但也兼容真实名 → 两个都认
            names = {(self.trade_symbol(inst_id) or "").upper(),
                     (self.real_symbol(inst_id) or "").upper()}
            rows = [x for x in rows if (x.get("symbol") or "").upper() in names]
        return st, rows

    def place_algo(self, inst_id, side, position_side, qty, order_type, trigger,
                   reduce_only=True):
        """补挂条件单。order_type: TAKE_PROFIT_MARKET(止盈) / STOP_MARKET(止损)
        ★字段名以官方 algoOrder 文档为准: `type`(不是 orderType) + `clientAlgoId`(不是 newClientOrderId)。
          side 传与持仓相反方向 + positionSide 传持仓方向 = 只减仓(不会反向开仓)。"""
        body = {"symbol": self.real_symbol(inst_id), "side": side.upper(),
                "positionSide": position_side.upper(), "type": order_type,
                "quantity": str(self.round_qty(inst_id, qty)),
                "triggerPrice": str(self.round_trigger(inst_id, trigger)),
                "clientAlgoId": self._gen_oid(), "reduceOnly": bool(reduce_only)}
        return self._call("POST", "/capi/v3/algoOrder", body=body)

    def modify_tp_sl(self, algo_id, trigger, trigger_type="CONTRACT_PRICE"):
        """改已有条件单触发价(不传 executePrice = 触发后市价执行)"""
        body = {"orderId": int(algo_id), "triggerPrice": str(trigger),
                "triggerPriceType": trigger_type}
        return self._call("POST", "/capi/v3/modifyTpSlOrder", body=body)

    def cancel_algo_order(self, algo_id):
        return self._call("DELETE", "/capi/v3/algoOrder", params={"orderId": str(algo_id)})

    # ================= 下单 =================
    def place_order(self, inst_id, side, position_side, qty, ord_type="MARKET",
                    price=None, tp=None, sl=None, client_oid=None,
                    tp_working="CONTRACT_PRICE", sl_working="CONTRACT_PRICE"):
        """side: BUY/SELL ; position_side: LONG/SHORT
        开多 = BUY+LONG ; 开空 = SELL+SHORT ; 平多 = SELL+LONG ; 平空 = BUY+SHORT
        tp/sl 为触发价(可不传); 内联一到下单里, 无需单独条件单接口。"""
        sym = self.trade_symbol(inst_id)
        body = {"symbol": sym, "side": side.upper(), "positionSide": position_side.upper(),
                "type": ord_type.upper(), "quantity": str(self.round_qty(inst_id, qty)),
                "newClientOrderId": client_oid or self._gen_oid()}
        if ord_type.upper() == "LIMIT":
            body["timeInForce"] = "GTC"
            body["price"] = str(self.round_px(inst_id, price))
        if tp:
            body["tpTriggerPrice"] = str(self.round_trigger(inst_id, tp))
            body["TpWorkingType"] = tp_working
        if sl:
            body["slTriggerPrice"] = str(self.round_trigger(inst_id, sl))
            body["SlWorkingType"] = sl_working
        return self._call("POST", "/capi/v3/sim/order", body=body)

    @staticmethod
    def _gen_oid():
        # 1-36 位, 允许 [.A-Z:/a-z0-9_-]
        return f"nh-{int(time.time()*1000)}-{os.getpid()%1000}"

    @staticmethod
    def ok(st, j):
        """判断下单是否被受理: success=true 且无 errorCode"""
        if st != 200 or not isinstance(j, dict):
            return False
        if j.get("success") is True and not j.get("errorCode"):
            return True
        return False

    @staticmethod
    def err_of(st, j):
        if isinstance(j, dict):
            return f"http={st} code={j.get('errorCode') or j.get('code')} msg={j.get('errorMessage') or j.get('msg')}"
        return f"http={st}"

    # ================= 平仓(反向市价单) =================
    def close_position(self, inst_id, position_side, qty, client_oid=None):
        """反向市价单平仓: 持多→SELL+LONG ; 持空→BUY+SHORT"""
        ps = position_side.upper()
        side = "SELL" if ps == "LONG" else "BUY"
        return self.place_order(inst_id, side, ps, qty, ord_type="MARKET", client_oid=client_oid)

    # ================= 自检 =================
    def ping(self):
        """连通性 + 鉴权自检(用于云端部署验证)"""
        self.sync_time()
        r = {"configured": self.configured, "time_offset_ms": self._t_off}
        try:
            st, j = self.get_balance()
            r["balance_http"] = st
            r["balance_raw"] = json.dumps(j, ensure_ascii=False)[:300]
            r["susdt"] = self.balance_asset()
        except Exception as e:
            r["balance_err"] = f"{type(e).__name__}: {e}"
        try:
            st, j = self.get_positions_raw()
            r["pos_http"] = st
            r["positions_n"] = len(self.get_positions())
        except Exception as e:
            r["pos_err"] = f"{type(e).__name__}: {e}"
        return r
