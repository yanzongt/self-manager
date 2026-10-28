<script setup lang="ts">
import type { Session } from '../types'
import { commentsOf } from '../data'
import { fmtComment } from '../time'
import { exportComment } from '../exports'
defineProps<{ session: Session }>()
</script>
<template>
  <div class="comment-list">
    <div
      v-for="comment in commentsOf(session)"
      :key="comment.id"
      class="comment-item"
    >
      <div class="comment-meta">
        <time :datetime="new Date(comment.at).toISOString()">
          {{ fmtComment(comment.at) }}
        </time>
        <button
          type="button"
          class="sm-button small-btn comment-export"
          :data-export-comment="comment.id"
          :data-session="session.id"
          @click="exportComment(session, comment)"
        >
          导出此条 TXT
        </button>
      </div>
      <div class="comment-text">{{ comment.text }}</div>
    </div>
  </div>
</template>
