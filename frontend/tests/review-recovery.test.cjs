const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');
function helper() {
  const exports = {};
  const saved = new Map();
  vm.runInNewContext(ts.transpileModule(fs.readFileSync(path.join(__dirname, '../src/reviewExecution.ts'), 'utf8'),
    { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 } }).outputText,
    { exports, TextDecoder, setTimeout, localStorage: { setItem: (k,v) => saved.set(k,v), getItem: k=>saved.get(k), removeItem:k=>saved.delete(k) } });
  return exports;
}
const snapshot = (sequence, status='in_progress') => ({session_id:'stable-run', status, run_metadata:{sequence}, specialist_reviews:[{specialist_id:'spec1', risks:['Retain actual finding']}]});
const json = value => ({ok:true,json:async()=>value});
const broken = () => ({ok:true,body:{getReader:()=>({read:async()=>{throw Error('Disconnected');},cancel:async()=>{}})}});

test('stream disconnect recovers via GET and retains partial results without another POST', async()=>{
  const api = helper(); const requests=[]; const events=[];
  const fetcher = async(url,options)=>{
    requests.push([url,options?.method||'GET']);
    if(options?.method==='POST') return json(snapshot(1));
    if(url.includes('/events')) return broken();
    return json(snapshot(7,'completed'));
  };
  const result=await api.startReview({session_id:'stable-run'}, e=>events.push(e), fetcher);
  assert.equal(result.status,'completed');
  assert.equal(requests.filter(r=>r[1]==='POST').length,1);
  assert(requests.every(r=>!r[0].endsWith('/run')&&!r[0].endsWith('/run-stream')));
  assert.equal(events[0].session.specialist_reviews[0].risks[0],'Retain actual finding');
});

test('reload recovery only reads the remembered ID and never executes a provider workflow',async()=>{
  const api=helper(); api.rememberRun('stable-run'); const requests=[];
  await api.observeReview(api.rememberedRun(),null,()=>{},async(url,options)=>{
    requests.push([url,options]); return json(snapshot(9,'partial_failure'));
  });
  assert.equal(requests.length,1); assert.equal(requests[0][1],undefined);
  assert.equal(api.rememberedRun(),null);
});

test('duplicate SSE cursor is ignored and partial chunks retain one copy of each result',async()=>{
  const api=helper(); const events=[];
  const event = s=>`id: ${s.run_metadata.sequence}\ndata: ${JSON.stringify({session:s,sequence:s.run_metadata.sequence})}\n\n`;
  const text=event(snapshot(2))+event(snapshot(2))+event(snapshot(3,'completed'));
  const chunks=[text.slice(0,18),text.slice(18)];
  const fetcher=async()=>({ok:true,body:{getReader:()=>({read:async()=>chunks.length?{done:false,value:new TextEncoder().encode(chunks.shift())}:{done:true},cancel:async()=>{}})}});
  const result=await api.observeReview('stable-run',snapshot(1),e=>events.push(e),fetcher);
  assert.deepEqual(events.map(e=>e.sequence),[1,2,3]);
  assert.equal(result.specialist_reviews.length,1);
});

test('premature stream EOF polls snapshots until a terminal budget stop without POST',async()=>{
  const api=helper();const requests=[];let reads=0;
  const fetcher=async(url,options)=>{
    requests.push([url,options]);
    if(url.includes('/events'))return {ok:true,body:{getReader:()=>({read:async()=>({done:true}),cancel:async()=>{}})}};
    return json(snapshot(++reads+1,reads===2?'budget_stopped':'in_progress'));
  };
  const result=await api.observeReview('stable-run',snapshot(1),()=>{},fetcher,async()=>{});
  assert.equal(result.status,'budget_stopped');assert.equal(reads,2);
  assert(requests.every(r=>!r[1]));
});

test('ambiguous start response reads the stable ID instead of repeating POST',async()=>{
  const api=helper();let posts=0;
  const result=await api.startReview({session_id:'stable-run'},()=>{},async(url,options)=>{
    if(options?.method==='POST'){posts++;throw Error('Lost start response');}
    return json(snapshot(8,'completed'));
  });
  assert.equal(posts,1);assert.equal(result.status,'completed');
});

test('definitive idempotency conflict is reported and never treated as successful recovery',async()=>{
  const api=helper();const requests=[];
  await assert.rejects(api.startReview({session_id:'stable-run'},()=>{},async(url,options)=>{
    requests.push([url,options]);return {ok:false,status:409,json:async()=>({detail:'Conflicting parameters'})};
  }),/Conflicting parameters/);
  assert.equal(requests.length,1);
});
