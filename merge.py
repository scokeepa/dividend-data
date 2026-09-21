# -*- coding: utf-8 -*-
"""
여러 소스를 합쳐 하나의 값을 정합니다.

순서대로 폴백만 시키면 위험합니다 — 세 번째 소스가 틀린 값을 줘도 알 수가 없고,
사용자는 그 값이 어디서 왔는지조차 모릅니다. 그래서:

  1. 기준선(내장 카탈로그)에서 터무니없이 벗어난 값은 아예 버립니다.
     티커가 겹치는 다른 시장 상품이 섞여 들어오는 사고를 막는 장치입니다.
  2. 살아남은 값들의 중앙값을 씁니다. 한 소스가 틀려도 끌려가지 않습니다.
  3. 소스끼리 얼마나 벌어졌는지를 같이 기록합니다. 벌어졌으면 화면에 표시합니다.
"""

REJECT_RATIO = 0.25   # 기준선 대비 이 비율을 넘게 벗어나면 버립니다
DISAGREE = 0.03       # 소스 간 이 이상 벌어지면 '불일치'로 표시합니다

def _median(xs):
    s = sorted(xs)
    n = len(s)
    if n == 0: return None
    return s[n//2] if n % 2 else (s[n//2 - 1] + s[n//2]) / 2.0

def consensus(values, baseline=None):
    """values = [(소스키, 값), ...] → (합의값, 쓴 소스들, 벌어진 정도, 버린 소스들)"""
    vals = [(k, float(v)) for k, v in values if v is not None and float(v) > 0]
    if not vals:
        return None, [], 0.0, []

    dropped = []
    if baseline and baseline > 0:
        keep = []
        for k, v in vals:
            if abs(v - baseline) / baseline > REJECT_RATIO:
                dropped.append((k, v))
            else:
                keep.append((k, v))
        # 전부 버려졌다면 기준선 쪽이 낡았을 수 있습니다.
        # 그럴 땐 소스가 둘 이상 서로 동의하는 경우에만 받아들입니다.
        if not keep:
            if len(vals) >= 2:
                m = _median([v for _, v in vals])
                if m and all(abs(v - m) / m <= DISAGREE * 2 for _, v in vals):
                    keep, dropped = vals, []
            if not keep:
                return None, [], 0.0, dropped
        vals = keep

    nums = [v for _, v in vals]
    med = _median(nums)
    spread = (max(nums) - min(nums)) / med if med else 0.0
    return med, [k for k, _ in vals], spread, dropped

def merge_ticker(t, baseline, own, externals):
    """
    baseline  : 내장 카탈로그 값 {'px':..,'ttm':..}  — 기준선이자 최후의 보루
    own       : 이번에 yfinance 로 직접 받은 값
    externals : {소스키: {'px':{},'ttm':{},'pm':{}}}
    """
    px_in, ttm_in, pm_in = [], [], []
    if own:
        if own.get("px"):  px_in.append(("yfinance", own["px"]))
        if own.get("ttm"): ttm_in.append(("yfinance", own["ttm"]))
    for key, src in externals.items():
        if t in src["px"]:  px_in.append((key, src["px"][t]))
        if t in src["ttm"]: ttm_in.append((key, src["ttm"][t]))
        if t in src["pm"]:  pm_in.append((key, src["pm"][t]))

    bpx = (baseline or {}).get("px")
    bttm = (baseline or {}).get("ttm")
    px, px_src, px_spread, px_drop = consensus(px_in, bpx)
    ttm, ttm_src, ttm_spread, ttm_drop = consensus(ttm_in, bttm)

    # 지급월은 숫자가 아니라 집합이라 중앙값이 없습니다.
    # 가장 많은 소스가 동의한 조합을 씁니다.
    pm = None; pm_src = []
    if pm_in:
        tally = {}
        for k, months in pm_in:
            key = tuple(sorted(set(months)))
            tally.setdefault(key, []).append(k)
        best = max(tally.items(), key=lambda kv: (len(kv[1]), len(kv[0])))
        pm, pm_src = list(best[0]), best[1]

    out = {"t": t}
    if px is not None:
        out["px"] = round(px, 4); out["pxSrc"] = px_src
        if px_spread > DISAGREE: out["pxSpread"] = round(px_spread, 4)
    if ttm is not None:
        out["ttm"] = round(ttm, 6); out["ttmSrc"] = ttm_src
        if ttm_spread > DISAGREE: out["ttmSpread"] = round(ttm_spread, 4)
    if pm:
        out["pm"] = pm; out["pmSrc"] = pm_src
    dropped = px_drop + ttm_drop
    if dropped:
        out["dropped"] = [k for k, _ in dropped]
    # 기준선만 남고 아무 소스도 못 받은 경우
    if px is None and bpx: out["px"] = bpx; out["pxSrc"] = ["카탈로그"]
    if ttm is None and bttm: out["ttm"] = bttm; out["ttmSrc"] = ["카탈로그"]
    return out
