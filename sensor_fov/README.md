# Sensor FOV 传感器布局工作台

推荐使用 `web/` 中的 Vue 网页：在浏览器里添加、复制、删除激光雷达、相机、超声波传感器，修改位置、姿态、FOV 与距离，实时更新 3D 视图。无需先运行 Python 生成 HTML。

## 启动

需要 **Node.js >= 22.12 和 npm**。首次构建需要联网下载 npm 依赖；后续浏览器运行完全使用本地静态资源，不依赖 CDN、ROS、Python 或后端 API。

```bash
cd /root/era_nav_algo_ws/src/LiDAR/lidar_common/experiment/scripts/sensor_fov
./serve.sh
```

脚本安装缺失/变更的依赖，进行 TypeScript 检查和生产构建，启动 HTTP 服务，尝试打开系统浏览器。默认地址 **http://127.0.0.1:8080/**；无桌面环境时打印地址，按 `Ctrl+C` 停止。端口被占用时直接报错，不会切换到其他端口。

```bash
# 指定端口，不打开浏览器
./serve.sh --port 9090 --no-open

# 让局域网其他设备访问：http://<本机IP>:8080/
./serve.sh --host 0.0.0.0 --no-open

# 前端开发，修改源码后自动更新
./serve.sh --dev --port 5173

# 只生成 web/dist
./serve.sh --build-only

# 直接部署已构建的文件，不调用 npm、不需要联网
./serve.sh --no-build --no-open

./serve.sh --help
```

SSH 远程机器可使用 `ssh -L 8080:127.0.0.1:8080 user@host`，然后在本地浏览器打开 `http://127.0.0.1:8080/`。该静态服务默认只监听本机，无鉴权；`--host 0.0.0.0` 用于受信任网络。

生产部署也可把 `web/dist/` 整个目录交给 Nginx/Caddy 等静态服务器；只需要这些构建产物，Node/npm 不属于浏览器运行时依赖。不要直接双击 `dist/index.html`，应通过 HTTP 访问。`base: './'` 支持部署到静态子目录。

## 网页使用

- 左侧选择类型并添加传感器，数量由列表决定，支持 0 ～ 100 个。
- 每个传感器可编辑名称、XYZ、Roll/Pitch/Yaw、距离、FOV、颜色和不透明度；选中后可以复制或删除。复选框控制显示。
- 激光雷达可编辑水平全角与垂直仰角上下限；相机可编辑水平/垂直全角；超声波可编辑圆锥全角。
- 展开“地面与车体”可编辑地面高度、尺寸、激光落地点，以及车体底面中心、四个 XY 顶点和高度。四个顶点自动按极角排序，必须形成非退化凸四边形。
- 顶部切换 3D、俯视、前视、侧视，支持适配视图和 PNG 截图；右下角可仅显示某类传感器。
- 左键旋转，右键平移，滚轮缩放；点击安装点也可选中传感器。
- 编辑期间保留观察视角。布局变化后可点击“适配视图”；导入/恢复默认布局会自动适配。

有效配置会在编辑停止约 100 ms 后保存到浏览器 `localStorage`，刷新恢复。它按 **协议、主机和端口** 区分，换地址或换浏览器不会共享配置。无法使用本地存储时显示提示，仍可手动导出 JSON。JSON 导入会整体替换当前配置，不合并列表；建议先导出当前方案。默认布局恢复操作有确认提示。

JSON 文件包含 `version: 1`、`sensors`、`ground` 和 `vehicle`，导出的文件就是完整示例。导入限 1 MB，严格检查字段、有限数值、角度范围、数量和唯一 ID。非法导入保留原配置；表单临时无效时提示原因，画面/存储保留上一次有效值，修正后继续更新。导入导出仅针对新网页的 JSON 格式。

## 几何约定

- 位置单位 **m**，姿态/FOV 单位 **°**，坐标为 **X 前、Y 左、Z 上**。传感器位置相对于世界/车体原点；移动车体盒子不联动传感器位置。
- 局部点通过 `p_world = Rz(yaw) × Ry(pitch) × Rx(roll) × p_local + pos` 变换，与 `sensor_vis.py` 一致。正 Pitch 会将局部 +X 轴向下转。
- **LiDAR**：方位角以局部 +X 为中心，范围 `[-水平FOV/2, +水平FOV/2]`；垂直角为相对局部 XY 平面的仰角，支持非对称上下限。距离为球面半径，水平全角可到 360°。
- **相机**：以局部 +X 为前向，四棱锥底面位于 `x = d`，半宽 `d × tan(hFov/2)`，半高 `d × tan(vFov/2)`。深度不是角点到光心的球面距离。这里不是 ROS 相机 optical frame（Z 前、X 右、Y 下），使用 optical frame 外参前需要转换。
- **超声波**：沿局部 +X 展开的圆锥，底面 `x = d`、半径 `d × tan(fov/2)`。深度不是圆锥侧面长度；保持旧脚本的几何含义。
- 相机/超声波全角限制为 0.1 ～ 179°，避免 `tan(90°)` 发散。距离允许 0.01 ～ 1000 m；激光垂直角在 ±90° 内且下限小于上限。
- 激光落地采样使用当前位姿、当前 FOV 和**同一个最大距离**，仅保留 `t >= 0` 且 `t <= range` 的射线交点。地面边长只影响参考网格，不裁剪交点。旧脚本的 FOV 半径为 3 m、落地距离为 2.5 m；新实现统一采用可编辑的 3 m 默认值。
- 默认仍是原脚本实际启用的双激光布局，车体底面 X 范围 `[-0.261, 0.323]`、Y 范围 `[-0.27, 0.27]`、高度 `0.2 m`，相机/超声波通过“添加”启用。

视场为理想几何包络，地面交点是离散采样，无遮挡裁剪、探测概率、测距误差或多传感器融合。不代表真实探测结果。

## 技术栈选择

采用 **Vue 3 + TypeScript + Vite + Three.js**，纯前端、无服务端状态。

| 方案 | 适用性 |
| --- | --- |
| Vue + TypeScript + Vite | Vue 响应式表单适合频繁编辑多组传感器；TypeScript 定义配置与校验边界；Vite 支持开发热更新和静态打包。无需 Router、Pinia 或 SSR。 |
| Three.js | 直接维护球带、视锥、圆锥和车体几何，支持 Z-up、交互相机与 PNG 截图；比图表式场景更适合后续增加模型、拖动等空间编辑能力。 |
| Vue + Plotly.js | 如果主要目标是图表、坐标刻度和最小化迁移，仍是可行方案；本次以空间布局编辑为主选用 Three.js。 |
| 原生 HTML/JS | 最小原型更轻，但参数校验、列表选择、存储和 UI 状态增多后，Vue 更便于维护。 |
| Python / Streamlit / Dash | 可复用 Python 几何，但在线编辑需要常驻 Python 服务；本工具的计算完全可在浏览器完成，因此无需引入。 |

参考：[Vue TypeScript 官方说明](https://vuejs.org/guide/typescript/overview)、[Vite 静态部署](https://vite.dev/guide/static-deploy.html)、[Three.js OrbitControls](https://threejs.org/docs/pages/OrbitControls.html)。

## 代码与检查

- `serve.sh`：安装依赖、开发/构建/静态启动入口。
- `web/server.mjs`：零依赖 Node HTTP 静态服务器，只服务 `web/dist`，支持 GET/HEAD。
- `web/src/App.vue`：参数编辑、选择、配置存储与导入导出。
- `web/src/model.ts`：类型、默认布局、校验、ZYX 变换和射线落地计算。
- `web/src/scene.ts`：Three.js 几何、相机、拾取、地面交点、截图及资源释放。
- `web/src/NumberField.vue`：数值输入。
- `web/src/style.css`：桌面和窄屏布局。

```bash
cd web
npm ci
npm test           # 几何与配置校验回归
npm run build     # Vue/TypeScript 类型检查与静态构建
```

`package-lock.json` 固定依赖解析结果；`node_modules`、`dist` 不入版本控制。浏览器需要 WebGL 2。

## 原 Python 工具

保留 `sensor_vis.py`（Plotly HTML 导出）和 `sensor_vis_matplot.py`（Matplotlib 静态多视图）供历史工作流使用，其配置依然需要在 Python 中编辑，不是新网页的运行依赖。

```bash
pip install numpy plotly matplotlib
python3 sensor_vis.py                  # 在当前目录生成 sensor_fov_vis.html，不自动打开
python3 sensor_vis_matplot.py --save   # 保存 sensor_fov_multi_view.png
```
