import { computed, ref } from 'vue'
import { ApiError, readData, writeData } from './api'
import { defaults, legacyData, normalizeDb } from './data'
import { fmtComment } from './time'

export function useStorage() {
  const db = ref(defaults())
  const ready = ref(false)
  const revision = ref<string | null>(null)
  const dirty = ref(false)
  const conflict = ref(false)
  const pending = ref(0)
  const message = ref('正在读取本机数据…')
  const legacy = ref(legacyData())
  const blocked = computed(() => !ready.value || pending.value > 0)
  let saveQueue: Promise<boolean> = Promise.resolve(true)
  let afterSave = () => {}

  async function load() {
    if (pending.value) return false
    if (
      dirty.value &&
      !confirm(
        '本页有尚未保存的数据。请先导出 JSON；继续读取会丢弃本页未保存的修改。确定继续？',
      )
    )
      return false
    ready.value = false
    message.value = '正在读取本机数据…'
    legacy.value = legacyData()
    if (!window.PDCA_NATIVE_TOKEN) {
      message.value =
        '请运行 ./start.sh 并打开 http://127.0.0.1:8765；直接打开 HTML 无法读写本机文件。'
      return false
    }
    try {
      const saved = await readData()
      db.value = normalizeDb(saved.data ?? legacy.value ?? defaults())
      revision.value = saved.revision
      ready.value = true
      dirty.value = false
      conflict.value = false
      if (saved.data === null && !(await save())) return false
      message.value =
        saved.data === null && legacy.value
          ? '旧浏览器数据已迁移到本机文件；原浏览器数据保留。'
          : '数据已读取 · 本机文件存储'
      return true
    } catch (e) {
      ready.value = false
      message.value = `读取失败：${(e as Error).message}。请检查本地服务；现有文件不会被覆盖。`
      return false
    }
  }

  function save(): Promise<boolean> {
    if (!ready.value || conflict.value) {
      dirty.value = true
      message.value =
        '尚未保存：请连接本地服务，或先导出本页 JSON 后重新读取数据。'
      return Promise.resolve(false)
    }
    const snapshot = JSON.stringify(db.value)
    dirty.value = true
    pending.value++
    message.value = '正在保存到本机文件…'
    const operation = saveQueue.then(async () => {
      try {
        if (conflict.value)
          throw new Error('数据版本冲突，请先导出 JSON 后重新读取。')
        const saved = await writeData(JSON.parse(snapshot), revision.value)
        revision.value = saved.revision
        dirty.value = JSON.stringify(db.value) !== snapshot
        afterSave()
        return true
      } catch (e) {
        if (e instanceof ApiError && e.status === 409) conflict.value = true
        dirty.value = true
        message.value = `尚未保存：${(e as Error).message}。本页数据仍在，可导出 JSON。`
        return false
      } finally {
        pending.value--
        if (!pending.value && !dirty.value)
          message.value = '已保存到本机文件 · ' + fmtComment(Date.now())
      }
    })
    saveQueue = operation.catch(() => false)
    return operation
  }
  return {
    db,
    ready,
    dirty,
    conflict,
    pending,
    blocked,
    message,
    legacy,
    load,
    save,
    onSaved(callback: () => void) {
      afterSave = callback
    },
  }
}
export type Storage = ReturnType<typeof useStorage>
