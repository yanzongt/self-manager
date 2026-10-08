// Exercise real page event handlers with a small DOM/storage harness.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(`${__dirname}/pdca_focus.html`, 'utf8').split('<script>')[1].split('</script>')[0];
const KEY = 'focus_pdca_singlefile_v1';

function page(storage = new Map()) {
  const elements = new Map(), intervals = [], downloads = [];
  let failSave = false;
  function element(id) {
    if (!elements.has(id)) elements.set(id, {
      value: id === 'minutes' ? '30' : id === 'tag' ? '学习' : id === 'trendTag' ? 'all' : '',
      hidden: true, innerHTML: '', handlers: {}, dataset: {},
      addEventListener(type, fn) { (this.handlers[type] ||= []).push(fn); },
      focus() {}, classList: {remove() {}, toggle() {}},
      click() {}, remove() {},
    });
    return elements.get(id);
  }
  const sandbox = {
    document: {getElementById: element, querySelectorAll: () => [], hidden: false,
      createElement: () => element('download'), body: {appendChild() {}}},
    window: {addEventListener() {}}, location: {protocol: 'file:'},
    localStorage: {getItem: key => storage.get(key) || null,
      setItem(key, value) { if (failSave) throw Error('Quota exceeded'); storage.set(key, value); }},
    structuredClone, crypto: require('node:crypto').webcrypto, Date, Math, Blob,
    URL: {createObjectURL(blob) { downloads.push(blob); return 'blob:test'; }, revokeObjectURL() {}},
    setTimeout: () => 0, clearTimeout() {}, setInterval(fn) { intervals.push(fn); }, confirm: () => true,
  };
  vm.runInNewContext(source, sandbox);
  return {element, storage, downloads, intervals,
    state: () => JSON.parse(storage.get(KEY)),
    failSave: value => {failSave = value;},
    fire(id, type, target = null) {
      for (const fn of element(id).handlers[type] || []) fn({preventDefault() {}, target});
    },
  };
}

async function main() {
  const p = page();
  assert.equal(p.element('commentSection').hidden, true);
  p.element('purpose').value = '读代码';
  p.fire('startForm', 'submit');
  assert.equal(p.element('commentSection').hidden, false);
  p.element('commentText').value = '  已找到问题\n<script>test</script>  ';
  const before = Date.now();
  p.fire('commentForm', 'submit');
  const first = p.state().active.comments[0];
  assert.ok(first.at >= before && first.at <= Date.now());
  assert.equal(first.text, '已找到问题\n<script>test</script>');
  assert.match(p.element('activeComments').innerHTML, /&lt;script&gt;/);
  assert.equal(p.element('commentText').value, '');
  p.element('commentText').value = '草稿不能被计时刷新清空';
  p.intervals[1]();
  assert.equal(p.element('commentText').value, '草稿不能被计时刷新清空');
  p.failSave(true);
  p.fire('commentForm', 'submit');
  assert.equal(p.element('commentText').value, '草稿不能被计时刷新清空');
  assert.equal(p.state().active.comments.length, 1);
  p.failSave(false);
  p.element('commentText').value = '第二条评论';
  p.fire('commentForm', 'submit');
  const restored = page(p.storage);
  assert.match(restored.element('activeComments').innerHTML, /第二条评论/);
  const sessionId = restored.state().active.id;
  const target = {closest: selector => selector === '[data-export-comment]' ?
    {dataset: {session: sessionId, exportComment: first.id}} : null};
  restored.fire('activeComments', 'click', target);
  let exported = await restored.downloads.at(-1).text();
  assert.match(exported, /评论添加时间：/);
  assert.ok(exported.includes(new Date(first.at).toISOString()));
  assert.ok(exported.includes(first.text));
  assert.ok(!exported.includes('第二条评论'));
  restored.element('exportTxt').onclick();
  assert.match(await restored.downloads.at(-1).text(), /第二条评论/);
  restored.element('exportJson').onclick();
  const backup = JSON.parse(await restored.downloads.at(-1).text());
  assert.equal(backup.data.active.comments.length, 2);
  restored.fire('reviewChoices', 'click', {closest: () => ({dataset: {result: 'completed'}})});
  restored.element('reviewText').value = '完成修复';
  restored.element('extendBtn').onclick();
  assert.equal(restored.state().active.comments.length, 2);
  restored.fire('reviewChoices', 'click', {closest: () => ({dataset: {result: 'completed'}})});
  restored.element('reviewText').value = '完成修复';
  restored.element('finishBtn').onclick();
  assert.equal(restored.state().active, null);
  assert.equal(restored.state().records[0].comments.length, 2);
  assert.match(restored.element('historyBody').innerHTML, /第二条评论/);
  restored.fire('historyBody', 'click', target);
  assert.ok((await restored.downloads.at(-1).text()).includes(first.text));
  const recordBackup = restored.state();
  recordBackup.records.push({...recordBackup.records[0], id: 'other-record', purpose: '另一条记录不应导出'});
  const historyPage = page(new Map([[KEY, JSON.stringify(recordBackup)]]));
  assert.match(historyPage.element('historyBody').innerHTML, /导出记录 TXT/);
  historyPage.fire('historyBody', 'click', {closest: selector => selector === '[data-export-record]' ?
    {dataset: {exportRecord: sessionId}} : null});
  const recordExport = await historyPage.downloads.at(-1).text();
  for (const text of ['单条历史记录', '开始时间：', '结束时间：', '读代码', '完成修复', '阶段复盘1', first.text, '第二条评论']) {
    assert.ok(recordExport.includes(text), `Missing in record export: ${text}`);
  }
  assert.ok(!recordExport.includes('另一条记录不应导出'));
  assert.equal(historyPage.state().records.length, 2);
  await restored.element('importInput').onchange({target: {files: [{text: async () => JSON.stringify(backup)}]}});
  assert.equal(restored.state().active.comments[0].at, first.at);
  // Old backups without comments still load and can accept their first comment.
  delete backup.data.active.comments;
  const old = page(new Map([[KEY, JSON.stringify(backup.data)]]));
  old.element('commentText').value = '旧会话的新评论';
  old.fire('commentForm', 'submit');
  assert.equal(old.state().active.comments.length, 1);
  console.log('Checks passed: comment lifecycle and exports, single history export with comments and extensions, no unrelated records, restore, old backups.');
}
main().catch(error => {console.error(error); process.exitCode = 1;});
