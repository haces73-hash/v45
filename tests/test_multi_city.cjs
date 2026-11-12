const fs=require('fs'),vm=require('vm'),assert=require('assert');
const html=fs.readFileSync(process.argv[2]||require('path').join(__dirname,'..','static','index.html'),'utf8');
const script=[...html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g)].map(m=>m[1]).join('\n').split("['profile','fulltime','region','radius'].forEach")[0];
const storage=new Map();let clock='2026-11-12T12:00:00Z',calls=[],pending=[],response;
class FakeDate extends Date{constructor(...args){super(...(args.length?args:[clock]))}static now(){return new Date(clock).getTime()}}
const make=(id,city,priority,score)=>({id,title:'Jobb '+id,company:'Test AB',city,priority,match_score:score,license_status:'not_required',employment_extent:'full_time'});
const candidates=[make('1','Halmstad',1,30),make('2','Laholm',1,90),make('3','Laholm',2,99),make('4','Halmstad',2,70),make('5','Laholm',3,99),make('6','Halmstad',4,100),make('7','Laholm',4,80)];
function boot(){
 const elements=new Map(),boxes=['Halmstad','Falkenberg','Varberg','Kungsbacka','Laholm','Hylte','Helsingborg','Göteborg'].map(value=>({value,checked:value==='Halmstad'}));
 function el(id){if(!elements.has(id))elements.set(id,{value:'',hidden:false,textContent:'',innerHTML:'',classList:{toggle(){}},style:{}});return elements.get(id)}
 const context={Intl,Date:FakeDate,JSON,Math,Set,Map,URL,console,setTimeout,clearTimeout,AbortController,document:{getElementById:el,querySelectorAll(){return boxes}},scrollTo(){},confirm(){return true},localStorage:{getItem:k=>storage.get(k)||null,setItem:(k,v)=>storage.set(k,v),removeItem:k=>storage.delete(k),key:i=>[...storage.keys()][i],get length(){return storage.size}},window:{},fetch(url){calls.push(url);if(url.includes('defer=yes'))throw Error();return Promise.resolve({ok:true,json:async()=>response})}};
 vm.createContext(context);vm.runInContext(script,context);const run=s=>vm.runInContext(s,context);
 el('profile').value='priority';el('fulltime').value='1';el('region').value='municipality';run('restoreCitySelection()');
 return {run,el,select(cities){boxes.forEach(b=>b.checked=cities.includes(b.value));run('saveCitySelection()')},ids(){return JSON.parse(run('JSON.stringify(jobs.map(j=>j.id))'))}};
}
(async()=>{
 response={jobs:[...candidates,candidates[1]],needs_review:[],search_complete:true};
 let app=boot();app.select(['Laholm','Halmstad']);await app.run('loadJobs()');
 assert.deepEqual(new URL(calls[0],'https://example.test').searchParams.getAll('city'),['Halmstad','Laholm']);
 assert.deepEqual(app.ids(),['2','1','3','4','5']);assert(app.el('status').textContent.includes('Halmstad, Laholm'));
 const identity=app.run('shortlistIdentity()');app.select(['Halmstad','Laholm']);assert.equal(calls.length,1);assert.equal(app.run('shortlistIdentity()'),identity);
 app.run('decline(0)');assert.deepEqual(app.ids(),['1','3','4','5']);
 await app.run('loadJobs(true)');assert.deepEqual(app.ids(),['1','3','4','5']);
 app.run('history.push({id:"3"});localStorage.setItem(HISTORY_KEY,JSON.stringify(history))');app.run('selectBestFive()');assert(!app.ids().includes('3'));assert.equal(app.ids().length,3);
 app=boot();await app.run('loadJobs()');assert.equal(calls.length,2);assert.equal(app.ids().length,3);assert(!app.ids().includes('3')); // applied job stays hidden after restart
 assert.equal(app.run('selectedCities().join(",")'),'Halmstad,Laholm');
 app.select([]);await app.run('loadJobs()');assert.equal(calls.length,2);assert.equal(app.ids().length,0);assert(app.el('status').textContent.includes('minst en kommun'));
 app.select(['Laholm']);response={jobs:[],needs_review:[],search_complete:false,errors:['offline']};await app.run('loadJobs()');
 assert.equal(app.run('Object.hasOwn(getShortlists(),shortlistIdentity())'),false);
 response={jobs:candidates.filter(j=>j.city==='Laholm'),needs_review:[],search_complete:true};await app.run('loadJobs()');assert(app.ids().length>0);
 assert.equal(app.run('Object.hasOwn(getShortlists(),shortlistIdentity())'),true);
 clock='2026-11-12T23:01:00Z';app.select(['Halmstad','Laholm']);response={jobs:candidates,needs_review:[],search_complete:true};await app.run('loadJobs()');assert.equal(app.ids().length,5);assert(app.ids().includes('2'));
 console.log('PASS multi-city: combined top five, priority then match score, duplicates, manual apply, selection persistence, fixed shortlist, empty selection, incomplete recovery and next Swedish day');
})().catch(e=>{console.error(e);process.exitCode=1});
