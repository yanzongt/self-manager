import { createServer } from 'node:http'
import { createReadStream, existsSync, statSync } from 'node:fs'
import { resolve, extname, sep } from 'node:path'
import { fileURLToPath } from 'node:url'
import { spawn } from 'node:child_process'

const root = fileURLToPath(new URL('./dist/', import.meta.url))
const [host = '127.0.0.1', portText = '8080', open = 'yes'] = process.argv.slice(2)
const port = Number(portText)
if (!Number.isInteger(port) || port < 1 || port > 65535) {
  console.error('端口必须为 1 ～ 65535 的整数'); process.exit(1)
}
if (!existsSync(resolve(root, 'index.html'))) {
  console.error('缺少 web/dist/index.html，请先运行 ./serve.sh 构建。'); process.exit(1)
}
const types = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8', '.json': 'application/json', '.png': 'image/png', '.svg': 'image/svg+xml', '.ico': 'image/x-icon' }
const server = createServer((req, res) => {
  if (req.method !== 'GET' && req.method !== 'HEAD') { res.writeHead(405, { Allow: 'GET, HEAD' }).end(); return }
  let path
  try { path = decodeURIComponent(new URL(req.url, 'http://localhost').pathname) }
  catch { res.writeHead(400).end('Bad request'); return }
  const file = resolve(root, `.${path === '/' ? '/index.html' : path}`)
  if (!file.startsWith(root.endsWith(sep) ? root : root + sep) || file.includes('\0')) { res.writeHead(403).end('Forbidden'); return }
  let stat
  try { stat = statSync(file) } catch { res.writeHead(404).end('Not found'); return }
  if (!stat.isFile()) { res.writeHead(404).end('Not found'); return }
  res.writeHead(200, { 'Content-Type': types[extname(file)] ?? 'application/octet-stream', 'Content-Length': stat.size, 'Cache-Control': 'no-cache' })
  if (req.method === 'HEAD') { res.end(); return }
  const stream = createReadStream(file)
  stream.on('error', () => res.destroy())
  stream.pipe(res)
})
server.on('error', e => { console.error(`HTTP 服务启动失败：${e.message}`); process.exitCode = 1 })
server.listen(port, host, () => {
  const urlHost = ['0.0.0.0', '::'].includes(host) ? '127.0.0.1' : host
  const url = `http://${urlHost.includes(':') ? `[${urlHost}]` : urlHost}:${port}/`
  console.log(`Sensor FOV: ${url}\n监听地址: ${host}:${port}\n静态目录: ${root}\n按 Ctrl+C 停止。`)
  if (open === 'yes' && (process.env.DISPLAY || process.env.WAYLAND_DISPLAY || process.platform === 'darwin' || process.platform === 'win32')) {
    const command = process.platform === 'darwin' ? 'open' : process.platform === 'win32' ? 'explorer.exe' : 'xdg-open'
    const browser = spawn(command, [url], { stdio: 'ignore' })
    browser.on('error', () => console.log(`请手动在浏览器打开 ${url}`))
    browser.unref()
  } else if (open === 'yes') console.log('当前无图形桌面，请在浏览器手动打开或通过 SSH 转发端口。')
})
for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, () => { server.close(); server.closeAllConnections() })
