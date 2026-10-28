<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { usePdca } from '../usePdca'
import { day, fmt, formatMin, duration } from '../time'
import { exportJson, exportTxt, exportRecord, resultLabels } from '../exports'
import CommentsList from './CommentsList.vue'
const { storage, restore, toast } = usePdca()
const { db } = storage
const from = ref(''),
  to = ref(''),
  tag = ref(''),
  size = ref(10),
  requestedPage = ref(1)
const importInput = ref<HTMLInputElement | null>(null)
const tags = computed(() => [
  ...new Set([...db.value.tags, ...db.value.records.map((r) => r.tag)]),
])
const records = computed(() =>
  db.value.records
    .filter(
      (r) =>
        (!from.value || day(r.startedAt) >= from.value) &&
        (!to.value || day(r.startedAt) <= to.value) &&
        (!tag.value || r.tag === tag.value),
    )
    .sort((a, b) => b.startedAt - a.startedAt),
)
const pages = computed(() =>
  Math.max(1, Math.ceil(records.value.length / size.value)),
)
const page = computed(() =>
  Math.max(1, Math.min(requestedPage.value, pages.value)),
)
const offset = computed(() => (page.value - 1) * size.value)
const visible = computed(() =>
  records.value.slice(offset.value, offset.value + size.value),
)
const empty = computed(() =>
  from.value && to.value && from.value > to.value
    ? '开始日期不能晚于结束日期，请调整筛选。'
    : db.value.records.length
      ? '没有符合筛选条件的记录。'
      : '还没有历史记录，开始你的第一轮 PDCA。',
)
watch([from, to, tag, size], () => (requestedPage.value = 1))
watch(
  pages,
  (value) => (requestedPage.value = Math.min(requestedPage.value, value)),
)
watch(tags, (values) => {
  if (!values.includes(tag.value)) tag.value = ''
})
function reset() {
  from.value = ''
  to.value = ''
  tag.value = ''
  requestedPage.value = 1
}
async function remove(id: string) {
  if (!confirm('确认永久删除这条记录？建议先备份。')) return
  db.value.records = db.value.records.filter((record) => record.id !== id)
  await storage.save()
}
async function importFile(event: Event) {
  const input = event.target as HTMLInputElement,
    file = input.files?.[0]
  input.value = ''
  if (!file) return
  try {
    const backup = JSON.parse(await file.text())
    await restore(backup.data)
  } catch (e) {
    toast('无法导入：' + (e as Error).message)
  }
}
</script>
<template>
  <section class="sm-panel panel">
    <div class="history-actions">
      <h2>03 / 历史记录</h2>
      <div class="actions">
        <button
          id="exportTxt"
          class="sm-button small-btn"
          @click="exportTxt(db)"
        >
          导出 TXT
        </button>
        <button
          id="exportJson"
          class="sm-button small-btn"
          @click="exportJson(db)"
        >
          备份 JSON
        </button>
        <button
          id="importJson"
          class="sm-button small-btn"
          @click="importInput?.click()"
        >
          恢复 JSON
        </button>
        <input
          id="importInput"
          ref="importInput"
          type="file"
          accept="application/json,.json"
          hidden
          @change="importFile"
        />
      </div>
    </div>
    <div class="history-filters">
      <label>
        开始日期
        <input
          id="historyFrom"
          v-model="from"
          type="date"
          class="sm-control control"
        />
      </label>
      <label>
        结束日期
        <input
          id="historyTo"
          v-model="to"
          type="date"
          class="sm-control control"
        />
      </label>
      <label>
        项目标签
        <select id="historyTag" v-model="tag" class="sm-control control">
          <option value="">全部标签</option>
          <option v-for="value in tags" :key="value" :value="value">
            {{ value }}
          </option>
        </select>
      </label>
      <label>
        每页条数
        <select
          id="historyPageSize"
          v-model.number="size"
          class="sm-control control"
        >
          <option v-for="value in [5, 10, 20, 50]" :key="value" :value="value">
            {{ value }} 条
          </option>
        </select>
      </label>
      <button
        id="historyReset"
        class="sm-button small-btn"
        type="button"
        @click="reset"
      >
        清除筛选
      </button>
    </div>
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>开始时间</th>
            <th>目的 / 复盘</th>
            <th>项目</th>
            <th>计划 / 实际</th>
            <th>结果</th>
            <th></th>
          </tr>
        </thead>
        <tbody id="historyBody">
          <tr v-for="record in visible" :key="record.id">
            <td style="white-space: nowrap">{{ fmt(record.startedAt) }}</td>
            <td>
              <div class="purpose">{{ record.purpose }}</div>
              <small>{{ record.review }}</small>
              <small v-if="record.extensions?.length">
                中途复盘 {{ record.extensions.length }} 次
              </small>
              <CommentsList :session="record" />
              <small v-if="record.workItemTitle">
                Work item：{{ record.workItemTitle }}
              </small>
            </td>
            <td>
              <span class="tag">{{ record.tag }}</span>
            </td>
            <td>
              {{ formatMin(record.plannedMinutes) }} /
              {{ formatMin(duration(record)) }} 分钟
            </td>
            <td>
              <span
                class="status"
                :class="{
                  partial: record.result === 'partial',
                  no: record.result === 'not_completed',
                }"
              >
                {{ resultLabels[record.result] || '未知' }}
              </span>
            </td>
            <td>
              <div class="actions">
                <button
                  type="button"
                  class="sm-button small-btn"
                  :data-export-record="record.id"
                  @click="exportRecord(record)"
                >
                  导出记录 TXT
                </button>
                <button
                  class="delete"
                  :data-delete="record.id"
                  title="删除该记录"
                  aria-label="删除记录"
                  @click="remove(record.id)"
                >
                  ✕
                </button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <div id="emptyHistory" class="empty" :hidden="records.length > 0">
      {{ empty }}
    </div>
    <nav class="history-pagination" aria-label="历史记录分页">
      <span id="historySummary" class="hint" role="status" aria-live="polite">
        共 {{ db.records.length }} 条，符合筛选 {{ records.length }} 条{{
          records.length
            ? `，显示第 ${offset + 1}–${offset + visible.length} 条`
            : ''
        }}
      </span>
      <div class="actions">
        <button
          id="historyPrev"
          class="sm-button small-btn"
          type="button"
          :disabled="page <= 1"
          @click="requestedPage = page - 1"
        >
          上一页
        </button>
        <span id="historyPage" class="hint">{{ page }} / {{ pages }} 页</span>
        <button
          id="historyNext"
          class="sm-button small-btn"
          type="button"
          :disabled="page >= pages"
          @click="requestedPage = page + 1"
        >
          下一页
        </button>
      </div>
    </nav>
    <p class="hint">
      日期范围包含起止两天，按会话开始日期筛选。导出 TXT 和备份 JSON
      仍包含全部记录。
    </p>
    <p class="hint">
      计时以真实时间戳为准，刷新页面后仍可恢复进行中的会话；记录以开始日期归属统计。数据保存到本机文件，建议定期备份
      JSON。
    </p>
  </section>
</template>
