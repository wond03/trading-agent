# WEEX 数据镜像 (沙盒连不上 WEEX, 靠这个把数据搬进来)
# 用法:
#   python tools/weex_cache.py mirror [--days 120]   # 在 GitHub Actions 里跑(能直连 WEEX) → 写 data/weex/*.json
#   python tools/weex_cache.py pull                  # 在沙盒里跑 → 从仓库把镜像下载到本地缓存
import os, sys, json, time, base64, argparse
import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "engine"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import weex_client                                    # noqa: E402
from _fetch_cache import load_cache, save_cache, CACHE_DIR   # noqa: E402

DATA_DIR = os.path.join(ROOT, "data", "weex")
INSTS = ["BTC-USDT-SWAP", "XAU-USDT-SWAP"]
TFS = ["1H", "4H", "15m"]
CST = None


def T(ts):
    import datetime
    return datetime.datetime.fromtimestamp(ts, datetime.timezone(datetime.timedelta(hours=8))
                                           ).strftime("%m-%d %H:%M")


def mirror(days):
    now = int(time.time())
    start = now - days * 86400
    os.makedirs(DATA_DIR, exist_ok=True)
    for inst in INSTS:
        for tf in TFS:
            store = load_cache(inst, tf)
            t0 = time.time()
            try:                                       # ① 最近 1000 根(便宜, 每次都要)
                rows = weex_client.get_candles(inst, tf, 1000)
                for r in rows:
                    store[r[0]] = list(r[1:])
            except Exception as e:
                print(f"  !! {inst} {tf} 最近段失败: {type(e).__name__} {e}", flush=True)
            if (not store) or min(store) > start:       # ② 更早的历史(仅首次/缺口时)
                try:
                    rows = weex_client.get_range(inst, tf, start, now)
                    for r in rows:
                        store[r[0]] = list(r[1:])
                except Exception as e:
                    print(f"  !! {inst} {tf} 历史段失败: {type(e).__name__} {e}", flush=True)
            save_cache(inst, tf, store)
            json.dump({str(k): store[k] for k in sorted(store)},
                      open(os.path.join(DATA_DIR, f"{inst}_{tf}.json"), "w"))
            print(f"  {inst} {tf}: {len(store)} 根  {T(min(store))} ~ {T(max(store))} "
                  f"({time.time() - t0:.0f}s)", flush=True)


def pull():
    """从 GitHub Actions 最新一次 mirror 运行的【制品】下载 data/weex/*.json → 本地缓存"""
    tok = os.environ["GITHUB_TOKEN"]
    repo = "wond03/trading-agent"
    H = {"Authorization": f"token {tok}"}
    r = requests.get(f"https://api.github.com/repos/{repo}/actions/workflows/mirror_weex.yml/runs",
                     headers=H, params={"per_page": 5, "status": "success"}, timeout=60).json()
    runs = r.get("workflow_runs") or []
    if not runs:
        print("  没有成功的 mirror 运行"); return
    rid = runs[0]["id"]
    arts = requests.get(f"https://api.github.com/repos/{repo}/actions/runs/{rid}/artifacts",
                        headers=H, timeout=60).json().get("artifacts") or []
    if not arts:
        print(f"  运行 {rid} 没有制品"); return
    aid = arts[0]["id"]
    z = requests.get(f"https://api.github.com/repos/{repo}/actions/artifacts/{aid}/zip",
                     headers=H, timeout=180, allow_redirects=True)
    z.raise_for_status()
    import io, zipfile
    os.makedirs(CACHE_DIR, exist_ok=True)
    n = 0
    for name in zipfile.ZipFile(io.BytesIO(z.content)).namelist():
        base = os.path.basename(name)
        if not base.endswith(".json"):
            continue
        raw = zipfile.ZipFile(io.BytesIO(z.content)).read(name)
        open(os.path.join(CACHE_DIR, base), "wb").write(raw)
        print(f"  {base}: {len(json.loads(raw))} 根")
        n += 1
    print(f"  已从 run {rid} 同步 {n} 个文件 → {CACHE_DIR}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["mirror", "pull"])
    ap.add_argument("--days", type=int, default=120)
    a = ap.parse_args()
    print(f"[weex_cache] {a.mode} days={a.days}", flush=True)
    (mirror(a.days) if a.mode == "mirror" else pull())
