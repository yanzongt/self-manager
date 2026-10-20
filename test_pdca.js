// PLAYWRIGHT_CORE=/path/to/playwright-core node test_pdca.js
// Uses a temporary data file and never touches the personal PDCA records.
const assert = require('node:assert/strict');
const { spawn } = require('node:child_process');
const readline = require('node:readline');
const { chromium } = require(process.env.PLAYWRIGHT_CORE || 'playwright');
const fixture = {
  tags: ['工作', '学习'], active: null, pomodoro: null,
  pomoSettings: { workMinutes: 25, breakMinutes: 5, autoSwitch: true },
  records: Array.from({ length: 23 }, (_, i) => ({
    id: `record-${i}`, purpose: `记录 ${i}`, tag: i === 22 ? '归档标签' : i % 2 ? '学习' : '工作',
    startedAt: Date.parse('2026-10-01T08:00:00+08:00') + i * 86400000,
    endedAt: Date.parse('2026-10-01T08:05:00+08:00') + i * 86400000,
    plannedMinutes: 5, actualMinutes: 5, result: 'completed', review: '已复盘',
  })),
  workItems: [{id: 'item', title: '需要调整的工作', important: true, urgent: true, done: false, createdAt: Date.now()}],
};
const server = spawn(process.env.PYTHON || 'python3', ['-u', '-c', `
import json, sys, tempfile
from pathlib import Path
from serve import create_server, Scheduler
with tempfile.TemporaryDirectory() as folder:
    server, _ = create_server(0, Scheduler(lambda *args: None), Path(folder) / 'pdca.json')
    server.data_store.write(json.loads(sys.stdin.read()), None)
    print('http://127.0.0.1:' + str(server.server_port), flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()
`], {cwd: __dirname, stdio: ['pipe', 'pipe', 'pipe']});
server.stdin.end(JSON.stringify(fixture));
let diagnostic = '';
server.stderr.on('data', value => { diagnostic += value; });
(async () => {
  let browser;
  try {
    const url = await new Promise((resolve, reject) => {
      const lines = readline.createInterface({input: server.stdout});
      lines.once('line', resolve);
      server.once('error', reject);
      server.once('exit', code => reject(Error(`Test server exited ${code}: ${diagnostic}`)));
    });
    browser = await chromium.launch({executablePath: process.env.CHROME_PATH || '/usr/bin/google-chrome', headless: true, args: ['--no-sandbox']});
    const context = await browser.newContext({viewport: {width: 1440, height: 1000}, timezoneId: 'Asia/Shanghai'});
    const page = await context.newPage(), errors = [];
    page.on('pageerror', e => errors.push(e.message));
    page.on('dialog', d => d.accept());
    const data = () => page.evaluate(async () => (await (await fetch('/api/data', {headers: {'X-PDCA-Token': window.PDCA_NATIVE_TOKEN}})).json()).data);
    const saved = () => page.waitForFunction(() => document.querySelector('#storageStatus').textContent.startsWith('已保存'));
    await page.goto(url + '/pdca/');
    await page.waitForFunction(() => !document.querySelector('#appContent').inert);
    assert.equal(await page.locator('#historyBody tr').count(), 10);
    await page.locator('#historyNext').click();
    assert.equal(await page.locator('#historyPage').textContent(), '2 / 3 页');
    await page.locator('#historyNext').click();
    assert.equal(await page.locator('#historyBody tr').count(), 3);
    await page.locator('#historyPageSize').selectOption('5');
    assert.equal(await page.locator('#historyPage').textContent(), '1 / 5 页');
    await page.locator('#historyFrom').fill('2026-10-05');
    await page.locator('#historyTo').fill('2026-10-08');
    await page.locator('#historyTag').selectOption('工作');
    assert.equal(await page.locator('#historyBody tr').count(), 2);
    assert.match(await page.locator('#historySummary').textContent(), /符合筛选 2 条/);
    await page.locator('#historyFrom').fill('2026-10-09');
    assert.match(await page.locator('#emptyHistory').textContent(), /开始日期不能晚于结束日期/);
    await page.locator('#historyReset').click();
    await page.locator('#historyTag').selectOption('归档标签');
    assert.equal(await page.locator('#historyBody tr').count(), 1);
    const download = page.waitForEvent('download');
    await page.locator('#exportJson').click();
    const fs = require('node:fs/promises');
    assert.equal(JSON.parse(await fs.readFile(await (await download).path(), 'utf8')).data.records.length, 23);
    await page.locator('#historyReset').click();
    for (let i = 0; i < 4; i++) await page.locator('#historyNext').click();
    for (let i = 0; i < 3; i++) { await page.locator('#historyBody [data-delete]').first().click(); await saved(); }
    assert.equal(await page.locator('#historyPage').textContent(), '4 / 4 页');
    assert.equal(await page.locator('#historyBody tr').count(), 5);

    await page.locator('[data-move-item="item"]').selectOption('1'); await saved();
    assert.equal(await page.locator('.q2 [data-work-id="item"]').count(), 1);
    assert.equal((await data()).workItems[0].urgent, false);
    await page.locator('[data-work-id="item"] .work-title').dragTo(page.locator('.q4'));
    await saved();
    assert.equal(await page.locator('.q4 [data-work-id="item"]').count(), 1);
    await page.reload(); await page.locator('.q4 [data-work-id="item"]').waitFor();
    await page.locator('[data-item-action="edit"]').click();
    await page.locator('#workItemTitle').fill('已调整标题');
    await page.locator('#workItemSave').click(); await saved();
    assert.equal((await data()).workItems[0].title, '已调整标题');

    await page.locator('#pomoStartBreak').click(); await saved();
    assert.equal((await data()).pomodoro.phase, 'break');
    assert.match(await page.locator('#pomoStatus').textContent(), /Break/);
    await page.reload(); await page.locator('#pomoStop').waitFor();
    assert.equal((await data()).pomodoro.phase, 'break');
    await page.locator('#pomoStop').click(); await saved();
    await page.locator('#pomoStart').click(); await saved();
    assert.equal((await data()).pomodoro.phase, 'work');
    await page.locator('#pomoStop').click(); await saved();
    await page.locator('#purpose').fill('测试复盘中的启动按钮');
    await page.locator('#startBtn').click(); await saved();
    await page.locator('#endEarly').click();
    await page.locator('#reviewPomoStartBreak').click(); await saved();
    assert.equal((await data()).pomodoro.phase, 'break');
    await page.locator('#reviewChoices [data-result="completed"]').click();
    await page.locator('#reviewText').fill('测试完成');
    await page.locator('#finishBtn').click(); await saved();
    await page.setViewportSize({width: 390, height: 844});
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    await page.locator('[data-move-item="item"]').selectOption('0'); await saved();
    assert.equal(await page.locator('.q1 [data-work-id="item"]').count(), 1);
    await page.locator('#historyPageSize').selectOption('5');
    await page.locator('#historyTag').selectOption('工作');
    assert.equal(await page.locator('#historyPage').textContent(), '1 / 2 页');
    if (process.env.PDCA_SCREENSHOT_PREFIX) {
      await page.locator('#historyFrom').locator('xpath=ancestor::section[1]').screenshot({path: process.env.PDCA_SCREENSHOT_PREFIX + '-history.png'});
      await page.locator('#workQuadrants').screenshot({path: process.env.PDCA_SCREENSHOT_PREFIX + '-work.png'});
    }
    assert.deepEqual(errors, []);
    console.log('PDCA browser checks passed: Work/Break starts, review controls, pagination, date/tag filters, full backup, last-page deletion, dropdown and drag moves, edit, refresh persistence and mobile layout.');
  } finally {
    if (browser) await browser.close();
    server.kill('SIGINT');
    await new Promise(resolve => server.exitCode !== null ? resolve() : server.once('exit', resolve));
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
