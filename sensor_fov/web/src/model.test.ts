import { test } from 'node:test'
import assert from 'node:assert/strict'
import { Vector3 } from 'three'
import { defaultConfig, direction, groundIntersection, newSensor, orientation, parseConfig } from './model'

const near = (a: number, b: number) => assert.ok(Math.abs(a - b) < 1e-9, `${a} != ${b}`)
test('默认布局保持原脚本的双激光位置、姿态和车体尺寸', () => {
  const c = parseConfig(defaultConfig())
  assert.equal(c.sensors.length, 2)
  assert.deepEqual(c.sensors[0]!.pos, [-0.161, -0.117, 0.244])
  assert.deepEqual(c.sensors[1]!.rpy, [0, 15, 0])
  assert.equal(c.vehicle.height, 0.2)
})
test('ZYX 旋转组合遵循 Rz × Ry × Rx，正 pitch 将 +X 朝向地面', () => {
  const p = new Vector3(1, 0, 0).applyQuaternion(orientation([0, 15, 0]))
  near(p.z, -Math.sin(Math.PI / 12))
  const q = new Vector3(1, 2, 3).applyQuaternion(orientation([90, 90, 90]))
  near(q.x, 3); near(q.y, 2); near(q.z, -1)
})
test('激光射线为单位向量，水平 FOV 中心为 +X', () => {
  near(direction(20, 52).length(), 1)
  assert.deepEqual(direction(0, 0).toArray(), [1, 0, 0])
  near(direction(90, 0).y, 1)
})
test('落地只接受前向、非平行且球面距离内的交点', () => {
  const p = new Vector3(0, 0, 1)
  assert.deepEqual(groundIntersection(p, new Vector3(0, 0, -1), 1, 0)?.toArray(), [0, 0, 0])
  assert.equal(groundIntersection(p, new Vector3(1, 0, 0), 2, 0), null)
  assert.equal(groundIntersection(p, new Vector3(0, 0, 1), 2, 0), null)
  assert.equal(groundIntersection(p, new Vector3(0, 0, -1), 0.99, 0), null)
  const tilted = direction(0, -30)
  assert.equal(groundIntersection(p, tilted, 1.9, 0), null)
  near(groundIntersection(p, tilted, 2.01, 0)!.x, Math.sqrt(3))
})
test('三类传感器、空列表、完整 JSON 往返', () => {
  const c = defaultConfig()
  c.sensors.push(newSensor('camera'), newSensor('ultrasonic'))
  const normalized = parseConfig(c)
  assert.deepEqual(parseConfig(JSON.parse(JSON.stringify(normalized))), normalized)
  c.sensors = []
  assert.equal(parseConfig(c).sensors.length, 0)
})
test('拒绝非有限数值、非法角度、反向垂直范围和重复 ID', () => {
  for (const value of [NaN, Infinity, -1, 0]) {
    const c = defaultConfig(); c.sensors[0]!.range = value
    assert.throws(() => parseConfig(c))
  }
  const c = defaultConfig()
  c.sensors[0]!.vMin = c.sensors[0]!.vMax
  assert.throws(() => parseConfig(c), /下限/)
  const d = defaultConfig(); d.sensors[1]!.id = d.sensors[0]!.id
  assert.throws(() => parseConfig(d), /重复/)
  for (const type of ['camera', 'ultrasonic'] as const) {
    const e = defaultConfig(); e.sensors.push({ ...newSensor(type), hFov: 180 })
    assert.throws(() => parseConfig(e), /视场/)
  }
})
test('拒绝错误结构、超量配置和退化车体', () => {
  for (const value of [null, [], { version: 2 }, { version: 1, sensors: new Array(101).fill({}) }]) assert.throws(() => parseConfig(value))
  const c = defaultConfig(); c.vehicle.corners[0] = c.vehicle.corners[1]!
  assert.throws(() => parseConfig(c), /凸四边形/)
  const d = defaultConfig(); d.sensors[0]!.color = 'red'
  assert.throws(() => parseConfig(d), /颜色/)
})
