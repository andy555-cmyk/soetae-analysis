"""쇠퇴 분석 시스템 - 웹앱.
브라우저에서 주소 입력 -> 뒤에서 지오코딩/상권/쇠퇴등급/빈점포 API 호출 -> 리포트 표시.
실행: pip install -r requirements.txt && (키 환경변수 설정) && python app.py -> http://localhost:5000
정부 API는 CORS로 브라우저 직접호출 불가 -> 이 백엔드가 대신 호출한다.

프런트엔드(PAGE)는 파트너 프로토타입(city-analyzer, Next.js)의 디자인을 1:1 재현:
Noto Sans KR + 뉴트럴/슬레이트 팔레트 + 종합판정 카드(빨강/초록) + 3대 지표 카드 + 지도/메모 레이아웃.
백엔드에 종합판정(compute_verdict)을 추가해 프로토타입의 mock 판정을 실데이터로 작동시킴.
등급 방향은 전국 상대등급 해석(증감률↑=양호, 노후율↑=쇠퇴)을 적용하고 화면에 명시(잠정)."""
import os
from flask import Flask, request, jsonify
import geocode, commercial, decline_grade, vacancy

app = Flask(__name__)
_GRADE_CACHE = {}   # 시군구+연도 쇠퇴등급 캐시(정적)

GRADE_LABEL = {"A":"양호","B":"주의","C":"경계","D":"쇠퇴 진행","E":"쇠퇴 심각","–":"미상"}

def _signgu_from_geo(geo):
    ld = geo.get("ldongCd") or geo.get("emd_code")
    if ld: return str(ld)[:5]
    return None

def _find_grade(grades, *keys):
    """grades에서 mean에 keys 중 하나가 포함된 지표의 (등급값 int, 표기명) 반환."""
    for k in keys:
        for g in grades:
            m = g.get("mean") or ""
            if k in m:
                v = g.get("value")
                try: return int(v), m.replace(" 등급", "")
                except (TypeError, ValueError): return None, m.replace(" 등급", "")
    return None, None

def _band_increase(g):
    """증가형 지표(인구변화율·사업체증감률): 등급 높을수록 양호."""
    if g is None: return ("–", GRADE_LABEL["–"], False)
    if g >= 9: return ("A", GRADE_LABEL["A"], False)
    if g >= 7: return ("B", GRADE_LABEL["B"], False)
    if g >= 5: return ("C", GRADE_LABEL["C"], False)
    if g >= 3: return ("D", GRADE_LABEL["D"], True)
    return ("E", GRADE_LABEL["E"], True)

def _band_old(g):
    """노후형 지표(노후건축물비율): 등급 높을수록 노후 심함(쇠퇴)."""
    if g is None: return ("–", GRADE_LABEL["–"], False)
    if g <= 2: return ("A", GRADE_LABEL["A"], False)
    if g <= 4: return ("B", GRADE_LABEL["B"], False)
    if g <= 6: return ("C", GRADE_LABEL["C"], False)
    if g <= 8: return ("D", GRADE_LABEL["D"], True)
    return ("E", GRADE_LABEL["E"], True)

def compute_verdict(grades):
    """검증된 쇠퇴등급 지표에서 3대 지표 종합판정을 산출.
    법정 활성화지역 지정(원본 증감률·시계열 필요)이 아니라 전국 상대등급 기반 잠정 판정."""
    pop_v, pop_name = _find_grade(grades, "인구변화율(주민등록", "인구순이동률", "인구변화율")
    biz_v, biz_name = _find_grade(grades, "총사업체수증감률", "총종사자수증감률")
    bld_v, bld_name = _find_grade(grades, "노후건축물비율", "노후주택비율")

    pl, plab, pdec = _band_increase(pop_v)
    bl, blab, bdec = _band_increase(biz_v)
    dl, dlab, ddec = _band_old(bld_v)

    indicators = [
        {"code":"POP","label":"인구 변화","source_name":pop_name or "인구변화율",
         "grade":pop_v,"letter":pl,"status":plab,"is_decline":pdec,"direction":"increase",
         "criterion":"전국 상대등급(1~10) · 등급 낮을수록 인구 감소 우세. 법정 기준: 최근 30년 최대 인구 대비 20% 이상 감소 또는 5년간 3년 연속 감소."},
        {"code":"BIZ","label":"사업체 변화","source_name":biz_name or "총사업체수증감률",
         "grade":biz_v,"letter":bl,"status":blab,"is_decline":bdec,"direction":"increase",
         "criterion":"전국 상대등급(1~10) · 등급 낮을수록 사업체 감소 우세. 법정 기준: 최근 10년 최대 사업체수 대비 5% 이상 감소 또는 5년간 3년 연속 감소."},
        {"code":"BLDG","label":"노후 건축물","source_name":bld_name or "노후건축물비율",
         "grade":bld_v,"letter":dl,"status":dlab,"is_decline":ddec,"direction":"old",
         "criterion":"전국 상대등급(1~10) · 등급 높을수록 노후 건축물 비중 큼. 법정 기준: 준공 후 20년 이상 경과 건축물 비율 50% 이상."},
    ]
    decline_count = sum(1 for i in indicators if i["is_decline"])
    letters = [i["letter"] for i in indicators]
    if decline_count >= 3:
        overall = "E"
    elif decline_count == 2:
        overall = "E" if "E" in letters else "D"
    elif decline_count == 1:
        overall = "C"
    else:
        overall = "A" if all(l == "A" for l in letters if l != "–") and "–" not in letters else "B"
    return {
        "overall_grade": overall,
        "overall_label": GRADE_LABEL.get(overall, "미상"),
        "decline_count": decline_count,
        "is_declining": decline_count >= 2,
        "indicators": indicators,
        "basis_note": "전국 상대등급(1~10) 기반 잠정 종합판정입니다. 증감률↑=양호, 노후율↑=쇠퇴로 해석했으며, 「도시재생 활성화 및 지원에 관한 특별법 시행령」상 활성화지역 지정 여부는 원본 증감률·시계열 데이터 연동 후 확정됩니다.",
    }

def diagnose(address, radius=500, year="2016"):
    geo = geocode.geocode(address)
    if not geo:
        dbg = getattr(geocode, "_LAST_GEO_DEBUG", None)
        return {"error": f"주소를 좌표로 변환하지 못했습니다. ({dbg})"}
    rows = commercial.stores_in_radius(geo["lon"], geo["lat"], radius) or []
    comm = commercial.summarize(rows) if rows else {"total_stores":0,"by_major_category":{},"note":""}
    key = f"{round(geo['lat'],4)}_{round(geo['lon'],4)}_{radius}"
    snap_path = f"snapshots/{key}.json"
    prev = vacancy.load(snap_path)
    cur = {"date": __import__("datetime").date.today().isoformat(),
           "lon":geo["lon"],"lat":geo["lat"],"radius":radius,"count":len(rows),
           "ids":{r.get("bizesId"):{"nm":r.get("bizesNm")} for r in rows}}
    if prev:
        vac = vacancy.compare(prev, cur); vac["has_prev"]=True
    else:
        vacancy.save(cur, snap_path)
        vac = {"has_prev":False, "base_date":cur["date"], "base_count":cur["count"]}
    signgu = _signgu_from_geo(geo)
    grades = []
    if signgu:
        ck = f"{signgu}_{year}"
        if ck not in _GRADE_CACHE:
            _GRADE_CACHE[ck] = decline_grade.sigungu_indicators(signgu, year)
        grades = _GRADE_CACHE[ck]
    gonga = next((int(g["value"]) for g in grades if "공가율" in (g["mean"] or "")), None)
    vac["gonga"] = gonga
    by_sector = {}
    for g in grades:
        by_sector.setdefault(g["sector"], []).append(
            {"name": (g["mean"] or "").replace(" 등급",""), "value": int(g["value"]) if g["value"] else None})
    verdict = compute_verdict(grades) if grades else None
    return {"address":address, "lat":geo["lat"], "lon":geo["lon"],
            "sigungu":geo.get("sigungu"), "emd":geo.get("emd"), "radius":radius,
            "commercial":comm, "vacancy":vac, "grades_by_sector":by_sector,
            "diagnosis":verdict,
            "grade_area":geo.get("sigungu"), "grade_year":year,
            "grade_count": len(grades)}

@app.route("/health")
def health():
    import requests as _rq
    out = {}
    tests = {
        "vworld": ("https://api.vworld.kr/req/address",
                   {"service":"address","request":"getcoord","version":"2.0","crs":"epsg:4326",
                    "type":"parcel","address":"부산광역시 기장군 기장읍 동부리 487","format":"json",
                    "key":config_get("VWORLD_KEY")}),
        "sbiz": ("https://apis.data.go.kr/B553077/api/open/sdsc2/storeListInRadius",
                 {"serviceKey":config_get("SBIZ_SERVICE_KEY"),"radius":500,"cx":129.2136,"cy":35.2473,
                  "type":"json","pageNo":1,"numOfRows":1}),
    }
    for name,(url,params) in tests.items():
        try:
            r = _rq.get(url, params=params, timeout=15)
            out[name] = {"http": r.status_code, "body": r.text[:120]}
        except Exception as e:
            out[name] = {"error": str(e)[:120]}
    return jsonify(out)

def config_get(k):
    import config
    return getattr(config, k, "")

@app.route("/api/diagnose")
def api_diagnose():
    addr = request.args.get("address","").strip()
    radius = int(request.args.get("radius", 500))
    if not addr:
        return jsonify({"error":"주소를 입력하세요."})
    try:
        return jsonify(diagnose(addr, radius))
    except Exception as e:
        return jsonify({"error": f"오류: {e}"})

@app.route("/")
def index():
    # PAGE에는 Jinja 문법이 없으므로 그대로 반환(브레이스 충돌 방지)
    return PAGE

PAGE = r"""<!doctype html><html lang=ko><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>도시쇠퇴 분석 — City Analyzer</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;500;600;700;900&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<script defer src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
:root{
  --bg:#fafafa; --fg:#0a0a0a; --card:#ffffff;
  --n50:#fafafa; --n100:#f5f5f5; --n200:#e5e5e5; --n300:#d4d4d4; --n400:#a3a3a3;
  --n500:#737373; --n600:#525252; --n700:#404040; --n800:#262626; --n900:#171717; --n950:#0a0a0a;
  --border:#e5e5e5; --muted:#f4f4f5; --accent:#0f172a;
  --gA:#10b981; --gB:#84cc16; --gC:#f59e0b; --gD:#ea580c; --gE:#dc2626;
  --red50:#fef2f2; --red200:#fecaca; --red600:#dc2626; --red700:#b91c1c;
  --em50:#ecfdf5; --em200:#a7f3d0; --em600:#059669; --em700:#047857;
  --shadow:0 1px 2px 0 rgba(0,0,0,.05);
  --shadow-md:0 4px 6px -1px rgba(0,0,0,.07),0 2px 4px -2px rgba(0,0,0,.05);
}
*{box-sizing:border-box}
html,body{height:100%}
body{margin:0;background:var(--bg);color:var(--fg);
  font-family:'Noto Sans KR',system-ui,-apple-system,'Malgun Gothic',sans-serif;
  font-feature-settings:"ss03","cv11";
  -webkit-font-smoothing:antialiased;line-height:1.5}
.wrap{max-width:1024px;margin:0 auto;padding:64px 24px 96px}
a{color:inherit;text-decoration:none}
svg{display:inline-block;vertical-align:middle}

/* 히어로 */
.eyebrow{font-size:12px;font-weight:600;letter-spacing:.1em;text-transform:uppercase;color:var(--n500)}
h1{margin:12px 0 0;font-size:44px;line-height:1.1;font-weight:700;letter-spacing:-.025em}
h1 .g{background:linear-gradient(90deg,#171717,#737373);-webkit-background-clip:text;background-clip:text;color:transparent}
.lead{margin:20px 0 0;max-width:640px;font-size:16px;line-height:1.7;color:var(--n600)}

/* 검색 */
.searchwrap{margin-top:40px}
.searchbar{display:flex;align-items:center;gap:12px;background:var(--card);border:1px solid var(--n200);
  border-radius:16px;box-shadow:var(--shadow);padding:16px 20px}
.searchbar .sicon{color:var(--n400);flex:0 0 auto}
input#addr{flex:1;min-width:0;border:0;outline:0;background:transparent;font-size:18px;color:var(--fg);font-family:inherit}
input#addr::placeholder{color:var(--n400)}
.gobtn{flex:0 0 auto;border:0;border-radius:12px;background:var(--accent);color:#fff;font-family:inherit;
  font-size:15px;font-weight:600;padding:11px 22px;cursor:pointer;transition:opacity .15s,transform .05s}
.gobtn:hover{opacity:.9} .gobtn:active{transform:scale(.98)} .gobtn:disabled{opacity:.5;cursor:default}
.searchmeta{display:flex;flex-wrap:wrap;align-items:center;gap:14px;margin:14px 2px 0}
.radiobar{display:inline-flex;background:var(--n100);border:1px solid var(--n200);border-radius:10px;padding:3px;gap:2px}
.radiobar button{border:0;background:transparent;font-family:inherit;font-size:13px;font-weight:500;color:var(--n600);
  padding:6px 12px;border-radius:7px;cursor:pointer;transition:.12s}
.radiobar button.on{background:var(--card);color:var(--fg);box-shadow:var(--shadow);font-weight:600}
.hint{font-size:13px;color:var(--n500)}

/* 사례지역 */
.quick{margin-top:40px}
.quick .qt{font-size:12px;font-weight:500;letter-spacing:.05em;text-transform:uppercase;color:var(--n500);margin-bottom:12px}
.qrow{display:flex;flex-wrap:wrap;gap:8px}
.qchip{display:inline-flex;align-items:center;gap:8px;background:var(--card);border:1px solid var(--n200);
  border-radius:999px;padding:8px 16px;font-size:14px;cursor:pointer;transition:border-color .15s,box-shadow .15s}
.qchip:hover{border-color:var(--n400);box-shadow:var(--shadow)}
.qchip .qn{font-weight:500}
.qchip .qs{color:var(--n500)}
.qchip .qa{color:var(--n400);transition:transform .15s}
.qchip:hover .qa{transform:translateX(2px)}

/* 특징 카드 */
.feats{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin-top:64px}
.feat{background:var(--card);border:1px solid var(--n200);border-radius:16px;padding:20px}
.feat .fi{color:var(--n500)}
.feat h3{margin:12px 0 0;font-size:14px;font-weight:600}
.feat p{margin:4px 0 0;font-size:12px;line-height:1.7;color:var(--n600)}

/* 결과 */
#out{margin-top:40px;display:flex;flex-direction:column;gap:24px}
.backrow{display:flex;align-items:center;gap:8px;color:var(--n500);font-size:14px;cursor:pointer;width:max-content}
.backrow:hover{color:var(--fg)}

/* 종합판정 카드 */
.summary{border-radius:16px;border:1px solid;padding:24px;box-shadow:var(--shadow)}
.summary.bad{border-color:var(--red200);background:var(--red50)}
.summary.good{border-color:var(--em200);background:var(--em50)}
.summary .row{display:flex;align-items:flex-start;gap:16px}
.summary .ibox{width:48px;height:48px;flex:0 0 auto;border-radius:12px;display:flex;align-items:center;justify-content:center;color:#fff}
.summary.bad .ibox{background:var(--red600)} .summary.good .ibox{background:var(--em600)}
.summary .mid{flex:1;min-width:0}
.summary .rt{display:flex;flex-wrap:wrap;align-items:baseline;gap:6px 12px}
.summary h2{margin:0;font-size:20px;font-weight:700;letter-spacing:-.02em}
.summary .sub{font-size:12px;color:var(--n500)}
.summary .live{color:var(--em700);font-weight:600}
.summary .verdict{margin:10px 0 0;font-size:16px;font-weight:500}
.summary.bad .vkey{color:var(--red700)} .summary.good .vkey{color:var(--em700)}
.summary .vsub{color:var(--n600);margin-left:6px}
.gradebadge{flex:0 0 auto;align-self:flex-start;border-radius:12px;padding:7px 14px;font-size:14px;font-weight:700;color:#fff}
.gradebadge .gl{font-weight:400;opacity:.85;margin-left:4px}

/* 3대 지표 카드 */
.indgrid{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}
.indcard{background:var(--card);border:1px solid var(--n200);border-radius:16px;padding:24px;box-shadow:var(--shadow)}
.indcard .ih{display:flex;align-items:flex-start;justify-content:space-between;gap:8px}
.indcard .il{font-size:16px;font-weight:600}
.indcard .iy{margin:2px 0 0;font-size:12px;color:var(--n500)}
.pill{flex:0 0 auto;border-radius:999px;padding:4px 10px;font-size:12px;font-weight:700;color:#fff;white-space:nowrap}
.indcard .big{display:flex;align-items:baseline;gap:6px;margin-top:20px}
.indcard .bigv{font-size:38px;font-weight:700;letter-spacing:-.02em;line-height:1}
.indcard .bigu{font-size:15px;color:var(--n500)}
.critbox{display:flex;align-items:flex-start;gap:8px;margin-top:16px;background:var(--n50);border-radius:8px;padding:12px;font-size:12px}
.critbox .ci{flex:0 0 auto;margin-top:1px}
.critbox .ct{font-weight:600}
.critbox.bad .ct{color:var(--red700)} .critbox.good .ct{color:var(--em700)}
.critbox .cd{margin:2px 0 0;line-height:1.6;color:var(--n600)}
/* 전국 상대등급 게이지 */
.gauge{margin-top:20px}
.gauge .gl2{display:flex;justify-content:space-between;font-size:11px;color:var(--n400);margin-bottom:6px}
.gtrack{display:flex;gap:3px;height:34px}
.gseg{flex:1;border-radius:3px;background:var(--n100)}
.gseg.on{background:var(--accent)}
.gcap{margin-top:8px;font-size:11px;color:var(--n500);text-align:right}

/* 카드 공통 */
.card{background:var(--card);border:1px solid var(--n200);border-radius:16px;padding:24px;box-shadow:var(--shadow)}
.sec2{display:grid;gap:24px;grid-template-columns:2fr 1fr}
.h3{margin:0 0 12px;font-size:14px;font-weight:600;color:var(--n700)}
.memo{font-size:14px;line-height:1.75}
.memo strong{font-weight:700}
.memo .bad{color:var(--red600)} .memo .good{color:var(--em600)}
.memo .note{margin-top:16px;font-size:12px;color:var(--n500)}
.mapcard{overflow:hidden;border:1px solid var(--n200);border-radius:16px;box-shadow:var(--shadow)}
#map{height:340px;width:100%}
.leaflet-container{border-radius:0}

/* 카드 헤더 */
.chead{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:18px}
.chead .ct2{display:flex;align-items:center;gap:10px;font-size:16px;font-weight:600}
.chead .ci2{color:var(--n500)}
.chead .cn{font-size:12px;font-weight:500;color:var(--n600);background:var(--n100);border:1px solid var(--n200);border-radius:8px;padding:4px 10px}

/* 막대 리스트 */
.rows{display:flex;flex-direction:column;gap:10px}
.row{display:grid;grid-template-columns:150px 1fr 52px;align-items:center;gap:12px}
.row .rn{font-size:13px;color:var(--n700);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.bar{height:8px;background:var(--n100);border-radius:99px;overflow:hidden}
.barf{height:100%;border-radius:99px;background:var(--accent)}
.barf.soft{background:var(--n700)}
.rv{font-size:13px;font-weight:600;text-align:right;color:var(--n700);font-variant-numeric:tabular-nums}
.rv .u{color:var(--n400);font-weight:400}
.cnote{margin-top:14px;font-size:12px;color:var(--n500);line-height:1.6}

/* 부문 */
.sector{margin-top:22px}
.sector:first-child{margin-top:0}
.sector .st{display:flex;align-items:center;gap:8px;font-size:13px;font-weight:600;margin-bottom:12px}
.sector .st .c{color:var(--n400);font-weight:400;font-size:12px}
.sector .st .mean{margin-left:auto;color:var(--accent);font-weight:700;font-variant-numeric:tabular-nums}

/* 통계 배지 */
.stats{display:flex;flex-wrap:wrap;gap:10px}
.stat{min-width:92px;background:var(--n50);border:1px solid var(--n200);border-radius:12px;padding:12px 16px;text-align:center}
.stat .sv{font-size:20px;font-weight:700;letter-spacing:-.02em}
.stat .sk{font-size:11px;color:var(--n500);margin-top:2px}
.badge{display:inline-flex;align-items:center;gap:6px;background:var(--muted);border:1px solid var(--n200);color:var(--n700);
  border-radius:999px;padding:6px 12px;font-size:12px;font-weight:600}
.disc{margin-top:16px;padding-top:14px;border-top:1px solid var(--n200);font-size:11.5px;color:var(--n500);line-height:1.6}

.loading{display:flex;align-items:center;justify-content:center;gap:12px;color:var(--n500);font-size:14px;padding:40px}
.spin{width:20px;height:20px;border:2.5px solid var(--n200);border-top-color:var(--accent);border-radius:50%;animation:sp .7s linear infinite}
@keyframes sp{to{transform:rotate(360deg)}}
.err{background:var(--red50);border:1px solid var(--red200);color:var(--red700);border-radius:14px;padding:16px;font-size:14px}

.footer{margin-top:80px;border-top:1px solid var(--n200);padding-top:24px;font-size:12px;color:var(--n500);line-height:1.8}

@media(max-width:820px){
  .sec2{grid-template-columns:1fr}
}
@media(max-width:640px){
  .wrap{padding:40px 18px 72px}
  h1{font-size:32px}
  .feats{grid-template-columns:1fr}
  .indgrid{grid-template-columns:1fr}
  .row{grid-template-columns:108px 1fr 46px}
}
</style></head><body><div class=wrap>

<div class=eyebrow>City Analyzer · 도시쇠퇴 진단툴</div>
<h1>지역을 입력하면<br><span class=g>쇠퇴 진단이 자동으로 나옵니다.</span></h1>
<p class=lead>주소만 넣으면 대상지의 인구·사업체·노후건축물 3대 쇠퇴진단지표와 상권·빈점포를 정부 실데이터로 즉시 진단합니다. 도시재생 활성화지역 지정 가능성을 한 화면에서 확인하세요.</p>

<div class=searchwrap>
  <div class=searchbar>
    <svg class=sicon width=22 height=22 viewBox="0 0 24 24" fill=none stroke=currentColor stroke-width=2 stroke-linecap=round stroke-linejoin=round><circle cx=11 cy=11 r=8></circle><path d="m21 21-4.3-4.3"></path></svg>
    <input id=addr placeholder="주소 또는 지역을 입력하세요 — 예: 부산광역시 기장군 기장읍 동부리 487" value="부산광역시 기장군 기장읍 동부리 487" onkeydown="if(event.key==='Enter')run()">
    <button id=go class=gobtn onclick=run()>진단</button>
  </div>
  <div class=searchmeta>
    <div class=radiobar id=radio></div>
    <span class=hint>처음 조회 시 10~20초 소요</span>
  </div>
</div>

<div class=quick>
  <div class=qt>빠른 진입 — 사례 지역</div>
  <div class=qrow id=quick></div>
</div>

<div class=feats id=feats></div>

<div id=out></div>

<div class=footer>
  데이터 출처: 국토교통부 쇠퇴진단 등급(DceDgnssGradeService) · 소상공인시장진흥공단 상가정보(sdsc2) · VWorld 지오코딩 — 공공데이터포털.<br>
  법적 기준: 도시재생 활성화 및 지원에 관한 특별법 시행령 제17조(쇠퇴 진단 기준). 종합판정은 전국 상대등급 기반 잠정치이며 원본 증감률 연동 후 확정.
</div>

<script>
const out=document.getElementById('out');
let RADIUS=500, _map=null;
function esc(s){return (s==null?'':(''+s)).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]))}

// 등급 색
const GC={A:'var(--gA)',B:'var(--gB)',C:'var(--gC)',D:'var(--gD)',E:'var(--gE)','–':'var(--n400)'};

// SVG 아이콘
const IC={
  search:'<svg width=20 height=20 viewBox="0 0 24 24" fill=none stroke=currentColor stroke-width=2 stroke-linecap=round stroke-linejoin=round><circle cx=11 cy=11 r=8></circle><path d="m21 21-4.3-4.3"></path></svg>',
  pin:'<svg width=14 height=14 viewBox="0 0 24 24" fill=none stroke=currentColor stroke-width=2 stroke-linecap=round stroke-linejoin=round><path d="M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0Z"></path><circle cx=12 cy=10 r=3></circle></svg>',
  arrow:'<svg width=14 height=14 viewBox="0 0 24 24" fill=none stroke=currentColor stroke-width=2 stroke-linecap=round stroke-linejoin=round><path d="M5 12h14"></path><path d="m12 5 7 7-7 7"></path></svg>',
  back:'<svg width=16 height=16 viewBox="0 0 24 24" fill=none stroke=currentColor stroke-width=2 stroke-linecap=round stroke-linejoin=round><path d="m12 19-7-7 7-7"></path><path d="M19 12H5"></path></svg>',
  bar:'<svg width=20 height=20 viewBox="0 0 24 24" fill=none stroke=currentColor stroke-width=2 stroke-linecap=round stroke-linejoin=round><path d="M3 3v18h18"></path><rect x=7 y=10 width=3 height=7></rect><rect x=12 y=6 width=3 height=11></rect><rect x=17 y=13 width=3 height=4></rect></svg>',
  map:'<svg width=20 height=20 viewBox="0 0 24 24" fill=none stroke=currentColor stroke-width=2 stroke-linecap=round stroke-linejoin=round><path d="M14.106 5.553a2 2 0 0 0 1.788 0l3.659-1.83A1 1 0 0 1 21 4.619v12.764a1 1 0 0 1-.553.894l-4.553 2.277a2 2 0 0 1-1.788 0l-4.212-2.106a2 2 0 0 0-1.788 0l-3.659 1.83A1 1 0 0 1 3 19.381V6.618a1 1 0 0 1 .553-.894l4.553-2.277a2 2 0 0 1 1.788 0Z"></path><path d="M15 5.764v15M9 3.236v15"></path></svg>',
  file:'<svg width=20 height=20 viewBox="0 0 24 24" fill=none stroke=currentColor stroke-width=2 stroke-linecap=round stroke-linejoin=round><path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"></path><path d="M14 2v4a2 2 0 0 0 2 2h4"></path></svg>',
  store:'<svg width=20 height=20 viewBox="0 0 24 24" fill=none stroke=currentColor stroke-width=2 stroke-linecap=round stroke-linejoin=round><path d="m2 7 4.41-4.41A2 2 0 0 1 7.83 2h8.34a2 2 0 0 1 1.42.59L22 7"></path><path d="M4 12v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8"></path><path d="M2 7h20"></path><path d="M12 7v5"></path></svg>',
  grid:'<svg width=20 height=20 viewBox="0 0 24 24" fill=none stroke=currentColor stroke-width=2 stroke-linecap=round stroke-linejoin=round><rect x=3 y=3 width=7 height=7></rect><rect x=14 y=3 width=7 height=7></rect><rect x=14 y=14 width=7 height=7></rect><rect x=3 y=14 width=7 height=7></rect></svg>',
  alert:'<svg width=24 height=24 viewBox="0 0 24 24" fill=none stroke=currentColor stroke-width=2 stroke-linecap=round stroke-linejoin=round><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"></path><path d="M12 9v4"></path><path d="M12 17h.01"></path></svg>',
  shield:'<svg width=24 height=24 viewBox="0 0 24 24" fill=none stroke=currentColor stroke-width=2 stroke-linecap=round stroke-linejoin=round><path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1Z"></path><path d="m9 12 2 2 4-4"></path></svg>',
  check:'<svg width=16 height=16 viewBox="0 0 24 24" fill=none stroke=currentColor stroke-width=2.5 stroke-linecap=round stroke-linejoin=round><path d="M20 6 9 17l-5-5"></path></svg>',
  x:'<svg width=16 height=16 viewBox="0 0 24 24" fill=none stroke=currentColor stroke-width=2.5 stroke-linecap=round stroke-linejoin=round><path d="M18 6 6 18"></path><path d="m6 6 12 12"></path></svg>'
};

// 반경 선택
const RADII=[500,1000,2000];
document.getElementById('radio').innerHTML=RADII.map(r=>
  '<button class="'+(r===RADIUS?'on':'')+'" data-r="'+r+'" onclick="setRadius('+r+')">반경 '+(r>=1000?(r/1000)+'km':r+'m')+'</button>'
).join('');
function setRadius(r){RADIUS=r;document.querySelectorAll('#radio button').forEach(b=>b.classList.toggle('on',+b.dataset.r===r));}

// 사례지역
const SAMPLES=[
  {a:'부산광역시 기장군 기장읍 동부리 487', n:'기장읍 동부리487', s:'부산 기장군'},
  {a:'부산광역시 해운대구 우동', n:'우동', s:'부산 해운대구'},
  {a:'경상남도 산청군 산청읍', n:'산청읍', s:'경남 산청군'},
  {a:'경상남도 합천군 합천읍', n:'합천읍', s:'경남 합천군'}
];
document.getElementById('quick').innerHTML=SAMPLES.map(x=>
  '<span class=qchip data-a="'+esc(x.a)+'" onclick="pick(this)">'+IC.pin+'<span class=qn>'+esc(x.n)+'</span><span class=qs>'+esc(x.s)+'</span>'+IC.arrow.replace('<svg','<svg class=qa')+'</span>'
).join('');
function pick(el){document.getElementById('addr').value=el.getAttribute('data-a');run();}

// 특징 카드
const FEATS=[
  {i:IC.bar,t:'3대 쇠퇴진단지표',b:'인구 변화·사업체 변화·노후 건축물을 전국 상대등급과 함께 자동 판정.'},
  {i:IC.store,t:'상권 + 빈점포 실측',b:'반경 영업 점포·업종 구성과 시점비교 폐업률을 함께 진단.'},
  {i:IC.file,t:'실데이터 · 응찰 자료',b:'정부 API 실데이터 기반. 도시재생 공모·기본계획 보고서에 즉시 활용.'}
];
document.getElementById('feats').innerHTML=FEATS.map(f=>
  '<div class=feat><span class=fi>'+f.i+'</span><h3>'+f.t+'</h3><p>'+f.b+'</p></div>'
).join('');

async function run(){
  const a=document.getElementById('addr').value.trim(); if(!a)return;
  const btn=document.getElementById('go'); btn.disabled=true;
  out.innerHTML='<div class="card"><div class=loading><div class=spin></div>정부 데이터를 불러오는 중…</div></div>';
  out.scrollIntoView({behavior:'smooth',block:'start'});
  try{
    const r=await fetch('/api/diagnose?address='+encodeURIComponent(a)+'&radius='+RADIUS);
    const d=await r.json();
    if(d.error){out.innerHTML='<div class=err>'+esc(d.error)+'</div>';}
    else render(d);
  }catch(e){out.innerHTML='<div class=err>요청 실패: '+esc(e)+'</div>';}
  btn.disabled=false;
}

function meanOf(arr){const vs=arr.map(g=>g.value).filter(v=>v!=null);
  if(!vs.length)return null;return Math.round(vs.reduce((a,c)=>a+c,0)/vs.length*10)/10;}

function gauge(g){ // 전국 상대등급 1~10 게이지
  let s='<div class=gauge><div class=gl2><span>전국 상대등급</span><span>1 ← → 10</span></div><div class=gtrack>';
  for(let i=1;i<=10;i++) s+='<div class="gseg'+(g!=null&&i<=g?' on':'')+'"></div>';
  s+='</div><div class=gcap>'+(g==null?'등급 미상':(g+' / 10 등급'))+'</div></div>';
  return s;
}

function render(d){
  const dg=d.diagnosis, c=d.commercial, v=d.vacancy, secs=d.grades_by_sector||{};
  let h='';

  // 뒤로(초기화)
  h+='<div class=backrow onclick="out.innerHTML=\'\';window.scrollTo({top:0,behavior:\'smooth\'})">'+IC.back+'다른 지역 진단</div>';

  // 종합판정
  if(dg){
    const bad=dg.is_declining;
    h+='<div class="summary '+(bad?'bad':'good')+'"><div class=row>'
      +'<div class=ibox>'+(bad?IC.alert:IC.shield)+'</div>'
      +'<div class=mid><div class=rt><h2>'+esc(d.sigungu||'')+' '+esc(d.emd||'')+'</h2>'
      +'<span class=sub>기준연도 '+esc(d.grade_year)+' · <span class=live>실데이터</span> · '+esc(d.address)+'</span></div>'
      +'<div class=verdict>';
    if(bad){h+='<span class=vkey>쇠퇴 신호 감지</span><span class=vsub>— 3대 지표 중 <strong>'+dg.decline_count+'개</strong> 쇠퇴 우세 (활성화지역 검토 대상)</span>';}
    else{h+='<span class=vkey>정상 범위</span><span class=vsub>— 3대 지표 중 '+dg.decline_count+'개 쇠퇴 우세 (쇠퇴 기준 미달)</span>';}
    h+='</div></div>'
      +'<div class=gradebadge style="background:'+GC[dg.overall_grade]+'">종합 '+esc(dg.overall_grade)+'등급<span class=gl>'+esc(dg.overall_label)+'</span></div>'
      +'</div></div>';

    // 3대 지표
    h+='<div class=indgrid>';
    for(const ind of dg.indicators){
      const dec=ind.is_decline;
      h+='<div class=indcard><div class=ih><div><div class=il>'+esc(ind.label)+'</div><div class=iy title="'+esc(ind.source_name)+'">'+esc(ind.source_name)+'</div></div>'
        +'<span class=pill style="background:'+GC[ind.letter]+'">'+esc(ind.letter)+' · '+esc(ind.status)+'</span></div>'
        +'<div class=big><span class=bigv>'+(ind.grade==null?'–':ind.grade)+'</span><span class=bigu>/ 10 등급</span></div>'
        +'<div class="critbox '+(dec?'bad':'good')+'"><span class=ci style="color:'+(dec?'var(--red600)':'var(--em600)')+'">'+(dec?IC.check:IC.x)+'</span>'
        +'<div><div class=ct>'+(dec?'쇠퇴 우세':'양호 우세')+'</div><div class=cd>'+esc(ind.criterion)+'</div></div></div>'
        +gauge(ind.grade)
        +'</div>';
    }
    h+='</div>';
  }

  // 지도 + 메모
  h+='<section class=sec2><div><div class=h3>지역 위치</div><div class=mapcard><div id=map></div></div></div>'
    +'<div><div class=h3>진단 요약 메모</div><div class="card memo">';
  if(dg){
    h+='<p><strong>'+esc(d.sigungu||'')+'</strong> 일대는 '+esc(d.grade_year)+'년 기준 3대 쇠퇴진단지표 중 '
      +'<strong class="'+(dg.is_declining?'bad':'good')+'">'+dg.decline_count+'개</strong> 항목이 전국 하위권(쇠퇴 우세)으로 나타났습니다.</p>';
    if(dg.is_declining){h+='<p style="margin-top:12px;color:var(--n600)">2개 이상 쇠퇴 우세 시 「도시재생 활성화 및 지원에 관한 특별법」상 활성화지역 지정 검토 대상에 해당할 수 있습니다. 다음 단계로 ① 잠재력 지표(자산·접근성·생활편의) 분석, ② 주민의견 수렴, ③ 도시재생전략계획 수립을 권장합니다.</p>';}
    else{h+='<p style="margin-top:12px;color:var(--n600)">정량 쇠퇴 신호는 크지 않으나, 개별 지표 등급이 낮은 항목은 선제적 관리를 고려해야 합니다. 상권·빈점포 추이와 함께 판단하세요.</p>';}
    h+='<p class=note>'+esc(dg.basis_note)+'</p>';
  }else{h+='<p class=note>이 지역의 쇠퇴등급 데이터를 불러오지 못했습니다.</p>';}
  h+='</div></div></section>';

  // 상권 현황
  h+='<div class=card><div class=chead><div class=ct2><span class=ci2>'+IC.store+'</span>상권 현황</div><span class=cn>반경 '+((d.radius||500)>=1000?((d.radius)/1000)+'km':(d.radius||500)+'m')+'</span></div>';
  const cats=Object.entries(c.by_major_category||{}).sort((a,b)=>b[1]-a[1]).slice(0,10);
  const cmax=cats.length?Math.max.apply(null,cats.map(x=>x[1])):1;
  if(cats.length){
    h+='<div class=stats style="margin-bottom:18px"><div class=stat><div class=sv>'+(c.total_stores||0)+'</div><div class=sk>영업 점포</div></div>'
      +'<div class=stat><div class=sv>'+cats.length+'</div><div class=sk>업종 대분류</div></div></div>';
    h+='<div class=rows>';
    for(const [k,val] of cats){
      const w=Math.max(4,Math.round(val/cmax*100));
      h+='<div class=row><div class=rn>'+esc(k)+'</div><div class=bar><div class=barf style="width:'+w+'%"></div></div><div class=rv>'+val+'</div></div>';
    }
    h+='</div>';
  }else{h+='<div class=cnote>반경 내 영업 점포 데이터가 없습니다.</div>';}
  h+='<div class=cnote>빈 점포·공실은 상가정보 API에 직접 제공되지 않아, 시점 비교(분기 스냅샷 차분)로 폐업·순증감을 추정합니다.</div></div>';

  // 빈점포
  h+='<div class=card><div class=chead><div class=ct2><span class=ci2>'+IC.store+'</span>빈 점포 · 공실</div></div>';
  if(v.has_prev){
    h+='<div class=cnote style="margin-top:0;margin-bottom:14px">기간 '+esc(v.t0_date)+' → '+esc(v.t1_date)+'</div>'
      +'<div class=stats><div class=stat><div class=sv>'+v.closed+'</div><div class=sk>폐업 추정</div></div>'
      +'<div class=stat><div class=sv>'+v.opened+'</div><div class=sk>신규</div></div>'
      +'<div class=stat><div class=sv>'+v.closure_rate_pct+'%</div><div class=sk>폐업률</div></div></div>';
  }else{
    h+='<div class=cnote style="margin-top:0">기준 스냅샷을 저장했습니다 ('+esc(v.base_date)+' · '+v.base_count+'개). 상가정보가 분기 갱신되면 재실행 시 폐업·공실 순증감이 자동 산출됩니다.</div>';
  }
  if(v.gonga!=null)h+='<div style="margin-top:16px"><span class=badge>공가율(빈집) 등급 '+v.gonga+' / 10</span><div class=cnote>※ 주거 빈집 지표로, 상업 공실과는 구분됩니다.</div></div>';
  h+='</div>';

  // 3부문 상세 등급
  h+='<div class=card><div class=chead><div class=ct2><span class=ci2>'+IC.grid+'</span>쇠퇴진단 지표 상세</div><span class=cn>'+esc(d.grade_area||'')+' · '+esc(d.grade_year)+' · '+(d.grade_count||0)+'개</span></div>';
  const order=['인구사회','산업경제','물리환경'];
  if(!secs||Object.keys(secs).length===0){h+='<div class=cnote>등급 데이터를 불러오지 못했습니다.</div>';}
  for(const sec of order){
    if(!secs[sec])continue;
    const m=meanOf(secs[sec]);
    h+='<div class=sector><div class=st>'+sec+'부문 <span class=c>'+secs[sec].length+'개 지표</span><span class=mean>평균 '+(m==null?'–':m)+'<span style="color:var(--n400);font-weight:400;font-size:11px"> /10</span></span></div><div class=rows>';
    for(const g of secs[sec]){
      const val=(g.value==null?0:g.value);
      h+='<div class=row><div class=rn title="'+esc(g.name)+'">'+esc(g.name)+'</div><div class=bar><div class="barf soft" style="width:'+(val*10)+'%"></div></div><div class=rv>'+(g.value==null?'–':g.value)+'<span class=u>/10</span></div></div>';
    }
    h+='</div></div>';
  }
  h+='<div class=disc>등급값(1~10)은 전국 대비 상대 위치입니다. 지표별로 높음/낮음의 의미가 달라, 종합판정은 증감률↑=양호·노후율↑=쇠퇴 해석을 적용한 잠정치이며 공식 범례 확정 후 보강합니다.</div></div>';

  out.innerHTML=h;

  // Leaflet 지도 (프로토타입: 빨간 마커)
  try{
    if(window.L){
      if(_map){_map.remove();_map=null;}
      _map=L.map('map',{scrollWheelZoom:false}).setView([d.lat,d.lon],14);
      L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{attribution:'&copy; OpenStreetMap',maxZoom:19}).addTo(_map);
      const ic=L.divIcon({className:'',html:'<div style="width:24px;height:24px;border-radius:50%;background:#dc2626;border:3px solid #fff;box-shadow:0 2px 8px rgba(0,0,0,.3)"></div>',iconSize:[24,24],iconAnchor:[12,12]});
      L.marker([d.lat,d.lon],{icon:ic}).addTo(_map).bindPopup(esc(d.address));
      if(d.radius){L.circle([d.lat,d.lon],{radius:d.radius,color:'#0f172a',weight:1,fillColor:'#0f172a',fillOpacity:.05}).addTo(_map);}
      setTimeout(()=>{if(_map)_map.invalidateSize();},200);
    }
  }catch(e){}
}
</script></div></body></html>"""

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
