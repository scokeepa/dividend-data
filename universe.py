# -*- coding: utf-8 -*-
"""
전 종목 파일 — 페이지 목록에 없는 종목도 자동으로 시세를 채우기 위한 것입니다.

미국 ~12,000종목, 국내 ETF ~1,200종목을 통째로 한 파일에 넣으면 1MB 가 넘어서
페이지가 매번 받기 부담스럽습니다. 그래서 첫 글자별로 쪼개 둡니다.
  universe/us-A.js … us-Z.js, us-_.js   미국 (티커 첫 글자)
  universe/kr.js                         국내 ETF 전체
페이지는 사용자가 목록에 없는 종목을 찾을 때 그 글자 파일 하나만 불러옵니다.

항목 형식 (용량을 줄이려고 배열로 둡니다)
  미국: [종목명, 구분(E=ETF,S=주식), 주가USD, 연분배금USD, 연지급횟수, 지급월비트]
  국내: [종목명, 자산군, 주가원, 연분배금원, 연지급횟수, 지급월비트, 총보수%, 시장(D/F/M)]
지급월비트: 1월=1, 2월=2, 3월=4 … 12월=2048 을 더한 값.
"""
import json, pathlib, datetime, statistics

def _mask(months):
    b = 0
    for m in months or []:
        if 1 <= int(m) <= 12: b |= 1 << (int(m) - 1)
    return b

def _num(v, nd):
    if v is None: return 0
    v = float(v)
    return int(v) if v == int(v) and abs(v) >= 100 else round(v, nd)

def build(externals, meta, outdir):
    outdir = pathlib.Path(outdir); outdir.mkdir(exist_ok=True)
    us_px   = externals.get("ttokjae-us-px", {}).get("px", {})
    us_div  = externals.get("ttokjae-us-div", {})
    kim     = externals.get("kimjaeohong", {})
    kr_px   = externals.get("ttokjae-kr-px", {}).get("px", {})
    kr_d1   = externals.get("ttokjae-kr-div", {})
    kr_d2   = externals.get("iankim-krx", {})

    shards = {}
    for t, px in us_px.items():
        m = meta["us"].get(t, {})
        vals = [v for v in (us_div["ttm"].get(t), kim.get("ttm", {}).get(t)) if v]
        ttm = statistics.median(vals) if vals else 0
        pm = us_div["pm"].get(t) or []
        n = m.get("n") or len(pm) or 0
        key = t[0] if t[0].isalpha() else "_"
        shards.setdefault(key, {})[t] = [m.get("name", ""), m.get("kind", "S"),
                                        _num(px, 4), _num(ttm, 6), n, _mask(pm)]

    kr = {}
    for c, px in kr_px.items():
        m = meta["kr"].get(c, {})
        vals = [v for v in (kr_d1["ttm"].get(c), kr_d2["ttm"].get(c)) if v]
        ttm = statistics.median(vals) if vals else 0
        pm = kr_d1["pm"].get(c) or kr_d2["pm"].get(c) or []
        kr[c] = [m.get("name", ""), m.get("cls", ""), _num(px, 2), _num(ttm, 2),
                 len(pm), _mask(pm), m.get("er", 0), m.get("mkt", "M")]

    gen = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    def write(name, data, updated):
        body = json.dumps({"g": gen, "u": updated, "d": data}, ensure_ascii=False, separators=(",", ":"))
        (outdir / name).write_text("export default " + body + ";\n", encoding="utf-8")
        return (outdir / name).stat().st_size

    sizes = {}
    for k, data in sorted(shards.items()):
        sizes[f"us-{k}.js"] = write(f"us-{k}.js", data, meta.get("usUpdated", ""))
    sizes["kr.js"] = write("kr.js", kr, meta.get("krUpdated", ""))
    index = {"g": gen, "us": sum(len(v) for v in shards.values()), "kr": len(kr),
             "shards": sorted(sizes), "usPriceAt": meta.get("usUpdated", ""),
             "usDivAt": meta.get("usDivUpdated", ""), "krAt": meta.get("krUpdated", "")}
    (outdir / "index.js").write_text("export default " + json.dumps(index, ensure_ascii=False) + ";\n", encoding="utf-8")
    return index, sizes
