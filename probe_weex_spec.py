# 探测⑤: 取 BTCUSDT / XAUTUSDT 规格【全字段】, 找止盈止损触发价要求的 stepSize / 精度字段
import json
import requests

BASE = "https://api-contract.weex.com"
H = {"User-Agent": "nighthunter/1.0"}
r = requests.get(BASE + "/capi/v3/market/exchangeInfo", headers=H, timeout=40)
syms = r.json().get("symbols") or []
for want in ("XAUTUSDT", "BTCUSDT"):
    for s in syms:
        if s.get("symbol") == want:
            print("=" * 70)
            print(f"### {want} 全字段:")
            print(json.dumps(s, ensure_ascii=False, indent=1))
            print(f"### {want} 含 step/tick/trigger/price 的字段:")
            for k, v in s.items():
                if any(t in k.lower() for t in ("step", "tick", "trigger", "price", "size", "precision")):
                    print(f"    {k} = {v}")
            break
print("完成")
