# 暗夜猎手 (NightHunter) · WEEX 模拟盘【适配层】
# 目的: 把 WEEX 模拟盘包装成 engine/main.py 原有交易接口的形状, 让主循环的改动降到最小。
# ★2026-10-04 用户裁定: 下单从 OKX 整体切到 WEEX 模拟盘, 不再保留 OKX。
#
# 关键差异(与 OKX 比):
#   · 数量单位 = 【币的数量】(0.0059 BTC), 不是张数
#   · 止盈止损 = 下单时【内联】提交(tpTriggerPrice/slTriggerPrice), 没有独立条件单接口
#     → supports_algo = False, main 里"挂/撤条件单/自愈补挂"全部跳过
#   · 无撤单接口, 无订单详情接口 → get_order() 改从 /sim/order/history 里按 orderId 反查
#   · 平仓 = 反向市价单
import json

from weex_trade import WeexTrade, SYMBOL_MAP

_STATE_MAP = {"FILLED": "filled", "PARTIALLY_FILLED": "partially_filled",
              "CANCELED": "canceled", "CANCELLED": "canceled", "NEW": "live",
              "REJECTED": "canceled", "EXPIRED": "canceled"}


class WeexBroker:
    """模拟盘交易适配器(形状对齐 OkxClient); supports_algo=False 表示无独立条件单接口"""

    # ★2026-10-05: 找到 WEEX 官方条件单接口 → 打开"自愈补挂/读回自检"(不再内联-only)
    supports_algo = True
    HOST = "api-contract.weex.com (sim)"

    def __init__(self, api_key=None, secret=None, passphrase=None):
        self.t = WeexTrade(api_key, secret, passphrase)
        self._oid_log = {}          # orderId -> clientOrderId

    # ---------- 配置 / 连通 ----------
    @property
    def configured(self):
        return self.t.configured

    def ping(self):
        self.t.sync_time()
        self.t.load_specs()
        r = self.t.ping()
        r["specs_loaded"] = len(self.t._spec)
        return r

    # ---------- 查询 ----------
    def get_positions(self, inst_id=None):
        """返回 OKX 形状: {"code":"0","data":[{instId,posSide,pos,avgPx,margin,lever,liqPx,upl}]}"""
        out = []
        for x in self.t.get_positions():
            sym = (x.get("symbol") or "").upper()
            inst = next((k for k, v in SYMBOL_MAP.items() if v[0].upper() == sym), None)
            if not inst:
                continue
            try:
                size = abs(float(x.get("size") or 0))
                ov = float(x.get("openValue") or 0)
            except Exception:
                continue
            avg = (ov / size) if size else 0.0
            out.append({"instId": inst, "posSide": (x.get("side") or "").lower(), "pos": str(size),
                        "avgPx": str(avg), "margin": x.get("marginSize") or x.get("isolatedMargin") or "0",
                        "lever": x.get("leverage"), "liqPx": x.get("liquidatePrice") or "0",
                        "upl": x.get("unrealizePnl")})
        if inst_id:
            out = [o for o in out if o["instId"] == inst_id]
        return {"code": "0", "data": out}

    def get_order(self, inst_id, ord_id):
        """无订单详情接口 → 从历史委托里按 orderId 反查(返回 OKX 形状)"""
        try:
            st, j = self.t.get_order_history(inst_id, limit=50)
            rows = j if isinstance(j, list) else (j.get("data") or [])
            for x in rows:
                if str(x.get("orderId")) == str(ord_id):
                    return {"code": "0", "data": [{
                        "ordId": str(ord_id),
                        "state": _STATE_MAP.get((x.get("status") or "").upper(), "live"),
                        "accFillSz": x.get("executedQty") or "0",
                        "avgPx": x.get("avgPrice") or "0",
                        "sz": x.get("origQty") or "0"}]}
        except Exception as e:
            print(f"[查询订单] {inst_id} {ord_id} 失败 {type(e).__name__}")
        return {"code": "0", "data": [{"ordId": str(ord_id), "state": "live", "accFillSz": "0"}]}

    def get_balance(self):
        return self.t.get_balance()

    def get_fills(self, inst_type="SWAP", inst_id=None, limit=20):
        st, j = self.t.get_order_history(inst_id, limit=limit)
        return {"code": "0", "data": (j if isinstance(j, list) else (j.get("data") or []))}

    # ---------- 下单 / 平仓 ----------
    def place_order(self, inst_id, side, sz, td_mode=None, ord_type="market",
                    pos_side=None, tp=None, sl=None, client_oid=None):
        """sz = 币的数量。tp/sl 为触发价(内联到本次下单)。返回 OKX 形状 code/sCode。"""
        st, j = self.t.place_order(
            inst_id, "BUY" if str(side).lower() == "buy" else "SELL",
            (pos_side or "LONG").upper(), sz,
            ord_type=("MARKET" if str(ord_type).lower() == "market" else "LIMIT"),
            tp=tp, sl=sl, client_oid=client_oid)
        if self.t.ok(st, j):
            oid = j.get("orderId")
            self._oid_log[str(oid)] = j.get("clientOrderId")
            print(f"[WEEX下单] {inst_id} {side} qty={sz} tp={tp} sl={sl} → orderId={oid}")
            return {"code": "0", "data": [{"ordId": str(oid), "sCode": "0", "sMsg": ""}]}
        msg = self.t.err_of(st, j)
        print(f"[WEEX下单失败] {inst_id} {side} qty={sz} → {msg} | {json.dumps(j, ensure_ascii=False)[:240]}")
        return {"code": "1", "data": [{"ordId": "", "sCode": "-1", "sMsg": msg}]}

    def close_position(self, inst_id, side, sz, td_mode=None, pos_side=None):
        """反向市价单平仓(side 传与持仓相反方向, 与 OKX 调用习惯一致)"""
        return self.place_order(inst_id, side, sz, ord_type="market", pos_side=pos_side)

    # ---------- 杠杆: sim 无接口 → 空实现 ----------
    def set_leverage(self, inst_id, lever, mgn_mode="isolated", pos_side=None):
        return {"code": "0", "data": [{"lever": str(lever)}], "msg": "WEEX sim 无设杠杆接口(以 App 设置为准)"}

    # ---------- 条件单 ★2026-10-05: 已找到 WEEX 条件单接口, 改为真实实现 ----------
    #   openAlgoOrders(查) / algoOrder(补挂/撤) / modifyTpSlOrder(改价)
    def algo_orders(self, inst_id=None):
        """交易所端真实条件单(原始行)"""
        st, rows = self.t.algo_orders(inst_id)
        return {"code": "0", "data": rows}

    def algo_ids(self, inst_id):
        """该品种当前条件单的 algoId 集合。
        ★查询失败(非200)返回 None = "未知" → main 里 `if _live is not None` 会【跳过补挂】,
          避免"查不到"被误判成"没有挂单"而重复补挂(实测: 该接口传 symbol 会返回空, 必须全量拉)。"""
        st, rows = self.t.algo_orders(inst_id)
        if st != 200:
            return None
        return {str(x.get("algoId")) for x in rows if x.get("algoId")}

    def tp_sl_open(self, inst_id, pos_side=None):
        """★读回交易所真实保护单: {"tp":行, "sl":行}(无则 None)。用于自检/对账。查询失败返回 None。"""
        st, rows = self.t.algo_orders(inst_id)
        if st != 200:
            return None
        out = {"tp": None, "sl": None}
        ps = (pos_side or "").upper()
        for x in rows:
            if ps and (x.get("positionSide") or "").upper() != ps:
                continue
            ot = (x.get("orderType") or "").upper()
            if ot == "TAKE_PROFIT_MARKET" and out["tp"] is None:
                out["tp"] = x
            elif ot == "STOP_MARKET" and out["sl"] is None:
                out["sl"] = x
        return out

    def _algo_resp(self, j):
        """把条件单接口返回规整成 OKX 形状(含 algoId)。
        ★注意: 失败时返回 {"code":-1141,"msg":...} (没有 success/errorCode 字段) → 必须用 code 判断, 不能只看 success。"""
        if isinstance(j, dict):
            _has_err = (j.get("success") is False) or bool(j.get("errorCode")) \
                or (isinstance(j.get("code"), (int, str)) and str(j.get("code")) not in ("0", ""))
            if not _has_err and (j.get("orderId") or j.get("success") is True):
                return {"code": "0", "data": [{"sCode": "0", "sMsg": "", "algoId": j.get("orderId")}]}
            msg = j.get("errorMessage") or j.get("msg") or str(j)[:150]
        else:
            msg = str(j)[:150]
        return {"code": "1", "data": [{"sCode": "-1", "sMsg": msg}]}

    def place_tp_order(self, inst_id, pos_side, sz, td_mode=None, px=None):
        side = "SELL" if str(pos_side).lower() == "long" else "BUY"
        st, j = self.t.place_algo(inst_id, side, pos_side, sz, "TAKE_PROFIT_MARKET", px)
        print(f"[WEEX补挂TP] {inst_id} sz={sz} px={px} → http={st} {json.dumps(j, ensure_ascii=False)[:220]}")
        return self._algo_resp(j)

    def place_sl_order(self, inst_id, pos_side, sz, td_mode=None, px=None):
        side = "SELL" if str(pos_side).lower() == "long" else "BUY"
        st, j = self.t.place_algo(inst_id, side, pos_side, sz, "STOP_MARKET", px)
        print(f"[WEEX补挂SL] {inst_id} sz={sz} px={px} → http={st} {json.dumps(j, ensure_ascii=False)[:220]}")
        return self._algo_resp(j)

    def modify_tp_sl(self, algo_id, px):
        """改已有条件单触发价"""
        st, j = self.t.modify_tp_sl(algo_id, px)
        print(f"[WEEX改价] algoId={algo_id} → {px} http={st} {json.dumps(j, ensure_ascii=False)[:200]}")
        return self._algo_resp(j)

    def get_algo_pending(self, inst_type="SWAP", inst_id=None):
        return self.algo_orders(inst_id)

    def cancel_algo(self, inst_id, algo_id):
        st, j = self.t.cancel_algo_order(algo_id)
        okk = isinstance(j, dict) and j.get("success") is not False and not j.get("errorCode")
        print(f"[WEEX撤条件单] algoId={algo_id} http={st} {json.dumps(j, ensure_ascii=False)[:200]}")
        return {"code": "0" if okk else "1", "msg": "" if okk else str(j)[:150],
                "data": [{"algoId": str(algo_id), "sCode": "0" if okk else "-1"}]}

    def cancel_order(self, inst_id, ord_id):
        return {"code": "1", "msg": "WEEX sim 无撤单接口"}

    # ---------- 规格相关 ----------
    def round_sz(self, inst_id, sz):
        return self.t.round_qty(inst_id, sz)

    def get_tick(self, inst_id):
        p = int((self.t.spec(inst_id) or {}).get("pricePrecision", 1))
        return 10 ** (-p)

    def round_tick(self, inst_id, px):
        return self.t.round_px(inst_id, px)

    def spec_of(self, inst_id):
        return self.t.spec(inst_id)

    # ---------- 兼容位 ----------
    def _get(self, path, params=None):
        return {"code": "1", "msg": "WeexBroker 不支持通用 _get"}

    def _post(self, path, body):
        return {"code": "1", "msg": "WeexBroker 不支持通用 _post"}
