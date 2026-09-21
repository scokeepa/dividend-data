# -*- coding: utf-8 -*-
"""
외부 데이터 소스들.

각 함수는 {티커: 값} 딕셔너리 두 개(주가, 분배금)를 돌려줍니다.
하나가 죽어도 나머지로 굴러가야 하므로, 실패는 예외로 터뜨리지 않고 빈 결과로 돌려줍니다.

여기 있는 소스는 전부 실제로 받아서 내 103종목과 대조해 본 것들입니다.
탈락시킨 것:
  - albertored/etfdb      유럽 UCITS 전용. SPYI 가 NEOS 가 아니라 State Street 상품이라
                          조용히 다른 펀드 값이 들어갑니다. 가장 위험한 유형.
  - cpasuyong etf_database.json  파일 안에 리터럴 NaN 이 3,442개라 JSON 파싱이 터집니다.
  - hck1205/snowball-income      cron 은 매일인데 PR 병합을 사람이 해야 해서 한 달씩 밀립니다.
  - zyhe16, sgdividends, jhirgit ETF 미포함(개별주만)
"""
import csv, io, json, urllib.request, urllib.error

TIMEOUT = 45
UA = {"User-Agent": "dividend-data-collector/1.0"}

def _get(url, timeout=TIMEOUT):
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", "replace")
    except Exception as e:
        print(f"    소스 실패 {url.split('/')[-1]}: {type(e).__name__}")
        return ""

def _f(v):
    try:
        v = float(str(v).replace(",", "").strip())
        return v if v > 0 else None
    except Exception:
        return None

GH = "https://cdn.jsdelivr.net/gh/"

# ── 1. ttokjaeTV — 미국 주가 (30분마다 갱신, 커버리지 최고) ────────────────────
def ttokjae_us_prices():
    b = _get(GH + "ttokjaeTV/portfolio-sheet-data@master/data/us_prices.csv")
    px = {}
    for r in csv.DictReader(io.StringIO(b)):
        t = (r.get("티커") or "").strip().upper()
        v = _f(r.get("현재가USD"))
        if t and v: px[t] = v
    return px, {}, {}

# ── 2. ttokjaeTV — 미국 분배금 + 지급월 ──────────────────────────────────────
def ttokjae_us_divs():
    b = _get(GH + "ttokjaeTV/portfolio-sheet-data@master/data/us_dividends.csv")
    ttm, pm = {}, {}
    for r in csv.DictReader(io.StringIO(b)):
        t = (r.get("티커") or "").strip().upper()
        if not t: continue
        v = _f(r.get("연배당USD"))
        if v: ttm[t] = v
        raw = (r.get("지급월") or "").strip()
        if raw:
            ms = [int(x) for x in raw.split("|") if x.strip().isdigit() and 1 <= int(x) <= 12]
            if ms: pm[t] = sorted(set(ms))
    return {}, ttm, pm

# ── 3. ttokjaeTV — 국내 ETF 주가 ────────────────────────────────────────────
def ttokjae_kr_prices():
    b = _get(GH + "ttokjaeTV/portfolio-sheet-data@master/data/etf_prices.csv")
    px = {}
    for r in csv.DictReader(io.StringIO(b)):
        c = (r.get("종목코드") or "").strip().upper().zfill(6)
        v = _f(r.get("현재가"))
        if c and v: px[c] = v
    return px, {}, {}

# ── 4. ttokjaeTV — 국내 ETF 분배금 (과세표준액까지) ──────────────────────────
def ttokjae_kr_divs():
    b = _get(GH + "ttokjaeTV/portfolio-sheet-data@master/data/etf_tax_base.json")
    ttm, pm = {}, {}
    try:
        d = json.loads(b).get("data", {})
    except Exception:
        return {}, {}, {}
    for code, rows in d.items():
        if not rows: continue
        c = str(code).zfill(6)
        # [배당락일, 분배금, 과세표준액] 최신순 — 최근 12개월치를 더합니다
        try:
            newest = str(rows[0][0])[:4]
            tot, months = 0.0, []
            for row in rows[:14]:
                y = str(row[0])[:4]
                if not y.isdigit() or int(newest) - int(y) > 1: break
                amt = _f(row[1])
                if amt is None: continue
                tot += amt
                mm = str(row[0]).replace("-", "/").split("/")
                if len(mm) >= 2 and mm[1].isdigit(): months.append(int(mm[1]))
                if len(months) >= 12: break
            if tot > 0: ttm[c] = round(tot, 4)
            if months: pm[c] = sorted(set(months))
        except Exception:
            continue
    return {}, ttm, pm

# ── 5. Kimjaeohong — 미국 주가·분배금 (매일, 독립 배치) ─────────────────────
def kimjaeohong():
    b = _get(GH + "Kimjaeohong/dividend@main/data/us_dividends.json")
    px, ttm = {}, {}
    try:
        for r in json.loads(b).get("tickers", []):
            t = (r.get("symbol") or r.get("ticker") or "").strip().upper()
            if not t: continue
            v = _f(r.get("price"));        
            if v: px[t] = v
            v2 = _f(r.get("ttm_dividend"))
            if v2: ttm[t] = v2
    except Exception:
        pass
    return px, ttm, {}

# ── 6. holaclea — SCHD 운용사 공식 (유일하게 야후 계열이 아닌 소스) ─────────
def holaclea_schd():
    b = _get(GH + "holaclea/dividend-data-toolkit@main/schd-payments-as-listed.csv")
    rows = [r for r in csv.DictReader(io.StringIO(b))]
    amts = []
    for r in rows[:4]:
        v = _f(r.get("distribution_per_share_usd"))
        if v: amts.append(v)
    return ({}, {"SCHD": round(sum(amts), 6)}, {}) if len(amts) == 4 else ({}, {}, {})

# ── 7. iankim1306 — 국내 ETF 분배금 (DART 공시 원천) ───────────────────────
def iankim_krx():
    b = _get(GH + "iankim1306/dividendcal-data@main/data.json")
    ttm, pm = {}, {}
    try:
        d = json.loads(b)
    except Exception:
        return {}, {}, {}
    buckets = {}
    for e in d.get("etfs", []):
        c = str(e.get("code") or "").zfill(6)
        amt = _f(e.get("dps"))
        rd = str(e.get("recordDate") or e.get("payDate") or "")
        if c and amt and len(rd) >= 6:
            buckets.setdefault(c, []).append((rd, amt))
    for c, rows in buckets.items():
        rows.sort(reverse=True)
        newest = rows[0][0][:4]
        tot, months = 0.0, []
        for rd, amt in rows[:14]:
            if not rd[:4].isdigit() or int(newest) - int(rd[:4]) > 1: break
            tot += amt
            if rd[4:6].isdigit(): months.append(int(rd[4:6]))
            if len(months) >= 12: break
        if tot > 0: ttm[c] = round(tot, 4)
        if months: pm[c] = sorted(set(months))
    return {}, ttm, pm


# ── 8. defeatbeta-api — 야후 데이터를 Hugging Face 에 올려둔 데이터셋 (레이트리밋 없음) ──
#    https://github.com/defeat-beta/defeatbeta-api
#    야후를 직접 긁지 않고 정리된 스냅샷을 DuckDB 로 조회하므로 429 차단을 받지 않습니다.
#    단, 개별 주식 데이터셋이라 **ETF 는 거의 없습니다.** (SPY·QQQ 정도만 있고
#    SCHD·JEPI·QYLD 같은 배당 ETF 는 없음 — 실측 기준 이 저장소 103종목 중 7종목만 커버:
#    O, ARCC, MAIN, AGNC, STAG, WPC, VICI.) 그래서 야후를 대체하지 않고 앞에 세워둡니다.
def defeatbeta(tickers):
    try:
        import logging, warnings, datetime
        warnings.filterwarnings("ignore")
        logging.getLogger().setLevel(logging.ERROR)
        from defeatbeta_api.data.ticker import Ticker
    except Exception as e:
        print(f"    defeatbeta 미설치 — 건너뜀 ({type(e).__name__})")
        return {}, {}, {}
    us = [t for t in tickers if not (len(t) == 6 and t[0].isdigit())]
    if not us:
        return {}, {}, {}
    try:
        probe = Ticker(us[0])
        db, hf = probe.duckdb_client, probe.huggingface_client
        up = hf.get_url_path("stock_prices")
        ud = hf.get_url_path("stock_dividend_events")
        inl = ",".join("'" + t.replace("'", "") + "'" for t in us)
        pxdf = db.query(f"""
            SELECT symbol, close FROM (
              SELECT symbol, close,
                     row_number() OVER (PARTITION BY symbol ORDER BY report_date DESC) AS rn
              FROM '{up}' WHERE symbol IN ({inl})
            ) WHERE rn = 1""")
        dvdf = db.query(f"""
            SELECT symbol, report_date, amount FROM '{ud}'
            WHERE symbol IN ({inl}) AND CAST(report_date AS DATE) >= current_date - INTERVAL 800 DAY""")
    except Exception as e:
        print(f"    defeatbeta 조회 실패 ({type(e).__name__}: {str(e)[:80]})")
        return {}, {}, {}

    px = {r.symbol: float(r.close) for r in pxdf.itertuples() if r.close and r.close > 0}
    ttm, pm = {}, {}
    by = {}
    for r in dvdf.itertuples():
        try:
            d = datetime.date.fromisoformat(str(r.report_date)[:10])
            if r.amount and float(r.amount) > 0:
                by.setdefault(r.symbol, []).append((d, float(r.amount)))
        except Exception:
            continue
    for sym, pairs in by.items():
        pairs.sort()
        anchor = pairs[-1][0]
        if (datetime.date.today() - anchor).days > 365:
            continue                      # 배당을 멈춘 종목
        start = anchor - datetime.timedelta(days=358)   # collect.py 와 같은 창
        use = [p for p in pairs if start < p[0] <= anchor]
        if use:
            ttm[sym] = round(sum(v for _, v in use), 6)
            pm[sym] = sorted({p[0].month for p in use})   # 배당락 기준 월
    return px, ttm, {}

SOURCES = [
    ("ttokjae-us-px",  "ttokjaeTV 미국 주가",        ttokjae_us_prices),
    ("ttokjae-us-div", "ttokjaeTV 미국 분배금",       ttokjae_us_divs),
    ("ttokjae-kr-px",  "ttokjaeTV 국내 주가",        ttokjae_kr_prices),
    ("ttokjae-kr-div", "ttokjaeTV 국내 분배금",       ttokjae_kr_divs),
    ("kimjaeohong",    "Kimjaeohong 미국",          kimjaeohong),
    ("holaclea",       "holaclea SCHD 공식",        holaclea_schd),
    ("iankim-krx",     "iankim1306 국내 분배금",      iankim_krx),
    ("defeatbeta",     "defeatbeta (HF 데이터셋)",    defeatbeta),
]

def fetch_all(tickers=()):
    """모든 외부 소스를 받아옵니다. 하나가 죽어도 나머지는 살립니다."""
    out = {}
    for key, name, fn in SOURCES:
        try:
            px, ttm, pm = fn(list(tickers)) if fn is defeatbeta else fn()
        except Exception as e:
            print(f"    {name}: 예외 {type(e).__name__}")
            px, ttm, pm = {}, {}, {}
        out[key] = {"name": name, "px": px, "ttm": ttm, "pm": pm}
        print(f"    {name:26} 주가 {len(px):>4} · 분배금 {len(ttm):>4} · 지급월 {len(pm):>4}")
    return out
