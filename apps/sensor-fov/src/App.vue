<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import NumberField from './NumberField.vue'
import {
  defaultConfig,
  MAX_SENSORS,
  newId,
  newSensor,
  parseConfig,
  sensorNames,
} from './model'
import type { Config, SensorType } from './model'
import { FovScene } from './scene'
import type { View } from './scene'

const STORAGE_KEY = 'sensor-fov-config-v1'
const config = ref<Config>(defaultConfig())
const notice = ref(''),
  error = ref(''),
  storageError = ref(''),
  renderError = ref('')
try {
  const saved = localStorage.getItem(STORAGE_KEY)
  if (saved) config.value = parseConfig(JSON.parse(saved))
} catch (e) {
  notice.value = `未加载本地配置：${(e as Error).message}`
}
const selectedId = ref(config.value.sensors[0]?.id ?? '')
const selected = computed(() =>
  config.value.sensors.find((s) => s.id === selectedId.value),
)
const host = ref<HTMLElement>()
const importInput = ref<HTMLInputElement>()
const view = ref<View>('3d')
const labelsVisible = ref(true)
const addType = ref<SensorType>('lidar')
const counts = computed(() =>
  Object.entries(sensorNames).map(([type, label]) => ({
    type,
    label,
    count: config.value.sensors.filter((s) => s.type === type).length,
  })),
)
let scene: FovScene | undefined
let timer: ReturnType<typeof setTimeout> | undefined
let validConfig = parseConfig(config.value)
let pendingFit = false

function update() {
  try {
    validConfig = parseConfig(config.value)
    error.value = ''
  } catch (e) {
    error.value = (e as Error).message
    return
  }
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(validConfig))
    storageError.value = ''
  } catch {
    storageError.value = '浏览器存储不可用，请导出 JSON 保存配置。'
  }
  if (scene) {
    try {
      scene.update(validConfig, selectedId.value)
      if (pendingFit) {
        scene.fit()
        pendingFit = false
      }
    } catch (e) {
      renderError.value = `3D 更新失败：${(e as Error).message}`
    }
  }
}
watch(
  config,
  () => {
    clearTimeout(timer)
    timer = setTimeout(update, 100)
  },
  { deep: true },
)
watch(selectedId, () => scene?.update(validConfig, selectedId.value))
onMounted(() => {
  try {
    scene = new FovScene(host.value!, (id) => {
      selectedId.value = id
    })
    update()
    scene.fit()
  } catch (e) {
    renderError.value = `无法启动 3D 视图，请启用浏览器 WebGL 2：${(e as Error).message}`
  }
})
onBeforeUnmount(() => {
  clearTimeout(timer)
  scene?.dispose()
})
function add() {
  if (config.value.sensors.length >= MAX_SENSORS) {
    notice.value = `最多支持 ${MAX_SENSORS} 个传感器`
    return
  }
  const sensor = newSensor(addType.value)
  sensor.name = `${sensorNames[addType.value]} ${config.value.sensors.filter((s) => s.type === addType.value).length + 1}`
  config.value.sensors.push(sensor)
  selectedId.value = sensor.id
}
function duplicate() {
  if (!selected.value || config.value.sensors.length >= MAX_SENSORS) return
  const sensor = JSON.parse(JSON.stringify(selected.value))
  sensor.id = newId()
  sensor.name = `${sensor.name.slice(0, 90)} 副本`
  config.value.sensors.push(sensor)
  selectedId.value = sensor.id
}
function remove() {
  const i = config.value.sensors.findIndex((s) => s.id === selectedId.value)
  if (i < 0) return
  config.value.sensors.splice(i, 1)
  selectedId.value =
    config.value.sensors[Math.min(i, config.value.sensors.length - 1)]?.id ?? ''
}
function setView(next: View) {
  view.value = next
  scene?.setView(next)
}
function toggleLabels() {
  labelsVisible.value = !labelsVisible.value
  scene?.setLabelsVisible(labelsVisible.value)
}
function filter(type: string) {
  config.value.sensors.forEach((s) => {
    s.visible = type === 'all' || s.type === type
  })
}
function exportConfig() {
  update()
  if (error.value) return
  const url = URL.createObjectURL(
    new Blob([JSON.stringify(validConfig, null, 2)], {
      type: 'application/json',
    }),
  )
  const a = document.createElement('a')
  a.href = url
  a.download = 'sensor-fov-config.json'
  a.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
async function importConfig(event: Event) {
  const input = event.target as HTMLInputElement,
    file = input.files?.[0]
  if (!file) return
  try {
    if (file.size > 1024 * 1024) throw new Error('配置文件不能超过 1 MB')
    const next = parseConfig(JSON.parse(await file.text()))
    pendingFit = true
    config.value = next
    selectedId.value = next.sensors[0]?.id ?? ''
    notice.value = `已导入 ${next.sensors.length} 个传感器`
  } catch (e) {
    notice.value = `导入失败，保留原配置：${(e as Error).message}`
  }
  input.value = ''
}
function reset() {
  if (
    !window.confirm(
      '恢复默认双激光布局？当前配置将被替换，可先取消并导出 JSON。',
    )
  )
    return
  config.value = defaultConfig()
  selectedId.value = config.value.sensors[0]!.id
  pendingFit = true
  notice.value = '已恢复默认布局'
}
</script>

<template>
  <div class="workbench">
    <header class="sm-header sm-container">
      <div class="sm-brand">
        <span class="sm-mark" aria-hidden="true">s</span>
        Self Manager / 传感器视场
      </div>
      <a href="/" class="sm-back">← 返回主页</a>
    </header>
    <section class="sm-intro sm-container tool-intro">
      <div>
        <p class="sm-eyebrow">SENSOR FIELD OF VIEW</p>
        <h1 class="sm-title">传感器视场</h1>
        <p class="sm-description">
          配置传感器安装方案，在三维空间中检查视场覆盖。
        </p>
      </div>
      <div class="header-actions">
        <span class="save-state" :class="{ warning: error || storageError }">
          {{
            error
              ? '参数待修正'
              : storageError
                ? '本地保存不可用'
                : '浏览器自动保存'
          }}
        </span>
        <input
          ref="importInput"
          type="file"
          accept=".json,application/json"
          hidden
          @change="importConfig"
        />
        <button class="sm-button" @click="importInput?.click()">
          导入 JSON
        </button>
        <button
          class="sm-button sm-button-primary"
          :disabled="!!error"
          @click="exportConfig"
        >
          导出 JSON ↗
        </button>
      </div>
    </section>
    <div v-if="notice" class="sm-container notice" role="status">
      {{ notice }}
      <button class="sm-button" aria-label="关闭提示" @click="notice = ''">
        ×
      </button>
    </div>
    <div v-if="error || storageError" class="sm-container error" role="alert">
      {{ error ? `${error}；画面和存储保留上一次有效配置。` : storageError }}
    </div>
    <main class="sm-container workspace">
      <aside class="sm-panel sidebar">
        <div class="section-title">
          <h2>传感器</h2>
          <span>{{ config.sensors.length }} 个</span>
        </div>
        <div class="add-row">
          <select
            class="sm-control"
            v-model="addType"
            aria-label="新增传感器类型"
          >
            <option
              v-for="(label, type) in sensorNames"
              :key="type"
              :value="type"
            >
              {{ label }}
            </option>
          </select>
          <button
            class="sm-button sm-button-primary"
            :disabled="config.sensors.length >= MAX_SENSORS"
            @click="add"
          >
            ＋ 添加
          </button>
        </div>
        <div class="sensor-list">
          <div
            v-for="sensor in config.sensors"
            :key="sensor.id"
            class="sensor-item"
            :class="{ selected: selectedId === sensor.id }"
          >
            <input
              v-model="sensor.visible"
              type="checkbox"
              :aria-label="`显示 ${sensor.name}`"
            />
            <button class="sensor-select" @click="selectedId = sensor.id">
              <span
                class="sensor-dot"
                :style="{ background: sensor.color }"
              ></span>
              <span>
                <strong>{{ sensor.name || '未命名传感器' }}</strong>
                <small>
                  {{ sensorNames[sensor.type] }} · {{ sensor.range }} m
                </small>
              </span>
              <span class="chevron">›</span>
            </button>
          </div>
          <p v-if="!config.sensors.length" class="empty">
            还没有传感器。选择类型并添加。
          </p>
        </div>
        <template v-if="selected">
          <div class="section-title editor-title">
            <h2>安装参数</h2>
            <div>
              <button
                class="text-button"
                :disabled="config.sensors.length >= MAX_SENSORS"
                @click="duplicate"
              >
                复制
              </button>
              <button class="text-button danger" @click="remove">删除</button>
            </div>
          </div>
          <div class="editor" :key="selected.id">
            <label class="field">
              <span>名称</span>
              <input
                class="sm-control"
                v-model="selected.name"
                maxlength="100"
                aria-label="传感器名称"
              />
            </label>
            <div class="field-heading">
              位置
              <small>m · 相对车体原点</small>
            </div>
            <div class="triple">
              <NumberField
                v-for="(axis, i) in ['X', 'Y', 'Z']"
                :key="axis"
                v-model="selected.pos[i]!"
                :label="axis"
                :min="-1000"
                :max="1000"
                :step="0.001"
              />
            </div>
            <div class="field-heading">
              姿态
              <small>° · ZYX 欧拉角</small>
            </div>
            <div class="triple">
              <NumberField
                v-for="(axis, i) in ['Roll', 'Pitch', 'Yaw']"
                :key="axis"
                v-model="selected.rpy[i]!"
                :label="axis"
                :min="-360"
                :max="360"
                :step="1"
              />
            </div>
            <div class="field-heading">
              视场范围
              <small>
                {{
                  selected.type === 'lidar' ? '球面半径' : '沿局部 +X 轴深度'
                }}
              </small>
            </div>
            <NumberField
              v-model="selected.range"
              :label="
                selected.type === 'lidar' ? '最大距离 / m' : '前向深度 / m'
              "
              :min="0.01"
              :max="1000"
              :step="0.1"
            />
            <NumberField
              v-model="selected.hFov"
              :label="
                selected.type === 'ultrasonic' ? '圆锥全角 / °' : '水平 FOV / °'
              "
              :min="0.1"
              :max="selected.type === 'lidar' ? 360 : 179"
              :step="1"
            />
            <div v-if="selected.type === 'lidar'" class="double">
              <NumberField
                v-model="selected.vMin"
                label="仰角下限 / °"
                :min="-90"
                :max="90"
                :step="1"
              />
              <NumberField
                v-model="selected.vMax"
                label="仰角上限 / °"
                :min="-90"
                :max="90"
                :step="1"
              />
            </div>
            <NumberField
              v-if="selected.type === 'camera'"
              v-model="selected.vFov"
              label="垂直 FOV / °"
              :min="0.1"
              :max="179"
              :step="1"
            />
            <div class="appearance">
              <label class="color-field">
                颜色
                <input
                  v-model="selected.color"
                  type="color"
                  aria-label="传感器颜色"
                />
              </label>
              <label class="opacity-field">
                不透明度 {{ Math.round(selected.opacity * 100) }}%
                <input
                  v-model.number="selected.opacity"
                  type="range"
                  min="0"
                  max="1"
                  step="0.01"
                  aria-label="不透明度"
                />
              </label>
            </div>
          </div>
        </template>
        <details class="environment">
          <summary>地面与车体</summary>
          <div class="editor">
            <div class="double">
              <NumberField
                v-model="config.ground.z"
                label="地面 Z / m"
                :min="-1000"
                :max="1000"
              />
              <NumberField
                v-model="config.ground.size"
                label="地面边长 / m"
                :min="0.1"
                :max="2000"
                :step="1"
              />
            </div>
            <label class="check">
              <input v-model="config.ground.hits" type="checkbox" />
              激光与地面的交点 / 边界
            </label>
            <label class="check">
              <input v-model="config.vehicle.visible" type="checkbox" />
              显示车体
            </label>
            <NumberField
              v-model="config.vehicle.height"
              label="车体高度 / m"
              :min="0.01"
              :max="1000"
            />
            <div class="field-heading">
              车体底面中心
              <small>m</small>
            </div>
            <div class="triple">
              <NumberField
                v-for="(axis, i) in ['X', 'Y', 'Z']"
                :key="axis"
                v-model="config.vehicle.center[i]!"
                :label="`中心 ${axis}`"
                :min="-1000"
                :max="1000"
              />
            </div>
            <div class="field-heading">
              底面四个顶点
              <small>相对底面中心 / m</small>
            </div>
            <div
              v-for="(corner, i) in config.vehicle.corners"
              :key="i"
              class="double"
            >
              <NumberField
                v-model="corner[0]"
                :label="`顶点 ${i + 1} X`"
                :min="-1000"
                :max="1000"
                :step="0.001"
              />
              <NumberField
                v-model="corner[1]"
                :label="`顶点 ${i + 1} Y`"
                :min="-1000"
                :max="1000"
                :step="0.001"
              />
            </div>
          </div>
        </details>
        <button class="sm-button reset" @click="reset">
          ↺ 恢复默认双激光布局
        </button>
      </aside>
      <section class="sm-panel viewport-panel" aria-label="FOV 三维视图">
        <div class="viewport-toolbar">
          <div class="view-buttons">
            <button
              class="sm-button"
              v-for="item in [
                ['3d', '3D'],
                ['top', '俯视 XY'],
                ['front', '前视 YZ'],
                ['side', '侧视 XZ'],
              ] as const"
              :key="item[0]"
              :class="{ active: view === item[0] }"
              @click="setView(item[0])"
            >
              {{ item[1] }}
            </button>
          </div>
          <div>
            <button
              class="sm-button"
              title="显示或隐藏方向标注和传感器名称"
              @click="toggleLabels"
            >
              {{ labelsVisible ? '隐藏文字' : '显示文字' }}
            </button>
            <button class="sm-button" @click="scene?.fit()">适配视图</button>
            <button class="sm-button" @click="scene?.screenshot()">
              截图 ↓
            </button>
          </div>
        </div>
        <div class="scene-info">
          <span class="live-dot"></span>
          实时预览
          <span class="divider">/</span>
          米 · 度
          <span class="divider">/</span>
          +X 前 · +Y 左 · +Z 上
        </div>
        <div ref="host" class="canvas-host"></div>
        <div v-if="renderError" class="render-error" role="alert">
          {{ renderError }}
        </div>
        <div class="scene-legend">
          <span v-for="count in counts" :key="count.type">
            <i :class="count.type"></i>
            {{ count.label }}
            <b>{{ count.count }}</b>
          </span>
        </div>
        <div class="viewport-footer">
          <span>左键旋转 · 右键平移 · 滚轮缩放 · 点击安装点选中</span>
          <div>
            <span>显示</span>
            <select
              class="sm-control"
              aria-label="显示传感器类别"
              @change="filter(($event.target as HTMLSelectElement).value)"
            >
              <option value="all">全部传感器</option>
              <option
                v-for="(label, type) in sensorNames"
                :key="type"
                :value="type"
              >
                仅{{ label }}
              </option>
            </select>
          </div>
        </div>
      </section>
    </main>
    <footer class="sm-footer sm-container app-footer">
      <span>FOV 几何预览 · 不计算遮挡或真实探测概率</span>
      <span>所有配置在浏览器中处理 · JSON 可迁移</span>
    </footer>
  </div>
</template>
