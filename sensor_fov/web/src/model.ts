import { Euler, Quaternion, Vector3 } from 'three'

export type SensorType = 'lidar' | 'camera' | 'ultrasonic'
export type Vec3 = [number, number, number]
export interface Sensor {
  id: string
  type: SensorType
  name: string
  visible: boolean
  color: string
  opacity: number
  pos: Vec3
  rpy: Vec3
  range: number
  hFov: number
  vFov: number
  vMin: number
  vMax: number
}
export interface Config {
  version: 1
  sensors: Sensor[]
  ground: { z: number; size: number; hits: boolean }
  vehicle: { visible: boolean; center: Vec3; height: number; corners: [number, number][] }
}
export const sensorNames: Record<SensorType, string> = {
  lidar: '激光雷达', camera: '相机', ultrasonic: '超声波',
}
export const MAX_SENSORS = 100
export const radians = (degrees: number) => degrees * Math.PI / 180

// 局域网 HTTP 页面不保证有 randomUUID；getRandomValues 仍可用于生成唯一 ID。
export function newId(): string {
  if (typeof crypto.randomUUID === 'function') return crypto.randomUUID()
  return Array.from(crypto.getRandomValues(new Uint8Array(16)), b => b.toString(16).padStart(2, '0')).join('')
}

export function newSensor(type: SensorType): Sensor {
  return {
    id: newId(), type, name: sensorNames[type], visible: true,
    color: { lidar: '#32c6e6', camera: '#8ad471', ultrasonic: '#f2b853' }[type],
    opacity: 0.2, pos: [0.3, 0, 0.3], rpy: [0, 0, 0],
    range: { lidar: 3, camera: 4, ultrasonic: 2 }[type],
    hFov: type === 'lidar' ? 360 : type === 'camera' ? 86 : 60,
    vFov: 57, vMin: -7, vMax: 52,
  }
}
export function defaultConfig(): Config {
  return {
    version: 1,
    sensors: [
      { ...newSensor('lidar'), name: 'Back LiDAR', pos: [-0.161, -0.117, 0.244], rpy: [0, -15, 0] },
      { ...newSensor('lidar'), name: 'Front LiDAR', pos: [0.265, 0, 0.298], rpy: [0, 15, 0], color: '#809dff' },
    ],
    ground: { z: 0, size: 10, hits: true },
    vehicle: {
      visible: true, center: [0, 0, 0], height: 0.2,
      corners: [[0.323, 0.27], [0.323, -0.27], [-0.261, -0.27], [-0.261, 0.27]],
    },
  }
}

// ZYX 欧拉角对应列向量变换 Rz(yaw) × Ry(pitch) × Rx(roll)。
export function orientation(rpy: Vec3): Quaternion {
  return new Quaternion().setFromEuler(new Euler(...rpy.map(radians) as Vec3, 'ZYX'))
}
export function direction(azimuth: number, elevation: number): Vector3 {
  const a = radians(azimuth), e = radians(elevation)
  return new Vector3(Math.cos(e) * Math.cos(a), Math.cos(e) * Math.sin(a), Math.sin(e))
}
export function groundIntersection(origin: Vector3, ray: Vector3, range: number, z: number): Vector3 | null {
  if (Math.abs(ray.z) < 1e-8) return null
  const t = (z - origin.z) / ray.z
  return t >= 0 && t <= range ? ray.clone().multiplyScalar(t).add(origin) : null
}

function object(value: unknown, label: string): Record<string, unknown> {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) throw new Error(`${label} 必须是对象`)
  return value as Record<string, unknown>
}
function number(value: unknown, label: string, min: number, max: number): number {
  if (typeof value !== 'number' || !Number.isFinite(value) || value < min || value > max)
    throw new Error(`${label} 必须是 ${min} ～ ${max} 之间的有限数值`)
  return value
}
function boolean(value: unknown, label: string): boolean {
  if (typeof value !== 'boolean') throw new Error(`${label} 必须是布尔值`)
  return value
}
function string(value: unknown, label: string): string {
  if (typeof value !== 'string' || !value.trim() || value.length > 100) throw new Error(`${label} 必须为 1 ～ 100 字符`)
  return value
}
function vec3(value: unknown, label: string, bound: number): Vec3 {
  if (!Array.isArray(value) || value.length !== 3) throw new Error(`${label} 必须包含三个数值`)
  return value.map((v, i) => number(v, `${label}[${i}]`, -bound, bound)) as Vec3
}

// 表单、本地缓存和 JSON 导入共用校验，拒绝无效值后保留上一次有效画面。
export function parseConfig(value: unknown): Config {
  const c = object(value, '配置')
  if (c.version !== 1) throw new Error('仅支持 version: 1 配置')
  if (!Array.isArray(c.sensors) || c.sensors.length > MAX_SENSORS) throw new Error(`传感器数量须为 0 ～ ${MAX_SENSORS}`)
  const ids = new Set<string>()
  const sensors = c.sensors.map((value, i): Sensor => {
    const s = object(value, `传感器 ${i + 1}`), label = `传感器 ${i + 1}`
    const id = string(s.id, `${label} ID`)
    if (ids.has(id)) throw new Error('传感器 ID 不得重复')
    ids.add(id)
    if (!['lidar', 'camera', 'ultrasonic'].includes(s.type as string)) throw new Error(`${label} 类型无效`)
    const type = s.type as SensorType
    if (typeof s.color !== 'string' || !/^#[0-9a-f]{6}$/i.test(s.color)) throw new Error(`${label} 颜色必须是 #RRGGBB`)
    const vMin = number(s.vMin, `${label} 垂直下限`, -90, 90)
    const vMax = number(s.vMax, `${label} 垂直上限`, -90, 90)
    if (vMin >= vMax) throw new Error(`${label} 垂直下限必须小于上限`)
    return {
      id, type, name: string(s.name, `${label} 名称`), color: s.color,
      visible: boolean(s.visible, `${label} 可见性`), opacity: number(s.opacity, `${label} 透明度`, 0, 1),
      pos: vec3(s.pos, `${label} 位置`, 1000), rpy: vec3(s.rpy, `${label} 姿态`, 360),
      range: number(s.range, `${label} 距离`, 0.01, 1000),
      hFov: number(s.hFov, `${label} 水平/圆锥视场`, 0.1, type === 'lidar' ? 360 : 179),
      vFov: number(s.vFov, `${label} 垂直视场`, 0.1, 179), vMin, vMax,
    }
  })
  const g = object(c.ground, '地面'), v = object(c.vehicle, '车体')
  if (!Array.isArray(v.corners) || v.corners.length !== 4) throw new Error('车体底面需要四个 XY 顶点')
  const corners = v.corners.map((p, i): [number, number] => {
    if (!Array.isArray(p) || p.length !== 2) throw new Error(`车体顶点 ${i + 1} 须为 [x,y]`)
    return [number(p[0], '车体 X', -1000, 1000), number(p[1], '车体 Y', -1000, 1000)]
  })
  // 与旧脚本一致，按中心极角排序；同时拒绝退化和非凸四边形。
  const cx = corners.reduce((a, p) => a + p[0], 0) / 4, cy = corners.reduce((a, p) => a + p[1], 0) / 4
  corners.sort((a, b) => Math.atan2(a[1] - cy, a[0] - cx) - Math.atan2(b[1] - cy, b[0] - cx))
  for (let i = 0; i < 4; i++) {
    const a = corners[i]!, b = corners[(i + 1) % 4]!, d = corners[(i + 2) % 4]!
    if ((b[0] - a[0]) * (d[1] - b[1]) - (b[1] - a[1]) * (d[0] - b[0]) <= 1e-8)
      throw new Error('车体底面必须为非退化凸四边形')
  }
  return {
    version: 1, sensors,
    ground: { z: number(g.z, '地面 Z', -1000, 1000), size: number(g.size, '地面边长', 0.1, 2000), hits: boolean(g.hits, '地面交点') },
    vehicle: { visible: boolean(v.visible, '车体可见性'), center: vec3(v.center, '车体底面中心', 1000), height: number(v.height, '车体高度', 0.01, 1000), corners },
  }
}
