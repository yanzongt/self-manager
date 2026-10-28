# Self Manager · 个人工具主页

统一访问行为闭环（PDCA）、力量训练、日常打卡、投资回测和传感器视场的本机工具。电脑与手机宽度均可使用，各工具均可返回个人主页。

## 启动

在仓库根目录执行：

```sh
./setup.sh       # 安装投资模块 Python 依赖，需要 uv 和 Python 3.13+
./start.sh
```

首次启动会使用 Node.js（22.12+）和 npm 安装并构建 PDCA、力量训练、投资回测、打卡与传感器视场前端；之后启动使用本机构建结果。自动打开 <http://127.0.0.1:8765>。只启动一个进程、监听一个端口，无需分别启动回测服务。两个脚本均支持从任意目录调用。

| 入口 | 地址 |
| --- | --- |
| 个人主页 | <http://127.0.0.1:8765/> |
| 行为闭环 · PDCA | <http://127.0.0.1:8765/pdca/> |
| 力量进阶 | <http://127.0.0.1:8765/strength/> |
| 日常打卡 | <http://127.0.0.1:8765/checkins/> |
| 投资回测 | <http://127.0.0.1:8765/investment/> |
| 传感器视场 | <http://127.0.0.1:8765/sensor-fov/> |

`setup.sh` 使用 `apps/investment/pyproject.toml` 和 `uv.lock`，将依赖安装到仓库根目录的 `.venv/`。`start.sh` 优先使用此环境，也兼容投资模块独立安装的 `.venv/`。缺少回测依赖时，仍可用系统 Python 启动首页、PDCA 和力量训练，首页会提示回测未就绪。

启动参数透传给服务器：`./start.sh --no-browser` 不打开浏览器；`./start.sh --port 8877` 更换端口；`--data-file /path/to/pdca.json` 指定 PDCA 数据文件。也可执行 `.venv/bin/python serve.py`。

启动时若端口被占用，会打印端口号及占用进程的 PID（优先使用 `ss`，否则尝试 `lsof`），然后退出；不会自动终止进程。若权限不足或工具不可用，会提示无法获取 PID。可通过 `./start.sh --port 8877` 更换端口。

服务仅监听 `127.0.0.1`，用于本机访问。原 `/pdca_focus.html` 和 `/strength_training_tracker.html` 地址继续可用。保持相同浏览器、域名和端口，力量训练会继续读取原有浏览器数据；若以前直接打开 HTML 或用其他端口，请先在原地址导出完整备份，再在新入口导入。

## 目录结构

```text
self-manager/
├── start.sh                 # 统一启动入口
├── setup.sh                 # 锁定依赖安装入口
├── serve.py                 # HTTP 路由、本机存储和提醒调度
├── apps/
│   ├── portal/index.html    # 个人主页
│   ├── pdca/                # 行为闭环（Vue + TypeScript + Vite）
│   ├── strength/           # 力量训练（Vue + TypeScript + Vite）
│   ├── checkins/            # 日常打卡（Vue + TypeScript + Vite）
│   ├── sensor-fov/          # 传感器视场（Vue + TypeScript + Three.js）
│   └── investment/          # Vue + TypeScript + Vite 前端与独立 Python 项目
│       ├── src/             # Vue 组件、类型模型与 API 数据访问
│       ├── f_analysis/      # Python 回测引擎与服务
│       ├── scripts/         # 命令行与独立服务
│       ├── configs/         # 内置股票池
│       ├── tests/           # 投资模块测试
│       ├── data/            # 行情缓存和自建股票池（本机数据）
│       └── outputs/         # 回测结果，含原有 legacy CSV
├── tests/                   # 统一服务、PDCA 和力量训练测试
├── docs/                    # 使用说明与目录迁移说明
├── data/                    # PDCA 本机数据（不提交）
└── .venv/                   # 统一 Python 环境（不提交）
```

按功能归置源码；投资模块内部保留原有包名、命令行接口和依赖锁定。服务以仓库位置解析资源和默认数据路径，不依赖启动时的工作目录。

## 数据与使用说明

| 内容 | 保存位置 / 说明 |
| --- | --- |
| PDCA 会话、任务、评论、设置 | `data/pdca.json`，上一版为 `data/pdca.json.bak` |
| 打卡事项、计次记录与计时记录 | `data/checkins.json`，上一版为 `data/checkins.json.bak` |
| 力量训练记录 | 当前访问地址的浏览器存储，使用页面备份功能导出 |
| 传感器布局 | 当前访问地址的浏览器存储，使用传感器页面导出 JSON |
| 行情缓存与自建股票池 | `apps/investment/data/` |
| 投资回测结果 | `apps/investment/outputs/` |

备份时保留上述本机数据与结果，并导出力量训练记录。不要清除浏览器数据后才备份。

- [行为闭环：提醒、存储、番茄钟、四象限与统计](docs/pdca.md)
- [投资分析：环境、网页、CLI、策略与结果说明](apps/investment/README.md)（其中的命令从 `apps/investment/` 执行）
- [传感器视场：使用、坐标约定与开发](apps/sensor-fov/README.md)
- [本次目录整理与路径对应](docs/layout.md)

## 验证

以下命令从仓库根目录执行，使用临时数据或模拟行情：

```sh
./apps/strength/setup.sh
npm run build --prefix apps/strength
npm test --prefix apps/strength
./apps/investment/setup.sh
npm run build --prefix apps/investment
npm test --prefix apps/investment
./apps/pdca/setup.sh
npm run build --prefix apps/pdca
npm test --prefix apps/pdca
./apps/checkins/setup.sh
npm run build --prefix apps/checkins
npm test --prefix apps/checkins
./apps/sensor-fov/setup.sh
npm run build --prefix apps/sensor-fov
npm test --prefix apps/sensor-fov
.venv/bin/python -m unittest discover -s tests -v
(cd apps/investment && ../../.venv/bin/python -m unittest discover -s tests -v)
```

前端浏览器测试使用临时数据，需要本机 Chrome：

```sh
npm run test:browser --prefix apps/strength
npm run test:browser --prefix apps/investment
npm run test:browser --prefix apps/pdca
npm run test:storage --prefix apps/pdca
npm run test:browser --prefix apps/checkins
npm run test:browser --prefix apps/sensor-fov
```

力量训练的浏览器交互验证可复用已安装的 Playwright：

```sh
PLAYWRIGHT_CORE="$PWD/apps/pdca/.generated/node_modules/playwright-core" node tests/test_strength.js
```

投资网页使用真实 Chromium 与模拟 API 进行交互回归，见投资模块说明。

## 日常打卡

在首页进入“日常打卡”，添加事项时选择“按次数”或“按时间”。计次事项点击 `+1` 保存一次打卡时间并更新累计次数；计时事项点击开始，再次点击结束，保存起止时间。刷新或关闭页面不终止计时，重新打开后可结束。

页面展示今日汇总、每个事项的累计值与完整记录，以及最近 7 / 30 天的每日次数和时长图表，可筛选单个事项。统计使用浏览器本地时区，跨午夜的计时按每天实际经过的时长拆分；进行中的计时也计入统计。数据使用独立 JSON 文件保存，支持原子写入、上一版备份及多页面冲突检测。若提示保存失败，请刷新读取最新记录后再操作。自定义 `--data-file` 时，打卡文件位于指定 PDCA 文件的同一目录，文件名为 `checkins.json`。

打卡前端源码位于 `apps/checkins/src/`，使用 Vue、TypeScript 和 Vite。生成的 npm 依赖、锁文件和构建产物存放在 `apps/checkins/.generated/`，不纳入 Git；`node_modules` 是指向该目录的本地链接。首次运行 `./start.sh` 会自动安装依赖并构建；修改前端源码后需运行 `npm run build --prefix apps/checkins`。直接运行 `serve.py` 前也需先构建。锁文件不纳入 Git，因此不同机器首次安装的间接依赖版本可能不同。浏览器测试默认使用 `/usr/bin/google-chrome`，可通过 `CHROME` 指定路径。

## PDCA 前端开发

PDCA 的入口为 `apps/pdca/src/App.vue`，计划、四象限、统计、历史和复盘界面位于 `src/components/`。文件存储、通知、会话和番茄钟分别由 `useStorage.ts`、`useNotifications.ts`、`useSession.ts` 和 `usePomodoro.ts` 管理；数据类型、旧备份兼容与纯计时算法独立维护。

首次运行 `./start.sh` 会安装并构建缺失的前端。修改 PDCA 源码后运行 `npm run build --prefix apps/pdca`，刷新 `/pdca/` 即可查看。可运行 `npm run format --prefix apps/pdca` 统一格式。直接运行 `serve.py` 前需先构建；缺少构建时返回明确的 503 提示，数据 API 仍可用。

PDCA 的依赖、自动生成的锁文件和构建结果均放在 `apps/pdca/.generated/`，由 Git 忽略，`node_modules` 仅为指向该目录的本地链接。已有 `/pdca/`、`/pdca_focus.html` 地址、接口、浏览器旧数据键和 JSON 备份格式继续可用。浏览器测试默认使用 `/usr/bin/google-chrome`，可通过 `CHROME_PATH` 指定路径；`PLAYWRIGHT_CORE` 可覆盖 Playwright 模块位置。

## 页面统一风格

主页、PDCA、打卡和传感器视场共同引用 `apps/shared/theme.css`，统一采用米白背景、深绿文字、柔和绿色点缀和浅色卡片。新增页面应使用共享的 `sm-*` 布局和控件类，避免另设全站字体和配色。开发要求见 [AGENTS.md](AGENTS.md)，样式约定和新增页面模板见 [统一风格说明](docs/ui-style.md)。修改共享主题后，需要重新构建 PDCA、打卡与传感器视场前端。

## 力量训练与投资前端开发

两个模块均使用 Vue 3、严格 TypeScript 和 Vite，入口位于各自的 `src/main.ts`。`src/model.ts` 负责类型、校验和兼容转换，`useStrength.ts` / `useInvestment.ts` 管理数据与持久化，组件负责各业务视图。投资回测算法、Python CLI 和数据目录继续沿用原实现。

依赖、npm 锁文件和构建产物均位于模块内忽略的 `.generated/`，`node_modules` 为本地符号链接。运行模块内 `setup.sh` 安装依赖，修改源码后执行 `npm run build --prefix apps/strength` 或 `npm run build --prefix apps/investment`。`start.sh` 首次启动会自动构建；直接运行 Python 服务前需自行构建。两个页面首先加载共享 `apps/shared/theme.css`，图表共用 `apps/shared/LineChart.vue`。

力量训练保持 `strengthTracker_v1` 存储键，兼容旧版重量数据及 v1/v2 JSON 备份；投资页面保持草稿和后台任务的存储键，可继续打开已有回测结果。Vite 开发时力量训练 API 代理指向统一服务 8765，投资代理指向独立回测服务 8766。可使用 `apps/<模块>/.generated/node_modules/.bin/vite apps/<模块>` 启动开发服务器。
