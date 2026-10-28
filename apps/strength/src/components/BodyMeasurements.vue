<script setup lang="ts">
import { computed, ref } from "vue";
import LineChart from "../../../shared/LineChart.vue";
import {
  bodyFields,
  byDate,
  clone,
  today,
  uid,
  validateBody,
  type BodyMetric,
  type Measurement,
} from "../model";
const props = defineProps<{ records: Measurement[] }>();
const emit = defineEmits<{
  save: [value: Measurement];
  remove: [id: string];
}>();
const fresh = (): Measurement => ({
  id: uid(),
  date: today(),
  note: "",
  weight: null,
  chest: null,
  arm: null,
  waist: null,
  hip: null,
  thigh: null,
});
const draft = ref(fresh()),
  editing = ref(false),
  metric = ref<BodyMetric>("weight"),
  error = ref("");
const ordered = computed(() => [...props.records].sort(byDate));
const series = computed(() => [
  {
    name: bodyFields[metric.value],
    points: [...ordered.value]
      .reverse()
      .filter((r) => r[metric.value] != null)
      .map((r) => ({ date: r.date, value: r[metric.value]! })),
  },
]);
function submit() {
  try {
    const normalized = clone(draft.value);
    for (const k of Object.keys(bodyFields) as BodyMetric[])
      normalized[k] =
        normalized[k] === null || String(normalized[k]) === ""
          ? null
          : Number(normalized[k]);
    emit("save", validateBody([normalized])[0]);
  } catch (e) {
    error.value = (e as Error).message;
  }
}
</script>
<template>
  <div class="two-columns">
    <section class="sm-panel">
      <h2 id="bodyFormTitle">
        {{ editing ? "编辑身体数据" : "添加身体数据" }}
      </h2>
      <form id="bodyForm" class="form-grid" @submit.prevent="submit">
        <label class="full"
          >测量日期<input
            id="bodyDate"
            v-model="draft.date"
            class="sm-control"
            type="date"
            required /></label
        ><label v-for="(label, key) in bodyFields" :key="key"
          >{{ label }} ({{ key === "weight" ? "kg" : "cm" }})<input
            :id="key === 'weight' ? 'bodyWeight' : key"
            v-model.number="draft[key]"
            class="sm-control"
            type="number"
            min="0.01"
            max="500"
            step="any" /></label
        ><label class="full"
          >备注<textarea
            id="bodyNote"
            v-model="draft.note"
            class="sm-control"
            maxlength="2000"
          />
        </label>
        <p v-if="error" role="alert">{{ error }}</p>
        <div class="actions full">
          <button class="sm-button sm-button-primary">保存身体数据</button
          ><button
            v-if="editing"
            id="bodyCancel"
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
        <h2>身体变化</h2>
        <select id="bodyMetric" v-model="metric" class="sm-control">
          <option v-for="(label, key) in bodyFields" :key="key" :value="key">
            {{ label }}
          </option>
        </select>
      </div>
      <p id="bodySummary">
        最新测量 {{ series[0].points.at(-1)?.value ?? "—" }} · 测量次数
        {{ series[0].points.length }}
      </p>
      <LineChart :series="series" label="身体测量变化" />
    </section>
  </div>
  <section class="sm-panel">
    <h2>身体测量历史</h2>
    <div id="bodyTable" class="table-scroll">
      <table>
        <thead>
          <tr>
            <th>日期</th>
            <th v-for="label in bodyFields" :key="label">{{ label }}</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in ordered" :key="r.id">
            <td>{{ r.date }}</td>
            <td v-for="(_, key) in bodyFields" :key="key">
              {{ r[key] ?? "—" }}
            </td>
            <td>
              <button
                class="text-button"
                :data-edit-body="r.id"
                @click="
                  draft = clone(r);
                  editing = true;
                "
              >
                编辑</button
              ><button
                class="text-button danger"
                :data-del-body="r.id"
                @click="emit('remove', r.id)"
              >
                删除
              </button>
            </td>
          </tr>
        </tbody>
      </table>
      <p v-if="!records.length" class="empty">尚无身体测量记录</p>
    </div>
  </section>
</template>
