<script setup lang="ts">
import { computed, ref } from "vue";
import {
  byDate,
  clone,
  today,
  uid,
  validateLogs,
  type Exercise,
  type TrainingLog,
} from "../model";
const props = defineProps<{
  exercises: Exercise[];
  logs: TrainingLog[];
  initial?: TrainingLog;
  filter?: string;
}>();
const emit = defineEmits<{ save: [log: TrainingLog]; remove: [id: string] }>();
const fresh = (): TrainingLog => {
  const e = props.exercises[0];
  return {
    id: uid(),
    date: today(),
    exId: e.id,
    sets: e.sets,
    reps: e.reps,
    weight: e.weight,
    unit: e.unit,
    pain: 0,
    note: "",
  };
};
const draft = ref(props.initial ? clone(props.initial) : fresh()),
  editing = ref(false),
  filter = ref(props.filter || ""),
  error = ref("");
const logs = computed(() =>
  props.logs
    .filter((l) => !filter.value || l.exId === filter.value)
    .sort(byDate),
);
function target() {
  const e = props.exercises.find((e) => e.id === draft.value.exId)!;
  Object.assign(draft.value, {
    sets: e.sets,
    reps: e.reps,
    weight: e.weight,
    unit: e.unit,
  });
}
function submit() {
  try {
    emit("save", validateLogs([draft.value], props.exercises)[0]);
  } catch (e) {
    error.value = (e as Error).message;
  }
}
</script>
<template>
  <div class="two-columns">
    <section class="sm-panel">
      <h2 id="logFormTitle">{{ editing ? "编辑训练记录" : "添加训练记录" }}</h2>
      <form id="logForm" class="form-grid" @submit.prevent="submit">
        <label
          >日期<input
            id="logDate"
            v-model="draft.date"
            class="sm-control"
            type="date"
            required /></label
        ><label
          >动作<select
            id="logEx"
            v-model="draft.exId"
            class="sm-control"
            @change="target"
          >
            <option v-for="e in exercises" :key="e.id" :value="e.id">
              {{ e.name }}
            </option>
          </select></label
        ><label
          >组数<input
            id="logSets"
            v-model.number="draft.sets"
            class="sm-control"
            type="number"
            min="1"
            max="30"
            required /></label
        ><label
          ><span id="logRepsLabel">{{
            draft.unit === "秒" ? "每组秒数" : "每组次数"
          }}</span
          ><input
            id="logReps"
            v-model.number="draft.reps"
            class="sm-control"
            type="number"
            min="1"
            max="500"
            required /></label
        ><label
          >重量 kg<input
            id="logWeight"
            v-model.number="draft.weight"
            class="sm-control"
            type="number"
            min="0"
            max="1000"
            step="any"
            required /></label
        ><label
          >肘痛 0–10<input
            id="logPain"
            v-model.number="draft.pain"
            class="sm-control"
            type="number"
            min="0"
            max="10"
            required /></label
        ><label class="full"
          >备注<textarea
            id="logNote"
            v-model="draft.note"
            class="sm-control"
            maxlength="2000"
          />
        </label>
        <p v-if="error" role="alert">{{ error }}</p>
        <div class="actions full">
          <button id="saveLog" class="sm-button sm-button-primary">
            保存训练记录</button
          ><button
            v-if="editing"
            id="cancelEdit"
            class="sm-button"
            type="button"
            @click="
              draft = fresh();
              editing = false;
            "
          >
            取消编辑
          </button>
        </div>
      </form>
    </section>
    <section class="sm-panel">
      <div class="section-heading">
        <h2>
          训练记录 <small id="logCount">{{ logs.length }} 条</small>
        </h2>
        <select id="filterEx" v-model="filter" class="sm-control">
          <option value="">全部动作</option>
          <option v-for="e in exercises" :key="e.id" :value="e.id">
            {{ e.name }}
          </option>
        </select>
      </div>
      <div id="allLogs" class="table-scroll">
        <table>
          <thead>
            <tr>
              <th>日期 / 动作</th>
              <th>组 × 数量</th>
              <th>重量</th>
              <th>肘痛</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="l in logs" :key="l.id">
              <td>
                {{ l.date }}<br />{{
                  exercises.find((e) => e.id === l.exId)?.name
                }}<small>{{ l.note }}</small>
              </td>
              <td>{{ l.sets }} × {{ l.reps }}{{ l.unit }}</td>
              <td>{{ l.weight }} kg</td>
              <td>{{ l.pain }}/10</td>
              <td>
                <button
                  class="text-button"
                  :data-edit-log="l.id"
                  @click="
                    draft = clone(l);
                    editing = true;
                  "
                >
                  编辑</button
                ><button
                  class="text-button danger"
                  :data-del-log="l.id"
                  @click="emit('remove', l.id)"
                >
                  删除
                </button>
              </td>
            </tr>
          </tbody>
        </table>
        <p v-if="!logs.length" class="empty">没有符合条件的训练记录</p>
      </div>
    </section>
  </div>
</template>
