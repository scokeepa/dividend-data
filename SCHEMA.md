# 데이터 스키마

이 프로젝트에는 별도 DB 서버가 없습니다. **GitHub 저장소의 파일이 곧 DB**이고, 페이지는 jsDelivr CDN으로 이 파일들을 읽기만 합니다.
사용자 설정은 서버에 저장하지 않고 **설정 코드(DIV1-…)** 문자열로 주고받습니다.

| 파일 | 역할 | 누가 쓰나 | 갱신 |
|---|---|---|---|
| `data.js` | 추적 종목(tickers.txt) 시세·분배금 합의값 | collect.py | 하루 4번 (Actions) |
| `universe/index.js` + `universe/*.js` | 미국 12,000+ · 국내 1,100+ 전 종목 요약 | universe.py | 하루 4번 |
| `yahoo_cache.json` | 야후 순환 조회 결과 캐시 (수집기 내부용) | collect.py | 하루 4번 |
| `tax.js` | 세율·공제·보험료율·계좌 한도 (시행일별) | 월간 점검 작업 / 수동 | 매달 1일 |
| `tickers.txt` | 매일 정밀 추적할 종목 목록 (한 줄에 하나) | 사람 | 필요 시 |

모든 `.js` 데이터 파일은 `export default { ... }` 형태의 ES 모듈입니다(아티팩트 CSP가 JSON·fetch를 막아 `import()`만 가능하기 때문).

---

## 1. data.js

```js
export default {
  generated: "2026-09-21T05:06:27+00:00",   // UTC 수집 시각
  count: 103,                               // quotes 항목 수
  yahoo: "fallback",                        // 야후 모드: fallback | off | on
  failed: [],                               // 모든 소스에서 실패한 티커
  sources: { "<소스키>": "<표시 이름>", ... },
  sourceCounts: { "<소스키>": <보유 종목 수>, ... },
  stats: { 단일소스, 불일치, 버려진값, 카탈로그만, 야후사용, 야후캐시 },  // 건수
  quotes: {
    "QYLD": {
      t: "QYLD",
      px: 18.55,            // 현재가 (cur 통화)
      pxSrc: ["ttokjae-us-px","kimjaeohong"],   // 합의에 쓰인 가격 소스
      ttm: 2.126,           // 최근 1년 주당 분배금 합 (마지막 배당락일 기준 358일 창)
      ttmSrc: ["ttokjae-us-div","kimjaeohong","yahoo-cache"],
      pm: [1,2,...,12],     // 분배(배당락) 월
      pmSrc: ["ttokjae-us-div"],
      n: 11,                // 1년간 지급 횟수
      cur: "USD"            // USD | KRW
    }
  }
};
```
합의 규칙(merge.py): 소스별 값의 **중앙값**, 기준값 대비 25% 넘게 벗어난 값은 버림, 소스 간 3% 이상 차이는 `불일치`로 집계.

## 2. universe/

`index.js`
```js
export default { g: "<UTC 생성시각>", us: 12290, kr: 1171, shards: ["kr.js","us-A.js", ... "us-Z.js"] }
```
샤드 파일(`kr.js`, `us-A.js` … 티커 첫 글자별)
```js
export default { g: "<UTC>", u: "2026-09-21 12:31" /* KST 표시용 */, d: { "<티커>": [ ...행 ] } }
```
행은 용량을 줄이려고 배열입니다.

| 시장 | 인덱스 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 |
|---|---|---|---|---|---|---|---|---|
| 미국 | 이름 | 종류(ETF/Stock…) | 가격 USD | TTM 분배금 | 연 지급횟수 | 지급월 비트마스크 | — | — |
| 국내 | 이름 | 분류(주식/채권…) | 가격 KRW | TTM 분배금 | 연 지급횟수 | 지급월 비트마스크 | 총보수 % | 과세구분 D/F/M |

- 지급월 비트마스크: 1월 = bit0 … 12월 = bit11 (예: 분기 3·6·9·12월 = 0b100100100100 = 2340)
- 과세구분: D 국내주식형(매매차익 비과세), F 해외형, M 기타/혼합

## 3. yahoo_cache.json (수집기 내부)

```json
{ "0005A0": { "at": "2026-09-21", "n": 12, "px": 9460.0, "ttm": 1481.0, "xm": [1,2,...,12] } }
```
야후를 한 번에 `YAHOO_ROTATE`(기본 15)종목씩 가장 오래된 것부터 조회해 쌓습니다. 10일 이내 값만 `yahoo-cache` 소스로 분배금 합의에 참여합니다.

## 4. tax.js

```js
export default {
  schema: 1,
  checked: "2026-09-21",          // 마지막 점검일 (45일 넘으면 페이지가 경고)
  note: "...",
  sets: [ {                       // 시행일별 세트. 페이지는 from ≤ 오늘 중 가장 최근 것을 사용
    from: "2026-07-01", label: "2026년 하반기",
    tax: { THRESHOLD, WHT, LOCAL, US_WHT, KR_WHT, REIT_SEP, BASIC_DEDUCT,
           HEALTH_RATE, LTC_RATE, HEALTH_FIN_FLOOR, HEALTH_EXTRA_FLOOR },
    brackets: [[상한, 세율, 누진공제], ..., ["Infinity", 0.45, 65940000]],   // 소득세법 §55
    earned: { steps: [[상한, 기본공제, 초과율], ...], cap,                  // §47 근로소득공제
              credit: { bp, lo, hi, caps: [[총급여상한, 한도, 감소율, 최저한도], ...] } },  // §59
    nps: { floor, cap, period, byYear: { "2026": 0.095, ..., "2033": 0.13 } },     // 국민연금
    acct: { isaGen, isaLow, pensionSv, irp: { capYear, capTotal, exempt, excess } },
    pensionWithdraw: [[나이이상, 연금소득세율], ...]
  } ],
  sources: { "<항목>": { law: "<조문>", url: "https://www.law.go.kr/..." } },
  watch: [ "<확정 전 개정 동향>" ],
  changelog: [ "<날짜 · 무엇이 · 근거>" ]
};
```
`"Infinity"`는 JSON에 무한대가 없어 문자열로 두고 페이지가 변환합니다. 값을 바꿀 땐 옛 세트를 지우지 말고 새 세트를 추가하세요.

## 5. 설정 코드 (페이지 ↔ 사용자, 서버 저장 없음)

`"DIV1-" + base64(UTF-8 JSON)`. JSON 필드:

| 키 | 뜻 | 키 | 뜻 |
|---|---|---|---|
| v | 버전(1) | ac | 계좌 taxable/isaGen/isaLow/pensionSv/irp |
| a | 투자금(원) | rp | 데이터 저장소 owner/repo |
| g | 목표 월배당(만원) | fa | FIRE 월 추가 납입 |
| y | 투자기간(년) | dp, dt | 재투자 비율 %, 재투자 대상 |
| b | 수익률 기준 ttm/fwd | c | [생활비, 공과금, 월세, 대출] |
| ag | 연령대 20s/40s/50s/60s | r | 실질(물가반영) 1/0 |
| mk | 시장 필터 US/KR | s | ["티커:비중%", ...] |
| w | [원금, 안정성, 비용, 성장] 가중치 | cu | 사용자가 추가한 종목 배열 |
| i | [연봉, 사업소득, 연금] | hd | 보유 종목 {티커: …} |
| wy, wm, wv | 근로기간, 임금상승 방식 pct/amt, 값 | rb | 리밸런싱 active/passive |
| h, tm, tv | 건강보험 유형, 세율 auto/manual, 수동 세율 | nc | 추가 투입 현금 |

## 6. 페이지 내장 종목 카탈로그 (script 안의 `CAT`)

```js
{ mkt:"US"|"KR", cur:"USD"|"KRW", tax:"US"|"KR_FOR"|"KR_DOM"|"KR_REIT", t:"티커", n:"이름",
  px, ttm, fwd, er /*보수%*/, fq /*연 지급횟수*/, cat /*유형*/, kind:"hi"|"gr",
  tr3 /*3년 총수익 연환산%*/, gPx /*주가 연성장 가정%*/, gDiv /*분배 성장 가정%*/, volLv /*분배 변동 1~5*/,
  roc /*자본환급 비중 설명*/, st /*전략*/, vt /*분배 이력*/, bs /*가정 근거*/, aum }
```
data.js 가 있으면 px·ttm·지급월이 매일 이 값을 덮어씁니다. 나머지(성장 가정·설명)는 페이지에 고정입니다.
