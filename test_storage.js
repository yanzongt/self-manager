// Exercise the actual page handlers against an asynchronous file API contract.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const KEY = 'focus_pdca_singlefile_v1';
const source = fs.readFileSync(`${__dirname}/pdca_focus.html`, 'utf8').split('<script>')[1].split('</script>')[0];
const start = Date.UTC(2026, 9, 8, 8), minute = 60000;
const empty = () => ({tags:['工作'], records:[], active:null, workItems:[], pomoSettings:{workMinutes:25,breakMinutes:5,autoSwitch:true}, pomodoro:null});
const settle = async () => { for(let i=0;i<8;i++) await new Promise(resolve=>setImmediate(resolve)); };
function page(server, {legacy=null, file=false}={}) {
  const elements = new Map(), downloads = [], intervals = [], events = {}, notifications = [];
  let now = start;
  const Clock = class extends Date { constructor(...args){super(...(args.length?args:[now]));} static now(){return now;} };
  function element(id) {
    if(!elements.has(id)) elements.set(id, {value:id==='minutes'?'30':id==='tag'?'工作':id==='trendTag'?'all':'', checked:false, hidden:true, inert:id==='appContent', handlers:{}, innerHTML:'', textContent:'',
      addEventListener(type,fn){(this.handlers[type] ||= []).push(fn);}, focus(){}, click(){}, remove(){}, classList:{remove(){},toggle(){}}});
    return elements.get(id);
  }
  const fetch = async (path, options={}) => {
    if(path!=='/api/data') return {ok:true,json:async()=>({available:false,ok:true})};
    if(server.unavailable) throw Error('服务不可用');
    if(options.method==='POST') {
      const payload=JSON.parse(options.body);
      server.writes++;
      if(server.failWrite) return {ok:false,status:500,json:async()=>({error:'磁盘写入失败'})};
      if(payload.revision !== server.revision) return {ok:false,status:409,json:async()=>({error:'数据已被其他页面修改，请先导出本页 JSON 后重新读取。'})};
      server.data=payload.data; server.revision=String(Number(server.revision||0)+1);
      return {ok:true,status:200,json:async()=>({revision:server.revision,ok:true})};
    }
    return {ok:true,status:200,json:async()=>({data:structuredClone(server.data),revision:server.revision})};
  };
  function Notification(title, config){notifications.push({title,...config});this.close=()=>{};}
  Notification.permission='granted';
  vm.runInNewContext(source, {
    document:{getElementById:element,querySelectorAll:()=>[],hidden:false,createElement:()=>element('download'),body:{appendChild(){}}},
    window:{PDCA_NATIVE_TOKEN:file?undefined:'token', Notification, addEventListener(type,fn){events[type]=fn;}}, Notification,
    location:{protocol:file?'file:':'http:'},
    localStorage:{getItem:()=>legacy?JSON.stringify(legacy):null,setItem(){throw Error('Browser writes forbidden');}},
    fetch,AbortSignal,structuredClone,crypto:require('node:crypto').webcrypto,Date:Clock,Math,Blob,
    URL:{createObjectURL(blob){downloads.push(blob);return 'blob:test';},revokeObjectURL(){}},
    setTimeout:()=>0,clearTimeout(){},setInterval(fn){intervals.push(fn);},confirm:()=>true,
  });
  return {element,downloads,notifications,events, async fire(id,type,target=null){await Promise.all((element(id).handlers[type]||[]).map(fn=>fn({preventDefault(){},target})));}, async tick(minutes){now=start+minutes*minute;await intervals[1]();}, async export(){element('exportJson').onclick();return JSON.parse(await downloads.at(-1).text());}};
}
const server = (data=null) => ({data,revision:data?'1':null,writes:0});
async function main(){
  const legacy=empty(); legacy.tags=['旧记录'];
  const disk=server(); const p=page(disk,{legacy}); await settle();
  assert.equal(disk.data.tags[0],'旧记录');
  assert.equal(p.element('appContent').inert,false);
  assert.match(p.element('storageStatus').textContent,/迁移/);
  p.element('purpose').value='测试会话';
  await p.fire('startForm','submit');
  p.element('commentText').value='进展'; await p.fire('commentForm','submit');
  assert.equal(disk.data.active.comments[0].text,'进展');
  assert.match(p.element('storageStatus').textContent,/已保存/);
  await p.element('pomoStart').onclick();
  const timerId=disk.data.pomodoro.id;
  await p.tick(25);
  assert.equal(disk.data.pomodoro.phase,'break');
  await p.fire('reviewChoices','click',{closest:()=>({dataset:{result:'completed'}})});
  p.element('reviewText').value='完成'; await p.element('finishBtn').onclick();
  assert.equal(disk.data.records[0].comments[0].text,'进展');
  assert.equal(disk.data.pomodoro.id,timerId);
  assert.equal(disk.data.active,null);
  const reopened=page(disk,{legacy}); await settle();
  assert.equal((await reopened.export()).data.records.length,1);
  assert.equal((await reopened.export()).data.pomodoro.phase,'break');
  await reopened.element('pomoStop').onclick();
  assert.equal(disk.data.pomodoro,null);
  const backup=await reopened.export(); backup.data.tags=['导入'];
  await reopened.element('importInput').onchange({target:{files:[{text:async()=>JSON.stringify(backup)}]}});
  assert.deepEqual(disk.data.tags,['导入']);

  disk.failWrite=true;
  reopened.element('workItemTitle').value='待重试'; reopened.element('workImportant').checked=true;
  await reopened.fire('workItemForm','submit');
  assert.equal(disk.data.workItems.length,0);
  assert.equal((await reopened.export()).data.workItems.length,1);
  assert.match(reopened.element('storageStatus').textContent,/尚未保存/);
  assert.equal(reopened.element('retrySave').hidden,false);
  assert.notEqual(reopened.element('toast').textContent,'事项已添加');
  let warned=false; reopened.events.beforeunload({preventDefault(){warned=true;}}); assert.equal(warned,true);
  disk.failWrite=false; await reopened.element('retrySave').onclick();
  assert.equal(disk.data.workItems.length,1);
  assert.match(reopened.element('storageStatus').textContent,/已保存/);

  // Two tabs cannot silently replace each other's saved data.
  const stale=page(disk); await settle();
  reopened.element('workItemTitle').value='第二条'; await reopened.fire('workItemForm','submit');
  stale.element('workItemTitle').value='冲突条目'; await stale.fire('workItemForm','submit');
  assert.equal(disk.data.workItems[1].title,'第二条');
  assert.match(stale.element('storageStatus').textContent,/其他页面修改/);
  assert.equal(stale.element('retrySave').hidden,true);
  assert.equal(stale.element('retryLoad').hidden,false);

  const offline=server(); offline.unavailable=true;
  const failed=page(offline,{legacy}); await settle();
  assert.equal(failed.element('appContent').inert,true);
  assert.equal(offline.writes,0);
  assert.match(failed.element('storageStatus').textContent,/读取失败/);
  offline.unavailable=false; await failed.element('retryLoad').onclick();
  assert.deepEqual(offline.data.tags,['旧记录']);
  const filePage=page(server(),{legacy,file:true}); await settle();
  assert.equal(filePage.element('appContent').inert,true);
  assert.match(filePage.element('storageStatus').textContent,/python3 serve.py/);
  filePage.element('exportLegacy').onclick();
  assert.deepEqual(JSON.parse(await filePage.downloads[0].text()).data.tags,['旧记录']);
  console.log('Page checks passed: migration, authoritative file data, comments, timers, refresh, import, failed writes/retry, conflicts, unavailable service and legacy export.');
}
main().catch(error=>{console.error(error);process.exitCode=1;});
