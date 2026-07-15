"""쇠퇴 분석 시스템 - 웹앱.
브라우저에서 주소 입력 -> 뒤에서 지오코딩/상권/쇠퇴등급/빈점포 API 호출 -> 리포트 표시.
실행: pip install -r requirements.txt && (키 환경변수 설정) && python app.py -> http://localhost:5000
정부 API는 CORS로 브라우저 직접호출 불가 -> 이 백엔드가 대신 호출한다.

프런트엔드(PAGE)는 파트너 프로토타입(city-analyzer, Next.js)의 디자인 언어를 이식:
랜딩 히어로 + 사례지역 퀵칩 + Leaflet 지도 + 요약 카드 + 정돈된 상권/빈점포/등급 섹션.
백엔드 파이프라인과 /api/diagnose 계약은 그대로 유지."""
import os
from flask import Flask, request, jsonify
import geocode, commercial, decline_grade, vacancy

app = Flask(__name__)
_GRADE_CACHE = {}   # 시군구+연도 쇠퇴등급 캐시(정적)

def _signgu_from_geo(geo):
    ld = geo.get("ldongCd") or geo.get("emd_code")
    if ld: return str(ld)[:5]
    return None

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
    return {"address":address, "lat":geo["lat"], "lon":geo["lon"],
            "sigungu":geo.get("sigungu"), "emd":geo.get("emd"),
            "commercial":comm, "vacancy":vac, "grades_by_sector":by_sector,
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
<title>도시쇠퇴 분석 · City Analyzer</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Pretendard:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<script defer src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
:root{
  --bg:#fafafa; --card:#ffffff; --line:#ececf0; --line2:#e2e2e8;
  --ink:#0a0a0a; --sub:#525252; --mut:#a3a3a3;
  --accent:#4f46e5; --accent-soft:#eef2ff; --accent-ink:#4338ca;
  --teal:#0d9488; --teal-soft:#f0fdfa;
  --good:#10b981; --warn:#f59e0b; --bad:#ef4444;
  --shadow:0 1px 2px rgba(16,24,40,.04), 0 4px 14px rgba(16,24,40,.05);
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
  font-family:'Pretendard',-apple-system,BlinkMacSystemFont,'Malgun Gothic',sans-serif;
  -webkit-font-smoothing:antialiased;line-height:1.5}
.wrap{max-width:860px;margin:0 auto;padding:48px 20px 90px}
a{color:inherit;text-decoration:none}

/* 헤더/히어로 */
.eyebrow{font-size:11px;font-weight:700;letter-spacing:.14em;text-transform:uppercase;color:var(--mut)}
.brand{display:flex;align-items:center;gap:10px;margin:8px 0 20px}
.dot{width:32px;height:32px;border-radius:10px;background:var(--accent);
  display:flex;align-items:center;justify-content:center;color:#fff;font-weight:800;font-size:16px}
h1{font-size:34px;font-weight:800;letter-spacing:-.03em;margin:0;line-height:1.18}
h1 .g{background:linear-gradient(90deg,#0a0a0a,#737373);-webkit-background-clip:text;background-clip:text;color:transparent}
.lead{color:var(--sub);font-size:15px;margin:16px 0 26px;max-width:620px}

/* 검색 */
.searchbar{display:flex;gap:10px;background:var(--card);padding:10px;border:1px solid var(--line2);
  border-radius:16px;box-shadow:var(--shadow)}
.searchbar .si{flex:1;display:flex;align-items:center;gap:10px;padding-left:8px}
.searchbar svg{flex:0 0 auto;color:var(--mut)}
input{flex:1;border:0;outline:0;padding:12px 4px;font-size:15px;background:transparent;color:var(--ink);
  font-family:inherit}
input::placeholder{color:var(--mut)}
button{border:0;border-radius:11px;background:var(--accent);color:#fff;font-weight:700;font-size:15px;
  padding:0 26px;cursor:pointer;font-family:inherit;transition:background .15s,transform .05s}
button:hover{background:var(--accent-ink)} button:active{transform:scale(.98)} button:disabled{opacity:.55;cursor:default}
.hint{color:var(--mut);font-size:12.5px;margin:11px 2px 0}

/* 사례지역 퀵칩 */
.quick{margin:22px 0 8px}
.quick .qt{font-size:11px;font-weight:600;letter-spacing:.06em;text-transform:uppercase;color:var(--mut);margin-bottom:10px}
.quick .qrow{display:flex;flex-wrap:wrap;gap:8px}
.qchip{display:inline-flex;align-items:center;gap:7px;background:var(--card);border:1px solid var(--line2);
  border-radius:999px;padding:8px 14px;font-size:13px;cursor:pointer;transition:border-color .15s,box-shadow .15s}
.qchip:hover{border-color:#c7c7d1;box-shadow:var(--shadow)}
.qchip .qp{color:var(--accent)}
.qchip .qs{color:var(--mut)}

/* 특징 카드 */
.feats{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin:26px 0 6px}
.feat{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:18px}
.feat .fi{width:34px;height:34px;border-radius:9px;background:var(--accent-soft);color:var(--accent-ink);
  display:flex;align-items:center;justify-content:center;font-size:17px}
.feat h3{font-size:14px;font-weight:700;margin:12px 0 4px}
.feat p{font-size:12.5px;color:var(--sub);margin:0;line-height:1.55}

/* 결과 */
#out{margin-top:26px;display:flex;flex-direction:column;gap:16px}
.meta{color:var(--sub);font-size:13px;display:flex;align-items:center;gap:7px;padding:0 2px}
.pin{color:var(--accent)}

/* 요약 카드 */
.summary{background:var(--card);border:1px solid var(--line);border-radius:18px;padding:22px;box-shadow:var(--shadow)}
.summary .top{display:flex;flex-wrap:wrap;align-items:flex-start;justify-content:space-between;gap:14px}
.summary .rn{font-size:22px;font-weight:800;letter-spacing:-.02em;margin:2px 0 3px}
.summary .rs{font-size:12.5px;color:var(--sub)}
.summary .rs .live{color:var(--good);font-weight:600}
.stats{display:flex;flex-wrap:wrap;gap:10px}
.stat{min-width:96px;background:#fafafb;border:1px solid var(--line);border-radius:13px;padding:10px 14px;text-align:center}
.stat.teal{background:var(--teal-soft);border-color:#ccfbf1}
.stat .sv{font-size:20px;font-weight:800;letter-spacing:-.02em}
.stat.teal .sv{color:#0f766e}
.stat .sk{font-size:11px;color:var(--sub);margin-top:2px}
.infobox{margin-top:16px;display:flex;gap:9px;background:#fafafb;border-radius:11px;padding:12px 13px;
  font-size:12px;color:var(--sub);line-height:1.55}
.infobox .ii{color:var(--mut);flex:0 0 auto}

/* 지도 */
#map{height:300px;width:100%}
.mapcard{overflow:hidden;border:1px solid var(--line);border-radius:18px;box-shadow:var(--shadow)}

/* 일반 카드 */
.card{background:var(--card);border:1px solid var(--line);border-radius:18px;padding:22px;box-shadow:var(--shadow)}
.h{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:16px}
.h .ht{display:flex;align-items:center;gap:9px;font-size:15px;font-weight:700;color:var(--ink)}
.h .hi{width:30px;height:30px;border-radius:8px;background:#f4f4f6;display:flex;align-items:center;justify-content:center;font-size:15px}
.h .num{color:var(--sub);font-size:12px;font-weight:600;background:#f4f4f6;border-radius:6px;padding:3px 9px}

/* bar 리스트 (상권/등급 공용) */
.rows{display:flex;flex-direction:column;gap:10px}
.row{display:grid;grid-template-columns:130px 1fr 58px;align-items:center;gap:12px}
.row .rn2{font-size:13px;color:#3f3f46;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.bar{height:9px;background:#f1f1f4;border-radius:99px;overflow:hidden}
.barf{height:100%;border-radius:99px}
.barf.indigo{background:linear-gradient(90deg,#818cf8,#4f46e5)}
.barf.teal{background:linear-gradient(90deg,#5eead4,#0d9488)}
.rv{font-size:13px;font-weight:700;text-align:right;color:#3f3f46;font-variant-numeric:tabular-nums}
.rv .u{color:var(--mut);font-weight:500}

/* 부문 */
.sector{margin-top:20px}
.sector:first-of-type{margin-top:4px}
.sector .st{font-size:13.5px;font-weight:700;color:var(--ink);margin-bottom:12px;display:flex;align-items:center;gap:8px}
.sector .st .c{color:var(--mut);font-weight:500;font-size:12px}
.sector .st .mean{margin-left:auto;color:var(--accent-ink);font-weight:800;font-variant-numeric:tabular-nums}

.note{font-size:12px;color:var(--sub);margin-top:12px;line-height:1.55}
.badge{display:inline-flex;align-items:center;gap:6px;background:var(--accent-soft);color:var(--accent-ink);
  border-radius:999px;padding:6px 13px;font-size:12.5px;font-weight:600}
.disc{font-size:11.5px;color:var(--mut);margin-top:16px;line-height:1.55;border-top:1px solid var(--line);padding-top:14px}
.loading{display:flex;align-items:center;gap:12px;color:var(--sub);font-size:14px;justify-content:center;padding:34px}
.spin{width:20px;height:20px;border:2.5px solid var(--line2);border-top-color:var(--accent);border-radius:50%;
  animation:sp .7s linear infinite}
@keyframes sp{to{transform:rotate(360deg)}}
.err{background:#fef2f2;border:1px solid #fecaca;color:#b91c1c;border-radius:14px;padding:14px 16px;font-size:13.5px}
.footer{margin-top:40px;border-top:1px solid var(--line);padding-top:20px;font-size:12px;color:var(--mut);line-height:1.6}
@media(max-width:640px){
  h1{font-size:27px}
  .feats{grid-template-columns:1fr}
  .stats{width:100%}
  .row{grid-template-columns:96px 1fr 46px}
  .wrap{padding:32px 16px 64px}
}
</style></head><body><div class=wrap>

<div class=eyebrow>City Analyzer · 도시쇠퇴 진단툴</div>
<div class=brand><div class=dot>쇠</div></div>
<h1>지역을 입력하면<br><span class=g>쇠퇴 진단이 자동으로 나옵니다.</span></h1>
<p class=lead>주소만 넣으면 대상지의 상권·빈점포·쇠퇴진단 등급을 정부 실데이터로 즉시 분석합니다.
국토교통부 · 소상공인시장진흥공단 · VWorld 연동.</p>

<div class=searchbar>
  <div class=si>
    <svg width=18 height=18 viewBox="0 0 24 24" fill=none stroke=currentColor stroke-width=2 stroke-linecap=round stroke-linejoin=round><circle cx=11 cy=11 r=8></circle><path d="m21 21-4.3-4.3"></path></svg>
    <input id=addr placeholder="주소를 입력하세요 — 예: 부산광역시 기장군 기장읍 동부리 487" value="부산광역시 기장군 기장읍 동부리 487" onkeydown="if(event.key==='Enter')run()">
  </div>
  <button id=go onclick=run()>진단</button>
</div>
<div class=hint>반경 500m 기준 · 처음 조회 시 10~20초 소요</div>

<div class=quick>
  <div class=qt>빠른 진입 — 사례 지역</div>
  <div class=qrow id=quick></div>
</div>

<div class=feats id=feats></div>

<div id=out></div>

<div class=footer>
  데이터 출처: 국토교통부 쇠퇴진단 등급(DceDgnssGradeService) · 소상공인시장진흥공단 상가정보(sdsc2) · VWorld 지오코딩 — 공공데이터포털.<br>
  법적 기준: 도시재생활성화 및 지원에 관한 특별법 시행령 제17조. 등급 방향·종합 점수화는 공식 범례 확정 후 반영.
</div>

<script>
const out=document.getElementById('out');
function esc(s){return (s==null?'':(''+s)).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]))}

// 사례지역 퀵칩
const SAMPLES=[
  {a:'부산광역시 기장군 기장읍 동부리 487', s:'첫 대상지'},
  {a:'부산광역시 해운대구 우동', s:'도심 안정'},
  {a:'경상남도 산청군 산청읍', s:'농촌형'},
  {a:'경상남도 합천군 합천읍', s:'로컬브랜딩'}
];
document.getElementById('quick').innerHTML=SAMPLES.map(x=>
  '<span class=qchip onclick="pick(this)" data-a="'+esc(x.a)+'"><span class=qp>◉</span>'+esc(x.a)+' <span class=qs>· '+esc(x.s)+'</span></span>'
).join('');
function pick(el){document.getElementById('addr').value=el.getAttribute('data-a');run();}

// 특징 카드
const FEATS=[
  {i:'▤',t:'3부문 쇠퇴진단',b:'인구사회·산업경제·물리환경 지표를 전국 상대등급(1~10)으로 자동 표시.'},
  {i:'◉',t:'상권 + 빈점포 실측',b:'반경 500m 영업 점포·업종 구성과 시점비교 폐업률을 함께 진단.'},
  {i:'▧',t:'실데이터 · 리포트',b:'정부 API 실데이터 기반. 도시재생 공모·기본계획 자료로 즉시 활용.'}
];
document.getElementById('feats').innerHTML=FEATS.map(f=>
  '<div class=feat><div class=fi>'+f.i+'</div><h3>'+f.t+'</h3><p>'+f.b+'</p></div>'
).join('');

let _map=null;
async function run(){
  const a=document.getElementById('addr').value.trim(); if(!a)return;
  const btn=document.getElementById('go'); btn.disabled=true;
  out.innerHTML='<div class="card"><div class=loading><div class=spin></div>정부 데이터를 불러오는 중…</div></div>';
  try{
    const r=await fetch('/api/diagnose?address='+encodeURIComponent(a));
    const d=await r.json();
    if(d.error){out.innerHTML='<div class=err>'+esc(d.error)+'</div>';}
    else render(d);
  }catch(e){out.innerHTML='<div class=err>요청 실패: '+esc(e)+'</div>';}
  btn.disabled=false;
}

function meanOf(arr){const vs=arr.map(g=>g.value).filter(v=>v!=null);
  if(!vs.length)return null;return Math.round(vs.reduce((a,c)=>a+c,0)/vs.length*10)/10;}

function render(d){
  const c=d.commercial, v=d.vacancy, secs=d.grades_by_sector||{};
  const gonga=(v.gonga!=null)?(v.gonga):null;
  let h='';

  // 요약 카드
  const sectorOrder=['인구사회','산업경제','물리환경'];
  let statHtml='';
  for(const s of sectorOrder){ if(!secs[s])continue;
    const m=meanOf(secs[s]);
    statHtml+='<div class=stat><div class=sv>'+(m==null?'–':m)+'<span style="font-size:13px;color:#a3a3a3;font-weight:500">/10</span></div><div class=sk>'+s+'</div></div>';
  }
  statHtml+='<div class="stat teal"><div class=sv>'+(c.total_stores||0)+'</div><div class=sk>상권 점포</div></div>';
  h+='<div class=summary><div class=top>'
    +'<div><div class=meta><span class=pin>◉</span>'+esc(d.sigungu||'')+' '+esc(d.emd||'')+'</div>'
    +'<div class=rn>'+esc(d.address)+'</div>'
    +'<div class=rs>기준연도 '+esc(d.grade_year)+' · 쇠퇴진단 지표 '+(d.grade_count||0)+'개 · <span class=live>실데이터</span> · '+d.lat.toFixed(5)+', '+d.lon.toFixed(5)+'</div></div>'
    +'<div class=stats>'+statHtml+'</div>'
    +'</div>'
    +'<div class=infobox><span class=ii>ⓘ</span><span>등급값은 전국 상대등급(1~10)이며, 높음/낮음의 양호·쇠퇴 방향은 국토부 공식 범례 확정 후 종합 점수화 예정. 상권 수치는 대상지 중심 반경 500m 기준 현재 영업 점포 스냅샷.</span></div>'
    +'</div>';

  // 지도
  h+='<div class=mapcard><div id=map></div></div>';

  // 상권 현황
  h+='<div class=card><div class=h><div class=ht><span class=hi>◉</span>상권 현황</div><span class=num>반경 500m</span></div>';
  const cats=Object.entries(c.by_major_category||{}).slice(0,8);
  const cmax=cats.length?Math.max.apply(null,cats.map(x=>x[1])):1;
  h+='<div class=rows>';
  for(const [k,val] of cats){
    const w=Math.max(4,Math.round(val/cmax*100));
    h+='<div class=row><div class=rn2>'+esc(k)+'</div><div class=bar><div class="barf teal" style="width:'+w+'%"></div></div><div class=rv>'+val+'</div></div>';
  }
  if(!cats.length)h+='<div class=note>영업 점포 데이터가 없습니다.</div>';
  h+='</div><div class=note>빈 점포·공실은 이 API에 직접 제공되지 않아, 시점 비교(분기 스냅샷 차분)로 폐업·순증감을 추정합니다.</div></div>';

  // 빈점포·공실
  h+='<div class=card><div class=h><div class=ht><span class=hi>▢</span>빈 점포 · 공실</div></div>';
  if(v.has_prev){
    h+='<div class=rows><div class=row style="grid-template-columns:130px 1fr 58px"><div class=rn2>기간</div><div style="font-size:13px;color:#3f3f46">'+v.t0_date+' → '+v.t1_date+'</div><div></div></div></div>';
    h+='<div class=stats style="margin-top:14px">'
      +'<div class=stat><div class=sv>'+v.closed+'</div><div class=sk>폐업</div></div>'
      +'<div class=stat><div class=sv>'+v.opened+'</div><div class=sk>신규</div></div>'
      +'<div class=stat><div class=sv>'+v.closure_rate_pct+'%</div><div class=sk>폐업률</div></div>'
      +'</div>';
  }else{
    h+='<div class=note>기준 스냅샷을 저장했습니다 ('+v.base_date+' · '+v.base_count+'개). 상가정보가 분기 갱신되면 재실행 시 폐업·공실 순증감이 자동 산출됩니다.</div>';
  }
  if(gonga!=null)h+='<div style="margin-top:14px"><span class=badge>공가율(빈집) 등급 '+gonga+' / 10</span><div class=note>※ 주거 빈집 지표로, 상업 공실과는 구분됩니다.</div></div>';
  h+='</div>';

  // 쇠퇴진단 등급 3부문
  h+='<div class=card><div class=h><div class=ht><span class=hi>▤</span>쇠퇴진단 등급</div><span class=num>'+esc(d.grade_area||'')+' · '+d.grade_year+'</span></div>';
  if(!secs||Object.keys(secs).length===0){h+='<div class=note>등급 데이터를 불러오지 못했습니다.</div>';}
  for(const sec of sectorOrder){
    if(!secs[sec])continue;
    const m=meanOf(secs[sec]);
    h+='<div class=sector><div class=st>'+sec+'부문 <span class=c>'+secs[sec].length+'개 지표</span><span class=mean>'+(m==null?'–':m)+'<span style="color:#a3a3a3;font-weight:500;font-size:12px">/10</span></span></div><div class=rows>';
    for(const g of secs[sec]){
      const val=(g.value==null?0:g.value);
      h+='<div class=row><div class=rn2 title="'+esc(g.name)+'">'+esc(g.name)+'</div>'
        +'<div class=bar><div class="barf indigo" style="width:'+(val*10)+'%"></div></div>'
        +'<div class=rv>'+(g.value==null?'–':g.value)+'<span class=u>/10</span></div></div>';
    }
    h+='</div></div>';
  }
  h+='<div class=disc>등급값(1~10)은 전국 대비 상대 위치입니다. 지표별로 높음/낮음의 의미가 달라, 종합 판정은 공식 참고문서 범례 확정 후 산출합니다.</div>';
  h+='</div>';

  out.innerHTML=h;

  // Leaflet 지도 초기화
  try{
    if(window.L){
      if(_map){_map.remove();_map=null;}
      _map=L.map('map',{scrollWheelZoom:false}).setView([d.lat,d.lon],14);
      L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
        {attribution:'&copy; OpenStreetMap',maxZoom:19}).addTo(_map);
      const ic=L.divIcon({className:'',html:'<div style="width:22px;height:22px;border-radius:50%;background:#4f46e5;border:3px solid #fff;box-shadow:0 2px 8px rgba(0,0,0,.3)"></div>',iconSize:[22,22],iconAnchor:[11,11]});
      L.marker([d.lat,d.lon],{icon:ic}).addTo(_map).bindPopup(esc(d.address));
      setTimeout(()=>{if(_map)_map.invalidateSize();},200);
    }
  }catch(e){}
}
</script></div></body></html>"""

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
