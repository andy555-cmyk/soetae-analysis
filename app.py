"""쇠퇴 분석 시스템 - 웹앱.
브라우저에서 주소 입력 -> 뒤에서 지오코딩/상권/쇠퇴등급/빈점포 API 호출 -> 리포트 표시.
실행: pip install -r requirements.txt && (키 환경변수 설정) && python app.py -> http://localhost:5000
정부 API는 CORS로 브라우저 직접호출 불가 -> 이 백엔드가 대신 호출한다."""
import os
from flask import Flask, request, jsonify, render_template_string
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
    return render_template_string(PAGE)

PAGE = r"""<!doctype html><html lang=ko><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>쇠퇴 분석 시스템</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Pretendard:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
:root{
  --bg:#f6f7f9; --card:#ffffff; --line:#edeff2; --line2:#e3e6ea;
  --ink:#0f172a; --sub:#64748b; --mut:#94a3b8;
  --accent:#4f46e5; --accent-soft:#eef2ff; --accent-ink:#4338ca;
  --good:#10b981; --warn:#f59e0b; --bad:#ef4444;
  --shadow:0 1px 2px rgba(16,24,40,.04), 0 4px 16px rgba(16,24,40,.05);
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
  font-family:'Pretendard',-apple-system,BlinkMacSystemFont,'Malgun Gothic',sans-serif;
  -webkit-font-smoothing:antialiased;line-height:1.5}
.wrap{max-width:760px;margin:0 auto;padding:40px 20px 80px}
.brand{display:flex;align-items:center;gap:10px;margin-bottom:6px}
.dot{width:30px;height:30px;border-radius:9px;background:var(--accent);
  display:flex;align-items:center;justify-content:center;color:#fff;font-weight:700;font-size:15px}
h1{font-size:26px;font-weight:700;letter-spacing:-.02em;margin:0}
.lead{color:var(--sub);font-size:14px;margin:8px 0 26px}
.searchbar{display:flex;gap:10px;background:var(--card);padding:10px;border:1px solid var(--line2);
  border-radius:16px;box-shadow:var(--shadow)}
input{flex:1;border:0;outline:0;padding:12px 14px;font-size:15px;background:transparent;color:var(--ink);
  font-family:inherit;border-radius:10px}
input::placeholder{color:var(--mut)}
button{border:0;border-radius:11px;background:var(--accent);color:#fff;font-weight:600;font-size:15px;
  padding:0 24px;cursor:pointer;font-family:inherit;transition:background .15s,transform .05s}
button:hover{background:var(--accent-ink)} button:active{transform:scale(.98)} button:disabled{opacity:.55;cursor:default}
.hint{color:var(--mut);font-size:12.5px;margin:10px 2px 0}
#out{margin-top:22px;display:flex;flex-direction:column;gap:16px}
.meta{color:var(--sub);font-size:13px;display:flex;align-items:center;gap:7px;padding:2px 4px}
.pin{color:var(--accent)}
.card{background:var(--card);border:1px solid var(--line);border-radius:18px;padding:22px 22px;box-shadow:var(--shadow)}
.h{display:flex;align-items:center;gap:8px;font-size:13px;font-weight:600;color:var(--sub);
  text-transform:none;letter-spacing:.01em;margin-bottom:16px}
.h .num{color:var(--accent);background:var(--accent-soft);border-radius:6px;padding:1px 7px;font-size:12px}
.metrics{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}
.metric{background:#fafbfc;border:1px solid var(--line);border-radius:14px;padding:14px 16px}
.metric .v{font-size:24px;font-weight:700;letter-spacing:-.02em}
.metric .k{font-size:12px;color:var(--sub);margin-top:2px}
.chips{display:flex;flex-wrap:wrap;gap:8px;margin-top:4px}
.chip{background:#f4f5f7;border:1px solid var(--line);color:#334155;border-radius:999px;
  padding:6px 13px;font-size:12.5px;font-weight:500}
.chip b{font-weight:700;color:var(--ink)}
.note{font-size:12px;color:var(--sub);margin-top:12px;line-height:1.55}
.badge{display:inline-flex;align-items:center;gap:6px;background:var(--accent-soft);color:var(--accent-ink);
  border-radius:999px;padding:6px 13px;font-size:12.5px;font-weight:600}
.sector{margin-top:18px}
.sector:first-of-type{margin-top:6px}
.sector .st{font-size:13px;font-weight:700;color:var(--ink);margin-bottom:10px;display:flex;align-items:center;gap:7px}
.sector .st .c{color:var(--mut);font-weight:500;font-size:12px}
.grow{display:grid;grid-template-columns:1fr 150px 26px;align-items:center;gap:12px;padding:7px 0;
  border-top:1px solid var(--line)}
.grow:first-child{border-top:0}
.gname{font-size:13.5px;color:#334155}
.bar{height:7px;background:#eef0f3;border-radius:99px;overflow:hidden}
.barf{height:100%;background:linear-gradient(90deg,#818cf8,#4f46e5);border-radius:99px}
.gv{font-size:13px;font-weight:700;text-align:right;color:var(--accent-ink)}
.disc{font-size:11.5px;color:var(--mut);margin-top:14px;line-height:1.5}
.loading{display:flex;align-items:center;gap:12px;color:var(--sub);font-size:14px;justify-content:center;padding:30px}
.spin{width:20px;height:20px;border:2.5px solid var(--line2);border-top-color:var(--accent);border-radius:50%;
  animation:sp .7s linear infinite}
@keyframes sp{to{transform:rotate(360deg)}}
.err{background:#fef2f2;border:1px solid #fecaca;color:#b91c1c;border-radius:14px;padding:14px 16px;font-size:13.5px}
@media(max-width:560px){.metrics{grid-template-columns:1fr}.grow{grid-template-columns:1fr 90px 24px}.wrap{padding:28px 16px 60px}}
</style></head><body><div class=wrap>
<div class=brand><div class=dot>쇠</div><h1>쇠퇴 분석 시스템</h1></div>
<p class=lead>주소만 입력하면 대상지의 상권·빈점포·쇠퇴진단 등급을 자동으로 분석합니다. 실데이터 · 국토교통부 · 소상공인시장진흥공단 · VWorld</p>
<div class=searchbar>
<input id=addr placeholder="예) 부산광역시 기장군 기장읍 동부리 487" value="부산광역시 기장군 기장읍 동부리 487" onkeydown="if(event.key==='Enter')run()">
<button id=go onclick=run()>진단</button>
</div>
<div class=hint>반경 500m 기준 · 처음 조회 시 10~20초 소요</div>
<div id=out></div>
<script>
const out=document.getElementById('out');
function esc(s){return (s==null?'':(''+s)).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]))}
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
function render(d){
  const c=d.commercial, v=d.vacancy; let h='';
  h+='<div class=meta><span class=pin>◉</span>'+esc(d.address)+' · '+d.lat.toFixed(5)+', '+d.lon.toFixed(5)+' · '+esc(d.sigungu||'')+' '+esc(d.emd||'')+'</div>';
  // metrics
  const gonga=(v.gonga!=null)?(v.gonga+'/10'):'—';
  const vac=v.has_prev?(v.closure_rate_pct+'%'):'기준설정';
  h+='<div class=metrics>'
   +'<div class=metric><div class=v>'+c.total_stores+'</div><div class=k>반경 500m 점포</div></div>'
   +'<div class=metric><div class=v>'+gonga+'</div><div class=k>공가율(빈집) 등급</div></div>'
   +'<div class=metric><div class=v>'+(d.grade_count||0)+'</div><div class=k>쇠퇴진단 지표</div></div>'
   +'</div>';
  // 상권
  h+='<div class=card><div class=h>상권 현황<span class=num>반경 500m</span></div><div class=chips>';
  const cats=Object.entries(c.by_major_category).slice(0,10);
  for(const [k,val] of cats)h+='<span class=chip>'+esc(k)+' <b>'+val+'</b></span>';
  h+='</div></div>';
  // 빈점포
  h+='<div class=card><div class=h>빈 점포 · 공실</div>';
  if(v.has_prev){
    h+='<div class=chips><span class=chip>기간 <b>'+v.t0_date+'→'+v.t1_date+'</b></span><span class=chip>폐업 <b>'+v.closed+'</b></span><span class=chip>신규 <b>'+v.opened+'</b></span><span class=chip>폐업률 <b>'+v.closure_rate_pct+'%</b></span></div>';
  }else{
    h+='<div class=note>기준 스냅샷을 저장했습니다 ('+v.base_date+' · '+v.base_count+'개). 상가정보가 분기 갱신되면 재실행 시 폐업·공실 순증감이 자동 산출됩니다.</div>';
  }
  if(v.gonga!=null)h+='<div style="margin-top:12px"><span class=badge>공가율(빈집) 등급 '+v.gonga+' / 10</span><div class=note>※ 주거 빈집 지표로, 상업 공실과는 구분됩니다.</div></div>';
  h+='</div>';
  // 쇠퇴 등급
  h+='<div class=card><div class=h>쇠퇴진단 등급<span class=num>'+esc(d.grade_area||'')+' · '+d.grade_year+'</span></div>';
  const secs=d.grades_by_sector;
  if(!secs||Object.keys(secs).length===0){h+='<div class=note>등급 데이터를 불러오지 못했습니다.</div>';}
  for(const sec of ['인구사회','산업경제','물리환경']){
    if(!secs[sec])continue;
    h+='<div class=sector><div class=st>'+sec+'부문 <span class=c>'+secs[sec].length+'개 지표</span></div>';
    for(const g of secs[sec]){
      const val=(g.value==null?0:g.value);
      h+='<div class=grow><div class=gname>'+esc(g.name)+'</div>'
        +'<div class=bar><div class=barf style="width:'+(val*10)+'%"></div></div>'
        +'<div class=gv>'+(g.value==null?'—':g.value)+'</div></div>';
    }
    h+='</div>';
  }
  h+='<div class=disc>등급값(1~10)은 전국 대비 상대 위치입니다. 지표별로 높음/낮음의 의미가 달라, 종합 판정은 공식 참고문서 범례 확정 후 산출합니다.</div>';
  h+='</div>';
  out.innerHTML=h;
}
</script></div></body></html>"""

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
