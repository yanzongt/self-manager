<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { usePdca } from '../usePdca'
import { clock, currentTotal, deadline, fmt } from '../time'
import CommentsList from './CommentsList.vue'
import PomodoroPanel from './PomodoroPanel.vue'
const { storage, session, notifications, now, planSelection, toast } = usePdca()
const { db } = storage
const { message: notifyMessage, nativeReady } = notifications
const purpose = ref(''),
  tag = ref(''),
  minutes = ref(30),
  itemId = ref(''),
  comment = ref('')
const purposeInput = ref<HTMLTextAreaElement | null>(null)
const active = computed(() => db.value.active)
const left = computed(() =>
  active.value ? deadline(active.value) - now.value : 0,
)
const progress = computed(() =>
  active.value
    ? Math.min(
        100,
        Math.max(
          0,
          ((now.value - active.value.startedAt) /
            (currentTotal(active.value) * 60000)) *
            100,
        ),
      )
    : 0,
)
const items = computed(() =>
  db.value.workItems.filter(
    (item) =>
      !item.done || item.id === (active.value?.workItemId || itemId.value),
  ),
)
watch(
  () => db.value.tags,
  (tags) => {
    if (!tags.includes(tag.value)) tag.value = tags[0] || ''
  },
  { immediate: true },
)
watch(planSelection, async (item) => {
  if (!item || active.value) return
  itemId.value = item.id
  purpose.value = item.title
  await nextTick()
  purposeInput.value?.focus()
})
watch(active, (value) => {
  if (value) itemId.value = value.workItemId || ''
  else comment.value = ''
})
async function newTag() {
  const answer = prompt('输入新项目标签（不超过20个字符）')
  if (answer === null) return
  const value = answer.trim()
  if (!value || value.length > 20) {
    toast('标签不能为空且最多20字符')
    return
  }
  if (!db.value.tags.includes(value)) db.value.tags.push(value)
  if (await storage.save()) tag.value = value
}
function selectItem() {
  const item = db.value.workItems.find((item) => item.id === itemId.value)
  if (item && !active.value) purpose.value = item.title
}
async function addComment() {
  const value = comment.value
  comment.value = ''
  await session.addComment(value)
}
</script>
<template>
  <aside class="sm-panel panel">
    <h2>01 / 计划一次行动</h2>
    <form
      id="startForm"
      @submit.prevent="session.start(purpose, tag, Number(minutes), itemId)"
    >
      <div class="field">
        <label for="purpose">本次目的</label>
        <textarea
          id="purpose"
          ref="purposeInput"
          v-model="purpose"
          class="sm-control control"
          rows="3"
          placeholder="例如：查阅 FastLIO2 的技术资料"
          required
          maxlength="300"
          :disabled="!!active"
        ></textarea>
      </div>
      <div class="field">
        <label for="tag">项目标签</label>
        <div class="tag-row">
          <select
            id="tag"
            v-model="tag"
            class="sm-control control"
            required
            :disabled="!!active"
          >
            <option v-for="value in db.tags" :key="value" :value="value">
              {{ value }}
            </option>
          </select>
          <button
            id="newTag"
            type="button"
            class="sm-button small-btn"
            :disabled="!!active"
            @click="newTag"
          >
            ＋ 新标签
          </button>
        </div>
      </div>
      <div class="field">
        <label for="minutes">计划时长（分钟）</label>
        <div id="presets" class="preset">
          <button
            v-for="value in [10, 20, 30, 60]"
            :key="value"
            type="button"
            :data-min="value"
            :class="{ active: minutes === value }"
            :disabled="!!active"
            @click="minutes = value"
          >
            {{ value }}
          </button>
        </div>
        <input
          id="minutes"
          v-model.number="minutes"
          class="sm-control control spaced"
          type="number"
          min="1"
          max="1440"
          step="1"
          required
          :disabled="!!active"
        />
      </div>
      <div class="field">
        <label for="workItemSelect">关联 Work item（可选）</label>
        <select
          id="workItemSelect"
          v-model="itemId"
          class="sm-control control"
          :disabled="!!active"
          @change="selectItem"
        >
          <option value="">不关联任务</option>
          <option v-for="item in items" :key="item.id" :value="item.id">
            {{ item.title }}
          </option>
        </select>
      </div>
      <button
        id="startBtn"
        type="submit"
        class="sm-button sm-button-primary button"
        :disabled="!!active"
      >
        开始计时 →
      </button>
    </form>
    <div class="divider"></div>
    <h2>02 / 当前会话</h2>
    <div id="sessionBox" class="session">
      <template v-if="active">
        <span class="tag">{{ active.tag }}</span>
        <div class="timer" :class="left >= 0 ? 'running' : 'expired'">
          {{ left >= 0 ? clock(left) : '+' + clock(left) }}
        </div>
        <div class="muted">{{ left >= 0 ? '距离预算结束' : '已经超时' }}</div>
        <div class="progress">
          <div :style="{ width: progress + '%' }"></div>
        </div>
        <p>
          <strong>{{ active.purpose }}</strong>
        </p>
        <div class="hint">
          开始：{{ fmt(active.startedAt) }} · 预算：{{ currentTotal(active) }}
          分钟
        </div>
        <div class="session-actions">
          <button
            id="endEarly"
            class="sm-button small-btn"
            @click="session.openReview"
          >
            主动结束并复盘
          </button>
        </div>
      </template>
      <template v-else>
        <div class="muted">当前没有进行中的会话</div>
        <div class="hint spaced">填写目的、标签、时间预算后即可启动。</div>
      </template>
    </div>
    <PomodoroPanel />
    <section id="commentSection" class="comment-section" :hidden="!active">
      <h2>随手评论</h2>
      <form id="commentForm" @submit.prevent="addComment">
        <div class="field">
          <label for="commentText">记录进展、想法或遇到的问题</label>
          <textarea
            id="commentText"
            v-model="comment"
            class="sm-control control"
            rows="3"
            maxlength="2000"
            required
            placeholder="记录此刻的进展或想法…"
          ></textarea>
        </div>
        <button class="sm-button small-btn" type="submit">添加评论</button>
      </form>
      <p class="hint">保存时自动记录添加时间；每条评论可单独导出 TXT。</p>
      <CommentsList v-if="active" id="activeComments" :session="active" />
    </section>
    <div class="divider"></div>
    <button
      id="notifyBtn"
      class="sm-button small-btn"
      type="button"
      @click="notifications.test"
    >
      {{
        nativeReady || notifications.browserAllowed()
          ? '发送测试提醒'
          : '开启桌面提醒'
      }}
    </button>
    <p id="notifyStatus" class="hint" role="status" aria-live="polite">
      {{ notifyMessage }}
    </p>
    <p class="hint">
      到时弹出复盘层并播放提示音。本地启动模式通过系统发送桌面提醒；浏览器通知需授权并保持标签页打开。
    </p>
  </aside>
</template>
