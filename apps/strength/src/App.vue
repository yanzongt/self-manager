<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { DAYS, DAY_ORDER, DEFAULT_EX } from "./defaults";
import {
  byDate,
  clone,
  exportData,
  importData,
  today,
  uid,
  validateExercises,
  type Exercise,
  type FileType,
  type TrainingLog,
  type Measurement,
} from "./model";
import { useStrength } from "./useStrength";
import ExerciseEditor from "./components/ExerciseEditor.vue";
import TrainingLogs from "./components/TrainingLogs.vue";
import BodyMeasurements from "./components/BodyMeasurements.vue";
import TrainingAnalysis from "./components/TrainingAnalysis.vue";
const { data, message, commit, update } = useStrength();
const pages = {
  overview: "训练概览",
  schedule: "每周计划",
  library: "动作仓库",
  logs: "训练记录",
  analysis: "趋势分析",
  body: "身体数据",
};
const page = ref<keyof typeof pages>("overview"),
  day = ref(new Date().getDay()),
  selected = ref(""),
  search = ref(""),
  part = ref(""),
  addExisting = ref(""),
  addDay = ref(1),
  editor = ref<Exercise | null>(null),
  initialLog = ref<TrainingLog>(),
  filter = ref(""),
  logKey = ref(0),
  bodyKey = ref(0);
const routine = computed(() => data.value.routines[day.value]);
const exercise = (id: string) => data.value.exercises.find((e) => e.id === id)!;
const current = computed(() =>
  data.value.exercises.find((e) => e.id === selected.value),
);
const library = computed(() =>
  data.value.exercises.filter(
    (e) =>
      (!part.value || e.part === part.value) &&
      [e.name, e.part, e.note, e.guide].some((t) =>
        t.toLocaleLowerCase().includes(search.value.toLocaleLowerCase()),
      ),
  ),
);
const currentLogs = computed(() =>
  data.value.logs.filter((l) => l.exId === selected.value).sort(byDate),
);
const currentDays = computed(() =>
  DAY_ORDER.filter((d) => data.value.routines[d].ids.includes(selected.value)),
);
watch(currentDays, (days) => {
  if (days.includes(addDay.value))
    addDay.value = DAY_ORDER.find((d) => !days.includes(d)) ?? 1;
});
const recent = computed(() => [...data.value.logs].sort(byDate).slice(0, 6));
const stats = computed(() => {
  const date = new Date();
  date.setDate(date.getDate() - 6);
  const since = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
  return [
    ["累计训练记录", data.value.logs.length],
    [
      "近7天训练日",
      new Set(
        data.value.logs
          .filter((l) => l.date >= since && l.date <= today())
          .map((l) => l.date),
      ).size,
    ],
    ["已追踪动作", new Set(data.value.logs.map((l) => l.exId)).size],
    ["身体测量", data.value.body.length],
  ];
});
function go(p: keyof typeof pages) {
  page.value = p;
  editor.value = null;
}
function showExercise(id: string) {
  selected.value = id;
  go("library");
}
function startLog(id?: string) {
  const e = exercise(id || data.value.exercises[0].id);
  initialLog.value = {
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
  filter.value = "";
  logKey.value++;
  go("logs");
}
function edit(e?: Exercise) {
  editor.value = e
    ? clone(e)
    : {
        id: uid(),
        name: "",
        part: "",
        note: "",
        guide: "",
        sets: 2,
        reps: 10,
        weight: 0,
        unit: "次",
      };
}
function saveExercise(value: Exercise) {
  try {
    const e = validateExercises([value])[0];
    if (
      update((d) => {
        const i = d.exercises.findIndex((x) => x.id === e.id);
        if (i < 0) {
          d.exercises.push(e);
          if (page.value === "schedule") d.routines[day.value].ids.push(e.id);
        } else d.exercises[i] = e;
      })
    ) {
      selected.value = e.id;
      search.value = "";
      part.value = "";
      editor.value = null;
      message.value = "动作已保存";
    }
  } catch (e) {
    message.value = (e as Error).message;
  }
}
function target(
  e: Exercise,
  key: "sets" | "reps" | "weight" | "unit",
  event: Event,
) {
  const input = event.target as HTMLInputElement;
  const next = {
    ...e,
    [key]: key === "unit" ? input.value : Number(input.value),
  };
  try {
    validateExercises([next]);
    if (
      !update((d) => {
        Object.assign(d.exercises.find((x) => x.id === e.id)!, next);
      })
    ) {
      input.value = String(e[key]);
    }
  } catch {
    input.value = String(e[key]);
    message.value = "请输入范围内的有效数值";
  }
}
function addToDay(id: string, d: number) {
  if (id && !data.value.routines[d].ids.includes(id))
    update((s) => s.routines[d].ids.push(id));
}
function saveLog(l: TrainingLog) {
  if (
    update((d) => {
      const i = d.logs.findIndex((x) => x.id === l.id);
      if (i < 0) d.logs.push(l);
      else d.logs[i] = l;
    })
  ) {
    initialLog.value = undefined;
    logKey.value++;
    message.value = "训练记录已保存";
  }
}
function saveBody(r: Measurement) {
  if (
    update((d) => {
      const i = d.body.findIndex((x) => x.id === r.id);
      if (i < 0) d.body.push(r);
      else d.body[i] = r;
    })
  ) {
    bodyKey.value++;
    message.value = "身体数据已保存";
  }
}
function remove(kind: "logs" | "body", id: string) {
  if (confirm("确定删除这条记录？"))
    update((d) => {
      if (kind === "logs") d.logs = d.logs.filter((l) => l.id !== id);
      else d.body = d.body.filter((l) => l.id !== id);
    });
}
function reset() {
  if (
    confirm(
      "恢复内置动作的默认组数、数量和重量？自定义动作和每周安排保留，训练记录不变。",
    )
  )
    update((d) =>
      d.exercises.forEach((e) => {
        const original = DEFAULT_EX.find((x) => x.id === e.id);
        if (original)
          Object.assign(e, {
            sets: original.sets,
            reps: original.reps,
            weight: original.weight,
            unit: original.unit,
          });
      }),
    );
}
const files = [
  {
    type: "plan",
    label: "训练计划",
    exportId: "exportPlan",
    importId: "importPlan",
    inputId: "planFile",
  },
  {
    type: "records",
    label: "训练记录",
    exportId: "exportLogs",
    importId: "importLogs",
    inputId: "logsFile",
  },
  {
    type: "backup",
    label: "完整备份",
    exportId: "exportBtn",
    importId: "importBtn",
    inputId: "importFile",
  },
] as const;
async function upload(event: Event, type: FileType) {
  const input = event.target as HTMLInputElement;
  try {
    const file = input.files?.[0];
    if (!file) return;
    if (file.size > 5e6) throw Error("文件超过5MB");
    const candidate = importData(
      JSON.parse(await file.text()),
      type,
      data.value,
    );
    if (
      !confirm(
        type === "backup"
          ? "确定用备份覆盖全部当前数据？建议先导出当前备份。"
          : type === "plan"
            ? "导入后将替换每周训练安排和动作目标，现有记录保留。是否继续？"
            : "将合并训练记录并跳过重复条目，当前计划保留。是否继续？",
      )
    )
      return;
    if (commit(candidate, type === "backup")) {
      editor.value = null;
      initialLog.value = undefined;
      logKey.value++;
      bodyKey.value++;
      message.value = "导入成功";
    }
  } catch (e) {
    alert("导入失败：" + (e as Error).message);
  } finally {
    input.value = "";
  }
}
function chooseFile(id: string) {
  document.getElementById(id)?.click();
}
</script>
<template>
  <div class="sm-container">
    <header class="sm-header">
      <div class="sm-brand">
        <span class="sm-mark">s.</span>Self Manager
        <span class="muted">/ 力量训练</span>
      </div>
      <a class="sm-back" href="/">← 返回主页</a>
    </header>
    <div class="sm-intro">
      <p class="sm-eyebrow">STRENGTH & RECOVERY</p>
      <h1 class="sm-title">让每一次训练，有迹可循。</h1>
      <p class="sm-description">
        安排训练、记录进步，在力量与恢复之间找到自己的节奏。
      </p>
    </div>
    <nav class="page-nav" aria-label="力量训练导航">
      <button
        v-for="(label, key) in pages"
        :key="key"
        class="sm-button"
        :class="{ 'sm-button-primary': page === key }"
        :data-page="key"
        :aria-current="page === key ? 'page' : undefined"
        @click="go(key)"
      >
        {{ label }}
      </button>
    </nav>
    <div v-if="message" class="notice" role="status">
      {{ message }}
      <button class="text-button" aria-label="关闭提示" @click="message = ''">
        ×
      </button>
    </div>
    <main>
      <template v-if="page === 'overview'"
        ><div class="stats">
          <article
            v-for="[label, value] in stats"
            :key="label"
            class="sm-panel"
          >
            <span class="muted">{{ label }}</span
            ><strong>{{ value }}</strong>
          </article>
        </div>
        <section class="sm-panel today-panel">
          <p class="sm-eyebrow">TODAY</p>
          <h2 id="todayTitle">
            {{ data.routines[new Date().getDay()].title }}
          </h2>
          <p id="todaySummary" class="muted">
            {{ data.routines[new Date().getDay()].purpose }}
          </p>
          <div class="actions">
            <button
              id="heroAction"
              class="sm-button sm-button-primary"
              @click="
                day = new Date().getDay();
                go('schedule');
              "
            >
              查看今日计划</button
            ><button id="quickLog" class="sm-button" @click="startLog()">
              记录一次训练
            </button>
          </div>
        </section>
        <section class="sm-panel">
          <h2>最近训练</h2>
          <div id="recentLogs">
            <p v-if="!recent.length" class="empty">
              尚无训练记录。从“记录一次训练”开始。
            </p>
            <div v-for="l in recent" :key="l.id" class="record-row">
              <div>
                {{ exercise(l.exId)?.name
                }}<small
                  >{{ l.date }} · {{ l.sets }}组 × {{ l.reps
                  }}{{ l.unit }}</small
                >
              </div>
              <strong>{{ l.weight }} kg</strong>
            </div>
          </div>
        </section></template
      >
      <template v-if="page === 'overview' || page === 'schedule'"
        ><section class="sm-panel">
          <h2>每周安排</h2>
          <div
            :id="page === 'schedule' ? 'fullWeek' : 'miniWeek'"
            class="week-grid"
          >
            <button
              v-for="d in DAY_ORDER"
              :key="d"
              class="sm-button day"
              :class="{ 'sm-button-primary': day === d }"
              :data-day="d"
              @click="
                day = d;
                go('schedule');
              "
            >
              <strong>{{ DAYS[d] }}</strong
              ><small>{{ data.routines[d].title.split(" · ")[0] }}</small>
            </button>
          </div>
        </section></template
      >
      <template v-if="page === 'schedule'"
        ><section class="sm-panel">
          <div class="section-heading">
            <h2 id="dayTitle">{{ DAYS[day] }} · {{ routine.title }}</h2>
            <button
              id="logSelected"
              class="sm-button sm-button-primary"
              :disabled="!routine.ids.length"
              @click="startLog(routine.ids[0])"
            >
              记录当天训练
            </button>
          </div>
          <p id="dayPurpose" class="muted">{{ routine.purpose }}</p>
          <div id="dayDetails">
            <article v-for="id in routine.ids" :key="id" class="exercise-row">
              <div>
                <button
                  class="text-button exercise-name"
                  :data-view-ex="id"
                  @click="showExercise(id)"
                >
                  {{ exercise(id).name }}
                </button>
                <span class="tag">{{ exercise(id).part }}</span>
                <p class="muted">{{ exercise(id).note }}</p>
                <button
                  class="text-button"
                  :data-edit-ex="id"
                  @click="edit(exercise(id))"
                >
                  编辑动作</button
                ><button
                  class="text-button danger"
                  :data-remove-ex="id"
                  @click="
                    update((d) => {
                      d.routines[day].ids = d.routines[day].ids.filter(
                        (x) => x !== id,
                      );
                    })
                  "
                >
                  移出当天
                </button>
              </div>
              <div class="plan-targets">
                <label
                  v-for="key in ['sets', 'reps', 'weight'] as const"
                  :key="key"
                  >{{
                    { sets: "组数", reps: "每组数量", weight: "重量 kg" }[key]
                  }}<input
                    class="sm-control"
                    :value="exercise(id)[key]"
                    :data-ex="id"
                    :data-target="key"
                    :aria-label="exercise(id).name + key"
                    type="number"
                    :min="key === 'weight' ? 0 : 1"
                    :max="key === 'sets' ? 30 : key === 'reps' ? 500 : 1000"
                    :step="key === 'weight' ? 'any' : 1"
                    @change="target(exercise(id), key, $event)" /></label
                ><label
                  >单位<select
                    class="sm-control"
                    :data-ex="id"
                    data-target="unit"
                    :value="exercise(id).unit"
                    @change="target(exercise(id), 'unit', $event)"
                  >
                    <option>次</option>
                    <option>秒</option>
                  </select></label
                ><button
                  class="sm-button"
                  :data-log-ex="id"
                  @click="startLog(id)"
                >
                  记录
                </button>
              </div>
            </article>
            <p v-if="!routine.ids.length" class="empty">
              今天没有必做的力量训练，也可以添加动作。
            </p>
          </div>
          <div class="actions">
            <select id="addExisting" v-model="addExisting" class="sm-control">
              <option value="">选择已有动作</option>
              <option
                v-for="e in data.exercises.filter(
                  (e) => !routine.ids.includes(e.id),
                )"
                :key="e.id"
                :value="e.id"
              >
                {{ e.name }}
              </option></select
            ><button
              id="addToDay"
              class="sm-button"
              @click="addToDay(addExisting, day)"
            >
              加入当天</button
            ><button id="newExercise" class="sm-button" @click="edit()">
              新建动作</button
            ><button id="resetPlans" class="text-button" @click="reset">
              恢复默认目标
            </button>
          </div>
        </section></template
      >
      <template v-if="page === 'library'"
        ><div class="two-columns library-layout">
          <section class="sm-panel">
            <div class="section-heading">
              <h2>动作仓库</h2>
              <button id="libraryNew" class="sm-button" @click="edit()">
                新建动作
              </button>
            </div>
            <label
              >搜索动作<input
                id="librarySearch"
                v-model="search"
                class="sm-control"
                placeholder="名称、部位、备注或动作指南" /></label
            ><label
              >训练部位<select
                id="libraryPart"
                v-model="part"
                class="sm-control"
              >
                <option value="">全部部位</option>
                <option
                  v-for="p in [...new Set(data.exercises.map((e) => e.part))]"
                  :key="p"
                >
                  {{ p }}
                </option>
              </select></label
            >
            <div class="library-list">
              <button
                v-for="e in library"
                :key="e.id"
                class="library-item"
                :class="{ selected: selected === e.id }"
                :data-library-ex="e.id"
                @click="selected = e.id"
              >
                <strong>{{ e.name }}</strong
                ><small
                  >{{ e.part }} · {{ e.sets }}组 × {{ e.reps }}{{ e.unit }} ·
                  {{ e.weight }} kg</small
                >
              </button>
              <p v-if="!library.length" class="empty">没有符合条件的动作</p>
            </div>
          </section>
          <section id="libraryDetail" class="sm-panel">
            <template v-if="current"
              ><h2>{{ current.name }}</h2>
              <p class="muted">{{ current.part }} · {{ current.note }}</p>
              <div class="actions">
                <button
                  id="libraryEdit"
                  class="sm-button"
                  @click="edit(current)"
                >
                  编辑动作</button
                ><button
                  id="libraryLog"
                  class="sm-button sm-button-primary"
                  @click="startLog(current.id)"
                >
                  记录训练
                </button>
              </div>
              <h3>动作指南</h3>
              <p id="libraryGuide" class="guide">
                {{ current.guide || "尚未填写动作指南" }}
              </p>
              <h3>每周计划</h3>
              <div id="libraryPlans" class="actions">
                <button
                  v-for="d in currentDays"
                  :key="d"
                  class="sm-button"
                  :data-library-day="d"
                  @click="
                    day = d;
                    go('schedule');
                  "
                >
                  {{ DAYS[d] }}
                </button>
                <p v-if="!currentDays.length" class="muted">尚未加入每周计划</p>
              </div>
              <div class="actions">
                <select
                  :disabled="currentDays.length === 7"
                  id="libraryAddDay"
                  v-model.number="addDay"
                  class="sm-control"
                >
                  <option
                    v-for="d in DAY_ORDER.filter(
                      (d) => !currentDays.includes(d),
                    )"
                    :key="d"
                    :value="d"
                  >
                    {{ DAYS[d] }}
                  </option></select
                ><button
                  :disabled="currentDays.length === 7"
                  id="libraryAddPlan"
                  class="sm-button"
                  @click="addToDay(current.id, addDay)"
                >
                  加入计划
                </button>
              </div>
              <h3>
                训练历史
                <small id="libraryLogCount">{{ currentLogs.length }} 条</small>
              </h3>
              <div id="libraryRecords">
                <p v-if="!currentLogs.length" class="muted">暂无训练记录</p>
                <p v-for="l in currentLogs.slice(0, 5)" :key="l.id">
                  {{ l.date }} · {{ l.sets }} × {{ l.reps }}{{ l.unit }} ·
                  {{ l.weight }} kg
                </p>
              </div>
              <button
                id="libraryAllLogs"
                class="text-button"
                @click="
                  filter = current.id;
                  initialLog = undefined;
                  logKey++;
                  go('logs');
                "
              >
                查看全部记录
              </button></template
            >
            <p v-else class="empty">选择一个动作，查看指南、计划与历史。</p>
          </section>
        </div></template
      >
      <ExerciseEditor
        v-if="editor"
        :key="editor.id"
        :exercise="editor"
        @save="saveExercise"
        @cancel="editor = null"
      />
      <TrainingLogs
        v-if="page === 'logs'"
        :key="logKey"
        :exercises="data.exercises"
        :logs="data.logs"
        :initial="initialLog"
        :filter="filter"
        @save="saveLog"
        @remove="remove('logs', $event)"
      />
      <TrainingAnalysis
        v-if="page === 'analysis'"
        :exercises="data.exercises"
        :logs="data.logs"
      />
      <BodyMeasurements
        v-if="page === 'body'"
        :key="bodyKey"
        :records="data.body"
        @save="saveBody"
        @remove="remove('body', $event)"
      />
      <section class="sm-panel backup-panel">
        <h2>数据与备份</h2>
        <div class="backup-grid">
          <div v-for="f in files" :key="f.type">
            <h3>{{ f.label }}</h3>
            <div class="actions">
              <button
                :id="f.exportId"
                class="sm-button"
                @click="exportData(data, f.type)"
              >
                导出{{ f.label }}</button
              ><button
                :id="f.importId"
                class="sm-button"
                @click="chooseFile(f.inputId)"
              >
                导入{{ f.label }}</button
              ><input
                :id="f.inputId"
                hidden
                type="file"
                accept=".json,application/json"
                @change="upload($event, f.type)"
              />
            </div>
          </div>
        </div>
      </section>
    </main>
    <footer class="sm-footer">
      数据仅保存在当前浏览器，请定期导出完整备份。清除网站数据或更换设备可能导致记录丢失。
    </footer>
  </div>
</template>
