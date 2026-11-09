const fs=require('fs'),vm=require('vm'),assert=require('assert');
const html=fs.readFileSync(process.argv[2]||require('path').join(__dirname,'..','static','index.html'),'utf8');
const script=[...html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g)].map(m=>m[1]).join('\n').split("['profile','fulltime','region','city','radius'].forEach")[0];
let clock='2026-11-04T22:59:00Z',calls=0;const data=new Map();
class FakeDate extends Date{constructor(...args){super(...(args.length?args:[clock]))}static now(){return new Date(clock).getTime()}}
const candidates=Array.from({length:8},(_,i)=>({id:String(80000000+i),title:'Montör '+i,company:'Test AB',city:'Halmstad',description:'Produktion',license_status:'not_required',employment_extent:'full_time',priority:4,match_score:100-i}));
function boot(){const els=new Map();function el(id){if(!els.has(id))els.set(id,{value:'',hidden:false,textContent:'',innerHTML:'',classList:{toggle(){}},addEventListener(){},style:{}});return els.get(id)}
 const ctx={Intl,Date:FakeDate,JSON,Math,Set,Map,URL,console,setTimeout,clearTimeout,AbortController,document:{getElementById:el},scrollTo(){},confirm(){return true},localStorage:{getItem:k=>data.get(k)||null,setItem:(k,v)=>data.set(k,v),removeItem:k=>data.delete(k),key:i=>[...data.keys()][i],get length(){return data.size}},window:{open(){throw Error('Outbound navigation')}},async fetch(url){assert(url.startsWith('/api/jobs?'));calls++;return {ok:true,json:async()=>({jobs:candidates,needs_review:[]})}}};
 vm.createContext(ctx);vm.runInContext(script,ctx);for(const [id,val]of Object.entries({profile:'priority',fulltime:'1',city:'Halmstad',region:'municipality',radius:'0'}))el(id).value=val;
 return {run:s=>vm.runInContext(s,ctx),el};}
(async()=>{
 let app=boot();assert.equal(app.run('todaySE()'),'2026-11-04');await app.run('loadJobs()');assert.equal(calls,1);assert.equal(app.run('jobs.length'),5);
 app.run('prepare(0)');app.el('body').value='Mitt sparade brev';app.run('saveDemoApplication()');
 app.run('decline(0)');assert.equal(app.run('jobs.length'),3);
 const saved=data.get('jobb4kevin-demo-applications-v1');
 app=boot();await app.run('loadJobs()');assert.equal(calls,1);assert.equal(app.run('jobs.length'),3);
 assert(!app.run('jobs.some(j=>j.id==="80000000"||j.id==="80000001")'));
 clock='2026-11-04T23:01:00Z'; // Swedish midnight, still November 4 in UTC.
 app=boot();assert.equal(app.run('todaySE()'),'2026-11-05');await app.run('loadJobs()');assert.equal(calls,2);
 assert.equal(app.run('jobs.length'),5);assert(!app.run('jobs.some(j=>j.id==="80000000")'));
 assert(app.run('jobs.some(j=>j.id==="80000001")'));assert(app.run('jobs.some(j=>j.id==="80000005")'));
 assert.equal(data.get('jobb4kevin-demo-applications-v1'),saved);
 assert(app.el('lastSearch').textContent.includes('5 nov. 2026'));
 app=boot();await app.run('loadJobs()');assert.equal(calls,2);
 assert(!app.run('jobs.some(j=>j.id==="80000000")'));assert.equal(app.run('readDemoApplications()[0].letter'),'Mitt sparade brev');
 // Two dismissals on different Swedish days block permanently.
 app.run('declineJob({id:"80000001"});declineJob({id:"80000001"})');
 assert.equal(app.run('declines["80000001"]'),2); // Same-day repeat does not count twice.
 app.run('declines["80000002"]=2;declineDays["80000002"]="2026-11-01";saveDeclines()');
 clock='2026-11-05T23:01:00Z';app=boot();await app.run('loadJobs()');assert.equal(calls,3);
 assert(!app.run('jobs.some(j=>j.id==="80000002")'));
 assert(!app.run('jobs.some(j=>j.id==="80000001")'));
 assert(!app.run('jobs.some(j=>j.id==="80000000")'));
 console.log('PASS: Swedish midnight triggers one new search; same-day cache reused; shortlist renewed without new ads; applied job stays excluded; previous-day decline returns; saved letter persists after reboot; second decline stays excluded.');
})().catch(e=>{console.error(e);process.exitCode=1});
