// Uses the built Vue page and a real server with temporary data, never personal files.
const assert = require('node:assert/strict');
const { spawn } = require('node:child_process');
const readline = require('node:readline');
const fs = require('node:fs/promises');
const { chromium } = require(process.env.PLAYWRIGHT_CORE || '../apps/pdca/.generated/node_modules/playwright-core');
const legacy = {
  tags: ['旧记录'], records: [], active: null, workItems: [],
  pomoSettings: { workMinutes: 25, breakMinutes: 5, autoSwitch: true }, pomodoro: null,
};
const server = spawn(process.env.PYTHON || 'python3', ['-u', '-c', `
import tempfile
from pathlib import Path
from serve import create_server, Scheduler
with tempfile.TemporaryDirectory() as folder:
    server, _ = create_server(0, Scheduler(lambda *args: None), Path(folder) / 'pdca.json')
    print('http://127.0.0.1:' + str(server.server_port), flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()
`], { cwd: require('node:path').resolve(__dirname, '..'), stdio: ['ignore', 'pipe', 'pipe'] });
let diagnostic = '';
server.stderr.on('data', value => diagnostic += value);
(async () => {
  let browser;
  try {
    const url = await new Promise((resolve, reject) => {
      readline.createInterface({ input: server.stdout }).once('line', resolve);
      server.once('error', reject);
      server.once('exit', code => reject(Error(`Test server exited ${code}: ${diagnostic}`)));
    });
    browser = await chromium.launch({ executablePath: process.env.CHROME_PATH || '/usr/bin/google-chrome', headless: true, args: ['--no-sandbox'] });
    const context = await browser.newContext({ timezoneId: 'Asia/Shanghai', acceptDownloads: true });
    const page = await context.newPage(), errors = [];
    page.on('pageerror', error => errors.push(error.message));
    page.on('dialog', dialog => dialog.accept());
    await page.clock.install({ time: new Date('2026-10-28T08:00:00+08:00') });
    await page.addInitScript(data => localStorage.setItem('focus_pdca_singlefile_v1', JSON.stringify(data)), legacy);
    const data = (target = page) => target.evaluate(async () => (await (await fetch('/api/data', { headers: { 'X-PDCA-Token': window.PDCA_NATIVE_TOKEN } })).json()).data);
    const ready = target => target.waitForFunction(() => document.querySelector('#appContent') && !document.querySelector('#appContent').inert);
    const save = async (action, target = page) => {
      const response = target.waitForResponse(response => response.url().endsWith('/api/data') && response.request().method() === 'POST');
      await action(); const result = await response; await ready(target); return result;
    };
    async function backup(target = page) {
      const pending = target.waitForEvent('download'); await target.locator('#exportJson').click();
      return JSON.parse(await fs.readFile(await (await pending).path(), 'utf8'));
    }
    await page.goto(url + '/pdca/'); await ready(page);
    assert.deepEqual((await data()).tags, ['旧记录']);
    assert.match(await page.locator('#storageStatus').innerText(), /迁移/);
    await page.locator('#purpose').fill('测试会话');
    await save(() => page.locator('#startBtn').click());
    const comment = '进展 <script>alert(1)</script> & 复盘';
    await page.locator('#commentText').fill(comment);
    await save(() => page.locator('#commentForm button').click());
    assert.equal(await page.locator('#activeComments .comment-text').innerText(), comment);
    const commentDownload = page.waitForEvent('download');
    await page.locator('#activeComments [data-export-comment]').click();
    assert.match(await fs.readFile(await (await commentDownload).path(), 'utf8'), /评论添加时间/);
    await save(() => page.locator('#pomoStart').click());
    const timerId = (await data()).pomodoro.id;
    await page.clock.fastForward(25 * 60000);
    await page.waitForFunction(() => document.querySelector('#pomoStatus').textContent.includes('Break'));
    assert.equal((await data()).pomodoro.phase, 'break');
    await page.locator('#endEarly').click();
    await page.locator('#reviewChoices [data-result=partial]').click();
    await page.locator('#reviewText').fill('阶段复盘');
    await save(() => page.locator('#extendBtn').click());
    assert.equal((await data()).active.extensions.length, 1);
    assert.equal((await data()).active.extraMinutes, 10);
    await page.locator('#endEarly').click();
    await page.locator('#reviewChoices [data-result=completed]').click();
    await page.locator('#reviewText').fill('完成');
    await save(() => page.locator('#finishBtn').click());
    assert.equal((await data()).records[0].comments[0].text, comment);
    assert.equal((await data()).pomodoro.id, timerId);
    await page.reload(); await ready(page);
    assert.equal((await data()).records.length, 1);
    assert.equal((await data()).pomodoro.phase, 'break');
    await save(() => page.locator('#pomoStop').click());
    const restored = await backup(); restored.data.tags = ['导入'];
    await save(() => page.locator('#importInput').setInputFiles({ name: 'backup.json', mimeType: 'application/json', buffer: Buffer.from(JSON.stringify(restored)) }));
    assert.deepEqual((await data()).tags, ['导入']);

    // Manual mode waits at the boundary, then enabling auto starts the next phase.
    await save(() => page.locator('#pomoAuto').uncheck());
    await save(() => page.locator('#pomoStartBreak').click());
    await page.clock.fastForward(5 * 60000);
    await page.waitForFunction(() => document.querySelector('#pomoStatus').textContent.includes('等待手动切换'));
    await ready(page);
    assert.equal((await data()).pomodoro.waiting, true);
    await save(() => page.locator('#pomoAuto').check());
    assert.equal((await data()).pomodoro.phase, 'work');
    assert.equal((await data()).pomodoro.waiting, false);
    await save(() => page.locator('#pomoNext').click());
    assert.equal((await data()).pomodoro.phase, 'break');
    await save(() => page.locator('#pomoStop').click());
    assert.equal((await data()).records.length, 1);
    assert.equal((await data()).active, null);

    // A disk error must keep the page changes exportable and retryable.
    let failWrite = true;
    await page.route('**/api/data', route => failWrite && route.request().method() === 'POST' ? route.fulfill({ status: 500, json: { error: '磁盘写入失败' } }) : route.continue());
    await page.locator('#workItemTitle').fill('待重试');
    const failure = await save(() => page.locator('#workItemSave').click());
    assert.equal(failure.status(), 500);
    assert.equal((await data()).workItems.length, 0);
    assert.equal((await backup()).data.workItems[0].title, '待重试');
    assert.match(await page.locator('#storageStatus').innerText(), /尚未保存/);
    assert(await page.locator('#retrySave').isVisible());
    assert(!await page.locator('#toast').innerText().then(text => text === '事项已添加'));
    failWrite = false;
    await save(() => page.locator('#retrySave').click());
    assert.equal((await data()).workItems.length, 1);

    // A stale browser tab must not replace the first tab's saved changes.
    const stale = await context.newPage(); stale.on('dialog', dialog => dialog.accept());
    await stale.goto(url + '/pdca/'); await ready(stale);
    await page.locator('#workItemTitle').fill('第二条');
    await save(() => page.locator('#workItemSave').click());
    await stale.locator('#workItemTitle').fill('冲突条目');
    const conflict = await save(() => stale.locator('#workItemSave').click(), stale);
    assert.equal(conflict.status(), 409);
    assert.equal((await data()).workItems[1].title, '第二条');
    assert.equal((await backup(stale)).data.workItems[1].title, '冲突条目');
    assert(!await stale.locator('#retrySave').isVisible());
    assert(await stale.locator('#retryLoad').isVisible());
    await stale.locator('#retryLoad').click();
    await stale.waitForFunction(() => document.querySelector('#storageStatus').textContent.includes('数据已读取'));
    assert.equal((await backup(stale)).data.workItems[1].title, '第二条');

    // An unavailable service cannot overwrite disk data or enable the editor.
    const offline = await context.newPage();
    await offline.route('**/api/data', route => route.abort());
    await offline.goto(url + '/pdca/');
    await offline.waitForFunction(() => document.querySelector('#storageStatus').textContent.includes('读取失败'));
    assert(await offline.locator('#appContent').evaluate(node => node.inert));
    await offline.unroute('**/api/data');
    await offline.locator('#retryLoad').click(); await ready(offline);
    assert.equal((await data(offline)).workItems.length, 2);
    // Overdue sessions reopen review, Esc cannot dismiss it, and extension starts
    // a fresh ten-minute budget even when the old deadline is far in the past.
    await offline.clock.install({ time: new Date('2026-10-28T10:00:00+08:00') });
    await offline.locator('#purpose').fill('超时复盘');
    await offline.locator('#minutes').fill('1');
    await save(() => offline.locator('#startBtn').click(), offline);
    await offline.clock.fastForward(20 * 60000);
    await offline.locator('#reviewOverlay').waitFor();
    await offline.keyboard.press('Escape');
    assert(await offline.locator('#reviewOverlay').isVisible());
    await offline.locator('#reviewChoices [data-result=partial]').click();
    await offline.locator('#reviewText').fill('继续十分钟');
    await save(() => offline.locator('#extendBtn').click(), offline);
    const active = (await data(offline)).active;
    assert(active.startedAt + (active.budgetMinutes + active.extraMinutes) * 60000 - await offline.evaluate(() => Date.now()) >= 10 * 60000);
    assert.deepEqual(errors, []);
    console.log('PDCA storage browser checks passed: migration, comments/export, independent timer transitions, review/extension, refresh, import, write failure/retry, stale-tab conflict, unavailable service and recovery.');
  } finally {
    await browser?.close(); server.kill('SIGINT');
    await new Promise(resolve => server.exitCode !== null ? resolve() : server.once('exit', resolve));
  }
})().catch(error => { console.error(error); process.exitCode = 1 });
