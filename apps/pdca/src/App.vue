<script setup lang="ts">
import { provide } from 'vue'
import { createPdca, pdcaKey } from './usePdca'
import { exportJson } from './exports'
import SessionPanel from './components/SessionPanel.vue'
import WorkBoard from './components/WorkBoard.vue'
import AnalyticsPanel from './components/AnalyticsPanel.vue'
import HistoryPanel from './components/HistoryPanel.vue'
import ReviewDialog from './components/ReviewDialog.vue'
const pdca = createPdca()
provide(pdcaKey, pdca)
const { message, dirty, conflict, ready, blocked, legacy } = pdca.storage
const { toastText } = pdca
</script>
<template>
  <header class="sm-header sm-container">
    <div class="sm-brand">
      <span class="sm-mark" aria-hidden="true">s</span>
      Self Manager / 行为闭环
    </div>
    <a href="/" class="sm-back">← 返回主页</a>
  </header>
  <section class="sm-intro sm-container">
    <p class="sm-eyebrow">PLAN · DO · CHECK · ACT</p>
    <h1 class="sm-title">行为闭环</h1>
    <p class="sm-description">先明确目的，给时间一个边界，再用复盘完成闭环。</p>
  </section>
  <div class="sm-container storage-panel">
    <div id="storageStatus" class="muted" role="status" aria-live="polite">
      {{ message }}
    </div>
    <div v-if="!ready || dirty || conflict || legacy" class="actions">
      <button
        id="retryLoad"
        class="sm-button small-btn"
        type="button"
        :hidden="ready && !conflict"
        @click="pdca.load"
      >
        重新读取
      </button>
      <button
        id="retrySave"
        class="sm-button small-btn"
        type="button"
        :hidden="!dirty || conflict"
        @click="pdca.storage.save"
      >
        重试保存
      </button>
      <button
        id="exportLegacy"
        class="sm-button small-btn"
        type="button"
        :hidden="!legacy"
        @click="legacy && exportJson(legacy, true)"
      >
        导出旧浏览器数据
      </button>
    </div>
  </div>
  <div id="appContent" class="sm-container" :inert="blocked">
    <div class="layout">
      <SessionPanel />
      <main class="wide">
        <WorkBoard />
        <AnalyticsPanel />
        <HistoryPanel />
      </main>
    </div>
  </div>
  <footer class="sm-footer sm-container pdca-footer">
    <span>SELF MANAGER / 行为闭环 · 数据保存在本机文件</span>
    <p>
      本页面可提醒和引导复盘，无法阻止切换程序或关闭标签页。浏览器通知是否显示取决于权限与运行环境。
    </p>
  </footer>
  <ReviewDialog />
  <div id="toast" class="toast" :hidden="!toastText">{{ toastText }}</div>
</template>
