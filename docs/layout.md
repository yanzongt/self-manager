# 目录整理说明

此次按工具划分 `apps/`，将公共测试集中到 `tests/`，详细使用说明归入 `docs/`。根目录保留统一服务、安装和启动入口。现有未提交的功能修改随文件一起保留。

| 原路径 | 新路径 |
| --- | --- |
| `f-analysis/` | `apps/investment/` |
| `index.html` | `apps/portal/index.html` |
| `pdca_focus.html` | `apps/pdca/index.html` |
| `strength_training_tracker.html` | `apps/strength/index.html` |
| 根目录 `test_*.py` / `test_*.js` | `tests/` |
| README 中 PDCA 详细说明 | `docs/pdca.md` |
| `f-analysis/.venv/` | 由 `./setup.sh` 在根目录重新建立 `.venv/` |

PDCA 的 `data/pdca.json` 与 `.bak` 继续使用原位置。投资模块的 `data/`、`outputs/`、`configs/` 随模块整体移动，行情缓存、自建股票池、历史结果和原有 legacy CSV 保留。浏览器存储键和公开 HTTP 路径保持原样，包括两个旧 HTML 地址。

直接用 `file://` 打开页面的路径会变化；旧地址的浏览器数据应先从旧地址导出，再通过新入口导入。日常使用统一服务地址。

投资模块保留 `f_analysis` 包名与独立项目配置，避免目录整理改变计算逻辑或锁定依赖。独立运行命令请先进入 `apps/investment/`，或从仓库根目录执行 `.venv/bin/python apps/investment/main.py --help`。重新安装统一环境用 `./setup.sh`。

复制项目带来的虚拟环境、Python 缓存和构建产物不属于源码；统一环境重新建立后可再生成这些文件。个人工具配置保留在原模块内，不纳入版本控制。
