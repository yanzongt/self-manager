<script setup lang="ts">
import { ref } from "vue";
import { clone, type Exercise } from "../model";
const props = defineProps<{ exercise: Exercise }>();
const emit = defineEmits<{ save: [exercise: Exercise]; cancel: [] }>();
const draft = ref(clone(props.exercise));
</script>
<template>
  <section id="exerciseEditor" class="sm-panel">
    <h2>{{ exercise.name ? "编辑动作" : "新建动作" }}</h2>
    <form
      id="exerciseForm"
      class="form-grid"
      @submit.prevent="emit('save', draft)"
    >
      <label
        >动作名称<input
          id="exerciseName"
          v-model.trim="draft.name"
          class="sm-control"
          required
          maxlength="100"
          autofocus /></label
      ><label
        >训练部位<input
          id="exercisePart"
          v-model.trim="draft.part"
          class="sm-control"
          required
          maxlength="100" /></label
      ><label class="full"
        >备注<textarea
          id="exerciseNote"
          v-model="draft.note"
          class="sm-control"
          maxlength="2000"
        /></label
      ><label class="full"
        >动作指南<textarea
          id="exerciseGuide"
          v-model="draft.guide"
          class="sm-control"
          rows="5"
          maxlength="10000"
        />
      </label>
      <div class="actions full">
        <button class="sm-button sm-button-primary" type="submit">
          保存动作</button
        ><button class="sm-button" type="button" @click="emit('cancel')">
          取消
        </button>
      </div>
    </form>
  </section>
</template>
