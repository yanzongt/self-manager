const assert = require('node:assert/strict');
const {page, KEY} = require('./test_comments.cjs');
const start = Date.UTC(2026, 9, 8, 8), minute = 60000;
function startSession(p, budget = 60, work = 25, rest = 5, auto = true) {
  p.element('purpose').value = '测试专注';
  p.element('minutes').value = String(budget);
  p.element('pomoWork').value = String(work);
  p.element('pomoBreak').value = String(rest);
  p.element('pomoAuto').checked = auto;
  p.fire('startForm', 'submit');
}
function tickAt(p, minutes) { p.setNow(start + minutes * minute); p.intervals[1](); }
function review(p, action) {
  p.fire('reviewChoices', 'click', {closest: () => ({dataset: {result: 'completed'}})});
  p.element('reviewText').value = '复盘内容';
  p.element(action).onclick();
}
function itemAction(p, id, action) {
  p.fire('workQuadrants', 'click', {closest: () => ({dataset: {itemId: id, itemAction: action}})});
}
async function main() {
  const p = page(new Map(), {now: start});
  startSession(p);
  assert.equal(p.state().active.pomodoro.phase, 'work');
  tickAt(p, 25);
  assert.equal(p.state().active.pomodoro.phase, 'break');
  assert.equal(p.state().active.pomodoro.records[0].actualMinutes, 25);
  assert.equal(p.notifications.length, 1);
  tickAt(p, 25);
  assert.equal(p.notifications.length, 1);
  tickAt(p, 30);
  assert.equal(p.state().active.pomodoro.phase, 'work');
  assert.equal(p.notifications.length, 2);
  tickAt(p, 56); // Catch up across the work boundary at minute 55.
  assert.equal(p.state().active.pomodoro.phase, 'break');
  const reloaded = page(p.storage, {now: start + 56 * minute});
  assert.equal(reloaded.state().active.pomodoro.records.length, 3);
  assert.equal(reloaded.notifications.length, 0);
  tickAt(reloaded, 60);
  assert.equal(reloaded.state().active.pomodoro.stopped, true);
  assert.equal(reloaded.state().active.pomodoro.records.length, 4);
  assert.equal(reloaded.element('reviewOverlay').hidden, false);
  tickAt(reloaded, 65);
  assert.equal(reloaded.state().active.pomodoro.records.length, 4);
  review(reloaded, 'extendBtn');
  assert.equal(reloaded.state().active.pomodoro.stopped, false);
  assert.equal(reloaded.state().active.pomodoro.startedAt, start + 65 * minute);
  tickAt(reloaded, 67);
  review(reloaded, 'finishBtn');
  assert.equal(reloaded.state().records[0].pomodoro.records.at(-1).actualMinutes, 2);
  assert.equal(reloaded.state().records[0].pomodoro.records.at(-1).status, 'interrupted');
  assert.match(reloaded.element('historyBody').innerHTML, /番茄钟/);
  reloaded.element('exportTxt').onclick();
  assert.match(await reloaded.downloads.at(-1).text(), /番茄钟阶段5/);

  const manual = page(new Map(), {now: start});
  startSession(manual, 10, 1, 1, false);
  tickAt(manual, 2);
  assert.equal(manual.state().active.pomodoro.waiting, true);
  tickAt(manual, 2.5);
  assert.equal(manual.state().active.pomodoro.records.length, 1);
  manual.element('pomoNext').onclick();
  assert.equal(manual.state().active.pomodoro.phase, 'break');
  assert.equal(manual.state().active.pomodoro.startedAt, start + 2.5 * minute);
  assert.match(manual.notifications.at(-1).title, /Break/);
  tickAt(manual, 4);
  manual.element('pomoAuto').checked = true;
  manual.element('pomoAuto').onchange();
  assert.equal(manual.state().active.pomodoro.phase, 'work');
  assert.equal(manual.state().active.pomodoro.startedAt, start + 4 * minute);
  tickAt(manual, 7.5); // Restore three transitions without a notification storm.
  assert.equal(manual.state().active.pomodoro.phase, 'break');
  assert.equal(manual.state().active.pomodoro.records.length, 5);
  assert.match(manual.notifications.at(-1).body, /3 次/);

  const short = page(new Map(), {now: start});
  startSession(short, 1);
  tickAt(short, 1);
  assert.equal(short.state().active.pomodoro.records[0].actualMinutes, 1);
  assert.equal(short.state().active.pomodoro.records[0].status, 'interrupted');
  assert.equal(short.notifications.length, 1); // Session deadline only.

  const tasks = page(new Map(), {now: start});
  for (const [important, urgent] of [[true, true], [true, false], [false, true], [false, false]]) {
    tasks.element('workItemTitle').value = `${important}/${urgent}`;
    tasks.element('workImportant').checked = important;
    tasks.element('workUrgent').checked = urgent;
    tasks.fire('workItemForm', 'submit');
  }
  assert.equal(tasks.state().workItems.length, 4);
  for (const title of ['重要 · 紧急', '重要 · 不紧急', '不重要 · 紧急', '不重要 · 不紧急']) {
    assert.ok(tasks.element('workQuadrants').innerHTML.includes(title));
  }
  const task = tasks.state().workItems[0];
  itemAction(tasks, task.id, 'edit');
  tasks.element('workItemTitle').value = '更新标题<script>';
  tasks.element('workUrgent').checked = false;
  tasks.fire('workItemForm', 'submit');
  assert.equal(tasks.state().workItems[0].urgent, false);
  assert.match(tasks.element('workQuadrants').innerHTML, /&lt;script&gt;/);
  itemAction(tasks, task.id, 'plan');
  assert.equal(tasks.element('purpose').value, '更新标题<script>');
  startSession(tasks);
  assert.equal(tasks.state().active.workItemId, task.id);
  itemAction(tasks, task.id, 'done');
  assert.equal(tasks.state().workItems[0].done, true);
  tasks.element('showDoneItems').checked = true;
  tasks.element('showDoneItems').onchange();
  assert.match(tasks.element('workQuadrants').innerHTML, /已完成/);
  const tasksReloaded = page(tasks.storage, {now: start});
  assert.equal(tasksReloaded.state().workItems.length, 4);
  tasksReloaded.element('exportJson').onclick();
  const backup = await tasksReloaded.downloads.at(-1).text();
  const imported = page(new Map(), {now: start});
  await imported.element('importInput').onchange({target: {files: [{text: async () => backup}]}});
  assert.equal(imported.state().workItems.length, 4);
  assert.equal(imported.state().active.pomodoro.phase, 'work');
  // Legacy active sessions acquire a timer without fabricating past phases.
  const legacyData = tasks.state();
  delete legacyData.active.pomodoro;
  delete legacyData.workItems;
  const legacy = page(new Map([[KEY, JSON.stringify(legacyData)]]), {now: start + minute});
  tickAt(legacy, 26);
  assert.equal(legacy.state().active.pomodoro.records.length, 1);
  console.log('Focus checks passed: auto/manual timers, notifications, refresh/catch-up, deadline, extension, early stop, quadrants, editing, linking, completion, backup and legacy data.');
}
main().catch(error => {console.error(error); process.exitCode = 1;});
