<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { usePdca } from '../usePdca'
import type { WorkItem } from '../types'
import { fmtComment } from '../time'
const { storage, planSelection, toast } = usePdca()
const { db } = storage
const groups = [
  { important: true, urgent: true, title: '重要 · 紧急', hint: '优先处理' },
  { important: true, urgent: false, title: '重要 · 不紧急', hint: '安排时间' },
  {
    important: false,
    urgent: true,
    title: '不重要 · 紧急',
    hint: '尽量委托或集中处理',
  },
  {
    important: false,
    urgent: false,
    title: '不重要 · 不紧急',
    hint: '减少投入',
  },
]
const title = ref(''),
  important = ref(true),
  urgent = ref(true),
  editing = ref<string | null>(null),
  showDone = ref(false)
const dragged = ref<string | null>(null),
  over = ref<number | null>(null)
const titleInput = ref<HTMLInputElement | null>(null)
const columns = computed(() =>
  groups.map((group) => ({
    ...group,
    items: db.value.workItems.filter(
      (item) =>
        item.important === group.important &&
        item.urgent === group.urgent &&
        (showDone.value || !item.done),
    ),
  })),
)
function reset() {
  title.value = ''
  important.value = true
  urgent.value = true
  editing.value = null
}
watch(() => db.value, reset)
async function submit() {
  if (!title.value.trim() || title.value.trim().length > 300) {
    toast('事项标题不能为空且最多300字符')
    return
  }
  const existing = db.value.workItems.find((item) => item.id === editing.value)
  const now = Date.now()
  const item: WorkItem = {
    ...existing,
    id: existing?.id || crypto.randomUUID(),
    title: title.value.trim(),
    important: important.value,
    urgent: urgent.value,
    done: existing?.done || false,
    createdAt: existing?.createdAt || now,
    updatedAt: now,
  }
  db.value.workItems = existing
    ? db.value.workItems.map((current) =>
        current.id === item.id ? item : current,
      )
    : [...db.value.workItems, item]
  if (await storage.save()) {
    reset()
    toast(existing ? '事项已更新' : '事项已添加')
  }
}
async function move(id: string, index: number) {
  const item = db.value.workItems.find((item) => item.id === id),
    group = groups[index]
  if (
    !item ||
    !group ||
    (item.important === group.important && item.urgent === group.urgent)
  )
    return
  Object.assign(item, {
    important: group.important,
    urgent: group.urgent,
    updatedAt: Date.now(),
  })
  if (editing.value === id) {
    important.value = group.important
    urgent.value = group.urgent
  }
  if (await storage.save()) toast('事项已移至「' + group.title + '」')
}
async function done(item: WorkItem) {
  item.done = !item.done
  item.completedAt = item.done ? Date.now() : null
  item.updatedAt = Date.now()
  if (await storage.save()) toast(item.done ? '事项已完成' : '事项已恢复')
}
async function edit(item: WorkItem) {
  editing.value = item.id
  title.value = item.title
  important.value = item.important
  urgent.value = item.urgent
  await nextTick()
  titleInput.value?.focus()
}
function plan(item: WorkItem) {
  if (db.value.active || item.done) return
  planSelection.value = { ...item }
  toast('已关联事项，可设置时长并开始工作')
}
async function remove(item: WorkItem) {
  if (!confirm('确认删除这个工作事项？已保存的会话记录仍会保留。')) return
  db.value.workItems = db.value.workItems.filter(
    (current) => current.id !== item.id,
  )
  if ((await storage.save()) && editing.value === item.id) reset()
}
function drag(event: DragEvent, id: string) {
  if ((event.target as HTMLElement).closest('button, input, select')) {
    event.preventDefault()
    return
  }
  dragged.value = id
  event.dataTransfer?.setData('text/plain', id)
  if (event.dataTransfer) event.dataTransfer.effectAllowed = 'move'
}
function clearDrag() {
  dragged.value = null
  over.value = null
}
async function drop(index: number) {
  const id = dragged.value
  clearDrag()
  if (id) await move(id, index)
}
</script>
<template>
  <section class="sm-panel panel work-panel">
    <h2>Work items / 四象限</h2>
    <form id="workItemForm" class="work-form" @submit.prevent="submit">
      <input
        id="workItemTitle"
        ref="titleInput"
        v-model="title"
        class="sm-control control"
        maxlength="300"
        required
        placeholder="添加一个工作事项…"
        aria-label="工作事项标题"
      />
      <label class="check-label" for="workImportant">
        <input id="workImportant" v-model="important" type="checkbox" />
        重要
      </label>
      <label class="check-label" for="workUrgent">
        <input id="workUrgent" v-model="urgent" type="checkbox" />
        紧急
      </label>
      <button id="workItemSave" class="sm-button small-btn" type="submit">
        {{ editing ? '保存修改' : '添加事项' }}
      </button>
      <button
        id="workItemCancel"
        class="sm-button small-btn"
        type="button"
        :hidden="!editing"
        @click="reset"
      >
        取消编辑
      </button>
    </form>
    <label class="check-label" for="showDoneItems">
      <input id="showDoneItems" v-model="showDone" type="checkbox" />
      显示已完成事项
    </label>
    <p class="hint">
      可拖动事项标题到其他象限，或使用卡片内的「移至象限」调整分类；点击「编辑」修改标题。
    </p>
    <div id="workQuadrants" class="quadrants">
      <section
        v-for="(group, index) in columns"
        :key="index"
        class="quadrant"
        :class="['q' + (index + 1), { 'drag-over': over === index }]"
        :data-quadrant="index"
        @dragover.prevent="over = dragged ? index : null"
        @dragleave="over = null"
        @drop.prevent="drop(index)"
      >
        <h3>
          {{ group.title }}
          <span class="hint">{{ group.items.length }}</span>
        </h3>
        <div class="hint">{{ group.hint }}</div>
        <article
          v-for="item in group.items"
          :key="item.id"
          class="work-item"
          :class="{ done: item.done }"
          draggable="true"
          :data-work-id="item.id"
          @dragstart="drag($event, item.id)"
          @dragend="clearDrag"
        >
          <div class="work-title">{{ item.title }}</div>
          <time>
            {{ fmtComment(item.createdAt) }}{{ item.done ? ' · 已完成' : '' }}
          </time>
          <label class="work-move">
            移至象限
            <select
              class="sm-control control"
              :data-move-item="item.id"
              :aria-label="item.title + '：移至象限'"
              :value="index"
              @change="
                move(
                  item.id,
                  Number(($event.target as HTMLSelectElement).value),
                )
              "
            >
              <option
                v-for="(target, targetIndex) in groups"
                :key="targetIndex"
                :value="targetIndex"
              >
                {{ target.title }}
              </option>
            </select>
          </label>
          <div class="actions">
            <button
              class="sm-button small-btn"
              data-item-action="done"
              :data-item-id="item.id"
              @click="done(item)"
            >
              {{ item.done ? '恢复待办' : '标记完成' }}
            </button>
            <button
              class="sm-button small-btn"
              data-item-action="edit"
              :data-item-id="item.id"
              @click="edit(item)"
            >
              编辑
            </button>
            <button
              class="sm-button small-btn"
              data-item-action="plan"
              :data-item-id="item.id"
              :disabled="!!db.active || item.done"
              @click="plan(item)"
            >
              用于本次工作
            </button>
            <button
              class="delete"
              data-item-action="delete"
              :data-item-id="item.id"
              aria-label="删除工作事项"
              @click="remove(item)"
            >
              删除
            </button>
          </div>
        </article>
        <p v-if="!group.items.length" class="work-empty">
          暂无事项，可拖动事项到这里
        </p>
      </section>
    </div>
  </section>
</template>
