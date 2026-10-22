#!/usr/bin/env python3
"""Agenda-preview: Notion-Calendar-achtige weekweergave met meeting-voorstellen
uitgelicht tussen de bestaande events van de reviewer, plus het annotator-snippet.

    python3 agenda-preview.py spec.json -o pagina.html

De spec (JSON) bouw je met bin/agenda-spec.py uit Graph get-calendar-view,
of met de hand. Velden (alles behalve events/proposals optioneel):

  title, heading, subheading        paginatitel, kop, regel onder de kop
  start "YYYY-MM-DD"                eerste dag (wordt naar maandag afgerond)
  weeks 3                           aantal weken
  hours [7, 23]                     zichtbaar uurbereik
  bgMinHours 3                      vanaf deze duur: achtergrond-lane links
  calendars [{id,label,color}]      color: purple|orange|blue|green|gray|red
  events [{cal,title,start,end,allDay,showAs,attendees:[{name,address,
           type,response}],organizer:{name,address},body,location,tag}]
  proposals [{nr,title,start,end,invitees:[{name,address}|"a@b"],
              toelichting,status:"open|verstuurd|vervallen",notitie,cal}]
  tags {"<exacte titel>": "nieuw"}  label + gestippelde rand op die events
  syncTitles ["Busy."]              sync-kopieën; vallen weg als een event in
  syncLabel "Busy (sync copy)"      een andere agenda ±1 min gelijk loopt

Tijden zijn lokaal (Europe/Amsterdam), "YYYY-MM-DDTHH:MM".
Voorstellen met status open zijn sleepbaar (verplaatsen binnen de week, grepen
boven/onder voor begin/eind, snap 15 min). Elke wijziging gaat via de bridge
naar state.json (component "agenda", key "voorstel-<nr>": {start, end, base});
bij laden wint die state van de overlay zolang base nog gelijk is aan de
overlay. Terugschrijven in de overlay: agenda-spec.py --apply-state.
De route naar de bridge is die van het annotator-snippet (blok LA-BRIDGE-KEUZE,
bij het bouwen ingeplakt): een /p/-pagina van de bridge praat met de eigen
origin, anders wint <meta name="html-annotator-endpoint">, anders de
standaardpoort. De pagina stuurt de slug van het -o-bestand mee, zodat de state
ook buiten /p/ onder <annotatie-root>/<slug>/state.json landt.

Een voorstel met status verstuurd vervangt het echte event met dezelfde titel
en start (±1 min) en neemt daarvan deelnemers + reacties over.
"""
import argparse, datetime as D, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
SNIPPET = os.path.join(HERE, "..", "references", "annotator-snippet.html")
sys.path.insert(0, os.path.join(HERE, ".."))
from html_annotator.bridge import slugify  # noqa: E402  zelfde slug als de bridge


def bridge_keuze():
    """Het blok LA-BRIDGE-KEUZE uit het annotator-snippet: route + pagina-identiteit.
    Eén bron voor snippet en agenda-pagina (docs/DECISIONS.md, 2026-10-21)."""
    s = open(SNIPPET, encoding="utf-8").read()
    i, j = s.index("/* LA-BRIDGE-KEUZE"), s.index("/* /LA-BRIDGE-KEUZE */")
    return s[i:j]


def P(s):
    return D.datetime.fromisoformat(s[:16])


def near(a, b, sec=60):
    return abs((P(a) - P(b)).total_seconds()) <= sec


def norm_person(p):
    if isinstance(p, str):
        p = p.strip()
        if "<" in p and p.endswith(">"):
            n, a = p[:-1].split("<", 1)
            return {"name": n.strip(), "address": a.strip()}
        return {"name": "", "address": p}
    return {k: p.get(k, "") for k in ("name", "address", "type", "response")}


def build(spec):
    sync_titles = {t.strip().casefold() for t in spec.get("syncTitles", ["Busy.", "Busy", "Bezet"])}
    sync_label = spec.get("syncLabel", "Busy (sync copy)")
    tags = spec.get("tags", {})
    evs = []
    for i, e in enumerate(spec.get("events", [])):
        t = e.get("title", "").strip()
        if t.startswith(("Geannuleerd:", "Canceled:", "Cancelled:")) or e.get("cancelled"):
            continue
        x = dict(e, kind="event", id=f"e{i}", title=t)
        x["attendees"] = [norm_person(a) for a in e.get("attendees", [])]
        x["sync"] = t.casefold() in sync_titles
        if t in tags:
            x["tag"] = tags[t]
        evs.append(x)
    real = [x for x in evs if not x["sync"]]
    out = []
    for x in evs:
        if x["sync"]:
            if any(r["cal"] != x["cal"] and near(r["start"], x["start"]) and near(r["end"], x["end"]) for r in real):
                continue  # spiegel van een event dat we al tonen
            x = dict(x, cal="sync", title=sync_label, origCal=x["cal"])
        out.append(x)
    props = []
    for p in spec.get("proposals", []):
        q = dict(p, kind="prop", id=f"p{p['nr']}", status=p.get("status", "open"))
        q["attendees"] = [norm_person(a) for a in p.get("invitees", [])]
        q.setdefault("cal", "prop")
        # echte (verstuurde) tegenhanger: weghalen, deelnemers + reacties overnemen
        for r in list(out):
            if r["title"].casefold() == q["title"].casefold() and near(r["start"], q["start"]):
                out.remove(r)
                if r.get("attendees"):
                    q["attendees"] = r["attendees"]
                q.setdefault("organizer", r.get("organizer"))
                q["realCal"] = r["cal"]
                if q["status"] == "open":
                    q["status"] = "verstuurd"
        props.append(q)
    cals = list(spec.get("calendars", []))
    ids = {c["id"] for c in cals}
    if any(x["cal"] == "sync" for x in out) and "sync" not in ids:
        cals.append({"id": "sync", "label": "busy (sync copy)", "color": "gray"})
    start = D.date.fromisoformat(spec.get("start") or min(x["start"] for x in out + props)[:10])
    start -= D.timedelta(days=start.weekday())
    return {
        "title": spec.get("title", "Agenda preview"),
        "heading": spec.get("heading", ""),
        "subheading": spec.get("subheading", ""),
        "start": start.isoformat(),
        "weeks": spec.get("weeks", 2),
        "hours": spec.get("hours", [7, 23]),
        "bgMinHours": spec.get("bgMinHours", 3),
        "today": spec.get("today"),
        "calendars": cals,
        "events": out,
        "proposals": sorted(props, key=lambda q: q["nr"]),
    }


CSS = r"""
:root{--bg:#fff;--fg:#37352f;--mut:#8f8e8a;--line:#efefed;--hl:#f7f7f5;--card:#fff;--shadow:0 8px 30px rgba(15,15,15,.16),0 0 0 1px rgba(15,15,15,.06);
--purple-bg:#f3e8fd;--purple-fg:#7b3fbf;--purple-bd:#b48ae6;--orange-bg:#fde9df;--orange-fg:#b5502a;--orange-bd:#e8946c;
--blue-bg:#e3effd;--blue-fg:#2463b5;--blue-bd:#7fa9e3;--green-bg:#e2f3e6;--green-fg:#2b7a3d;--green-bd:#7cc08b;
--gray-bg:#f1f1ef;--gray-fg:#86857f;--gray-bd:#b9b8b3;--red-bg:#fde4e4;--red-fg:#b42323;--red-bd:#e98a8a;
--prop:#e5370f;--prop-bg:#fff4c2;--sent:#1f8f4a;--sent-bg:#e3f6e9;--tag:#0f7b6c;--tag-bg:#ddf3ee;--nowc:#eb5757}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#191919;--fg:#e6e6e4;--mut:#7d7c78;--line:#2a2a28;--hl:#202020;--card:#252525;--shadow:0 8px 30px rgba(0,0,0,.5),0 0 0 1px rgba(255,255,255,.08);
--purple-bg:#2f2440;--purple-fg:#c9a7f2;--purple-bd:#7b55aa;--orange-bg:#3a2820;--orange-fg:#f0a582;--orange-bd:#a8613f;
--blue-bg:#1d2b3d;--blue-fg:#8fb9ef;--blue-bd:#41689c;--green-bg:#1d3324;--green-fg:#8fd7a0;--green-bd:#3f7d4f;
--gray-bg:#262625;--gray-fg:#8a8984;--gray-bd:#5a5955;--red-bg:#3d1f1f;--red-fg:#f0a0a0;--red-bd:#a04848;
--prop-bg:#4a3d00;--sent:#4cc47a;--sent-bg:#173823;--tag:#5fd0bd;--tag-bg:#173b35}}
:root[data-theme="dark"]{--bg:#191919;--fg:#e6e6e4;--mut:#7d7c78;--line:#2a2a28;--hl:#202020;--card:#252525;--shadow:0 8px 30px rgba(0,0,0,.5),0 0 0 1px rgba(255,255,255,.08);
--purple-bg:#2f2440;--purple-fg:#c9a7f2;--purple-bd:#7b55aa;--orange-bg:#3a2820;--orange-fg:#f0a582;--orange-bd:#a8613f;
--blue-bg:#1d2b3d;--blue-fg:#8fb9ef;--blue-bd:#41689c;--green-bg:#1d3324;--green-fg:#8fd7a0;--green-bd:#3f7d4f;
--gray-bg:#262625;--gray-fg:#8a8984;--gray-bd:#5a5955;--red-bg:#3d1f1f;--red-fg:#f0a0a0;--red-bd:#a04848;
--prop-bg:#4a3d00;--sent:#4cc47a;--sent-bg:#173823;--tag:#5fd0bd;--tag-bg:#173b35}
*{box-sizing:border-box}html,body{max-width:100%;overflow-x:hidden}
body{margin:0;background:var(--bg);color:var(--fg);font:13px/1.35 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
main{padding:16px;max-width:1500px;margin:0 auto}
.top{display:flex;flex-wrap:wrap;gap:8px 16px;align-items:baseline;margin-bottom:8px}.top h2{margin:0;font-size:17px}.top .sub{color:var(--mut)}
.legend{display:flex;flex-wrap:wrap;gap:4px 14px;margin:0 0 10px}.legend span{display:inline-flex;align-items:center;gap:5px;color:var(--mut);font-size:12px}
.legend i{width:11px;height:11px;border-radius:3px;display:inline-block}
.tablewrap{overflow-x:auto;margin:4px 0 18px}table{border-collapse:collapse;width:100%;min-width:560px;font-size:13px}
td{border-top:1px solid var(--line);padding:7px 8px;vertical-align:top}tr.prow{cursor:pointer}tr.prow:hover td{background:var(--hl)}
.pn{color:#fff;font-weight:700;border-radius:4px;padding:1px 6px;white-space:nowrap;font-size:12px}
.st-open .pn,.pn.st-open{background:var(--prop)}.st-verstuurd .pn,.pn.st-verstuurd{background:var(--sent)}.st-vervallen .pn,.pn.st-vervallen{background:var(--gray-fg)}
.sub{color:var(--mut)}.note{color:var(--prop);font-size:12px;margin-top:2px}.to{font-size:12px;color:var(--mut);word-break:break-word}
.nav{display:flex;align-items:center;gap:8px;margin:4px 0 8px}.nav h1{font-size:22px;margin:0 8px 0 0;font-weight:700}
.nav button{border:1px solid var(--line);background:var(--bg);color:var(--fg);border-radius:6px;min-width:30px;height:28px;font-size:15px;cursor:pointer;padding:0 8px}
.nav .range{color:var(--mut)}
.scroll{overflow-x:auto;-webkit-overflow-scrolling:touch;border-top:1px solid var(--line)}.wkwrap{min-width:860px}
.grid{display:grid;grid-template-columns:52px repeat(7,minmax(0,1fr));border-bottom:1px solid var(--line)}
.dh{text-align:center;padding:6px 0;color:var(--mut)}.dh b{color:var(--fg);font-weight:500}.dh.today b{background:var(--nowc);color:#fff;border-radius:5px;padding:0 5px}
.adwrap{grid-column:2/9;display:grid;grid-template-columns:repeat(7,minmax(0,1fr));gap:2px;padding:3px 0;min-height:24px}
.lbl{color:var(--mut);font-size:10px;padding-top:6px;text-align:right;padding-right:6px}
.ad{font-size:11.5px;padding:2px 6px;border-radius:4px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin:0 2px;cursor:pointer;border-left:3px solid}
.body{display:grid;grid-template-columns:52px repeat(7,minmax(0,1fr));position:relative}
.hours{position:relative}.hr{position:absolute;right:6px;transform:translateY(-6px);color:var(--mut);font-size:10.5px}
.day{position:relative;border-left:1px solid var(--line)}.day.wknd{background:var(--hl)}.line{position:absolute;left:0;right:0;border-top:1px solid var(--line)}
.bgev{position:absolute;z-index:2;border-radius:4px;border-left:3px solid;cursor:pointer;overflow:hidden;opacity:.9}
.bgev .vt{writing-mode:vertical-rl;white-space:nowrap;font-size:11px;font-weight:600;padding:5px 0 0;display:block;margin:0 auto;line-height:1}
.bgev .vt small{font-weight:400;opacity:.8}
.ev{position:absolute;border-radius:4px;padding:2px 5px;overflow:hidden;font-size:11.5px;line-height:13px;border-left:3px solid;z-index:1;cursor:pointer}
.ev .t{font-weight:500;overflow:hidden;word-break:break-word}.ev .tm{opacity:.75;font-size:10.5px;white-space:nowrap}
.ev:hover,.bgev:hover,.ad:hover{filter:brightness(.97)}.sel{outline:2px solid var(--fg)!important;outline-offset:0}
.k-prop{color:var(--fg);z-index:3;border:2px solid var(--prop);border-left-width:6px;background:var(--prop-bg);box-shadow:0 0 0 3px rgba(229,55,15,.16),0 3px 10px rgba(0,0,0,.15)}
.k-prop.s-verstuurd{border-color:var(--sent);background:var(--sent-bg);box-shadow:0 0 0 3px rgba(31,143,74,.16),0 3px 10px rgba(0,0,0,.12)}
.k-prop.s-vervallen{border-color:var(--gray-bd);border-style:dashed;background:var(--gray-bg);color:var(--mut);box-shadow:none;text-decoration:line-through}
.badge{display:inline-block;margin-right:4px;background:var(--prop);color:#fff;font-size:9px;font-weight:700;border-radius:3px;padding:0 4px;text-transform:uppercase;vertical-align:1px;line-height:13px;text-decoration:none}
.ev{container-type:inline-size}@container (max-width:120px){.badge .full,.mv .full{display:none}}.s-verstuurd .badge{background:var(--sent)}.s-vervallen .badge{background:var(--gray-fg)}
.ev.tagged{outline:2px dashed var(--tag);outline-offset:-2px;background:var(--tag-bg);color:var(--tag);border-color:var(--tag);z-index:2}.tagged .badge{background:var(--tag)}
.now{position:absolute;left:0;right:0;border-top:2px solid var(--nowc);z-index:5;pointer-events:none}.now:before{content:"";position:absolute;left:-5px;top:-6px;width:10px;height:10px;border-radius:50%;background:var(--nowc)}
#pop{position:fixed;z-index:2147483000;width:340px;max-width:calc(100vw - 24px);max-height:min(560px,calc(100vh - 24px));overflow:auto;background:var(--card);color:var(--fg);border-radius:10px;box-shadow:var(--shadow);padding:14px 16px 16px;display:none;font-size:13px}
#pop.open{display:block}#pop h3{margin:0 26px 6px 0;font-size:16px;line-height:1.3;display:flex;gap:8px;align-items:flex-start}
#pop h3 .dot{flex:none;width:12px;height:12px;border-radius:3px;margin-top:4px}#pop .x{position:absolute;right:8px;top:8px;border:0;background:none;color:var(--mut);font-size:20px;cursor:pointer;width:28px;height:28px;border-radius:6px}
#pop .x:hover{background:var(--hl)}#pop .row{display:flex;gap:10px;padding:6px 0;border-top:1px solid var(--line)}#pop .row:first-of-type{border-top:0}
#pop .k{flex:none;width:84px;color:var(--mut);font-size:12px}#pop .v{flex:1;min-width:0;word-break:break-word}
#pop ul{list-style:none;margin:0;padding:0}#pop li{padding:2px 0}#pop li .a{color:var(--mut);font-size:12px}#pop .r{font-size:11px;color:var(--mut)}
#pop .r.ok{color:var(--sent)}#pop .r.no{color:var(--red-fg)}#pop .txt{display:block;white-space:pre-wrap;color:var(--fg)}
.k-prop.drag{touch-action:none;cursor:grab;user-select:none;-webkit-user-select:none}.k-prop.dragging{cursor:grabbing;z-index:6;opacity:.92}
.k-prop .hd{position:absolute;left:0;right:0;height:7px;cursor:ns-resize;z-index:2}.k-prop .hd.ht{top:-2px}.k-prop .hd.hb{bottom:-2px}
.k-prop .hd:after{content:"";position:absolute;left:50%;width:18px;margin-left:-9px;height:3px;border-radius:2px;background:var(--prop);opacity:0;top:2px}.k-prop.drag:hover .hd:after{opacity:.7}
.k-prop.clash{border-color:var(--red-fg)!important;box-shadow:0 0 0 3px rgba(180,35,35,.35)!important}
.mv{display:inline-block;margin-right:4px;background:var(--blue-fg);color:#fff;font-size:9px;font-weight:700;border-radius:3px;padding:0 4px;text-transform:uppercase;vertical-align:1px;line-height:13px}
#dtip{position:fixed;z-index:2147483001;pointer-events:none;background:var(--fg);color:var(--bg);font-size:12px;font-weight:600;border-radius:5px;padding:2px 7px;display:none;white-space:nowrap}
.agpill{font-size:11.5px;border-radius:10px;padding:2px 9px;background:var(--hl);color:var(--mut);border:1px solid var(--line)}.agpill.ok{color:var(--sent)}.agpill.off{color:var(--red-fg)}
#pop .reset{margin-top:6px;border:1px solid var(--line);background:var(--bg);color:var(--fg);border-radius:6px;padding:3px 9px;font-size:12px;cursor:pointer}#pop .reset:hover{background:var(--hl)}
.chip{display:inline-block;font-size:11px;font-weight:700;border-radius:4px;padding:1px 6px;color:#fff;margin:0 0 6px}
@media (max-width:640px){main{padding:12px 16px}table{min-width:0}tr.prow{display:grid;grid-template-columns:auto 1fr;gap:4px 10px;border-top:1px solid var(--line);padding:8px 0}tr.prow td{border:0;padding:0}tr.prow td:nth-child(n+3){grid-column:1/-1}#pop{left:0!important;right:0;bottom:0;top:auto!important;width:100%;max-width:100%;border-radius:14px 14px 0 0;max-height:75vh}.nav h1{font-size:18px}}
"""

JS = r"""
(function(){
const S=JSON.parse(document.getElementById('agenda-data').textContent);
const H0=S.hours[0],H1=S.hours[1],PX=60,LANE=24,BG=S.bgMinHours*60;
const DN=['Sun','Mon','Tue','Wed','Thu','Fri','Sat'],MN=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'],MF=['January','February','March','April','May','June','July','August','September','October','November','December'];
const P=s=>{const m=s.match(/(\d+)-(\d+)-(\d+)(?:T(\d+):(\d+))?/);return new Date(+m[1],m[2]-1,+m[3],+(m[4]||0),+(m[5]||0))};
const esc=s=>String(s==null?'':s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const pad=n=>String(n).padStart(2,'0'),hm=d=>pad(d.getHours())+':'+pad(d.getMinutes());
const day0=d=>new Date(d.getFullYear(),d.getMonth(),d.getDate());
const addD=(d,n)=>new Date(d.getFullYear(),d.getMonth(),d.getDate()+n);
const same=(a,b)=>a.getTime()===b.getTime();
const mins=(a,b)=>(b-a)/60000;
const CAL={};S.calendars.forEach(c=>CAL[c.id]=c);CAL.prop={id:'prop',label:'proposal',color:'prop'};
const all=S.events.concat(S.proposals).map(x=>Object.assign({},x,{s:P(x.start),e:P(x.end)}));
all.forEach(x=>{if(x.kind==='prop'){x.os=x.s;x.oe=x.e;}});
const L16=d=>d.getFullYear()+'-'+pad(d.getMonth()+1)+'-'+pad(d.getDate())+'T'+pad(d.getHours())+':'+pad(d.getMinutes());
const moved=x=>x.kind==='prop'&&(x.s-x.os||x.e-x.oe);
const BY={};all.forEach(x=>BY[x.id]=x);
function prep(){all.forEach(x=>{x.multi=!x.allDay&&!same(day0(x.s),day0(new Date(x.e-60000)));x.top=x.allDay||x.multi;});}prep();
const today=S.today?P(S.today):day0(new Date());
const W0=P(S.start),NW=S.weeks;
const col=x=>x.kind==='prop'?'':('c-'+((CAL[x.cal]||{}).color||'gray'));
const cssc=c=>'background:var(--'+c+'-bg);color:var(--'+c+'-fg);border-color:var(--'+c+'-bd)';
document.head.insertAdjacentHTML('beforeend','<style>'+['purple','orange','blue','green','gray','red'].map(c=>'.c-'+c+'{'+cssc(c)+'}').join('')+'</style>');
const SL={open:'proposal',verstuurd:'sent',vervallen:'dropped'};
const BGM=x=>x.kind!=='prop'&&!x.top&&mins(x.s,x.e)>=BG;
const clash=x=>x.kind==='prop'&&x.status==='open'&&all.some(y=>y.kind!=='prop'&&!y.top&&!BGM(y)&&y.s<x.e&&y.e>x.s);
const canDrag=x=>x.kind==='prop'&&x.status==='open'&&!x.top;
const badge=x=>x.kind==='prop'?(moved(x)?'<span class="mv">↕<span class="full"> moved</span></span>':'')+'<span class="badge">#'+x.nr+'<span class="full"> '+SL[x.status]+'</span></span>':(x.tag?'<span class="badge">'+esc(x.tag)+'</span>':'');
const cls=x=>(x.kind==='prop'?'k-prop s-'+x.status+(canDrag(x)?' drag':'')+(clash(x)?' clash':''):col(x))+(x.tag?' tagged':'');
// --- render
const wrap=document.getElementById('weeks');let secs=[],cur=0;
function render(){let html='';prep();
for(let w=0;w<NW;w++){
  const ws=addD(W0,7*w),days=[...Array(7)].map((_,i)=>addD(ws,i));
  html+='<section class="week" data-w="'+w+'" hidden>';
  html+='<div class="grid"><div></div>'+days.map(d=>'<div class="dh'+(same(d,today)?' today':'')+'">'+DN[d.getDay()]+' <b>'+d.getDate()+'</b></div>').join('')+'</div>';
  // hele-dag-rij
  const we=addD(ws,7),ad=all.filter(x=>x.top&&x.s<we&&x.e>ws).sort((a,b)=>a.s-b.s||b.e-a.e),rows=[];
  html+='<div class="grid"><div class="lbl">all day</div><div class="adwrap">';
  ad.forEach(x=>{const a=Math.max(0,Math.round((day0(x.s)-ws)/864e5)),b=Math.min(6,Math.round((day0(new Date(x.e-60000))-ws)/864e5));
    let r=0;while(rows[r]&&rows[r].some(([p,q])=>!(b<p||a>q)))r++;(rows[r]=rows[r]||[]).push([a,b]);
    const tm=x.allDay?'':' · '+DN[x.s.getDay()]+' '+hm(x.s)+' → '+DN[x.e.getDay()]+' '+hm(x.e);
    html+='<div class="ad '+cls(x)+'" data-id="'+x.id+'" role="button" tabindex="0" style="grid-column:'+(a+1)+'/'+(b+2)+';grid-row:'+(r+1)+'">'+badge(x)+esc(x.title)+tm+'</div>';});
  html+='</div></div><div class="body" style="height:'+((H1-H0)*PX)+'px"><div class="hours">'+[...Array(H1-H0)].map((_,i)=>'<div class="hr" style="top:'+(i*PX)+'px">'+pad(H0+i)+':00</div>').join('')+'</div>';
  days.forEach(d=>{
    const lo=new Date(d.getFullYear(),d.getMonth(),d.getDate(),H0),hi=new Date(d.getFullYear(),d.getMonth(),d.getDate(),H1);
    html+='<div class="day'+(d.getDay()%6===0?' wknd':'')+'" data-day="'+d.toDateString()+'">'+[...Array(H1-H0)].map((_,i)=>'<div class="line" style="top:'+(i*PX)+'px"></div>').join('');
    const items=all.filter(x=>!x.top&&same(day0(x.s),d)&&x.e>lo&&x.s<hi).map(x=>Object.assign(x,{cs:x.s<lo?lo:x.s,ce:x.e>hi?hi:x.e}));
    const bg=items.filter(x=>x.kind!=='prop'&&mins(x.s,x.e)>=BG).sort((a,b)=>a.s-b.s||b.e-a.e),lanes=[];
    bg.forEach(x=>{let l=0;while(lanes[l]&&lanes[l]>x.s)l++;lanes[l]=x.e;x.lane=l;
      const top=mins(lo,x.cs)/60*PX,h=mins(x.cs,x.ce)/60*PX;
      html+='<div class="bgev '+cls(x)+'" data-id="'+x.id+'" role="button" tabindex="0" title="'+esc(x.title)+'" style="top:'+top+'px;height:'+(h-1)+'px;left:'+(l*LANE+1)+'px;width:'+(LANE-2)+'px"><span class="vt">'+esc(x.title)+' <small>'+hm(x.s)+'–'+hm(x.e)+'</small></span></div>';});
    const reg=items.filter(x=>!bg.includes(x)).sort((a,b)=>a.s-b.s||b.e-a.e);
    const off=x=>bg.reduce((m,b)=>mins(b.s>x.s?b.s:x.s,b.e<x.e?b.e:x.e)>=15?Math.max(m,(b.lane+1)*LANE):m,0); // <15 min overlap: lane ligt erboven
    let cl=[],end=null;const clusters=[];
    reg.forEach(x=>{if(cl.length&&x.s>=end){clusters.push(cl);cl=[];end=null}cl.push(x);end=end&&end>x.e?end:x.e});if(cl.length)clusters.push(cl);
    clusters.forEach(c=>{const cols=[];c.forEach(x=>{let i=cols.findIndex(e=>x.s>=e);if(i<0){i=cols.length;cols.push(x.e)}else cols[i]=x.e;x.col=i});
      const o=Math.max(...c.map(off)),n=cols.length;
      c.forEach(x=>{const top=mins(lo,x.cs)/60*PX,h=Math.max(16,mins(x.cs,x.ce)/60*PX-2);
        const L='calc('+o+'px + (100% - '+o+'px) * '+(x.col/n)+' + 1px)',Wd='calc((100% - '+o+'px) / '+n+' - 3px)';
        html+='<div class="ev '+cls(x)+'" data-id="'+x.id+'" role="button" tabindex="0" style="top:'+top+'px;height:'+h+'px;left:'+L+';width:'+Wd+'"><div class="t">'+badge(x)+esc(x.title)+'</div>'+(h>=30?'<div class="tm">'+hm(x.s)+'–'+hm(x.e)+'</div>':'')+(canDrag(x)?'<i class="hd ht" data-h="top"></i><i class="hd hb" data-h="bottom"></i>':'')+'</div>';});});
    html+='</div>';});
  html+='</div></section>';
}
wrap.innerHTML=html;secs=[...wrap.querySelectorAll('.week')];
S.proposals.forEach(q=>{const x=BY[q.id],r=document.querySelector('tr.prow[data-pid="'+q.id+'"] td:nth-child(2)');
  if(x&&r)r.innerHTML=DN[x.s.getDay()]+' '+pad(x.s.getDate())+'-'+pad(x.s.getMonth()+1)+'<br>'+hm(x.s)+'–'+hm(x.e)+(moved(x)?'<div class="note">moved</div>':'');});
}
render();
// --- week-navigatie + now-lijn
const tw=Math.floor((day0(new Date())-W0)/(7*864e5));if(tw>=0&&tw<NW)cur=tw;
function show(i){cur=Math.max(0,Math.min(NW-1,i));secs.forEach((s,j)=>s.hidden=j!==cur);const a=addD(W0,7*cur),b=addD(a,6);
  document.getElementById('wkm').textContent=MF[a.getMonth()]+' '+a.getFullYear();
  document.getElementById('wkr').textContent=a.getDate()+' '+MN[a.getMonth()]+' – '+b.getDate()+' '+MN[b.getMonth()];}
document.getElementById('prev').onclick=()=>show(cur-1);document.getElementById('next').onclick=()=>show(cur+1);
document.getElementById('tdy').onclick=()=>show(tw>=0&&tw<NW?tw:0);
function now(){document.querySelectorAll('.now').forEach(n=>n.remove());const t=new Date(),c=document.querySelector('.day[data-day="'+day0(t).toDateString()+'"]');
  const h=t.getHours()+t.getMinutes()/60;if(c&&h>=H0&&h<=H1)c.insertAdjacentHTML('beforeend','<div class="now" style="top:'+((h-H0)*PX)+'px"></div>');}
show(cur);now();setInterval(now,60000);
function rerender(){render();show(cur);now();}
// --- popover
const pop=document.getElementById('pop');let selEl=null;
const RS={accepted:['accepted','ok'],tentativelyAccepted:['tentative',''],declined:['declined','no'],organizer:['organizer','ok'],none:['no response',''],notResponded:['no response','']};
const SA={busy:'busy',free:'free',oof:'out of office',tentative:'tentative',workingElsewhere:'working elsewhere'};
const person=p=>'<li>'+esc(p.name||p.address)+(p.name&&p.address?' <span class="a">'+esc(p.address)+'</span>':'')+(p.type==='optional'?' <span class="r">(optional)</span>':'')+(p.response&&RS[p.response]?' <span class="r '+RS[p.response][1]+'">· '+RS[p.response][0]+'</span>':'')+'</li>';
function when(x){const d=x.s,e=x.e;if(x.allDay){const l=addD(e,-1);return DN[d.getDay()]+' '+d.getDate()+' '+MN[d.getMonth()]+(same(day0(l),day0(d))?'':' – '+DN[l.getDay()]+' '+l.getDate()+' '+MN[l.getMonth()])+' · all day';}
  const m=mins(d,e),dur=m>=60?(Math.floor(m/60)+' h'+(m%60?' '+(m%60)+' min':'')):m+' min';
  return DN[d.getDay()]+' '+d.getDate()+' '+MN[d.getMonth()]+' '+d.getFullYear()+' · '+hm(d)+' – '+(same(day0(d),day0(e))?'':DN[e.getDay()]+' '+e.getDate()+' '+MN[e.getMonth()]+' ')+hm(e)+' ('+dur+')';}
function row(k,v){return v?'<div class="row"><div class="k">'+k+'</div><div class="v">'+v+'</div></div>':''}
function fill(x){const c=x.kind==='prop'?null:(CAL[x.cal]||{label:x.cal,color:'gray'});
  const dot=x.kind==='prop'?'var(--'+(x.status==='verstuurd'?'sent':x.status==='vervallen'?'gray-fg':'prop')+')':'var(--'+c.color+'-bd)';
  let calTxt=x.kind==='prop'?('proposal'+(x.realCal&&CAL[x.realCal]?' → '+esc(CAL[x.realCal].label):'')):esc(c.label)+(x.cal==='sync'?' <span class="r">(copy from another calendar, without details)</span>':'');
  let h='<button class="x" aria-label="close">×</button>';
  if(x.kind==='prop')h+='<span class="chip" style="background:'+dot+'">#'+x.nr+' · '+(x.status==='open'?'open proposal':SL[x.status])+'</span>';
  h+='<h3><span class="dot" style="background:'+dot+'"></span><span>'+esc(x.title)+'</span></h3>';
  h+=row('When',esc(when(x)))+row('Calendar',calTxt+(x.showAs&&SA[x.showAs]?' · '+SA[x.showAs]:''))+row('Location',esc(x.location||''));
  if(x.organizer&&x.organizer.address)h+=row('Organizer',esc(x.organizer.name||'')+' <span class="r">'+esc(x.organizer.address)+'</span>');
  if(x.attendees&&x.attendees.length)h+=row('Attendees ('+x.attendees.length+')','<ul>'+x.attendees.map(person).join('')+'</ul>');
  else if(x.kind!=='prop'&&x.cal!=='sync')h+=row('Attendees','<span class="r">none (solo block)</span>');
  if(moved(x))h+=row('Moved','from '+esc(when({s:x.os,e:x.oe}))+'<br><button class="reset">back to proposal</button>');
  if(clash(x))h+=row('Warning','<span style="color:var(--red-fg)">overlaps an existing event</span>');
  if(x.kind==='prop'){h+=row('Details','<span class="txt">'+esc(x.toelichting||'')+'</span>')+row('Note',x.notitie?'<span class="txt" style="color:var(--prop)">'+esc(x.notitie)+'</span>':'');}
  else h+=row('Description',x.body?'<span class="txt">'+esc(x.body)+'</span>':'');
  if(x.tag)h+=row('Label',esc(x.tag));
  pop.innerHTML=h;pop.querySelector('.x').onclick=close;
  const rb=pop.querySelector('.reset');if(rb)rb.onclick=ev=>{ev.stopPropagation();x.s=x.os;x.e=x.oe;close();save(x);rerender();};}
function place(el){pop.style.left=pop.style.top='';if(innerWidth<=640)return;const r=el.getBoundingClientRect(),pw=pop.offsetWidth,ph=pop.offsetHeight;
  let l=r.right+8;if(l+pw>innerWidth-12)l=r.left-pw-8;if(l<12)l=Math.min(innerWidth-pw-12,Math.max(12,r.left));
  let t=r.top;if(t+ph>innerHeight-12)t=innerHeight-ph-12;if(t<12)t=12;pop.style.left=l+'px';pop.style.top=t+'px';}
function open(id,el){const x=BY[id];if(!x)return;if(selEl)selEl.classList.remove('sel');selEl=el;el&&el.classList.add('sel');fill(x);pop.classList.add('open');if(el)place(el);}
function close(){pop.classList.remove('open');if(selEl)selEl.classList.remove('sel');selEl=null;}
document.addEventListener('click',ev=>{if(justDragged){justDragged=false;ev.stopPropagation();return;}const t=ev.target.closest('[data-id]');
  if(t&&wrap.contains(t)){ev.stopPropagation();if(selEl===t&&pop.classList.contains('open'))return close();return open(t.dataset.id,t);}
  const r=ev.target.closest('tr.prow');if(r){const id=r.dataset.pid,x=BY[id];show(Math.floor((day0(x.s)-W0)/(7*864e5)));const el=wrap.querySelector('[data-id="'+id+'"]');
    if(el){el.scrollIntoView({block:'center',inline:'center'});}open(id,el);return;}
  if(!pop.contains(ev.target))close();});
document.addEventListener('keydown',ev=>{if(ev.key==='Escape'&&pop.classList.contains('open'))close();
  else if((ev.key==='Enter'||ev.key===' ')&&ev.target.dataset&&ev.target.dataset.id&&wrap.contains(ev.target)){ev.preventDefault();open(ev.target.dataset.id,ev.target);}});
addEventListener('resize',()=>{if(selEl&&pop.classList.contains('open'))place(selEl)});
// --- slepen: voorstellen verplaatsen (ook naar een andere dag in de week) en begin/eind aanpassen
const SNAP=15,MINDUR=15,tip=document.createElement('div');tip.id='dtip';document.body.appendChild(tip);
let drag=null,justDragged=false,laterRender=false;const touched={};
const snap=m=>Math.round(m/SNAP)*SNAP;
function dayAt(sec,cx){const ds=[...sec.querySelectorAll('.day')];let best=null;ds.forEach(d=>{const r=d.getBoundingClientRect();if(cx>=r.left&&cx<r.right)best=d;});
  if(!best){const r0=ds[0].getBoundingClientRect();best=cx<r0.left?ds[0]:ds[ds.length-1];}return best;}
const minAt=(dayEl,cy)=>H0*60+(cy-dayEl.getBoundingClientRect().top)/PX*60;
wrap.addEventListener('pointerdown',ev=>{if(ev.button>0)return;const el=ev.target.closest('.k-prop.drag');if(!el||!wrap.contains(el))return;
  const x=BY[el.dataset.id];if(!x)return;const dayEl=el.closest('.day');
  drag={x,el,dayEl,mode:ev.target.dataset.h||'move',sx:ev.clientX,sy:ev.clientY,on:false,
    s0:x.s.getHours()*60+x.s.getMinutes(),dur:mins(x.s,x.e),grab:minAt(dayEl,ev.clientY)-(x.s.getHours()*60+x.s.getMinutes()),pid:ev.pointerId};
  ev.preventDefault();});
addEventListener('pointermove',ev=>{if(!drag||ev.pointerId!==drag.pid)return;const d=drag;
  if(!d.on){if(Math.abs(ev.clientX-d.sx)+Math.abs(ev.clientY-d.sy)<4)return;d.on=true;close();d.el.classList.add('dragging');
    touched[d.x.nr]=1;try{d.el.setPointerCapture(d.pid)}catch(e){}d.el.style.left='1px';d.el.style.width='calc(100% - 3px)';}
  const sec=d.el.closest('.week');let dayEl=d.dayEl,s=d.s0,e=d.s0+d.dur;
  const lo=H0*60,hi=H1*60;
  if(d.mode==='move'){dayEl=dayAt(sec,ev.clientX);s=snap(minAt(dayEl,ev.clientY)-d.grab);s=Math.max(lo,Math.min(hi-d.dur,s));e=s+d.dur;
    if(dayEl!==d.el.parentNode)dayEl.appendChild(d.el);}
  else if(d.mode==='top'){s=Math.max(lo,Math.min(e-MINDUR,snap(minAt(dayEl,ev.clientY))));}
  else{e=Math.min(hi,Math.max(s+MINDUR,snap(minAt(dayEl,ev.clientY))));}
  d.cur={dayEl,s,e};d.el.style.top=((s-lo)/60*PX)+'px';d.el.style.height=((e-s)/60*PX-2)+'px';
  const dd=new Date(dayEl.dataset.day),tm=pad(s/60|0)+':'+pad(s%60)+'–'+pad(e/60|0)+':'+pad(e%60);
  tip.textContent=DN[dd.getDay()]+' '+dd.getDate()+' '+MN[dd.getMonth()]+' · '+tm+' ('+(e-s)+' min)';tip.style.display='block';
  tip.style.left=Math.min(innerWidth-tip.offsetWidth-8,ev.clientX+14)+'px';tip.style.top=Math.max(8,ev.clientY-30)+'px';
  const tmEl=d.el.querySelector('.tm');if(tmEl)tmEl.textContent=tm;
  const ns=new Date(dd.getFullYear(),dd.getMonth(),dd.getDate(),0,s),ne=new Date(dd.getFullYear(),dd.getMonth(),dd.getDate(),0,e);
  d.el.classList.toggle('clash',all.some(y=>y.kind!=='prop'&&!y.top&&!BGM(y)&&y.s<ne&&y.e>ns));});
function endDrag(ev){if(!drag||ev.pointerId!==drag.pid)return;const d=drag;drag=null;tip.style.display='none';
  if(!d.on||!d.cur){if(laterRender){laterRender=false;rerender();}return;}laterRender=false;justDragged=true;setTimeout(()=>{justDragged=false},0);
  const dd=new Date(d.cur.dayEl.dataset.day);const x=d.x;
  x.s=new Date(dd.getFullYear(),dd.getMonth(),dd.getDate(),0,d.cur.s);x.e=new Date(dd.getFullYear(),dd.getMonth(),dd.getDate(),0,d.cur.e);
  save(x);rerender();}
addEventListener('pointerup',endDrag);addEventListener('pointercancel',endDrag);
// --- autosave via de bridge (component agenda, key voorstel-<nr>)
// Route en pagina-identiteit: het blok LA-BRIDGE-KEUZE uit het annotator-snippet, bij het
// bouwen letterlijk ingeplakt (één bron; werkt ook zonder snippet op de pagina).
/*LA-BRIDGE-KEUZE*/
const BRIDGE=laBridgeKeuze().origin,pill=document.getElementById('agsave'),pending={},busy={};
// slug: die van het paginabestand (bij het bouwen bepaald), zodat de state ook buiten /p/
// (dev-server, preview-pane) landt waar de sync hem zoekt
const basis=()=>({page:location.href,pageFile:paginaBestand(),slug:S.slug||slug(),title:document.title});
function setPill(t,c){if(!pill)return;pill.hidden=false;pill.textContent=t;pill.className='agpill '+(c||'');}
const post=(path,body)=>fetch(BRIDGE+path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}).then(r=>r.json());
function save(x){touched[x.nr]=1;pending[x.nr]=Object.assign(basis(),{component:'agenda',key:'voorstel-'+x.nr,
  value:{start:L16(x.s),end:L16(x.e),base:{start:L16(x.os),end:L16(x.oe)},title:x.title}});flush();}
// per key één verzoek tegelijk; wat intussen binnenkomt gaat daarna (de laatste stand wint,
// ook als de bridge traag is)
function flush(){Object.keys(pending).forEach(k=>{if(busy[k])return;const b=pending[k];busy[k]=1;
  post('/state-save',b).then(r=>{if(!r||!r.ok)throw 0;if(pending[k]===b)delete pending[k];
    setPill('saved '+hm(new Date()),'ok');}).catch(()=>setPill('bridge off · not saved','off'))
  .then(()=>{busy[k]=0;if(pending[k]&&pending[k]!==b)flush();});});}
setInterval(flush,3000);
post('/state',basis()).then(r=>{const comp=(r&&r.state&&r.state.components&&r.state.components.agenda)||{};let n=0;
  all.forEach(x=>{if(x.kind!=='prop'||x.status!=='open'||x.top||touched[x.nr])return; // al door de reviewer verzet: die wint
    const e=comp['voorstel-'+x.nr];if(!e||!e.start||!e.end)return;
    const b=e.base;if(b&&(b.start.slice(0,16)!==L16(x.os)||b.end.slice(0,16)!==L16(x.oe)))return; // overlay sindsdien gewijzigd: state is oud
    x.s=P(e.start);x.e=P(e.end);n++;});
  if(n){if(drag)laterRender=true;else rerender();} // midden in een sleep: pas na het neerzetten
  setPill('autosave on','ok');}).catch(()=>setPill('bridge off','off'));
window.AgendaPreview={items:()=>all.filter(x=>x.kind==='prop').map(x=>({nr:x.nr,start:L16(x.s),end:L16(x.e),moved:!!moved(x),clash:clash(x)}))};
})();
"""


def page(m):
    import html as H
    e = H.escape
    def dt(s):
        d = P(s); return f"{['Mon','Tue','Wed','Thu','Fri','Sat','Sun'][d.weekday()]} {d.day:02d}-{d.month:02d}"
    rows = "".join(
        f'<tr class="prow st-{p["status"]}" data-pid="{p["id"]}"><td><span class="pn">#{p["nr"]} {e({"open":"open","verstuurd":"sent","vervallen":"dropped"}[p["status"]])}</span></td>'
        f'<td>{dt(p["start"])}<br>{p["start"][11:16]}–{p["end"][11:16]}</td>'
        f'<td><b>{e(p["title"])}</b><div class="sub">{e(p.get("toelichting",""))}</div>'
        + (f'<div class="note">{e(p["notitie"])}</div>' if p.get("notitie") else "")
        + f'</td><td class="to">{e(", ".join(a.get("address") or a.get("name","") for a in p["attendees"]))}</td></tr>'
        for p in m["proposals"])
    st = {p["status"] for p in m["proposals"]}
    leg = ""
    if "open" in st: leg += '<span><i style="background:var(--prop)"></i>open proposal</span>'
    if "verstuurd" in st: leg += '<span><i style="background:var(--sent)"></i>sent</span>'
    if "vervallen" in st: leg += '<span><i style="background:var(--gray-fg)"></i>dropped</span>'
    if any(x.get("tag") for x in m["events"]): leg += '<span><i style="background:var(--tag)"></i>' + e(", ".join(sorted({x["tag"] for x in m["events"] if x.get("tag")}))) + '</span>'
    leg += "".join(f'<span><i style="background:var(--{c.get("color","gray")}-bd)"></i>{e(c["label"])}</span>' for c in m["calendars"])
    leg += f'<span class="sub">blocks ≥ {m["bgMinHours"]} h are shown as a narrow lane on the left · click an event for details</span>'
    data = json.dumps(m, ensure_ascii=False).replace("</", "<\\/")
    js = JS.replace("/*LA-BRIDGE-KEUZE*/", bridge_keuze())
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{e(m["title"])}</title><style>{CSS}</style></head><body><main>
<div class="top"><h2>{e(m["heading"])}</h2>{f'<span class="sub">{e(m["subheading"])}</span>' if m["subheading"] else ""}</div>
<div class="legend">{leg}</div>
{f'<div class="tablewrap"><table>{rows}</table></div>' if rows else ""}
<div class="nav"><h1 id="wkm"></h1><button id="prev" aria-label="previous week">‹</button><button id="tdy">Today</button><button id="next" aria-label="next week">›</button><span class="range" id="wkr"></span><span class="agpill" id="agsave" hidden></span></div>
<div class="scroll"><div class="wkwrap" id="weeks"></div></div>
</main>
<div id="pop" role="dialog" aria-modal="false"></div>
<script type="application/json" id="agenda-data">{data}</script>
<script>{js}</script>
</body></html>'''


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("spec")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--no-snippet", action="store_true", help="zonder annotator-snippet (alleen voor tests)")
    a = ap.parse_args()
    m = build(json.load(open(a.spec)))
    m["slug"] = slugify(os.path.splitext(os.path.basename(a.out))[0])
    h = page(m)
    if not a.no_snippet:
        snip = open(SNIPPET).read()
        i = h.rindex("</body>")  # rindex: de laatste </body>, zie SKILL.md
        h = h[:i] + snip + "\n" + h[i:]
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    open(a.out, "w").write(h)
    n = {s: sum(p["status"] == s for p in m["proposals"]) for s in ("open", "verstuurd", "vervallen")}
    print(f"{a.out}: {len(m['events'])} events, voorstellen {n}")


if __name__ == "__main__":
    main()
