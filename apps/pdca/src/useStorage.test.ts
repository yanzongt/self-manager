import { beforeEach, afterEach, expect, it, vi } from 'vitest'
import { useStorage } from './useStorage'
import { defaults, LEGACY_KEY } from './data'
import type { Database } from './types'
let disk: Database | null,
  revision: string | null,
  failWrite: boolean,
  unavailable: boolean,
  writes: number,
  legacy: Database | null
beforeEach(() => {
  disk = null
  revision = null
  failWrite = false
  unavailable = false
  writes = 0
  legacy = null
  vi.stubGlobal('window', { PDCA_NATIVE_TOKEN: 'token' })
  vi.stubGlobal('confirm', () => true)
  vi.stubGlobal('localStorage', {
    getItem: (key: string) =>
      key === LEGACY_KEY && legacy ? JSON.stringify(legacy) : null,
  })
  vi.stubGlobal(
    'fetch',
    vi.fn(async (_path, options) => {
      if (unavailable) throw new Error('服务不可用')
      if (options.method === 'GET')
        return Response.json({ data: disk, revision })
      const payload = JSON.parse(options.body)
      writes++
      if (failWrite)
        return Response.json({ error: '磁盘写入失败' }, { status: 500 })
      if (payload.revision !== revision)
        return Response.json({ error: '数据已被其他页面修改' }, { status: 409 })
      disk = payload.data
      revision = String(Number(revision || 0) + 1)
      return Response.json({ revision })
    }),
  )
})
afterEach(() => vi.unstubAllGlobals())
it('migrates the old browser key only when disk is empty; disk stays authoritative', async () => {
  legacy = { ...defaults(), tags: ['旧记录'] }
  const storage = useStorage()
  expect(await storage.load()).toBe(true)
  expect(disk?.tags).toEqual(['旧记录'])
  expect(storage.message.value).toContain('迁移')
  disk = { ...defaults(), tags: ['磁盘数据'] }
  await storage.load()
  expect(storage.db.value.tags).toEqual(['磁盘数据'])
  expect(writes).toBe(1)
})
it('preserves unsaved changes on failure and retries without rereading the disk', async () => {
  const storage = useStorage()
  await storage.load()
  failWrite = true
  storage.db.value.tags.push('尚未保存')
  expect(await storage.save()).toBe(false)
  expect(disk?.tags).not.toContain('尚未保存')
  expect(storage.db.value.tags).toContain('尚未保存')
  expect(storage.dirty.value).toBe(true)
  expect(storage.blocked.value).toBe(false)
  failWrite = false
  expect(await storage.save()).toBe(true)
  expect(disk?.tags).toContain('尚未保存')
  expect(storage.dirty.value).toBe(false)
})
it('serializes snapshots with the latest revision, including edits made during a save', async () => {
  const storage = useStorage()
  await storage.load()
  storage.db.value.tags.push('第一项')
  const first = storage.save()
  expect(storage.blocked.value).toBe(true)
  expect(await storage.load()).toBe(false)
  storage.db.value.tags.push('第二项')
  const second = storage.save()
  expect(await first).toBe(true)
  expect(await second).toBe(true)
  expect(disk?.tags.slice(-2)).toEqual(['第一项', '第二项'])
  expect(storage.pending.value).toBe(0)
  expect(storage.dirty.value).toBe(false)
})
it('rejects a stale tab and keeps its changes available until explicitly reloaded', async () => {
  const first = useStorage()
  await first.load()
  const stale = useStorage()
  await stale.load()
  first.db.value.tags.push('新数据')
  await first.save()
  stale.db.value.tags.push('冲突数据')
  expect(await stale.save()).toBe(false)
  expect(stale.conflict.value).toBe(true)
  expect(stale.db.value.tags).toContain('冲突数据')
  expect(disk?.tags).not.toContain('冲突数据')
  const previousWrites = writes
  expect(await stale.save()).toBe(false)
  expect(writes).toBe(previousWrites)
  await stale.load()
  expect(stale.db.value.tags).toContain('新数据')
  expect(stale.conflict.value).toBe(false)
})
it('never writes defaults over an unreadable or unavailable file', async () => {
  unavailable = true
  const storage = useStorage()
  expect(await storage.load()).toBe(false)
  expect(storage.blocked.value).toBe(true)
  expect(writes).toBe(0)
  expect(storage.message.value).toContain('读取失败')
  unavailable = false
  disk = {} as Database
  expect(await storage.load()).toBe(false)
  expect(writes).toBe(0)
})
