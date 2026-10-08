// Run with PLAYWRIGHT_CORE=/path/to/playwright-core node test_strength.js.
// CHROME_PATH may override the local Chrome executable.
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const { pathToFileURL } = require('node:url');
const path = require('node:path');
const { chromium } = require(process.env.PLAYWRIGHT_CORE || 'playwright');
const KEY = 'strengthTracker_v1';
const url = pathToFileURL(path.join(__dirname, 'strength_training_tracker.html')).href;
(async () => {
  const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH || '/usr/bin/google-chrome', headless: true, args: ['--no-sandbox'] });
  const errors = [], dialogs = [];
  async function open(initial) {
    const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
    const page = await context.newPage();
    page.on('pageerror', error => errors.push(error.message));
    page.on('dialog', async dialog => { dialogs.push(dialog.message()); await dialog.accept(); });
    await page.goto(url);
    if (initial) { await page.evaluate(({ KEY, initial }) => localStorage.setItem(KEY, JSON.stringify(initial)), { KEY, initial }); await page.reload(); }
    return page;
  }
  const state = page => page.evaluate(key => JSON.parse(localStorage.getItem(key)), KEY);
  async function upload(page, selector, payload) {
    await page.setInputFiles(selector, { name: 'test.json', mimeType: 'application/json', buffer: Buffer.from(JSON.stringify(payload)) });
    await page.waitForFunction(selector => document.querySelector(selector).value === '', selector);
  }
  async function download(page, selector) {
    const waiting = page.waitForEvent('download'); await page.click(selector);
    const file = await waiting; return JSON.parse(await fs.readFile(await file.path(), 'utf8'));
  }
  try {
    const legacy = { logs: [], body: [], weights: { squat: 4.5 } };
    const page = await open(legacy);
    await page.click('[data-page="schedule"]'); await page.click('#fullWeek [data-day="1"]');
    assert.equal(await page.inputValue('[data-ex="squat"][data-target="weight"]'), '4.5');
    for (const [key, value] of [['sets', '4'], ['reps', '14'], ['weight', '6.3']]) {
      await page.fill(`[data-ex="squat"][data-target="${key}"]`, value);
      await page.locator(`[data-ex="squat"][data-target="${key}"]`).blur();
    }
    let stored = await state(page), squat = stored.exercises.find(x => x.id === 'squat');
    assert.deepEqual([squat.sets, squat.reps, squat.weight], [4, 14, 6.3]);
    await page.fill('[data-ex="squat"][data-target="sets"]', '0'); await page.locator('[data-ex="squat"][data-target="sets"]').blur();
    assert.equal((await state(page)).exercises.find(x => x.id === 'squat').sets, 4);
    await page.click('#newExercise'); await page.fill('#exerciseName', '测试划船 <安全>'); await page.fill('#exercisePart', '背部'); await page.fill('#exerciseNote', '左右各做，保持稳定');
    await page.click('#exerciseForm button[type="submit"]');
    stored = await state(page); const custom = stored.exercises.at(-1);
    assert.ok(stored.routines[1].ids.includes(custom.id));
    await page.click(`[data-edit-ex="${custom.id}"]`); await page.fill('#exerciseNote', '更新备注'); await page.click('#exerciseForm button[type="submit"]');
    await page.reload(); await page.click('[data-page="schedule"]'); await page.click('#fullWeek [data-day="1"]');
    assert.equal(await page.inputValue('[data-ex="squat"][data-target="sets"]'), '4');
    assert.match(await page.textContent('#dayDetails'), /更新备注/);
    const plan = await download(page, '#exportPlan'); assert.equal(plan.type, 'plan'); assert.equal(plan.exercises.at(-1).note, '更新备注');
    await page.click('#logSelected');
    assert.deepEqual(await Promise.all(['#logSets', '#logReps', '#logWeight'].map(id => page.inputValue(id))), ['4', '14', '6.3']);
    await page.click('#saveLog');
    await page.click('[data-page="schedule"]');
    await page.click(`[data-log-ex="${custom.id}"]`);
    assert.equal(await page.inputValue('#logEx'), custom.id);
    assert.deepEqual(await Promise.all(['#logSets', '#logReps', '#logWeight'].map(id => page.inputValue(id))), ['2', '10', '0']);
    await page.click('#saveLog');
    const records = await download(page, '#exportLogs'); assert.equal(records.logs.length, 2);
    const backup = await download(page, '#exportBtn'); assert.equal(backup.type, 'backup');
    const target = await open(); await page.click('[data-page="schedule"]');
    await upload(target, '#planFile', plan);
    assert.deepEqual((await state(target)).routines, plan.routines);
    await upload(target, '#logsFile', records); assert.equal((await state(target)).logs.length, 2);
    await upload(target, '#logsFile', records); assert.equal((await state(target)).logs.length, 2);
    const before = await state(target), bad = structuredClone(plan); bad.exercises[0].sets = 0;
    await upload(target, '#planFile', bad); assert.deepEqual(await state(target), before);
    await upload(target, '#planFile', records); assert.deepEqual(await state(target), before);
    const conflict = structuredClone(records); conflict.logs[0].weight = 9;
    await upload(target, '#logsFile', conflict); assert.deepEqual(await state(target), before);
    const invalidDate = structuredClone(records); invalidDate.logs[0].date = '2026-02-30';
    await upload(target, '#logsFile', invalidDate); assert.deepEqual(await state(target), before);
    // Storage failures must leave both the stored and live plan untouched.
    await target.evaluate(() => { window.originalSetItem = Storage.prototype.setItem; Storage.prototype.setItem = () => { throw new Error('quota'); }; });
    await upload(target, '#planFile', plan); assert.deepEqual(await state(target), before);
    await target.evaluate(() => { Storage.prototype.setItem = window.originalSetItem; });
    const replaced = structuredClone(plan); replaced.exercises.find(x => x.id === 'squat').name = '完全不同的动作';
    await upload(target, '#planFile', replaced);
    stored = await state(target); const originalLog = stored.logs.find(x => x.id === records.logs[0].id);
    assert.equal(stored.exercises.find(x => x.id === originalLog.exId).name, '徒手深蹲');
    await upload(target, '#importFile', backup); assert.deepEqual((await state(target)).logs, backup.logs);
    await upload(target, '#importFile', { app: 'strengthTracker', version: 1, ...legacy });
    assert.equal((await state(target)).exercises.find(x => x.id === 'squat').weight, 4.5);
    // Records alone restore custom action definitions without changing the weekly plan.
    const recordsOnly = await open(); await upload(recordsOnly, '#logsFile', records);
    stored = await state(recordsOnly); assert.ok(stored.exercises.some(x => x.id === custom.id)); assert.ok(!stored.routines[1].ids.includes(custom.id));
    await upload(recordsOnly, '#logsFile', records); assert.equal((await state(recordsOnly)).logs.length, 2);
    await page.click(`[data-remove-ex="${custom.id}"]`);
    assert.equal((await state(page)).logs.length, 2);
    await page.selectOption('#addExisting', custom.id); await page.click('#addToDay');
    await page.setViewportSize({ width: 390, height: 844 });
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    await page.screenshot({ path: '/tmp/strength-training-mobile.png', fullPage: true });
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.click('#fullWeek [data-day="2"]');
    await page.click('[data-log-ex="wrist"]');
    assert.equal(await page.inputValue('#logEx'), 'wrist');
    assert.equal(await page.textContent('#logRepsLabel'), '每组秒数');
    assert.equal(await page.inputValue('#logReps'), '20');
    await page.click('#saveLog'); assert.equal((await state(page)).logs.at(-1).unit, '秒');
    await page.click('[data-page="analysis"]'); await page.click('[data-page="body"]');
    assert.deepEqual(errors, []);
    assert.ok(dialogs.some(x => x.includes('同编号记录内容冲突')));
    console.log('Passed: legacy migration, editable targets, exercise add/edit, reload persistence, plan/records/backup round trips, duplicate/conflict/invalid imports, history preservation and mobile layout.');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
