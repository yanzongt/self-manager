<script setup lang="ts">
import { usePdca } from '../usePdca'
defineProps<{ review?: boolean }>()
const { pomodoro } = usePdca()
const { pomo, nextLabel } = pomodoro
</script>
<template>
  <div class="session-actions">
    <button
      :id="review ? 'reviewPomoStart' : 'pomoStart'"
      :hidden="!!pomo"
      type="button"
      class="sm-button small-btn"
      @click="pomodoro.start('work')"
    >
      启动 Work
    </button>
    <button
      :id="review ? 'reviewPomoStartBreak' : 'pomoStartBreak'"
      :hidden="!!pomo"
      type="button"
      class="sm-button small-btn"
      @click="pomodoro.start('break')"
    >
      启动 Break
    </button>
    <button
      :id="review ? 'reviewPomoStop' : 'pomoStop'"
      :hidden="!pomo"
      type="button"
      class="sm-button small-btn"
      @click="pomodoro.stop"
    >
      关闭番茄钟
    </button>
    <button
      :id="review ? 'reviewPomoNext' : 'pomoNext'"
      :hidden="!pomo"
      type="button"
      class="sm-button small-btn"
      @click="pomodoro.next"
    >
      {{ nextLabel }}
    </button>
  </div>
</template>
