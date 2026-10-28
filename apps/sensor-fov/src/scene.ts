import * as T from 'three'
import { sceneTheme } from './theme'
import { OrbitControls } from 'three/addons/controls/OrbitControls.js'
import { direction, groundIntersection, orientation, radians } from './model'
import type { Config, Sensor } from './model'

export type View = '3d' | 'top' | 'front' | 'side'
export class FovScene {
  private theme = sceneTheme()
  private scene = new T.Scene()
  private camera = new T.PerspectiveCamera(43, 1, 0.001, 10000)
  private renderer: T.WebGLRenderer
  private controls: OrbitControls
  private content = new T.Group()
  private labels = new T.Group()
  private resize: ResizeObserver
  private onPick: (id: string) => void
  private host: HTMLElement
  private down = new T.Vector2()
  private target = new T.Vector3()
  private span = 5
  private view: View = '3d'

  constructor(host: HTMLElement, onPick: (id: string) => void) {
    this.host = host
    this.onPick = onPick
    this.renderer = new T.WebGLRenderer({
      antialias: true,
      preserveDrawingBuffer: true,
    })
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    this.renderer.setClearColor(this.theme.background)
    host.append(this.renderer.domElement)
    this.camera.up.set(0, 0, 1)
    this.camera.position.set(5, -6, 4.5)
    this.controls = new OrbitControls(this.camera, this.renderer.domElement)
    this.controls.addEventListener('change', this.render)
    this.controls.minDistance = 0.05
    this.controls.maxDistance = 5000
    this.scene.add(this.content, this.labels)
    this.scene.add(
      new T.HemisphereLight(this.theme.surface, this.theme.muted, 3),
    )
    this.resize = new ResizeObserver(() => {
      const width = Math.max(1, host.clientWidth),
        height = Math.max(1, host.clientHeight)
      this.renderer.setSize(width, height)
      this.camera.aspect = width / height
      this.camera.updateProjectionMatrix()
      this.render()
    })
    this.resize.observe(host)
    this.renderer.domElement.addEventListener('pointerdown', this.pointerDown)
    this.renderer.domElement.addEventListener('pointerup', this.pointerUp)
  }
  private render = () => this.renderer.render(this.scene, this.camera)
  private pointerDown = (e: PointerEvent) => this.down.set(e.clientX, e.clientY)
  private pointerUp = (e: PointerEvent) => {
    if (
      e.button !== 0 ||
      this.down.distanceTo(new T.Vector2(e.clientX, e.clientY)) > 5
    )
      return
    const rect = this.renderer.domElement.getBoundingClientRect()
    const ray = new T.Raycaster()
    ray.setFromCamera(
      new T.Vector2(
        ((e.clientX - rect.left) / rect.width) * 2 - 1,
        (-(e.clientY - rect.top) / rect.height) * 2 + 1,
      ),
      this.camera,
    )
    const bodies = this.content.children.filter((c) => c.userData.sensorId)
    const hit = ray.intersectObjects(bodies, false)[0]
    if (hit) this.onPick(hit.object.userData.sensorId)
  }
  private clear() {
    for (const group of [this.content, this.labels]) {
      group.traverse((object) => {
        const mesh = object as T.Mesh
        mesh.geometry?.dispose()
        if (Array.isArray(mesh.material))
          mesh.material.forEach((m) => m.dispose())
        else mesh.material?.dispose()
        if (object instanceof T.Sprite) object.material.map?.dispose()
      })
      group.clear()
    }
  }
  setLabelsVisible(visible: boolean) {
    this.labels.visible = visible
    this.render()
  }

  private mesh(
    points: T.Vector3[],
    indices: number[],
    color: string,
    opacity: number,
    parent = this.content,
  ) {
    const geometry = new T.BufferGeometry().setFromPoints(points)
    geometry.setIndex(indices)
    geometry.computeVertexNormals()
    const mesh = new T.Mesh(
      geometry,
      new T.MeshBasicMaterial({
        color,
        transparent: true,
        opacity,
        side: T.DoubleSide,
        depthWrite: false,
      }),
    )
    parent.add(mesh)
    return mesh
  }
  private line(points: T.Vector3[], color: string, parent = this.content) {
    parent.add(
      new T.Line(
        new T.BufferGeometry().setFromPoints(points),
        new T.LineBasicMaterial({ color, transparent: true, opacity: 0.8 }),
      ),
    )
  }
  private label(text: string, position: T.Vector3, color: string) {
    const canvas = document.createElement('canvas')
    canvas.width = 512
    canvas.height = 64
    const ctx = canvas.getContext('2d')!
    ctx.font = '26px sans-serif'
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    ctx.fillStyle = color
    ctx.fillText(text.slice(0, 28), 256, 32, 500)
    const texture = new T.CanvasTexture(canvas)
    const sprite = new T.Sprite(
      new T.SpriteMaterial({
        map: texture,
        transparent: true,
        depthTest: false,
        depthWrite: false,
      }),
    )
    sprite.position.copy(position)
    sprite.scale.set(0.9, 0.1125, 1)
    this.labels.add(sprite)
  }
  update(config: Config, selected: string) {
    this.clear()
    const g = config.ground
    const grid = new T.GridHelper(
      g.size,
      20,
      this.theme.muted,
      this.theme.border,
    )
    grid.rotation.x = Math.PI / 2
    grid.position.z = g.z
    this.content.add(grid)
    const plane = new T.Mesh(
      new T.PlaneGeometry(g.size, g.size),
      new T.MeshBasicMaterial({
        color: this.theme.border,
        transparent: true,
        opacity: 0.22,
        side: T.DoubleSide,
        depthWrite: false,
      }),
    )
    plane.position.z = g.z - 0.003
    this.content.add(plane)
    const axes = new T.AxesHelper(0.65)
    axes.position.z = g.z + 0.01
    this.content.add(axes)
    this.label('X 前', new T.Vector3(0.8, 0, g.z + 0.03), this.theme.danger)
    this.label('Y 左', new T.Vector3(0, 0.8, g.z + 0.03), this.theme.accent)
    this.label('Z 上', new T.Vector3(0, 0, g.z + 0.85), this.theme.info)
    const v = config.vehicle
    if (v.visible) {
      const bottom = v.corners.map(([x, y]) =>
        new T.Vector3(x, y, 0).add(new T.Vector3(...v.center)),
      )
      const points = [
        ...bottom,
        ...bottom.map((p) => p.clone().add(new T.Vector3(0, 0, v.height))),
      ]
      const indices = [0, 2, 1, 0, 3, 2, 4, 5, 6, 4, 6, 7]
      for (let i = 0; i < 4; i++) {
        const j = (i + 1) % 4
        indices.push(i, j, i + 4, j, j + 4, i + 4)
        this.line(
          [points[i]!, points[j]!, points[j + 4]!, points[i + 4]!, points[i]!],
          this.theme.muted,
        )
      }
      this.mesh(points, indices, this.theme.info, 0.45).userData.fit = true
    }
    for (const sensor of config.sensors.filter((s) => s.visible))
      this.sensor(sensor, config, sensor.id === selected)
    const bounds = new T.Box3()
    for (const child of this.content.children.filter((c) => c.userData.fit))
      bounds.union(new T.Box3().setFromObject(child))
    if (bounds.isEmpty())
      bounds.set(new T.Vector3(-1, -1, 0), new T.Vector3(1, 1, 1))
    bounds.getCenter(this.target)
    this.span = Math.max(1, bounds.getSize(new T.Vector3()).length() * 0.55)
    this.camera.far = Math.max(10000, this.span * 100)
    this.camera.updateProjectionMatrix()
    this.controls.maxDistance = Math.max(5000, this.span * 20)
    this.render()
  }
  private sensor(s: Sensor, config: Config, selected: boolean) {
    const group = new T.Group()
    group.userData.fit = true
    group.position.set(...s.pos)
    group.quaternion.copy(orientation(s.rpy))
    this.content.add(group)
    const body = new T.Mesh(
      new T.SphereGeometry(selected ? 0.055 : 0.035, 16, 10),
      new T.MeshBasicMaterial({ color: selected ? this.theme.text : s.color }),
    )
    body.position.set(...s.pos)
    body.userData.sensorId = s.id
    this.content.add(body)
    const axes = new T.AxesHelper(selected ? 0.3 : 0.15)
    group.add(axes)
    this.label(
      s.name,
      new T.Vector3(...s.pos).add(new T.Vector3(0, 0, 0.12)),
      this.theme.text,
    )
    if (s.type === 'lidar') this.lidar(s, group, config)
    else if (s.type === 'camera') this.cameraFov(s, group)
    else this.ultrasonic(s, group)
  }
  private lidar(s: Sensor, parent: T.Group, config: Config) {
    const rows = 20,
      cols = 96
    const points: T.Vector3[] = [],
      indices: number[] = []
    for (let i = 0; i <= rows; i++)
      for (let j = 0; j <= cols; j++) {
        points.push(
          direction(
            -s.hFov / 2 + (s.hFov * j) / cols,
            s.vMin + ((s.vMax - s.vMin) * i) / rows,
          ).multiplyScalar(s.range),
        )
        if (i < rows && j < cols) {
          const a = i * (cols + 1) + j,
            b = a + cols + 1
          indices.push(a, a + 1, b, a + 1, b + 1, b)
        }
      }
    this.mesh(points, indices, s.color, s.opacity, parent)
    for (const elevation of [s.vMin, s.vMax]) {
      const edge = Array.from({ length: cols + 1 }, (_, j) =>
        direction(-s.hFov / 2 + (s.hFov * j) / cols, elevation).multiplyScalar(
          s.range,
        ),
      )
      this.line(edge, s.color, parent)
      // 上下边界从球心展开，构成球带的径向边界面。
      const cap = [new T.Vector3(), ...edge],
        triangles: number[] = []
      for (let j = 1; j < cap.length - 1; j++) triangles.push(0, j, j + 1)
      this.mesh(cap, triangles, s.color, s.opacity * 0.45, parent)
    }
    if (s.hFov < 360)
      for (const azimuth of [-s.hFov / 2, s.hFov / 2]) {
        const edge = Array.from({ length: rows + 1 }, (_, i) =>
          direction(
            azimuth,
            s.vMin + ((s.vMax - s.vMin) * i) / rows,
          ).multiplyScalar(s.range),
        )
        const face = [new T.Vector3(), ...edge],
          triangles: number[] = []
        for (let i = 1; i < face.length - 1; i++) triangles.push(0, i, i + 1)
        this.mesh(face, triangles, s.color, s.opacity * 0.5, parent)
        this.line([new T.Vector3(), ...edge, new T.Vector3()], s.color, parent)
      }
    if (!config.ground.hits) return
    const origin = new T.Vector3(...s.pos),
      rotation = orientation(s.rpy)
    const hitPoints: T.Vector3[] = []
    for (let i = 0; i <= 48; i++)
      for (let j = 0; j <= 180; j++) {
        const ray = direction(
          -s.hFov / 2 + (s.hFov * j) / 180,
          s.vMin + ((s.vMax - s.vMin) * i) / 48,
        ).applyQuaternion(rotation)
        const hit = groundIntersection(origin, ray, s.range, config.ground.z)
        if (hit) {
          hit.z += 0.008
          hitPoints.push(hit)
        }
      }
    this.content.add(
      new T.Points(
        new T.BufferGeometry().setFromPoints(hitPoints),
        new T.PointsMaterial({
          color: s.color,
          size: 2.5,
          sizeAttenuation: false,
          depthWrite: false,
        }),
      ),
    )
    for (const elevation of [s.vMin, s.vMax]) {
      let line: T.Vector3[] = []
      for (let j = 0; j <= 360; j++) {
        const ray = direction(
          -s.hFov / 2 + (s.hFov * j) / 360,
          elevation,
        ).applyQuaternion(rotation)
        const hit = groundIntersection(origin, ray, s.range, config.ground.z)
        if (hit) {
          hit.z += 0.012
          line.push(hit)
        } else {
          if (line.length > 1) this.line(line, s.color)
          line = []
        }
      }
      if (line.length > 1) this.line(line, s.color)
    }
  }
  private cameraFov(s: Sensor, parent: T.Group) {
    const y = s.range * Math.tan(radians(s.hFov / 2)),
      z = s.range * Math.tan(radians(s.vFov / 2))
    const p = [
      new T.Vector3(),
      new T.Vector3(s.range, y, z),
      new T.Vector3(s.range, -y, z),
      new T.Vector3(s.range, -y, -z),
      new T.Vector3(s.range, y, -z),
    ]
    this.mesh(
      p,
      [0, 1, 2, 0, 2, 3, 0, 3, 4, 0, 4, 1, 1, 4, 3, 1, 3, 2],
      s.color,
      s.opacity,
      parent,
    )
    this.line([p[1]!, p[2]!, p[3]!, p[4]!, p[1]!], s.color, parent)
    for (let i = 1; i < 5; i++) this.line([p[0]!, p[i]!], s.color, parent)
  }
  private ultrasonic(s: Sensor, parent: T.Group) {
    const radius = s.range * Math.tan(radians(s.hFov / 2))
    const ring = Array.from(
      { length: 65 },
      (_, i) =>
        new T.Vector3(
          s.range,
          radius * Math.cos((i * Math.PI) / 32),
          radius * Math.sin((i * Math.PI) / 32),
        ),
    )
    const p = [new T.Vector3(), new T.Vector3(s.range, 0, 0), ...ring],
      indices: number[] = []
    for (let i = 2; i < p.length - 1; i++)
      indices.push(0, i, i + 1, 1, i + 1, i)
    this.mesh(p, indices, s.color, s.opacity, parent)
    this.line(ring, s.color, parent)
    for (const i of [0, 16, 32, 48])
      this.line([new T.Vector3(), ring[i]!], s.color, parent)
  }
  setView(view: View) {
    this.view = view
    const offsets: Record<View, T.Vector3> = {
      '3d': new T.Vector3(1, -1.3, 0.9).normalize(),
      top: new T.Vector3(0, 0, 1),
      front: new T.Vector3(1, 0, 0),
      side: new T.Vector3(0, -1, 0),
    }
    this.camera.up.set(0, view === 'top' ? 1 : 0, view === 'top' ? 0 : 1)
    this.camera.position
      .copy(this.target)
      .addScaledVector(
        offsets[view],
        (this.span * Math.max(1, 1 / this.camera.aspect)) /
          Math.tan(radians(this.camera.fov / 2)),
      )
    this.controls.target.copy(this.target)
    this.controls.update()
    this.render()
  }
  fit() {
    this.setView(this.view)
  }
  screenshot() {
    this.render()
    const a = document.createElement('a')
    a.download = 'sensor-fov.png'
    a.href = this.renderer.domElement.toDataURL('image/png')
    a.click()
  }
  dispose() {
    this.resize.disconnect()
    this.controls.removeEventListener('change', this.render)
    this.controls.dispose()
    this.renderer.domElement.removeEventListener(
      'pointerdown',
      this.pointerDown,
    )
    this.renderer.domElement.removeEventListener('pointerup', this.pointerUp)
    this.clear()
    this.renderer.dispose()
    this.host.replaceChildren()
  }
}
