const $ = id => document.getElementById(id);
const config = await (await fetch('/config.json')).json();
const api = config.apiUrl.replace(/\/$/,'');
let current = null;
let ready = false;
const savedVersions=config.availableEvaluations||[];
const hasSaved=savedVersions.length>0;
$('evaluation-controls').hidden=!hasSaved;
$('evaluation-version').replaceChildren(...savedVersions.map(v=>Object.assign(document.createElement('option'),{value:v,textContent:v==='v4'?'v4 最终评测 · 10题':'v3 历史实验 · 含失败案例'})));
if(!hasSaved)$('experiment-hint').textContent='点选问题填入输入框。评测结果及作业附件保存在项目作者本地，不随代码仓库发布。';
function notice(message){$('notice').hidden=!message;$('notice').textContent=message;}
function node(tag,text,className){const n=document.createElement(tag);n.textContent=text;if(className)n.className=className;return n;}
function inline(parent,text){
  for(const part of text.split(/(\*\*[^*]+\*\*|\[\d+\])/g)){
    if(/^\*\*/.test(part))parent.append(node('strong',part.slice(2,-2)));
    else if(/^\[\d+\]$/.test(part)){const a=node('a',part);a.href='#source-'+Number(part.slice(1,-1));a.onclick=()=>{const d=document.getElementById(a.hash.slice(1));if(d)d.open=true;};parent.append(a);}
    else parent.append(document.createTextNode(part));
  }
}
function renderAnswer(text){
  const target=$('answer');target.replaceChildren();const lines=text.split('\n');
  for(let i=0;i<lines.length;i++){
    if(lines[i].includes('|') && i+1<lines.length && /^\s*\|?\s*:?-{3}/.test(lines[i+1])){
      const table=node('table',''),wrap=node('div','','answer-table');let heading=true;
      for(;i<lines.length && lines[i].includes('|');i++){
        if(/^\s*\|?\s*:?-{3}/.test(lines[i]))continue;
        const tr=node('tr','');for(const value of lines[i].trim().replace(/^\||\|$/g,'').split('|')){const cell=node(heading?'th':'td','');inline(cell,value.trim());tr.append(cell);}table.append(tr);heading=false;
      }
      i--;wrap.append(table);target.append(wrap);
    }else{const p=node('p','');inline(p,lines[i].replace(/^#{1,6}\s+/,''));target.append(p);}
  }
}
function show(result){
  current=result;$('result').hidden=false;
  $('record-label').textContent=result.historical?'历史实验 · v3 索引 · 修复前的真实结果，不能作为当前 v4 质量结论':result.record_kind==='evaluation'?`已保存评测 · v4 索引 · ${result.model||''}`:'实时检索 · v4 索引';
  $('review-status').hidden=!result.manual_review;
  $('review-status').textContent=result.manual_review?`助手复核：${result.manual_review.correct?'答对':'未通过'}。${result.manual_review.reason}`:'';
  $('result-question').textContent=result.question;
  renderAnswer(result.answer || '已检索到以下证据。选择 GPT 回答方式后，可基于证据生成带引用的答案。');
  notice(result.error || result.notice || '');
  const chunks=result.chunks||[],covered=[...new Set(chunks.map(c=>c.company))];
  const firstCitation=Number((result.answer||'').match(/\[(\d+)\]/)?.[1])||1;
  $('coverage').textContent=`证据覆盖 ${covered.length} 家：${covered.join('、') || '暂无'}。请核对是否包含问题所需的全部指标。`;
  $('chunk-count').textContent=`${chunks.length} 个块`;$('evidence').replaceChildren();
  chunks.forEach((c,i)=>{
    const d=node('details','');d.id='source-'+(i+1);if(i+1===firstCitation)d.open=true;
    d.append(node('summary',`[${i+1}] ${c.company} · ${c.year} · PDF 第 ${c.page} 页 · ${c.chapter}`));
    try{const u=new URL(c.url);if(u.protocol==='https:' && ['static.cninfo.com.cn','www.cninfo.com.cn'].includes(u.hostname)){
      const a=node('a','打开官方 PDF ↗');a.href=u.href.split('#')[0]+`#page=${Number(c.page)}`;a.target='_blank';a.rel='noopener noreferrer';d.append(a);
    }}catch{}
    d.append(node('pre',c.text),node('p',`块 ID：${c.id}`,'chunk-id'));$('evidence').append(d);
  });
}
for(const name of config.companies){const o=node('option',name);o.value=name;$('company').append(o);}
for(const q of config.questions){
  const row=node('div','','question-row'),pick=node('button',q.question,'pick'),history=node('button','评测记录','quiet');
  pick.type=history.type='button';pick.onclick=()=>{$('question').value=q.question;$('company').value=q.companies.length===1?q.companies[0]:'';$('year').value=q.years.length===1?String(q.years[0]):'';$('panoramic').checked=q.type==='panoramic';$('question').focus();};
  history.onclick=async()=>{try{show(await (await fetch(`/examples/${$('evaluation-version').value}/${q.id}.json`)).json());$('result').scrollIntoView({behavior:'smooth',block:'start'});}catch{notice('评测记录载入失败，请刷新重试。');}};
  row.append(node('span',q.id,'qid'),pick);if(hasSaved)row.append(history);$('questions').append(row);
}
$('auth').onchange=()=>{$('key-fields').hidden=$('auth').value!=='own_key';$('local-note').hidden=$('auth').value!=='local';$('submit').firstChild.textContent=$('auth').value==='retrieval'?'检索证据 ':'检索并回答 ';};
$('clear-key').onclick=()=>{$('api-key').value='';};
$('download').onclick=()=>{if(!current)return;const u=URL.createObjectURL(new Blob([JSON.stringify(current,null,2)],{type:'application/json'}));const a=node('a','');a.href=u;a.download='financial_report_record.json';a.click();setTimeout(()=>URL.revokeObjectURL(u),1000);};
$('ask').onsubmit=async e=>{
  e.preventDefault();notice('');if(!ready){notice(hasSaved?'实时后端尚未连接。你仍可以查看下方 10 道题的评测记录。':'尚未配置或连接实时后端，请先按照部署说明连接后端。');return;}
  const auth=$('auth').value;if(auth==='own_key'&&!$('api-key').value.trim()){notice('请填写你自己的 API key，或选择只检索证据。');return;}
  const button=$('submit');button.disabled=true;button.textContent=auth==='retrieval'?'正在检索…':'检索与生成中…';
  const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),300000);
  try{
    const payload={question:$('question').value.trim(),companies:$('company').value?[$('company').value]:[],years:$('year').value?[Number($('year').value)]:[2024,2025],mode:$('mode').value,enhanced:$('enhanced').checked,panoramic:$('panoramic').checked,generate:auth!=='retrieval',auth:auth==='local'?'local':'own_key',model:$('model').value.trim()};
    if(auth==='own_key')payload.api_key=$('api-key').value.trim();
    const response=await fetch(api+'/api/query',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload),signal:controller.signal});
    const data=await response.json();if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:'请求失败，请检查参数。');show(data);
  }catch(error){notice(error.name==='AbortError'?'请求等待超时，请稍后重试。':(error.message==='Failed to fetch'?'无法连接后端，请检查后端服务及跨域配置。':error.message));}
  finally{clearTimeout(timer);button.disabled=false;$('auth').onchange();}
};
async function connect(){
  if(!api){$('status').textContent=hasSaved?'评测记录演示':'未配置实时后端';notice(hasSaved?'尚未配置实时后端：可查看本地已保存评测。':'当前仅展示提问入口；配置后端公开地址 RAG_API_URL 并重新部署后，可启用实时检索。');return;}
  try{
    const r=await fetch(api+'/health',{signal:AbortSignal.timeout(15000)}),h=await r.json();ready=r.ok&&h.ready;
    $('status').textContent=ready?'实时后端已连接':'索引准备中';$('status').classList.toggle('online',ready);
    if(h.local_auth && ['localhost','127.0.0.1'].includes(location.hostname)){$('auth').append(Object.assign(node('option','GPT · 本机已有授权'),{value:'local'}));}
    if(!ready)notice('后端已启动，正在准备索引。');
  }catch{$('status').textContent='后端暂未连接';notice(hasSaved?'实时后端暂时不可用，可以先查看评测记录。':'实时后端暂时不可用，请检查后端服务。');}
}
await connect();
