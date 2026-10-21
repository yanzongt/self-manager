# Self Manager · 个人工具主页

统一访问行为闭环（PDCA）、力量训练和投资回测的本机工具。电脑与手机宽度均可使用，各工具均可返回个人主页。

## 启动

在仓库根目录执行：

```sh
./setup.sh       # 首次安装或更新锁定依赖，需要 uv 和 Python 3.13+
./start.sh
```

自动打开 <http://127.0.0.1:8765>。只启动一个进程、监听一个端口，无需分别启动回测服务。两个脚本均支持从任意目录调用。

| 入口 | 地址 |
| --- | --- |
| 个人主页 | <http://127.0.0.1:8765/> |
| 行为闭环 · PDCA | <http://127.0.0.1:8765/pdca/> |
| 力量进阶 | <http://127.0.0.1:8765/strength/> |
| 投资回测 | <http://127.0.0.1:8765/investment/> |

`setup.sh` 使用 `apps/investment/pyproject.toml` 和 `uv.lock`，将依赖安装到仓库根目录的 `.venv/`。`start.sh` 优先使用此环境，也兼容投资模块独立安装的 `.venv/`。缺少回测依赖时，仍可用系统 Python 启动首页、PDCA 和力量训练，首页会提示回测未就绪。

启动参数透传给服务器：`./start.sh --no-browser` 不打开浏览器；`./start.sh --port 8877` 更换端口；`--data-file /path/to/pdca.json` 指定 PDCA 数据文件。也可执行 `.venv/bin/python serve.py`。

服务仅监听 `127.0.0.1`，用于本机访问。原 `/pdca_focus.html` 和 `/strength_training_tracker.html` 地址继续可用。保持相同浏览器、域名和端口，力量训练会继续读取原有浏览器数据；若以前直接打开 HTML 或用其他端口，请先在原地址导出完整备份，再在新入口导入。

## 目录结构

```text
self-manager/
├── start.sh                 # 统一启动入口
├── setup.sh                 # 锁定依赖安装入口
├── serve.py                 # HTTP 路由、本机存储和提醒调度
├── apps/
│   ├── portal/index.html    # 个人主页
│   ├── pdca/index.html      # 行为闭环
│   ├── strength/index.html  # 力量训练
│   └── investment/          # 原 f-analysis，保留独立 Python 项目
│       ├── f_analysis/      # 回测引擎和网页资源
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
| 力量训练记录 | 当前访问地址的浏览器存储，使用页面备份功能导出 |
| 行情缓存与自建股票池 | `apps/investment/data/` |
| 投资回测结果 | `apps/investment/outputs/` |

备份时保留上述本机数据与结果，并导出力量训练记录。不要清除浏览器数据后才备份。

- [行为闭环：提醒、存储、番茄钟、四象限与统计](docs/pdca.md)
- [投资分析：环境、网页、CLI、策略与结果说明](apps/investment/README.md)（其中的命令从 `apps/investment/` 执行）
- [本次目录整理与路径对应](docs/layout.md)

## 验证

以下命令从仓库根目录执行，使用临时数据或模拟行情：

```sh
.venv/bin/python -m unittest discover -s tests -v
(cd apps/investment && ../../.venv/bin/python -m unittest discover -s tests -v)
node tests/test_storage.js
```

浏览器交互验证需要 Playwright 和 Chrome：

```sh
PLAYWRIGHT_CORE=/path/to/playwright-core node tests/test_pdca.js
PLAYWRIGHT_CORE=/path/to/playwright-core node tests/test_strength.js
```

投资网页的可选 DOM 测试见投资模块说明。
