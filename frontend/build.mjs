import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const here=path.dirname(fileURLToPath(import.meta.url)),root=path.dirname(here),dist=path.join(here,'dist');
if(path.dirname(path.resolve(dist))!==path.resolve(here))throw new Error('Invalid frontend output directory');
fs.rmSync(dist,{recursive:true,force:true});
fs.mkdirSync(path.join(dist,'examples'),{recursive:true});
for(const file of ['index.html','style.css','app.js'])fs.copyFileSync(path.join(here,file),path.join(dist,file));
let apiUrl=(process.env.RAG_API_URL||'').trim().replace(/\/$/,'');
if(apiUrl){const u=new URL(apiUrl);if(u.protocol!=='https:' && !(u.protocol==='http:'&&['127.0.0.1','localhost'].includes(u.hostname)))throw new Error('RAG_API_URL must use HTTPS (except localhost)');if(u.username||u.password||u.search||u.hash)throw new Error('API URL must not contain credentials/query/hash');}
const questions=JSON.parse(fs.readFileSync(path.join(root,'output/questions.json'),'utf8')).map(({id,question,companies,years,type})=>({id,question,companies,years,type}));
const companies=[...new Set(JSON.parse(fs.readFileSync(path.join(root,'data/manifest.json'),'utf8')).map(r=>r.company))];
fs.writeFileSync(path.join(dist,'config.json'),JSON.stringify({apiUrl,companies,questions,defaultEvaluation:'v4'}));
for(const version of ['v4','v3']){
  fs.mkdirSync(path.join(dist,'examples',version),{recursive:true});
  for(const q of questions){
    const folder=version==='v4'?'evaluation_v4':'evaluation';
    const record=JSON.parse(fs.readFileSync(path.join(root,'output',folder,q.id+'_hybrid_expanded.json'),'utf8'));
    const {question,answer,chunks,mode,error,manual_review,model,checks,retrieval_revision}=record;
    if(version==='v4'&&!manual_review)throw new Error('Current evaluation must be reviewed');
    fs.writeFileSync(path.join(dist,'examples',version,q.id+'.json'),JSON.stringify({question,answer,chunks,mode,error,manual_review,model,checks,retrieval_revision,record_kind:'evaluation',historical:version==='v3',index_version:version,notice:version==='v3'?'历史真实实验：使用修复前 v3 索引，不代表当前 v4 质量。':'v4 固定题评测记录，非实时生成；10题用于开发，不能代表总体准确率。'}));
  }
}
console.log(`Built frontend: ${questions.length} current and ${questions.length} historical examples; live backend ${apiUrl?'configured':'not configured'}`);
