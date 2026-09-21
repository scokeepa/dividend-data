#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
월배당 포트폴리오 설계실 — 시세·분배금 수집기

하는 일: tickers.txt 에 적힌 종목의 현재가와 최근 1년 분배금을 야후 파이낸스에서 받아
        data.js 한 파일로 만들어 커밋합니다. 페이지는 jsDelivr 를 통해 이 파일을 읽습니다.

data.js 를 .json 이 아니라 .js 로 내보내는 이유:
  발행된 아티팩트는 fetch 가 전부 막혀 있고 스크립트만 몇몇 CDN 에서 불러올 수 있습니다.
  jsDelivr 가 .js 를 application/javascript 로 서빙하므로 import() 로 읽을 수 있습니다.
  같은 내용을 .json 으로 두고 import attributes 로 읽는 방법은 CSP 에 막힙니다(실측 확인).
"""
import json, sys, time, datetime, pathlib, traceback
import yfinance as yf
import sources, merge

ROOT = pathlib.Path(__file__).parent
TICKERS = ROOT / "tickers.txt"
OUT = ROOT / "data.js"

# 국내 종목은 6자리 숫자 코드입니다. 야후에서는 .KS(코스피) / .KQ(코스닥) 를 붙여야 합니다.
def yahoo_symbol(t):
    if t.isdigit() and len(t) == 6:
        return t + ".KS"
    # 0008S0 처럼 문자가 섞인 국내 코드도 있습니다
    if len(t) == 6 and any(c.isdigit() for c in t) and t[0].isdigit():
        return t + ".KS"
    return t

def read_tickers():
    if not TICKERS.exists():
        print("tickers.txt 가 없습니다.", file=sys.stderr)
        return []
    out = []
    for line in TICKERS.read_text(encoding="utf-8").splitlines():
        line = line.split("#")[0].strip()
        if line:
            out.append(line.upper())
    # 중복 제거, 순서 유지
    seen, uniq = set(), []
    for t in out:
        if t not in seen:
            seen.add(t); uniq.append(t)
    return uniq

def ttm_dividends(tk, today):
    """최근 1년 분배금 합계와 지급 횟수, 배당락월.

    오늘부터 365일을 거꾸로 세면 배당 주기의 경계에서 한 번을 놓칩니다.
    예: VICI 는 분기 배당이고 배당락일이 3·6·9·12월 중순인데, 오늘이 9월 중순이면
    9월분이 아직 안 나와서 창에 3회만 들어오고 분배금이 25% 적게 잡힙니다.

    그래서 **가장 최근 배당락일에서 1년을 거슬러** 셉니다. 이러면 주기가 어떻든
    항상 꽉 찬 한 바퀴가 들어옵니다. 지급 주기를 추정해서 개수를 맞추는 방법도
    써봤지만, 월배당인데 분기로 잘못 추정되는 경우가 있어 더 위험했습니다.
    """
    try:
        d = tk.dividends
    except Exception:
        return None, 0, []
    if d is None or len(d) == 0:
        return None, 0, []

    pairs = sorted(
        ((ts.date() if hasattr(ts, "date") else ts), float(v))
        for ts, v in zip(d.index, d.values)
    )
    if not pairs:
        return None, 0, []

    anchor = pairs[-1][0]
    # 마지막 배당락이 1년도 더 지났으면 배당을 멈춘 종목입니다 — 오늘 기준으로 셉니다
    if (today - anchor).days > 365:
        anchor = today
    # 창을 358일로 잡습니다. 배당락일은 해마다 며칠씩 앞당겨지기 때문에
    # 365일로 자르면 작년 같은 분기 배당이 한 번 더 걸려 분배금이 부풀려집니다.
    # 103개 종목을 손으로 검증한 값과 대조해 폭을 고른 결과입니다:
    #   365일 → 25종목이 10% 넘게 틀림 / 358일 → 2종목 (둘 다 월배당↔분기배당 전환 중인 종목)
    start = anchor - datetime.timedelta(days=358)
    use = [p for p in pairs if start < p[0] <= anchor]
    if not use:
        return None, 0, []

    months = sorted({p[0].month for p in use})
    return float(sum(v for _, v in use)), len(use), months


def collect_one(t, today):
    sym = yahoo_symbol(t)
    tk = yf.Ticker(sym)
    row = {"t": t, "sym": sym}

    # 현재가 — fast_info 가 가장 가볍고, 실패하면 최근 종가로 넘어갑니다
    px = None
    try:
        fi = tk.fast_info
        px = fi.get("last_price") or fi.get("lastPrice") or fi.get("regularMarketPrice")
    except Exception:
        pass
    if not px:
        try:
            h = tk.history(period="5d")
            if len(h):
                px = float(h["Close"].dropna().iloc[-1])
        except Exception:
            pass
    if not px:
        return None
    row["px"] = round(float(px), 4)

    # 통화 — 국내는 KRW, 미국은 USD 로 떨어져야 정상입니다
    try:
        row["cur"] = (tk.fast_info.get("currency") or "").upper() or ("KRW" if sym.endswith((".KS", ".KQ")) else "USD")
    except Exception:
        row["cur"] = "KRW" if sym.endswith((".KS", ".KQ")) else "USD"

    # 최근 1년 분배금
    ttm, n, months = ttm_dividends(tk, today)
    if ttm is not None:
        row["ttm"] = round(ttm, 6)
        row["n"] = n            # 합산에 쓴 지급 횟수 = 연 지급 횟수
        row["xm"] = months      # 배당락 기준 월 — 지급월과 한 달 차이가 날 수 있습니다
    return row

def load_baseline():
    """직전 data.js 를 기준선으로 씁니다. 없으면 빈 값으로 시작합니다."""
    if not OUT.exists(): return {}
    try:
        prev = OUT.read_text(encoding="utf-8")
        d = json.loads(prev[prev.index("{"):prev.rindex("}") + 1])
        return d.get("quotes", {})
    except Exception:
        return {}

# 야후 사용 방식 — 환경변수 USE_YAHOO 로 바꿀 수 있습니다
#   fallback (기본) : GitHub·Hugging Face 소스로 못 채운 종목에만 야후를 부릅니다
#   off             : 야후를 아예 부르지 않습니다
#   on              : 예전처럼 전 종목을 야후에서도 받아 교차검증 표로 씁니다 (429 위험)
import os
USE_YAHOO = os.environ.get("USE_YAHOO", "fallback").strip().lower()

def main():
    tickers = read_tickers()
    if not tickers:
        sys.exit("수집할 종목이 없습니다.")
    today = datetime.date.today()
    baseline = load_baseline()

    # ── 1단계: 사용량 제한이 없는 소스 (GitHub 저장소 + Hugging Face 데이터셋) ──
    print("1단계 — GitHub·Hugging Face 소스 수집 (사용량 제한 없음)")
    externals = sources.fetch_all(tickers)

    # ── 2단계: 야후 — 기본은 비상용 ──────────────────────────────────────────
    own, failed = {}, []
    if USE_YAHOO == "on":
        need = list(tickers)
    elif USE_YAHOO == "off":
        need = []
    else:
        need = []
        for t in tickers:
            r = merge.merge_ticker(t, {}, None, externals)
            if not r.get("px") or not r.get("ttm"):
                need.append(t)
    print(f"\n2단계 — 야후 ({USE_YAHOO}): {len(need)}종목 요청")
    for i, t in enumerate(need, 1):
        try:
            row = collect_one(t, today)
            if row: own[t] = row
            else: failed.append(t)
        except Exception:
            failed.append(t)
        time.sleep(0.35)
    if need:
        print(f"    받음 {len(own)} · 실패 {len(failed)}")

    # ── 3단계: 합의 ──────────────────────────────────────────────────────────
    print("\n3단계 — 교차검증 후 합의")
    quotes = {}
    stats = {"단일소스": 0, "불일치": 0, "버려진값": 0, "카탈로그만": 0, "야후사용": len(own)}
    for t in tickers:
        base = baseline.get(t) or {}
        row = merge.merge_ticker(t, base, own.get(t), externals)
        if "px" not in row and "ttm" not in row:
            continue
        o = own.get(t) or {}
        for k in ("sym", "cur", "n"):
            if o.get(k) is not None: row[k] = o[k]
        if "pm" not in row and o.get("xm"): row["xm"] = o["xm"]
        if not row.get("n") and row.get("pm"): row["n"] = len(row["pm"])
        if not row.get("n") and base.get("n"): row["n"] = base["n"]
        if not row.get("cur"):
            row["cur"] = base.get("cur") or ("KRW" if yahoo_symbol(t).endswith((".KS", ".KQ")) else "USD")
        ps = [s for s in row.get("pxSrc", []) if s != "카탈로그"]
        ts = [s for s in row.get("ttmSrc", []) if s != "카탈로그"]
        if len(ps) <= 1 or len(ts) <= 1: stats["단일소스"] += 1
        if row.get("pxSpread") or row.get("ttmSpread"): stats["불일치"] += 1
        if row.get("dropped"): stats["버려진값"] += 1
        if not ps: stats["카탈로그만"] += 1
        quotes[t] = row

    if not quotes:
        sys.exit("한 종목도 확정하지 못했습니다 — data.js 를 덮어쓰지 않고 중단합니다.")
    if baseline and len(quotes) < len(baseline) * 0.6:
        sys.exit(f"결과가 급감했습니다({len(baseline)} → {len(quotes)}). 기존 data.js 를 지킵니다.")

    src_names = {k: v["name"] for k, v in externals.items()}
    src_names["yfinance"] = "야후 파이낸스 (비상용)"
    src_names["카탈로그"] = "페이지 내장 기준값"
    payload = {
        "generated": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "count": len(quotes),
        "yahoo": USE_YAHOO,
        "failed": failed,
        "sources": src_names,
        "sourceCounts": {k: len(v["px"]) + len(v["ttm"]) for k, v in externals.items()},
        "stats": stats,
        "quotes": quotes,
    }
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    OUT.write_text("export default " + body + ";\n", encoding="utf-8")
    print(f"\ndata.js 작성 완료 — {len(quotes)}종목, {OUT.stat().st_size:,} bytes")
    print(f"    야후 호출 {len(need)}종목 · 소스 1개뿐 {stats['단일소스']} · 불일치 {stats['불일치']}"
          f" · 이상치 제거 {stats['버려진값']} · 기준값만 {stats['카탈로그만']}")

if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        traceback.print_exc()
        sys.exit(1)
