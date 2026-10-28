<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { usePdca } from '../usePdca'
import { deadline, formatMin, mins } from '../time'
import { resultLabels } from '../exports'
import type { Result } from '../types'
import PomodoroControls from './PomodoroControls.vue'
const { storage, session, pomodoro, now } = usePdca()
const { reviewOpen, result, reviewText } = session
const { status } = pomodoro
const active = computed(() => storage.db.value.active)
const input = ref<HTMLTextAreaElement | null>(null)
const choices = Object.entries(resultLabels) as [Result, string][]
watch(reviewOpen, async (open) => {
  if (open) {
    await nextTick()
    input.value?.focus()
  }
})
</script>
<template>
  <div
    id="reviewOverlay"
    class="overlay"
    :hidden="!reviewOpen"
    role="dialog"
    aria-modal="true"
    aria-labelledby="reviewTitle"
    :inert="storage.pending.value > 0"
  >
    <div class="review">
      <div id="reviewEyebrow" class="eyebrow">CHECK / ACT</div>
      <h2 id="reviewTitle">
        {{
          active && now >= deadline(active)
            ? '时间到了，请完成复盘'
            : '结束前，请完成复盘'
        }}
      </h2>
      <div id="reviewInfo" class="muted" v-if="active">
        {{ active.purpose }} · {{ active.tag }} · 已用
        {{ formatMin(mins(now - active.startedAt)) }} 分钟
      </div>
      <div class="field">
        <label>本次目的是否完成？</label>
        <div id="reviewChoices" class="options">
          <button
            v-for="[value, label] in choices"
            :key="value"
            type="button"
            class="sm-button choice"
            :class="{ selected: result === value }"
            :data-result="value"
            @click="result = value"
          >
            {{ label }}
          </button>
        </div>
      </div>
      <div class="field">
        <label for="reviewText">复盘记录（至少写一点收获或偏离原因）</label>
        <textarea
          id="reviewText"
          ref="input"
          v-model="reviewText"
          class="sm-control control"
          maxlength="2000"
          placeholder="例如：已整理三个关键结论；剩余部分明天继续"
        ></textarea>
      </div>
      <div class="review-actions">
        <button
          id="extendBtn"
          class="sm-button sm-button-primary button secondary"
          type="button"
          @click="session.extend"
        >
          复盘后延长 10 分钟
        </button>
        <button
          id="finishBtn"
          class="sm-button sm-button-primary button"
          type="button"
          @click="session.finish"
        >
          保存复盘并结束
        </button>
      </div>
      <div class="divider"></div>
      <div id="reviewPomoStatus" class="hint">番茄钟 · {{ status }}</div>
      <PomodoroControls review />
      <div class="fineprint">
        当前页面的遮罩不可直接关闭。延长也需要填写复盘，形成决策记录。浏览器仍允许你切到其他程序或关闭页面。
      </div>
    </div>
  </div>
</template>
