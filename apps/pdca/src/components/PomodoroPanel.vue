<script setup lang="ts">
import { ref, watch } from 'vue'
import { usePdca } from '../usePdca'
import { clock } from '../time'
import PomodoroControls from './PomodoroControls.vue'
const { storage, pomodoro, now } = usePdca()
const { db } = storage
const { pomo, status } = pomodoro
const work = ref(25),
  rest = ref(5),
  auto = ref(true)
function reset() {
  work.value = db.value.pomoSettings.workMinutes
  rest.value = db.value.pomoSettings.breakMinutes
  auto.value = pomo.value?.auto ?? db.value.pomoSettings.autoSwitch
}
watch(() => [db.value.pomoSettings, pomo.value?.auto], reset, {
  immediate: true,
})
async function saveSettings() {
  await pomodoro.settings({
    workMinutes: Number(work.value),
    breakMinutes: Number(rest.value),
    autoSwitch: auto.value,
  })
  reset()
}
</script>
<template>
  <section id="pomoSection" class="pomo-card">
    <h2>番茄钟</h2>
    <div class="field">
      <label>独立计时设置</label>
      <div class="pomo-fields">
        <div>
          <label for="pomoWork">Work（分钟）</label>
          <input
            id="pomoWork"
            v-model.number="work"
            class="sm-control control"
            type="number"
            min="1"
            max="1440"
            step="1"
            :disabled="!!pomo"
            @change="saveSettings"
          />
        </div>
        <div>
          <label for="pomoBreak">Break（分钟）</label>
          <input
            id="pomoBreak"
            v-model.number="rest"
            class="sm-control control"
            type="number"
            min="1"
            max="1440"
            step="1"
            :disabled="!!pomo"
            @change="saveSettings"
          />
        </div>
      </div>
      <label class="check-label" for="pomoAuto">
        <input
          id="pomoAuto"
          v-model="auto"
          type="checkbox"
          @change="saveSettings"
        />
        自动切换 Work / Break
      </label>
      <p class="hint">
        未勾选时，到时提醒并等待你手动开始下一阶段。可随时切换阶段；番茄钟独立于工作会话运行。
      </p>
    </div>
    <div id="pomoStatus" class="muted" role="status" aria-live="polite">
      {{ status }}
    </div>
    <div
      id="pomoTimer"
      class="pomo-clock"
      :class="pomo?.phase === 'break' ? 'phase-break' : 'running'"
    >
      {{
        !pomo || pomo.waiting
          ? '00:00'
          : clock(Math.max(0, pomo.phaseEndsAt - now))
      }}
    </div>
    <PomodoroControls />
  </section>
</template>
