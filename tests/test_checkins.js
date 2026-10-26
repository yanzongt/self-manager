// Exercise the actual page's statistics and actions without a browser dependency.
const fs=require('fs'), vm=require('vm'), assert=require('assert');
const source=fs.readFileSync('apps/checkins/index.html','utf8').split('<script>')[1].split('</script>')[0];
const elements=new Map();
function element(key){if(!elements.has(key))elements.set(key,{value:key==='#range'?'7':key==='#chart-item'?'all':'',dataset:{},setAttribute(){},reset(){},focus(){},showModal(){this.open=true},close(){this.open=false}});return elements.get(key)}
let saved=null;
const ctx=vm.createContext({console,Date,Math,Number,String,Object,JSON,structuredClone,crypto:require('crypto').webcrypto,
 document:{querySelector:element,querySelectorAll:()=>[]},setInterval(){},fetch:async(url,opts)=>({ok:true,json:async()=>opts.method==='GET'?{data:saved,revision:null}:(saved=JSON.parse(opts.body).data,{revision:'new'})})});
vm.runInContext(source.replace('load();',''),ctx);
vm.runInContext(`
const midnight=new Date(2026,9,26,0,0,0).getTime();
const sample=[{type:'count',records:[{start:midnight},{start:midnight+1000}]},{type:'timer',records:[{start:midnight-60000,end:midnight+120000}],activeSince:midnight+180000}];
const result=daily(sample,midnight+240000);
if(result.counts[localDay(midnight)]!==2)throw Error('count aggregation');
if(result.times[localDay(midnight-1)]!==60000)throw Error('previous day split');
if(result.times[localDay(midnight)]!==180000)throw Error('today plus running session');
`,ctx);
(async()=>{
 await vm.runInContext('load()',ctx);
 element('#name').value='喝水';element('#type').value='count';
 await element('#add-form').onsubmit({preventDefault(){}});
 assert.equal(saved.items[0].name,'喝水');
 const id=saved.items[0].id;
 await element('#cards').onclick({target:{closest:()=>({dataset:{id,action:'check'}})}});
 assert.equal(saved.items[0].records.length,1);
 element('#name').value='阅读';element('#type').value='timer';
 await element('#add-form').onsubmit({preventDefault(){}});
 const timer=saved.items[1].id;
 const click=()=>element('#cards').onclick({target:{closest:()=>({dataset:{id:timer,action:'check'}})}});
 await click();assert.equal(typeof saved.items[1].activeSince,'number');
 await vm.runInContext('load()',ctx); // recover active session from persisted data
 await click();assert.equal(saved.items[1].activeSince,null);assert.equal(saved.items[1].records.length,1);
 assert(saved.items[1].records[0].end>=saved.items[1].records[0].start);
 assert(element('#time-chart').innerHTML.includes('<svg'));
 console.log('Check-in actions, persistence recovery, daily aggregation and midnight split passed.');
})().catch(e=>{console.error(e);process.exitCode=1});
