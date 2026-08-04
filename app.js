
const DEFAULT_WEIGHTS={barrier:.31,recent:.16,moisture:.23,weight_fit:.12,body:.05,odds_value:.03,consistency:.10};
const LABELS={barrier:"障害力",recent:"近走",moisture:"馬場水分適性",weight_fit:"斤量適性",body:"馬体・増減",odds_value:"妙味",consistency:"障害安定"};
const KEY_RACES="banei_ai_races_v1",KEY_SETTINGS="banei_ai_settings_v1";
let currentRace=null,currentPred=null;

function loadRaces(){try{return JSON.parse(localStorage.getItem(KEY_RACES)||"[]")}catch{return[]}}
function saveRaces(x){localStorage.setItem(KEY_RACES,JSON.stringify(x))}
function loadSettings(){try{const s=JSON.parse(localStorage.getItem(KEY_SETTINGS)||"{}");return {weights:{...DEFAULT_WEIGHTS,...(s.weights||{})},learning_rate:s.learning_rate??.02}}catch{return{weights:{...DEFAULT_WEIGHTS},learning_rate:.02}}}
function saveSettings(s){localStorage.setItem(KEY_SETTINGS,JSON.stringify(s))}
function clamp(x,a,b){return Math.max(a,Math.min(b,x))}
function secScore(sec){return !sec||sec<=0?50:clamp(160-sec*(160/240),0,100)}
function barrierScore(sec){return !sec||sec<=0?50:clamp(120-sec*1.5,0,100)}
function recentScore(hist){let vals=[];hist.slice(0,5).forEach((s,i)=>{if(!s.time_sec&&!s.finish)return;let sc=s.time_sec?secScore(s.time_sec):50;if(s.finish)sc=.68*sc+.32*Math.max(0,100-(s.finish-1)*10);let w=1/(1+i*.2);vals.push([w,sc])});return vals.length?vals.reduce((a,[w,s])=>a+w*s,0)/vals.reduce((a,[w])=>a+w,0):50}
function moistureScore(today,hist){let vals=[];hist.forEach(s=>{if(s.moisture==null||!s.time_sec)return;let diff=Math.abs(today-s.moisture),sim=Math.max(0,1-diff/1.8);if(diff<=.3)sim*=1.18;vals.push([sim,secScore(s.time_sec)])});return vals.length?vals.reduce((a,[x,y])=>a+x*y,0)/(vals.reduce((a,[x])=>a+x,0)||1):50}
function barrierStats(hist){const v=hist.filter(s=>s.barrier_sec).map(s=>+s.barrier_sec);if(!v.length)return[50,50];const avg=v.reduce((a,b)=>a+b,0)/v.length;let bs=barrierScore(avg);if(v.length===1)return[bs,60];const sd=Math.sqrt(v.reduce((a,x)=>a+(x-avg)**2,0)/v.length);let cs=clamp(100-sd*4.5,0,100);bs=Math.min(100,bs+v.filter(x=>x<=35).length*2.5);return[bs,cs]}
function weightScore(w,hist){const vals=[];hist.forEach(s=>{if(!s.carry_weight||!s.time_sec)return;const sim=Math.max(0,1-Math.abs(w-s.carry_weight)/70);vals.push(sim*secScore(s.time_sec))});return vals.length?vals.reduce((a,b)=>a+b,0)/vals.length:50}
function bodyScore(b,c){let base=clamp(45+((b||950)-850)/14,35,75);c=c||0;let adj=(-10<=c&&c<=20)?8:(-25<=c&&c<=35?2:-8);return clamp(base+adj,0,100)}
function oddsValue(o){return !o||o<=0?50:clamp(35+Math.log2(o+1)*9,20,90)}
function scoreHorse(h,m,wts){const hist=h.history||[],[bs,cs]=barrierStats(hist);const f={barrier:bs,recent:recentScore(hist),moisture:moistureScore(m,hist),weight_fit:weightScore(h.carry_weight||0,hist),body:bodyScore(h.body_weight,h.body_change),odds_value:oddsValue(h.odds),consistency:cs};const total=Object.keys(f).reduce((a,k)=>a+f[k]*(wts[k]||0),0);const longshot=.55*total+.18*f.barrier+.17*f.consistency+.10*f.odds_value;return{...h,score:total,longshot,features:f}}
function predict(r,wts){let p=r.horses.map(h=>scoreHorse(h,+r.moisture,wts)).sort((a,b)=>b.score-a.score);const marks=["◎","○","▲","☆","△","△","注","注","-","-","-","-"];p.forEach((h,i)=>h.mark=marks[i]||"-");return p}
function bets(p){const win=p.slice(0,3).map(x=>x.number),place=p.slice(0,5).map(x=>x.number),long=[...p].sort((a,b)=>b.longshot-a.longshot).slice(0,4).map(x=>x.number);return [`本線3連単: ${win[0]} → ${win[1]}・${win[2]} → ${place.join("・")}`,`押さえ3連単: ${win[1]}・${win[2]} → ${win[0]} → ${place.join("・")}`,`穴3連系: 軸 ${win[0]} / 穴候補 ${long.join("・")}`,`3連複: ${place.slice(0,4).join("・")} BOX`]}
function timeToSec(s){const m=(s||"").match(/(\d+):(\d+(?:\.\d+)?)/);return m?+m[1]*60+ +m[2]:null}
function lines(t){return (t||"").replace(/\r/g,"").split("\n").map(x=>x.trim()).filter(Boolean)}

function parseEntry(text){
 const a=lines(text),horses=[];let i=0;
 while(i<a.length){
  if(/^\d{1,2}$/.test(a[i])&&i+2<a.length&&a[i+2].includes("データベース")){
   const no=+a[i],name=a[i+1];let j=i+3;while(j<a.length&&!( /^\d{1,2}$/.test(a[j])&&j+2<a.length&&a[j+2].includes("データベース")))j++;
   const b=a.slice(i,j),joined=b.join("\n");let carry=0,odds=0,popularity=null,body=0,change=0;
   let m=joined.match(/(?:牡|牝|セ)\d+\s+.*?\s+[^\s]+\s+(\d{3}(?:\.\d+)?)/s);if(m)carry=+m[1];
   for(let k=0;k<b.length;k++){
    if(/^\d+(?:\.\d+)?$/.test(b[k])&&k+1<b.length&&/\d+人気/.test(b[k+1])){
      odds=+b[k];const pm=b[k+1].match(/(\d+)人気/);if(pm)popularity=+pm[1];
      const bm=b[k+1].match(/人気\s+(\d{3,4})/);if(bm)body=+bm[1];
      for(let z=k+2;z<Math.min(k+7,b.length);z++){if(!body&&/^\d{3,4}$/.test(b[z]))body=+b[z];const cm=b[z].match(/\(([+-]?\d+)\)/);if(cm){change=+cm[1];break}}
      break;
    }
   }
   horses.push({number:no,name,carry_weight:carry,body_weight:body,body_change:change,odds,popularity,history:[]});i=j;
  }else i++;
 }
 return horses;
}
function parseHistory(text){
 const raw=(text||"").replace(/\r/g,""),re=/^(\d{1,2})\s*\n([^\n]+)\s*\n\2のデータベース\s*$/gm,heads=[];let m;
 while((m=re.exec(raw)))heads.push({no:+m[1],name:m[2],start:re.lastIndex,idx:m.index});
 const out={};
 heads.forEach((h,hi)=>{
   const block=raw.slice(h.start,hi+1<heads.length?heads[hi+1].idx:raw.length),dates=[...block.matchAll(/^(\d{2}\/\d{2})\s+帯広\(ば\s+\d+R\s*$/gm)],races=[];
   dates.slice(0,5).forEach((dm,ri)=>{
     const chunk=block.slice(dm.index,ri+1<dates.length?dates[ri+1].index:block.length);
     const fm=chunk.match(/^\s*(\d{1,2})\s*\n\s*(\d{1,2})頭\s*$/m),mm=chunk.match(/(\d+(?:\.\d+)?)%/),wm=chunk.match(/^\s*(\d{3}(?:\.\d+)?)\s*\n\s*\d{3,4}kg/m),bm=chunk.match(/^後\s*\n\s*(\d+(?:\.\d+)?)\s*$/m);
     races.push({date:dm[1],finish:fm?+fm[1]:null,moisture:mm?+mm[1]:null,time_sec:timeToSec(chunk),carry_weight:wm?+wm[1]:null,barrier_sec:bm?+bm[1]:null});
   }); out[h.no]=races;
 });
 return out;
}
function parseAll(e,h){const horses=parseEntry(e),hist=parseHistory(h);horses.forEach(x=>x.history=hist[x.number]||[]);return horses}

function renderPrediction(p){
 let html=`<table><thead><tr><th>印</th><th>馬番</th><th>馬名</th><th>総合</th><th>障害</th><th>近走</th><th>水分</th><th>斤量</th><th>安定</th><th>穴</th></tr></thead><tbody>`;
 p.forEach(h=>html+=`<tr><td class="mark">${h.mark}</td><td>${h.number}</td><td>${h.name}</td><td>${h.score.toFixed(1)}</td><td>${h.features.barrier.toFixed(1)}</td><td>${h.features.recent.toFixed(1)}</td><td>${h.features.moisture.toFixed(1)}</td><td>${h.features.weight_fit.toFixed(1)}</td><td>${h.features.consistency.toFixed(1)}</td><td>${h.longshot.toFixed(1)}</td></tr>`);
 html+=`</tbody></table><div class="card"><h3>最終印</h3>${p.slice(0,6).map(h=>`<span class="pill">${h.mark}${h.number} ${h.name}</span>`).join("")}</div><div class="card"><h3>買い目候補</h3>${bets(p).map(x=>`<div>${x}</div>`).join("")}</div>`;
 document.querySelector("#prediction").innerHTML=html;
}
function review(r,p){const res=r.result||[],d=Object.fromEntries(p.map(h=>[h.number,h]));if(res.length<3)return"結果未入力";let out=[];res.slice(0,3).forEach((n,i)=>{const h=d[n];if(h)out.push(`${i+1}着 ${n} ${h.name} / 予想${h.mark} / 総合${h.score.toFixed(1)} / 穴${h.longshot.toFixed(1)}`)});const top3=new Set(p.slice(0,3).map(h=>h.number)),top6=new Set(p.slice(0,6).map(h=>h.number));out.push(`上位3頭捕捉 ${res.filter(x=>top3.has(x)).length}/3 / 印6頭捕捉 ${res.filter(x=>top6.has(x)).length}/3`);res.forEach(n=>{if(!top3.has(n)&&d[n]){const h=d[n],s=Object.entries(h.features).sort((a,b)=>b[1]-a[1]).slice(0,3);out.push(`見落とし ${n} ${h.name} / 強み ${s.map(([k,v])=>`${LABELS[k]}:${v.toFixed(0)}`).join("・")}`)}});return out.join("\n")}
function learn(r,s){const res=r.result||[];if(res.length<3)return s;const p=predict(r,s.weights),d=Object.fromEntries(p.map(h=>[h.number,h])),win=res.map(n=>d[n]).filter(Boolean),lose=p.filter(h=>!res.includes(h.number));if(!win.length||!lose.length)return s;const pw={[res[0]]:1,[res[1]]:.75,[res[2]]:.55},sumw=win.reduce((a,h)=>a+pw[h.number],0),lr=s.learning_rate||.02;Object.keys(s.weights).forEach(k=>{const wa=win.reduce((a,h)=>a+h.features[k]*pw[h.number],0)/sumw,la=lose.reduce((a,h)=>a+h.features[k],0)/lose.length;s.weights[k]=Math.max(.01,s.weights[k]+lr*(wa-la)/100)});const z=Object.values(s.weights).reduce((a,b)=>a+b,0);Object.keys(s.weights).forEach(k=>s.weights[k]/=z);return s}

function renderSaved(){
 const box=document.querySelector("#savedRaces"),rs=loadRaces(),s=loadSettings();if(!rs.length){box.innerHTML='<div class="notice">保存レースはまだありません</div>';return}
 box.innerHTML=rs.slice().reverse().map((r,ri)=>{const idx=rs.length-1-ri,p=predict(r,s.weights),res=(r.result||[]).join("-");return `<div class="card"><h3>${r.date||""} ${r.name} <span class="muted">水分${r.moisture}%</span></h3><div>${p.slice(0,6).map(h=>`<span class="pill">${h.mark}${h.number} ${h.name}</span>`).join("")}</div><label>結果<input id="res_${idx}" value="${res}" placeholder="7-2-9"></label><div class="actions"><button onclick="saveResult(${idx})">結果保存＋自動学習</button><button class="danger" onclick="deleteRace(${idx})">削除</button></div>${r.review?`<pre>${r.review}</pre>`:""}</div>`}).join("");
}
window.saveResult=function(idx){let rs=loadRaces(),s=loadSettings(),r=rs[idx],txt=document.querySelector(`#res_${idx}`).value;const res=txt.replace(/→/g,"-").split("-").map(x=>+x.trim()).filter(Boolean).slice(0,3);if(res.length<3){alert("1-2-3 のように3着まで入力してください");return}r.result=res;const p=predict(r,s.weights);r.review=review(r,p);s=learn(r,s);rs[idx]=r;saveRaces(rs);saveSettings(s);renderSaved();renderStats();renderSettings()}
window.deleteRace=function(idx){if(!confirm("削除しますか？"))return;const rs=loadRaces();rs.splice(idx,1);saveRaces(rs);renderSaved();renderStats()}

function renderStats(){const rs=loadRaces(),s=loadSettings(),done=rs.filter(r=>(r.result||[]).length>=3);if(!done.length){document.querySelector("#statsBox").innerHTML='<div class="notice">結果入力済みレースはまだありません</div>';return}let a=0,b=0;const rows=done.map(r=>{const p=predict(r,s.weights),res=r.result.slice(0,3),t3=new Set(p.slice(0,3).map(h=>h.number)),t6=new Set(p.slice(0,6).map(h=>h.number)),h3=res.filter(x=>t3.has(x)).length,h6=res.filter(x=>t6.has(x)).length;a+=h3;b+=h6;return `<tr><td>${r.date||""}</td><td>${r.name}</td><td>${res.join("-")}</td><td>${h3}/3</td><td>${h6}/3</td></tr>`});document.querySelector("#statsBox").innerHTML=`<div class="card"><b>${done.length}レース</b> / 上位3平均 ${(a/done.length).toFixed(2)}/3 / 印6平均 ${(b/done.length).toFixed(2)}/3</div><table><tr><th>日付</th><th>レース</th><th>結果</th><th>上位3</th><th>印6</th></tr>${rows.join("")}</table>`}
function renderSettings(){const s=loadSettings();document.querySelector("#settingsBox").innerHTML=`<h2>学習重み</h2>${Object.entries(s.weights).map(([k,v])=>`<label>${LABELS[k]} ${(v*100).toFixed(1)}%<input data-weight="${k}" type="range" min="0.01" max="0.6" step="0.01" value="${v}"></label>`).join("")}<label>学習率<input id="lr" type="number" min="0" max=".2" step=".01" value="${s.learning_rate}"></label><div class="actions"><button id="saveSettingsBtn">設定保存</button><button id="resetSettingsBtn">初期値へ戻す</button></div>`;document.querySelector("#saveSettingsBtn").onclick=()=>{const ns={weights:{},learning_rate:+document.querySelector("#lr").value};document.querySelectorAll("[data-weight]").forEach(el=>ns.weights[el.dataset.weight]=+el.value);const z=Object.values(ns.weights).reduce((a,b)=>a+b,0)||1;Object.keys(ns.weights).forEach(k=>ns.weights[k]/=z);saveSettings(ns);alert("保存しました");renderSettings()};document.querySelector("#resetSettingsBtn").onclick=()=>{saveSettings({weights:{...DEFAULT_WEIGHTS},learning_rate:.02});renderSettings()}}
document.querySelector("#parseBtn").onclick=()=>{const horses=parseAll(document.querySelector("#entryText").value,document.querySelector("#historyText").value),info=document.querySelector("#parseInfo");if(!horses.length){info.innerHTML='<p class="error">出馬表を解析できませんでした。</p>';return}const missing=horses.filter(h=>!h.history.length).map(h=>h.number);info.innerHTML=`<p class="good">${horses.length}頭を解析。${missing.length?`近走未取得: ${missing.join("・")}番`:"全馬の近走を取得"}</p>`;currentRace={id:Date.now().toString(),name:document.querySelector("#raceName").value,date:document.querySelector("#raceDate").value,moisture:+document.querySelector("#moisture").value,horses,result:[]};currentPred=predict(currentRace,loadSettings().weights);renderPrediction(currentPred);document.querySelector("#saveCurrentBtn").disabled=false}
document.querySelector("#saveCurrentBtn").onclick=()=>{if(!currentRace)return;const rs=loadRaces();currentRace.prediction=currentPred.map(h=>({number:h.number,name:h.name,mark:h.mark,score:h.score,features:h.features}));rs.push(currentRace);saveRaces(rs);alert("保存しました");renderSaved();renderStats()}
document.querySelector("#exportBtn").onclick=()=>{const blob=new Blob([JSON.stringify({races:loadRaces(),settings:loadSettings()},null,2)],{type:"application/json"}),a=document.createElement("a");a.href=URL.createObjectURL(blob);a.download=`banei-ai-backup-${new Date().toISOString().slice(0,10)}.json`;a.click();URL.revokeObjectURL(a.href)}
document.querySelector("#importFile").onchange=e=>{const f=e.target.files[0];if(!f)return;const r=new FileReader();r.onload=()=>{try{const x=JSON.parse(r.result);if(x.races)saveRaces(x.races);if(x.settings)saveSettings(x.settings);renderSaved();renderStats();renderSettings();alert("復元しました")}catch{alert("JSONを読み込めませんでした")}};r.readAsText(f)}
document.querySelector("#clearBtn").onclick=()=>{if(confirm("保存レースと学習設定を全削除しますか？")){localStorage.removeItem(KEY_RACES);localStorage.removeItem(KEY_SETTINGS);renderSaved();renderStats();renderSettings()}}
document.querySelectorAll(".tabs button").forEach(b=>b.onclick=()=>{document.querySelectorAll(".tabs button").forEach(x=>x.classList.remove("active"));document.querySelectorAll(".panel").forEach(x=>x.classList.remove("active"));b.classList.add("active");document.querySelector("#"+b.dataset.tab).classList.add("active");if(b.dataset.tab==="saved")renderSaved();if(b.dataset.tab==="stats")renderStats();if(b.dataset.tab==="settings")renderSettings()});
document.querySelector("#raceDate").value=new Date().toISOString().slice(0,10);
renderSaved();renderStats();renderSettings();
