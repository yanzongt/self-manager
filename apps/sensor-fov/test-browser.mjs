import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { createInterface } from 'node:readline'
import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { chromium } from 'playwright-core'

// The combined service uses temporary data; personal files and browser storage are untouched.
const server = spawn(process.env.PYTHON || 'python3', ['-u', '-c', `
import tempfile
from pathlib import Path
from serve import create_server
with tempfile.TemporaryDirectory() as folder:
    server, _ = create_server(0, data_path=Path(folder) / 'pdca.json')
    print('http://127.0.0.1:' + str(server.server_port), flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()
`], { cwd: resolve(import.meta.dirname, '../..'), stdio: ['ignore', 'pipe', 'pipe'] })
let diagnostic = '', browser
server.stderr.on('data', value => diagnostic += value)
try {
  const origin = await new Promise((resolve, reject) => {
    createInterface({ input: server.stdout }).once('line', resolve)
    server.once('error', reject)
    server.once('exit', code => reject(new Error(`Test server exited ${code}: ${diagnostic}`)))
  })
  browser = await chromium.launch({
    executablePath: process.env.CHROME_PATH || '/usr/bin/google-chrome', headless: true,
    args: ['--no-sandbox', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'],
  })
  const page = await browser.newPage({ viewport: { width: 1440, height: 1100 }, acceptDownloads: true })
  const errors = [], external = []
  page.on('pageerror', error => errors.push(error.message))
  page.on('request', request => { if (request.url().startsWith('http') && !request.url().startsWith(origin + '/')) external.push(request.url()) })
  page.on('dialog', dialog => dialog.accept())
  await page.goto(origin + '/')
  assert.equal(await page.locator('.tools .tool').count(), 5)
  assert.equal(await page.locator('.count').textContent(), '05')
  await page.locator('.tool[href="/sensor-fov/"]').click()
  await page.locator('.canvas-host canvas').waitFor()
  const stored = () => page.evaluate(() => JSON.parse(localStorage.getItem('sensor-fov-config-v1')))
  const waitSensors = count => page.waitForFunction(count => JSON.parse(localStorage.getItem('sensor-fov-config-v1'))?.sensors.length === count, count)
  await waitSensors(2)
  assert.equal(await page.locator('.render-error').count(), 0)
  assert(await page.locator('.canvas-host canvas').evaluate(canvas => !!canvas.getContext('webgl2')))
  assert(await page.locator('.canvas-host canvas').evaluate(canvas => canvas.toDataURL().length > 10000))
  assert.equal(await page.evaluate(() => getComputedStyle(document.body).backgroundColor), 'rgb(246, 245, 240)')
  assert.equal(await page.getByRole('link', { name: '← 返回主页' }).getAttribute('href'), '/')

  // The toggle must change the actual 3D render and restore it without moving the view.
  await page.getByRole('button', { name: '适配视图', exact: true }).click()
  const canvasImage = () => page.locator('.canvas-host canvas').evaluate(canvas => canvas.toDataURL())
  const withLabels = await canvasImage()
  await page.getByRole('button', { name: '隐藏文字', exact: true }).click()
  assert.notEqual(await canvasImage(), withLabels)
  await page.getByRole('button', { name: '显示文字', exact: true }).click()
  assert.equal(await canvasImage(), withLabels)
  await page.getByRole('button', { name: '隐藏文字', exact: true }).click()

  await page.getByRole('spinbutton', { name: 'X', exact: true }).fill('0.42')
  await page.waitForFunction(() => JSON.parse(localStorage.getItem('sensor-fov-config-v1'))?.sensors[0].pos[0] === .42)
  assert(await page.getByRole('button', { name: '显示文字', exact: true }).isVisible())
  const editedHidden = await canvasImage()
  await page.getByRole('button', { name: '显示文字', exact: true }).click()
  assert.notEqual(await canvasImage(), editedHidden)
  await page.getByRole('button', { name: '隐藏文字', exact: true }).click()
  assert.equal(await canvasImage(), editedHidden)
  await page.reload(); await page.locator('.canvas-host canvas').waitFor()
  assert.equal(await page.getByRole('spinbutton', { name: 'X', exact: true }).inputValue(), '0.42')
  for (const name of ['俯视 XY', '前视 YZ', '侧视 XZ', '3D']) {
    const button = page.getByRole('button', { name, exact: true }); await button.click()
    assert.match(await button.getAttribute('class'), /active/)
  }
  await page.getByLabel('新增传感器类型').selectOption('camera')
  await page.getByRole('button', { name: '＋ 添加', exact: true }).click(); await waitSensors(3)
  await page.getByRole('button', { name: '复制', exact: true }).click(); await waitSensors(4)
  await page.getByRole('button', { name: '删除', exact: true }).click(); await waitSensors(3)
  await page.getByLabel('新增传感器类型').selectOption('ultrasonic')
  await page.getByRole('button', { name: '＋ 添加', exact: true }).click(); await waitSensors(4)
  assert.equal((await stored()).sensors.at(-1).type, 'ultrasonic')
  await page.getByLabel('显示传感器类别').selectOption('lidar')
  await page.waitForFunction(() => JSON.parse(localStorage.getItem('sensor-fov-config-v1')).sensors.filter(s => s.visible).length === 2)
  await page.getByLabel('显示传感器类别').selectOption('all')
  await page.waitForFunction(() => JSON.parse(localStorage.getItem('sensor-fov-config-v1')).sensors.every(s => s.visible))

  const before = await stored()
  const range = page.getByRole('spinbutton', { name: '前向深度 / m', exact: true })
  await range.fill('0')
  await page.locator('.error').waitFor()
  assert.equal((await stored()).sensors.at(-1).range, before.sensors.at(-1).range)
  assert(await page.getByRole('button', { name: '导出 JSON ↗', exact: true }).isDisabled())
  await range.fill('2.5')
  await page.waitForFunction(() => JSON.parse(localStorage.getItem('sensor-fov-config-v1')).sensors.at(-1).range === 2.5)
  assert.equal(await page.locator('.error').count(), 0)

  const download = page.waitForEvent('download')
  await page.getByRole('button', { name: '导出 JSON ↗', exact: true }).click()
  const config = JSON.parse(await readFile(await (await download).path(), 'utf8'))
  assert.equal(config.sensors.length, 4)
  const fileInput = page.locator('input[type=file]')
  await fileInput.setInputFiles({ name: 'invalid.json', mimeType: 'application/json', buffer: Buffer.from('{"version":2}') })
  assert.match(await page.locator('.notice').textContent(), /导入失败/)
  assert.equal((await stored()).sensors.length, 4)
  config.sensors[0].name = '导入布局'
  await fileInput.setInputFiles({ name: 'valid.json', mimeType: 'application/json', buffer: Buffer.from(JSON.stringify(config)) })
  await page.waitForFunction(() => JSON.parse(localStorage.getItem('sensor-fov-config-v1')).sensors[0].name === '导入布局')
  const png = page.waitForEvent('download')
  await page.getByRole('button', { name: '截图 ↓', exact: true }).click()
  const pngBytes = await readFile(await (await png).path())
  assert.equal(pngBytes.subarray(1,4).toString(), 'PNG')

  await page.getByRole('button', { name: '↺ 恢复默认双激光布局', exact: true }).click(); await waitSensors(2)
  await page.getByRole('button', { name: '适配视图', exact: true }).click()
  await page.locator('.sidebar').evaluate(node => node.scrollTop = 0)
  if (process.env.FOV_SCREENSHOT_PREFIX) await page.screenshot({ path: process.env.FOV_SCREENSHOT_PREFIX + '-desktop.png', fullPage: true })
  await page.setViewportSize({ width: 390, height: 844 })
  await page.getByRole('button', { name: '适配视图', exact: true }).click()
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth))
  if (process.env.FOV_SCREENSHOT_PREFIX) await page.screenshot({ path: process.env.FOV_SCREENSHOT_PREFIX + '-mobile.png', fullPage: true })
  assert.deepEqual(errors, [])
  assert.deepEqual(external, [])
  console.log('FOV browser checks passed: homepage entry, local WebGL rendering, shared theme, edit/reload, sensor operations, views/filters, label visibility through edits, validation, JSON import/export, PNG and mobile layout.')
} finally {
  await browser?.close()
  server.kill('SIGINT')
  await new Promise(resolve => server.exitCode !== null ? resolve() : server.once('exit', resolve))
}
