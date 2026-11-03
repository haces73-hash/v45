const fs=require('fs'),vm=require('vm'),assert=require('assert');
const html=fs.readFileSync(process.argv[2]||require('path').join(__dirname,'..','static','index.html'),'utf8');
const script=[...html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g)].map(m=>m[1]).join('\n').split("['profile','fulltime','region','city','radius'].forEach")[0];
const initialHistory=JSON.stringify([{id:'older',title:'Tidigare ansökan',company:'Tidigare AB',at:'2026-10-01',external:true}]);
const data=new Map([['king-history-v24',initialHistory]]),elements=new Map();let denySave=false;
function element(id){if(!elements.has(id))elements.set(id,{id,value:'',hidden:false,textContent:'',innerHTML:'',classList:{toggle(){}},addEventListener(){},style:{}});return elements.get(id)}
const ctx={Intl,Date,JSON,Math,Set,Map,URL,console,setTimeout,clearTimeout,AbortController,
 document:{getElementById:element},scrollTo(){},alert(){},confirm(){throw Error('Unexpected confirmation')},
 localStorage:{getItem:k=>data.get(k)||null,setItem(k,v){if(denySave)throw Error('storage full');data.set(k,v)},removeItem:k=>data.delete(k),key:i=>[...data.keys()][i],get length(){return data.size}},
 window:{open(){throw Error('Outbound window opened')},location:{}},fetch(){throw Error('Outbound request attempted')}};
vm.createContext(ctx);vm.runInContext(script,ctx);
const run=s=>vm.runInContext(s,ctx);
const job={id:'31451515',title:'Betongarbetare',company:'Test <AB>',city:'Halmstad',description:'Byggarbete med säkra lyft och HLR',application:{type:'external',url:'https://employer.invalid/apply'}};
run('jobs='+JSON.stringify([job])+';applicationAction(0)');
assert(element('body').value.includes('Betongarbetare'));assert(element('body').value.includes('Säkra lyft'));
assert(!element('body').value.includes('Jag har B-körkort'));assert.equal(element('demoEditor').hidden,false);
element('body').value='Mitt redigerade brev <script>alert(1)</script>';
run('saveDemoApplication()');
let saved=JSON.parse(data.get('jobb4kevin-demo-applications-v1'));assert.equal(saved.length,1);assert.equal(saved[0].status,'demo_saved');assert.equal(saved[0].letter,element('body').value);
assert.equal(data.get('king-history-v24'),initialHistory);assert.equal(run('jobs.length'),1);assert(element('historyItems').innerHTML.includes('&lt;script&gt;'));
run('openSavedDemoAt(0)');assert.equal(element('body').value,saved[0].letter);
element('body').value='Uppdaterat brev';run('saveDemoApplication()');saved=JSON.parse(data.get('jobb4kevin-demo-applications-v1'));assert.equal(saved.length,1);assert.equal(saved[0].letter,'Uppdaterat brev');
// Reopen after reload-like state reset: persisted content is the source of truth.
run('draft=null;editingDemoId=null;openSavedDemoAt(0)');assert.equal(element('body').value,'Uppdaterat brev');
element('body').value='';run('saveDemoApplication()');assert.equal(JSON.parse(data.get('jobb4kevin-demo-applications-v1'))[0].letter,'Uppdaterat brev');
element('body').value='Osparad text';denySave=true;run('saveDemoApplication()');assert.equal(element('body').value,'Osparad text');assert(element('demoSaveStatus').textContent.includes('Kunde inte spara'));denySave=false;
run('markApplied(0)');assert.equal(data.get('king-history-v24'),initialHistory);
assert(!html.includes('>MARKERA SOM ANSÖKT<'));assert(!html.includes('>SIMULERA SÄNDNING<'));
console.log('PASS: prepare → edit → local save → review → reopen/update; no outbound calls; history/shortlist preserved; escaped rendering; empty/storage-error handling.');
