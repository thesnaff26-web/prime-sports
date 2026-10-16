'use strict';
let feed=null,league='ALL',tab='picks',offline=false;
const $=s=>document.querySelector(s);
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const date=s=>new Date(s).toLocaleString('ru-RU',{day:'2-digit',month:'short',hour:'2-digit',minute:'2-digit',timeZone:'Europe/Moscow'})+' МСК';
const pct=n=>n==null?'—':(n*100).toFixed(1)+'%';
function render(){
 if(!feed)return;
 const picks=(feed.predictions||[]).filter(p=>league==='ALL'||p.sport===league);
 const wins=picks.filter(p=>p.result==='win').length,losses=picks.filter(p=>p.result==='loss').length;
 $('#accuracy').textContent=wins+losses?pct(wins/(wins+losses)):'—';$('#record').textContent=wins+' / '+losses;$('#pending').textContent=picks.filter(p=>p.status==='pending').length;
 const stale=!feed.updated_at||Date.now()-Date.parse(feed.updated_at)>3*3600000;
 $('#status').textContent=(offline?'Сохранённые данные · ':stale?'Данные требуют обновления · ':'Обновлено · ')+(feed.updated_at?date(feed.updated_at):'первый запуск бота ещё не выполнен');
 let html='';
 if(feed.errors?.length)html+='<div class="notice wide">Источник данных временно недоступен. Новые прогнозы по этой лиге приостановлены. Проверьте последний запуск Actions.<br>'+feed.errors.map(esc).join('<br>')+'</div>';
 if(tab==='model'){
 for(const l of ['KHL','NHL'].filter(l=>league==='ALL'||l===league)){
 const m=feed.leagues?.[l]||{};
 html+='<article class="card"><small>'+l+' / ELO V1</small><h3>'+(m.status==='ready'?'Проверка пройдена':m.status==='error'?'Ошибка источника':'Накопление данных')+'</h3><p>Завершённых игр: '+esc(m.games||0)+'<br>Исторических прогнозов: '+esc(m.samples||0)+' / 60<br>Историческая проходимость: '+pct(m.accuracy)+'<br>Нижняя граница 95%: '+pct(m.lower95)+'</p><small>Историческая оценка, отдельно от опубликованных прогнозов.</small></article>';
 }
 }else{
 let list=tab==='fixtures'?(feed.fixtures||[]):picks.filter(p=>tab==='history'?p.status==='settled':p.status==='pending');
 list=list.filter(p=>league==='ALL'||p.sport===league);
 if(!list.length)html+='<div class="notice wide"><b>'+(tab==='history'?'История пока пуста':tab==='fixtures'?'Нет загруженных матчей':'Сейчас нет отобранных прогнозов')+'</b><p>'+(tab==='picks'?'Бот пропускает матчи, пока модель не прошла проверку или данных недостаточно. Это нормальный результат отбора.':'Матчи и результаты появятся после успешного запуска бота.')+'</p></div>';
 for(const p of list){
 const expired=Date.parse(p.date)<=Date.now();
 html+='<article class="card"><small>'+esc(p.sport)+' · '+esc(date(p.date))+'</small><h3>'+esc(p.home)+'<br><span class="muted">vs</span> '+esc(p.away)+'</h3>';
 if(p.pick)html+='<div class="pick"><small>ПОБЕДА · ОТ И БУЛЛИТЫ</small><p><b>'+esc(p.pick)+'</b></p><small>Оценка модели: '+pct(p.estimate)+' · не гарантия</small></div><small>Опубликован '+esc(date(p.published_at))+'</small><p class="'+(p.result==='win'?'green':p.result==='loss'?'loss':'muted')+'">'+(p.result==='win'?'Выигран':p.result==='loss'?'Проигран':expired?'Матч начался · ожидаем итог':'Ожидается матч')+' '+esc(p.score||'')+'</p>';
 else html+='<p class="muted">В расписании · прогноз может отсутствовать</p>';
 html+='</article>';
 }
 }
 $('#content').innerHTML=html;
}
async function refresh(){
 $('#refresh').disabled=true;
 try{const r=await fetch('data/feed.json?t='+Date.now(),{cache:'no-store'});if(!r.ok)throw Error('HTTP '+r.status);const x=await r.json();if(!Array.isArray(x.predictions)||!x.leagues)throw Error('schema');feed=x;offline=false;try{localStorage.setItem('prime-feed-v1',JSON.stringify(feed))}catch{}render()}
 catch{if(!feed){try{feed=JSON.parse(localStorage.getItem('prime-feed-v1'))}catch{}}offline=true;if(feed)render();else $('#status').textContent='Не удалось загрузить данные. Проверьте интернет и запуск Actions.'}
 finally{$('#refresh').disabled=false}
}
document.querySelectorAll('[data-league]').forEach(b=>b.onclick=()=>{league=b.dataset.league;document.querySelectorAll('[data-league]').forEach(x=>x.classList.toggle('active',x===b));render()});
document.querySelectorAll('[data-tab]').forEach(b=>b.onclick=()=>{tab=b.dataset.tab;document.querySelectorAll('[data-tab]').forEach(x=>x.classList.toggle('active',x===b));render()});
$('#refresh').onclick=refresh;refresh();setInterval(refresh,300000);
if('serviceWorker'in navigator)navigator.serviceWorker.register('sw.js').catch(()=>{});
