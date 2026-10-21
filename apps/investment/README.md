# f-analysis

基于 Yahoo Finance 复权日线的股票池与策略分析框架。核心由 `StockPool`（可交易股票池）、策略、统一回测引擎和绩效分析模块组成。支持单只或多只股票，内置买入持有、MA 偏离、固定权重再平衡与截面动量；原有相关性分析、参数研究和组合扫描入口继续可用。

本目录保留原 `f-analysis` 的 Python 包、命令行入口和测试。统一使用时，在仓库根目录执行 `./setup.sh` 和 `./start.sh`，依赖安装到根目录 `.venv/`；本节也支持单独安装本模块环境。下文中的“项目根目录”指 `apps/investment/`；个人工具统一入口见[仓库说明](../../README.md)。

## 环境配置

- Python 3.13 或更高版本，项目通过 `.python-version` 默认选择 3.13。
- 推荐使用 [uv](https://docs.astral.sh/uv/getting-started/installation/) 管理 Python、虚拟环境和依赖。
- 首次下载或主动刷新行情时需要能够访问 Yahoo Finance；不需要配置 API Key。缓存齐全后可以完全离线运行。
- 依赖：`yfinance`、`pandas`、`numpy`、`matplotlib`，声明在 `pyproject.toml`，精确版本记录在 `uv.lock`。

在项目根目录执行：

```bash
uv python install 3.13
uv sync --locked
```

`uv sync` 会创建/更新 `.venv`。后面的 `uv run --locked` 会使用此环境，无需手动激活。

也可以使用普通虚拟环境：

```bash
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
python main.py --help
```

Windows 激活命令为 `.venv\Scripts\activate`。pip 安装按照 `pyproject.toml` 解析依赖；需要复现锁定版本时使用 uv。

## 网页工作台（推荐）

启动本机网页，无需安装 Node.js 或构建前端：

```bash
uv sync --locked
uv run --locked python main.py web --open
```

也可从仓库根目录运行 `./start.sh`，通过个人主页的 `/investment/` 入口使用回测；统一服务器默认地址为 **http://127.0.0.1:8765**，无需另开本节的独立服务。

独立启动时，浏览器访问 **http://127.0.0.1:8766**。保持终端运行，按 `Ctrl+C` 停止服务。若不希望自动打开浏览器，去掉 `--open`。端口被占用时可指定 `--port 8877`；也支持 `uv run --locked python -m scripts.web --port 8877`。

网页支持：

- 编辑多股票池、名称和百分比权重，一键等权配置，载入 `configs/pools/` 中的 JSON 模板。
- 同时选择买入持有、MA 均线、固定权重再平衡、截面动量；MA30 / MA60 / MA120 / MA250 快捷切换，也可填写任意有效窗口。
- 设置历史范围、初始资金、单边手续费、再平衡频率，以及缓存优先、刷新或完全离线三种行情模式。
- 后台运行与进度提示，查看各策略收益、年化收益、最大回撤；曲线支持悬停查看、切换收益/回撤/总资产、隐藏策略及选择显示区间。
- 查看交易盈亏、实际成交、月度/年度收益、期末持仓与订单；下载完整 CSV 或全部结果 ZIP。
- 查看网页及标准输出目录中的 `portfolio_backtest`、`single_stock_backtest` 历史结果，恢复配置重新运行；更早、没有独立策略结果的记录不会列入。
- 查看共享 SQLite 缓存的股票、行情区间和更新时间。缓存列表的「刷新」只重新读取列表，下载新行情需在配置中选择刷新模式。

网页不会自动运行回测或自动刷新行情。首次打开时，如有兼容的历史记录，会直接展示最新结果；如果同时恢复了上次保存的草稿，页面会提示参数与已显示结果不同，避免将旧结果误认为当前配置的结果。

股票池支持命名保存：编辑股票及权重后填写「股票池名称」，点击「保存股票池」，即可在「快速载入」中再次选择。同名保存会提示覆盖确认；「新建股票池」清空当前股票行，便于建立另一组配置。载入会恢复股票代码、名称和原配置权重（包括未投资的现金比例），保留当前策略参数。内置模板仍按等权载入。

自建股票池保存在本机 `data/stock_pools.json`，刷新页面、重启服务或换浏览器均可再次载入。此文件已忽略版本控制，备份时请一并复制。原 `configs/pools/*.json` 内置模板保持可用。

每次新回测保存到 `outputs/web_backtest/<运行时间>/`，其结果文件与统一回测入口一致，另有任务状态 `status.json`。关闭页面不会终止后台任务；结束服务前会等待已提交任务完成。服务异常中断后，未完成记录会显示为中断，可复用参数重新运行。任务串行执行，避免图表和缓存更新并发冲突；失败信息在页面显示，不用示例数据代替失败结果。

图表每条曲线最多约 2500 个采样点，明细表最多展示最近 500 条（期末持仓仅显示最后一日）；汇总指标与导出的 CSV/ZIP 始终基于完整数据。选择图表显示区间只改变曲线可见范围，不重新计算区间收益。较早的单股票报告可能没有持仓、订单和成交文件，这些表会显示为空，可用新入口重新运行生成。

服务仅监听 `127.0.0.1`，页面资源不使用外部 CDN，前端与后端同源；已有 Python 引擎和行情缓存直接复用，不另起计算模型。运行和缓存均留在本机，只有主动下载行情时由现有 Yahoo 数据接口联网。此入口面向本机使用，不提供公网部署或多用户账户。

## 快速运行

推荐使用新的统一入口，在同一股票池上比较四种策略：

```bash
uv run --locked python main.py portfolio_backtest --tickers 600036.SS 002594.SZ --no-show

# 不等权股票池，20% 保留为现金；只比较持有与月度再平衡
uv run --locked python main.py portfolio_backtest --tickers 600036.SS 002594.SZ --weights 0.5 0.3 --strategy buy_hold fixed_weight --fee-rate 0.0003 --no-show

# 从 JSON 定义股票池，股票名称会保留在运行记录中
uv run --locked python main.py portfolio_backtest --pool configs/pools/example.json --offline --no-show
```

离线命令要求各标的已缓存。首次运行可去掉 `--offline`；需要最新行情时添加 `--refresh-data`。


以下命令在项目根目录执行。`--no-show` 会保存图表但不打开窗口，适合服务器、SSH 和批量执行。

```bash
# 两只资产的相关性分析
uv run --locked python main.py correlation_analysis --no-show

# 简版 50/50 买入持有与每月再平衡对比
uv run --locked python main.py rebalance_comparison --no-show

# 单组合的频率比较、权重扫描、滚动回测
uv run --locked python main.py rebalance_analysis --no-show

# 扫描资产池中所有两两组合
uv run --locked python main.py etf_pair_scan --no-show

# 单股票：低于 MA30 5% 买入，高于 MA30 5% 卖出
uv run --locked python main.py single_stock_backtest --ticker 600036.SS --no-show
```

省略 `--no-show` 时，图表仍会保存，并依次弹出窗口；关闭当前图窗后继续。`rebalance_comparison` 没有图表。

各脚本也能通过模块方式独立运行：

```bash
uv run --locked python -m scripts.rebalance_analysis --no-show
uv run --locked python -m scripts.etf_pair_scan --help
```

请使用 `main.py` 或 `python -m scripts.<脚本名>`，不要直接执行 `python scripts/xxx.py`，因为脚本使用包内相对导入。

### 输出位置

默认输出目录始终相对于项目根目录，与调用命令时的工作目录无关：

```text
outputs/<脚本名>/<本地时间 YYYYMMDD-HHMMSS-微秒>/
```

每次运行创建新目录，保存该次 CSV、PNG 和 `run_config.json`（脚本名、带时区的创建时间和主要配置）。控制台会打印目录。参数记录包含每只标的的缓存来源、行情范围、下载时间和 yfinance 版本。行情缓存在独立数据库中，刷新会替换历史；运行记录不包含历史行情快照，不能独立用于精确复现已被替换的行情。

可以指定输出目录，相对路径相对于当前工作目录：

```bash
uv run --locked python main.py rebalance_analysis --no-show --output-dir outputs/my-experiment
```

指定同一个目录重复运行会覆盖同名文件，并可能留下前次运行的其他文件；需要独立留档时请使用新目录或默认目录。控制台统计不自动保存，如需留存可自行重定向输出。

## 目录结构

```text
apps/investment/
├── README.md
├── main.py                       # 统一命令入口
├── pyproject.toml                # 项目信息及依赖范围
├── uv.lock                       # uv 精确依赖锁定
├── .python-version               # 默认 Python 版本
├── f_analysis/                   # 独立于行情服务的核心框架
│   ├── models.py                 # StockPool、配置、策略上下文、标准结果
│   ├── strategies.py             # 策略接口与内置策略
│   ├── account.py                # 现金、平均成本持仓与手续费
│   ├── engine.py                 # 多资产调度、成交和估值
│   ├── analytics.py              # 收益、回撤、相关性和期间盈亏
│   ├── reporting.py              # 标准结果输出及对比图
│   ├── research.py               # 独立子区间与参数扰动分析
│   ├── adapters.py               # 原双资产研究接口的适配层
│   ├── web_service.py            # 网页后台任务、历史及结果读取
│   └── web_static/               # 无构建依赖的 HTML / CSS / JS 界面
├── configs/pools/example.json    # 可编辑的股票池示例
├── scripts/
│   ├── __init__.py                # Python 包声明
│   ├── _runtime.py                # 参数解析、输出目录、参数记录、图表保存
│   ├── market_data.py             # 共享 SQLite 行情缓存与下载
│   ├── correlation_analysis.py    # 原 tmp.py
│   ├── rebalance_comparison.py    # 原 tmp2.py
│   ├── rebalance_analysis.py      # 原 tmp3.py
│   ├── etf_pair_scan.py           # 原 tmp4.py
│   ├── single_stock_backtest.py   # 单股票兼容入口，使用统一引擎
│   ├── portfolio_backtest.py      # 新的多股票统一入口
│   └── web.py                     # 本机网页服务入口
├── data/cache/
│   └── market_data.sqlite3        # 所有脚本共享的复权日线缓存（不提交 Git）
├── outputs/
│   ├── rebalance_analysis/legacy/ # 原根目录 frequency/weight/rolling_results.csv
│   ├── etf_pair_scan/legacy/      # 原根目录 etf_rotation_scan.csv
│   └── <脚本名>/<运行时间>/        # 新生成的结果
└── tests/
    ├── test_web.py                # HTTP、任务、文件导出与访问边界
    ├── test_framework.py          # 多资产资金守恒、成交、缺失行情和策略接口
    ├── test_portfolio_cli.py      # JSON 股票池、不等权配置及入口校验
    ├── test_market_data.py        # 缓存复用、刷新、离线及事务验证
    ├── test_single_stock_backtest.py # 成交时点、费用、收益与回撤验证
    └── test_workflows.py          # 使用模拟行情的离线流程验证
```

`legacy/` 中的 CSV 原样保留，原始运行参数未知，不能直接认定与当前默认配置对应。新运行目录、虚拟环境、Python 缓存和本地工具设置由 `.gitignore` 忽略；历史 CSV 保留在版本管理范围内。

## 行情缓存与更新

所有脚本共用项目根目录下的 `data/cache/market_data.sqlite3`，不需要安装或启动数据库服务，也没有新增第三方依赖。缓存与脚本输出目录彼此独立。

- **默认行为**：有缓存就直接读取，没有缓存才下载；不设置自动过期，不会自动检查最新行情。
- **缓存粒度**：按数据源、标的、日线频率、自动复权口径与缓存版本区分。每只标的首次下载 `max` 全部可用历史，后续不同组合和不同 `PERIOD` 共享这些数据。
- **时间截取**：`PERIOD = "3y"` 等范围按运行当天（Asia/Shanghai）的日历日期向前截取，不以缓存最后一天为基准；支持 `max`、`ytd` 和正整数加 `d`/`wk`/`mo`/`y`。缓存太旧导致所需区间内没有数据时会报错，提示刷新或扩大范围。
- **数据处理**：缓存保存各标的独立的有效复权收盘价，不进行跨标的填充、共同交易日筛选或月度采样。这些处理仍由分析脚本完成。

```bash
# 正常运行：复用已有数据，只下载缺失标的
uv run --locked python main.py rebalance_analysis --no-show

# 主动刷新：重新下载本次任务涉及标的的完整历史
uv run --locked python main.py rebalance_analysis --refresh-data --no-show

# 完全离线：缺少任一所需标的时直接报错
uv run --locked python main.py rebalance_analysis --offline --no-show
```

`--refresh-data` 与 `--offline` 互斥，同样支持 `python -m scripts.<脚本名>`。修改分析权重、再平衡频率或输出目录都不会重新下载；向资产池添加标的时仅下载新增标的。

每次读取都会在控制台显示各标的的行情截止日和缓存更新时间；`run_config.json` 的 `market_data` 部分记录具体来源和范围。**默认缓存可能过时，需要最新行情时请主动刷新。** 不同标的可能在不同时间缓存，按需刷新可以统一更新本次组合；即使同批下载，不同标的的最后有效交易日也可能不同。

刷新采用完整历史替换，而非仅追加新日期，避免历史复权值变化后混用不同价格基准。所有待下载标的验证成功后才在一个 SQLite 事务中写入；下载为空、标的缺失或无效价格会使当前运行失败，旧缓存不受影响，写入失败时事务回滚。

如需重建全部缓存，可在没有分析进程运行时删除 `data/cache/`，下次运行会重新下载。缓存与新生成的分析结果均不提交 Git；删除 `outputs/` 不会影响缓存。

## 框架：股票池、策略与统一账户

`StockPool` 表示允许交易的代码及名称，不等于当前实际持仓。策略只输出目标权重；引擎负责成交数量、资金约束、手续费、持仓账本和估值。核心不访问网络，调用者传入日期索引、股票代码列的复权收盘价 DataFrame；CLI 则复用现有 SQLite 缓存一次加载行情。

### 内置策略与交易时钟

| 策略 | 行为 | 成交时点 |
| --- | --- | --- |
| `BuyAndHold` / `buy_hold` | 按给定权重首次建仓，随后不调整 | 各标的首次有效收盘价；缺失初期报价的标的等待有效报价 |
| `MABand` / `ma_band` | 低于 MA 的 95% 买入，高于 105% 清仓；窗口、阈值可配置 | 信号之后该标的下一个有效收盘日 |
| `FixedWeightRebalance` / `fixed_weight` | 首次建仓，之后按日历频率恢复目标权重 | 新月/季度/半年/年度的首个观察日收盘，计划提前确定；缺失报价的标的等待 |

每种策略使用独立的现金和持仓账户，相同输入行情下互不影响。`each_observation` 频率表示每个输入行情点恢复权重，主要供原有月度/季度采样分析适配使用。

共享的 `compare_results()` 会检查行情日期、初始资金和费率一致，避免将不同区间或不同资金口径的结果混为策略比较。

MA 的股票权重代表触发买入时的资金配置目标。例如池中两只股票权重各 50%，只有一只触发时只投入约 50%，其余为现金，不把未触发股票的额度自动分给已触发股票。持仓期间不因价格波动持续恢复配置权重；再次出现买入条件也不会重复买入。均线按各股票自己的有效价格计数，新上市股票预热期间保持空仓，不截短其他股票的历史。

### Python 使用方式

```python
from f_analysis import (
    StockPool, BacktestConfig, BacktestEngine,
    BuyAndHold, MABand, FixedWeightRebalance,
)
from f_analysis.reporting import save_result, compare_results
from scripts.market_data import get_prices
from pathlib import Path

pool = StockPool({"600036.SS": "招商银行", "002594.SZ": "比亚迪"})
weights = {"600036.SS": 0.5, "002594.SZ": 0.5}
prices = get_prices(pool.tickers, period="5y")
engine = BacktestEngine(pool, BacktestConfig(initial_cash=100000, fee_rate=0.0003))
strategies = [
    BuyAndHold(weights),
    MABand(window=30, threshold=0.05, weights=weights),
    FixedWeightRebalance(weights, frequency="monthly"),
]
results = {s.name: engine.run(prices, s) for s in strategies}
print(compare_results(results))
for name, result in results.items():
    save_result(Path("outputs/python-demo") / name, result)
```

### 添加自己的策略

继承 `BaseStrategy`，通常只需要实现 `on_close(context)`。上下文包含截至当天收盘的数据、现金、总资产和只读持仓数量，不提供未来行情。

```python
from f_analysis import BaseStrategy

class ExampleStrategy(BaseStrategy):
    name = "example"

    def on_close(self, context):
        ticker = context.pool.tickers[0]
        if len(context.history[ticker].dropna()) == 20:
            return {ticker: 0.5}
        return None
```

接口约定：

- `None` 或空映射：不提交新调整，不会隐式再平衡，也不取消已挂起的订单。
- `{代码: 目标权重}`：只调整明确列出的标的，其余持仓不变；`0` 表示清仓。需要完整恢复组合时应返回所有标的的目标权重。
- 目标权重以**执行日成交前账户资产**为基准，未提及持仓的实际占比可能已漂移。现金不足时仅对本次买单等比例缩减，不借款、不强制卖出未提及的持仓。
- `on_close` 提交的目标最早在下一有效报价日成交；最后一天的目标保持 `pending`。已有未成交目标可被该标的新目标替换，旧订单记录为 `superseded`。
- 可选的 `initial_targets(pool)` 用于回测开始前确定的初始配置；`scheduled_targets(date, previous_date, pool)` 用于提前确定的日历计划，二者允许当天收盘执行，不应依赖当天价格信号。
- 每次目标都是一次调整请求。资金缩减后不自动持续补单；后续需要调整时由策略再次提交。权重不能为负或超过 1，同次提交权重和不能超过 1。

### 账户与缺失行情规则

先卖后买；同日多笔买单按资金需求等比例缩减，避免股票排列顺序决定谁先占用现金。买卖双方都按实际成交金额分别计费，建仓也计费。手续费会使实际成交后的权重与配置目标略有偏差。

股票池行情不全局 `dropna()`。缺少当日行情时不成交，持仓使用最近有效价格估值；从未有报价且未持仓的股票市值为 0。后续有报价时，等待中的订单才执行；等待期间目标金额会随执行日账户资产变化。`positions.csv` 同时记录真实当日报价和用于估值的价格，便于识别陈旧估值。框架不向后填充未来报价。

持仓使用平均成本法；部分卖出按比例分摊成本及买入费用，每次卖出填单算一个已平仓记录。期末剩余仓位记为 `open`，不强制卖出。逐日满足：`总资产 = 现金 + 持仓市值`，`总盈亏 = 已实现盈亏 + 浮动盈亏`。最大回撤包含初始资金及建仓费用。

当前为同一计价货币下的复权收盘价、小数份额模型，不含外汇换算、借贷、做空、整手约束、最低佣金和实际涨跌停成交限制。

### 原有脚本迁移说明

原单股票入口保留参数、返回接口与已有输出布局，通过适配层使用统一引擎；相关性分析使用共享分析函数。双资产频率研究、权重扫描、滚动回测和组合扫描也复用同一账户引擎，保留原有采样及展示口径。

两处行为调整：简版双资产对比现在统一从首个月末价格开始，消除原有起点差异；双资产的非零交易成本改为按实际买卖成交额分别收费（包含建仓），替代旧的半换手成本近似，所以非零成本结果可能变化。历史 `legacy/` 文件保持原样。旧频率研究不同频率的采样区间差异仍保留；严格在同一日线区间比较，使用新 `portfolio_backtest` 入口。

## 每个脚本的功能与配置

原有分析脚本的业务参数通过修改顶部常量配置；单股票回测另外提供业务参数命令行选项。所有脚本共同提供 `--output-dir`、`--no-show`、`--refresh-data`、`--offline` 和 `--help`。Yahoo Finance 代码中，深圳使用 `.SZ`，上海使用 `.SS`。

### correlation_analysis.py：双资产相关性

默认研究比亚迪 `002594.SZ` 与招商银行 `600036.SS`，最近 3 年（`PERIOD = "3y"`）。

- 下载两只资产的复权日线收盘价，保留共同有效交易日。
- 计算日收益、月收益的 Pearson 相关系数和相关矩阵。
- 绘制归一化价格、月收益散点、12 个月滚动月收益相关性。

修改 `TICKERS`（必须恰好两只且不同）和 `PERIOD`；滚动窗口在 `plot_result()` 的 `rolling_correlation(..., window=12)` 中调整。

输出：

| 文件 | 内容 |
| --- | --- |
| `daily_returns.csv` | 两只资产的日收益率，包含日期索引 |
| `monthly_returns.csv` | 两只资产的月收益率，包含日期索引 |
| `normalized_prices.png` | 首日价格归一为 1 的走势 |
| `monthly_returns_scatter.png` | 月收益散点及相关系数 |
| `rolling_correlation.png` | 12 个月滚动相关性 |

### rebalance_comparison.py：简版再平衡对比

默认研究半导体设备 `159516.SZ` 与红利 `560020.SS`，最近 3 年。修改顶部 `TICKERS`、`PERIOD`。

初始总资产为 1，两只资产各占 50%。比较买入后不再平衡和每月恢复 50/50 的最终资产、累计收益与收益差，并打印月收益相关矩阵、反向涨跌月份比例和强弱反转比例。不计交易成本。

输出 `comparison_results.csv`（`strategy`、`final_value`、`total_return`）与 `monthly_returns.csv`。此脚本导入时不会下载行情，运行入口时才执行分析。

两种策略现在使用相同月末价格区间，起点均为首个有效月末。

### rebalance_analysis.py：单组合完整研究

默认研究 `159516.SZ` 与 `560020.SS` 的全部可用历史。

| 配置 | 默认值 | 含义 |
| --- | --- | --- |
| `TICKERS` | 上述两只资产 | 第一只为资产 A，第二只为资产 B |
| `PERIOD` | `"max"` | 下载历史范围，可改为 `"3y"` 等 |
| `TRANSACTION_COST` | `0.0` | 频率比较与权重扫描使用的交易成本参数 |
| `WEIGHTS` | `np.arange(0.2, 0.81, 0.05)` | 扫描 A 的 20%～80% 权重，步长 5%，B 为剩余权重 |
| `ROLLING_MONTHS` | `36` | 每个滚动窗口包含的月度价格点数 |

执行顺序：月度相关性和强弱切换统计 → 月度/季度/半年度/年度再平衡比较 → 权重扫描 → 滚动窗口比较 → 保存 CSV 和图表。

| 输出文件 | 主要内容 |
| --- | --- |
| `frequency_results.csv` | `strategy`、最终净值 `final_value`、年化收益 `cagr`、相对持有年化差 `extra_vs_hold`、累计换手率 `total_turnover` |
| `weight_results.csv` | `weight_a`、`weight_b`、持有年化 `buy_hold`、再平衡年化 `rebalance`、两者之差 `extra` |
| `rolling_results.csv` | 窗口 `start`/`end`、两种策略年化、年化差、月收益相关性 |
| `recent_3y.png` | 最近约 1095 天的 50/50 净值对比 |
| `weight_scan.png` | 不同权重下的年化收益 |
| `rolling_extra_return.png` | 各滚动窗口的再平衡年化收益差 |

历史不足时滚动结果可能为空，此时不生成滚动图。滚动回测和最近三年图始终不计交易成本；调整 `TRANSACTION_COST` 不会改变这两部分。

**区间限制：** 频率比较先分别按月/季/半年/年采样，起止采样点可能不同，但年化统一使用月度数据的期数。因此频率表不是严格同区间比较。滚动窗口默认包含 36 个价格点，对应 35 个月收益；代码中的“滚动3年”标题是近似称呼。修改窗口大小后，部分图表/终端标题仍沿用原称呼。

### etf_pair_scan.py：资产池两两组合扫描

修改顶部 `ETF_POOL`（名称到 Yahoo 代码的映射）、`MIN_MONTHS` 和 `TRANSACTION_COST`。默认池有 13 个标的，包含 ETF、招商银行和比亚迪，最多扫描 78 对组合；下载范围为 `max`。

- 每对资产独立按月末有效价对齐，避免整个池被最晚上市标的截短。
- `MIN_MONTHS = 12` 表示至少 12 个月度价格点，即至少 11 个收益期。
- 对每对组合计算月收益相关性、反向涨跌比例、强弱反转比例。
- 比较 50/50 买入持有和每月再平衡的累计收益、年化收益、最大回撤。
- 按再平衡年化收益减持有年化收益降序排列，绘制前 15 对组合。

输出：`etf_rotation_scan.csv` 和 `top_pairs.png`。没有满足历史要求的组合时，不生成排名图。

CSV 中 `name_a/b`、`ticker_a/b` 标识组合，`start`/`end` 是月度索引日期，`months` 为收益期数；`corr` 为相关系数；`opposite_ratio`/`reversal_ratio` 为月份比例；`buy_hold_return`/`rebalance_return`/`extra_return` 为累计收益及其差；`buy_hold_cagr`/`rebalance_cagr`/`annualized_extra` 为年化收益及其差；`buy_hold_mdd`/`rebalance_mdd` 为最大回撤。

不同组合可能覆盖不同历史区间，因此排名包含区间差异，不能直接视为同区间排名。

### portfolio_backtest.py：股票池统一回测入口

支持 `python main.py portfolio_backtest` 或 `python -m scripts.portfolio_backtest`。

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `--tickers` | `600036.SS 002594.SZ` | 一只或多只代码，用空格分隔 |
| `--pool` | 不指定 | JSON 股票池，与 `--tickers` 互斥；格式参考 `configs/pools/example.json` |
| `--weights` | 等权 | 按股票池顺序配置，如 `0.5 0.3`；总和可小于 1，剩余现金 |
| `--strategy` | `all` | 可选 `buy_hold`、`ma_band`、`fixed_weight`、`cross_sectional_momentum`，可一次指定多个 |
| `--period` | `5y` | 本地截取的分析范围 |
| `--initial-cash` | `100000` | 每个策略的独立初始资金 |
| `--fee-rate` | `0` | 买卖各自单边费率 |
| `--ma-window` / `--threshold` | `30` / `0.05` | MA 策略参数 |
| `--rebalance-frequency` | `monthly` | `monthly`、`quarterly`、`semiannual`、`annual` 或 `each_observation` |

通用的 `--output-dir`、`--no-show`、`--offline`、`--refresh-data` 均支持。

每次输出到 `outputs/portfolio_backtest/<运行时间>/`，根目录包含 `run_config.json`、`comparison.csv`、`comparison.png`；每个策略有独立子目录：

| 文件 | 内容 |
| --- | --- |
| `summary.json` | 统一绩效指标、股票池、最终各股票数量、待执行订单数 |
| `daily_history.csv` | 每日现金、市值、总资产、已实现/浮动盈亏、费用、收益及回撤 |
| `positions.csv` | 每日每只股票的真实报价、估值价、数量、成本、市值及浮动盈亏 |
| `fills.csv` | 实际买卖成交记录、成交额、手续费及本次卖出实现的盈亏 |
| `orders.csv` | 目标权重、信号日、执行日、成交数量和订单状态 |
| `trades.csv` | 平均成本分摊后的已卖出部分与期末未平仓记录 |
| `monthly_returns.csv` / `yearly_returns.csv` | 月/年盈亏、收益率及期末资产 |

订单状态包括 `pending`、`superseded`、`filled`、`partial`（资金缩减）、`no_change`、`insufficient_cash`。初始化/计划订单的 `signal_date` 为空，收盘信号订单记录真实信号日。`comparison.csv` 在选择买入持有时添加 `extra_return_vs_buy_hold`，表示累计收益率之差。空交易表仍保留表头。没有已平仓记录时胜率为空。

`analysis/` 另包含 `daily_correlation.csv` 与 `monthly_correlation.csv`，直接从行情生成，不依赖交易策略；收益计算不自动前向填补缺失价格，相关性按列两两匹配有效样本。这样股票池可以同时用于交易回测和纯行情分析。

### single_stock_backtest.py：单股票多策略回测与对比

指定一只股票，默认同时运行 `ma_band`（MA 偏离择时）与 `buy_hold`（初始买入一直持有）两种独立策略。两者共用一次行情读取，使用相同区间、初始资金、费率和账户计价逻辑，分别输出最终资产、累计盈亏、年化收益、最大回撤、已实现/浮动盈亏、胜率、逐笔交易及日/月/年历史盈亏。默认股票为招商银行 `600036.SS`。

```bash
# 默认比较两种策略：10 万初始资金、最近 5 年，MA30 上下偏离 5%
uv run --locked python main.py single_stock_backtest --ticker 600036.SS --no-show

# 只运行买入持有（首日买入一直持有）
uv run --locked python main.py single_stock_backtest --ticker 600036.SS --strategy buy_hold --no-show

# 只运行 MA 策略
uv run --locked python main.py single_stock_backtest --ticker 600036.SS --strategy ma_band --no-show

# 修改股票、回测时间、资金和费率；0.0003 表示买卖各收 0.03%
uv run --locked python main.py single_stock_backtest --ticker 002594.SZ --period 3y --initial-cash 100000 --ma-window 30 --threshold 0.05 --fee-rate 0.0003 --no-show

# 复用缓存完全离线运行
uv run --locked python -m scripts.single_stock_backtest --ticker 600036.SS --offline --no-show
```

| 参数 | 默认值 | 含义 |
| --- | --- | --- |
| `--strategy` | `all` | `all` 同时比较两种策略；`ma_band` 或 `buy_hold` 单独运行 |
| `--ticker` | `600036.SS` | 股票代码，也可以修改脚本顶部 `TICKER` |
| `--period` | `5y` | 参与分析的行情范围 |
| `--initial-cash` | `100000` | 初始现金，金额单位与行情计价货币一致 |
| `--ma-window` | `30` | 简单移动平均的有效交易日数，含当天收盘 |
| `--threshold` | `0.05` | 相对于均线的偏离比例，需在 0 和 1 之间 |
| `--fee-rate` | `0` | 每次买入/卖出分别按成交金额收取的费率 |

MA 策略（`ma_band`）与共同成交规则：

- 空仓时，当天复权收盘价严格小于 `MA30 × 0.95`，产生买入信号；持仓时严格大于 `MA30 × 1.05`，产生卖出信号。等于边界时无信号，不要求价格先穿越边界。
- 信号在**下一有效交易日的复权收盘价**成交，不以信号当天价格成交，也不使用开盘价。中间发生跳空或价格回到均线附近时，仍执行前一日的信号。
- 全仓买入、全部卖出，不加仓、不做空。买入数量为 `现金 / [成交价 × (1 + 费率)]`；卖出所得为 `数量 × 成交价 × (1 - 费率)`。
- 均线只使用所选 `period` 内的有效日线，前 29 个有效交易日处于预热期，不使用区间外行情补足；MA30 最早在第 30 日产生信号，第 31 日成交。运行 MA 策略时，有效行情不足均线窗口会报错；单独运行买入持有不需要均线预热或足够的均线窗口数据。
- 期末未平仓时按最后有效收盘价计入资产，不强制卖出，也不预扣未来卖出费用。最后一天的信号只记为待执行，不虚构下一交易日成交。
- 使用复权价格和小数份额模拟，不重复计入分红；不处理实际整手数量、停牌/涨跌停成交限制、最低佣金、差异税费、滑点或现金利息。

买入持有策略（`buy_hold`）在区间首个有效交易日收盘投入全部初始资金，仅扣一次买入费用，之后不卖出、不再平衡。该买入计划在回测开始前确定，不依赖当天的 MA 信号；交易记录中的 `entry_signal_date` 为空，`entry_date` 为首日，`status` 为 `open`。期末按市值计价，不预扣未来卖出费用。它包含 MA 策略的预热期，代表整段区间持续持有的对照。

默认输出至 `outputs/single_stock_backtest/<运行时间>/`，各策略分别保存结果：

```text
<运行时间>/
├── run_config.json
├── comparison.csv
├── backtest.png
├── ma_band/
│   ├── summary.json
│   ├── daily_history.csv
│   ├── trades.csv
│   ├── monthly_returns.csv
│   └── yearly_returns.csv
└── buy_hold/
    └── ... 同样的 5 个结果文件
```

单独选择策略时只创建该策略子目录。之前版本直接写在运行目录根部的单策略文件，现在放在对应策略子目录中。

| 文件 | 内容 |
| --- | --- |
| `comparison.csv` | 每种策略一行，比较最终资产、盈亏、累计/年化收益、最大回撤、费用、交易笔数等；`extra_return_vs_buy_hold` 是相对买入持有的累计收益率之差（如 `0.1` 表示高 10 个百分点） |
| `<策略>/summary.json` | 策略名、配置、区间、最终资产/现金/持仓、盈亏、CAGR、最大回撤、交易笔数、胜率、基准收益和期末待执行信号 |
| `<策略>/daily_history.csv` | 每日价格、当日信号、实际成交动作、现金/数量/市值/总资产、日收益与日盈亏、累计/已实现/浮动盈亏、累计费用和回撤；MA 策略另含均线与阈值 |
| `<策略>/trades.csv` | 每轮交易的信号日、成交日、买卖价、数量、费用、盈亏和收益率；`closed` 表示已平仓，`open` 表示期末仍持有 |
| `<策略>/monthly_returns.csv` | 每月末资产、当月盈亏/收益率、累计盈亏；首月相对初始资金 |
| `<策略>/yearly_returns.csv` | 按年汇总的同类指标；未结束年度为截至最后有效行情的结果 |
| `backtest.png` | 价格/均线/各策略成交点、各策略累计收益曲线、各策略每日回撤曲线 |
| `run_config.json` | 本次运行的策略列表、参数及缓存来源 |

MA 的 `signal` 中 `1` 为买入条件、`-1` 为卖出条件、`0` 为无信号；实际是否成交还取决于前一日信号与当前仓位，见 `executed_action`。买入持有不产生价格条件信号，因此 `signal` 始终为 0，首日 `executed_action` 为 `buy`。历史记录按复权日线收盘逐日计价。

总资产为现金加持仓市值，总盈亏为总资产减初始资金，等于已实现盈亏加浮动盈亏。最大回撤为每日总资产相对于此前最高资产（包含初始资金）的最大跌幅，以负数表示；首日买入费用也可能形成初始回撤。CAGR 按实际首尾日历天数年化。胜率只统计已平仓交易，盈亏为 0 不计胜；没有已平仓交易时胜率为 `null`，因此一直持有策略不会被记成“胜率 100%”。持仓天数按日历日计算。

### main.py 与辅助模块

`main.py` 负责选择并调用上述脚本；`web` 启动本机网页服务，其他分析入口按原方式运行。`scripts/__init__.py` 仅声明包；`scripts/_runtime.py` 和 `scripts/market_data.py` 供脚本复用，不需要单独运行。原 `main.py` 的 Hello World 占位入口已替换。

## 数据与指标口径

- 所有下载都使用 `auto_adjust=True` 的日线 `Close`；月度价格通过 `resample("ME").last()` 得到，月收益使用相邻月度价格的百分比变化。
- 收益率在 CSV 中以小数记录，如 `0.1` 表示 10%；年化超额是两种 CAGR 的差，不是超额净值的 CAGR。
- 完整研究与组合扫描的年化公式是 `最终净值 ** (12 / 月收益期数) - 1`。
- 月末索引是日历月末，可能不是真实交易日；当前未结束月份也可能被纳入，最后一期不一定是完整月份。
- 反向月份表示两只资产月收益乘积小于 0；强弱反转表示相邻月份的收益差发生符号切换。现有实现先比较再 `dropna()`，首个无前值月份会按 False 纳入分母，可能略低估反转比例。
- 所有回测统一按实际买入/卖出成交额分别收取单边费用，并计入建仓费用；默认费率为 0。旧双资产结果的非零成本近似模型已替换，详见迁移说明。
- 原有双资产脚本的最大回撤基于月度净值，不能反映月内低点；单股票策略基于每日收盘净值，不能反映日内低点。默认成本为 0；模型未加入滑点、税费、交易单位等约束。

## 常见问题

**下载失败、空数据、限流或网络错误：** 先检查网络和代码后缀，再缩小资产池后重试。首次缓存固定下载完整历史，缩短 `PERIOD` 不会缩短首次下载范围。下载/刷新失败时旧缓存保持不变，当前运行报错，不会悄悄以旧行情代替刷新结果；如需继续使用旧行情，请明确以 `--offline` 重跑。失败运行可能只有输出目录和参数记录。流程测试使用模拟行情，不代表真实数据源一定可用。

**服务器没有图形界面：** 添加 `--no-show`，图表使用 Agg 后端保存为 PNG。

**中文显示方框：** 组合扫描会自动查找系统中文字体；可安装 Noto Sans CJK、文泉驿等候选字体后重新运行。字体缺失不会改变 CSV 的计算结果。

## 验证

```bash
uv run --locked python -m unittest discover -s tests -v
```

测试使用模拟行情执行 6 个脚本入口，比较首次运行与离线重跑的 CSV，验证 CSV/PNG/参数记录、无窗口运行和默认输出目录隔离；另验证缓存复用、只下载新增标的、完整历史替换、下载失败及数据库写入失败时的事务回滚。单股票回测另以可手算行情验证信号边界、次日成交、手续费、未平仓处理、无交易情况、未来行情不改变历史成交和最大回撤，并验证买入持有首日成交、单次收费、独立持仓与历史收益、基准一致性和策略选择。多资产测试另覆盖平均成本分摊、同时买入的资金分配、卖出资金复用、持仓漂移、非同步报价、上市时间差异、日历调仓、目标权重校验和每日资金守恒。网页测试通过本机 HTTP 接口运行真实回测引擎，验证后台状态、完整结果下载、配置校验、缓存读取和文件访问边界；行情使用测试数据。测试不访问 Yahoo Finance。这些检查用于验证项目整理后的运行流程，不是对回测模型准确性的全面验证。

网页前端另有可选的 DOM 逻辑测试（不是真实浏览器的版式测试），使用独立临时目录安装开发测试依赖，不影响项目运行：

```bash
npm install --prefix /tmp/f-analysis-dom-test --no-audit --no-fund happy-dom
HAPPY_DOM_MODULE=/tmp/f-analysis-dom-test/node_modules/happy-dom/lib/index.js node tests/web_ui_smoke.mjs
```

该测试的 API 全部使用固定测试数据，不会访问行情服务或创建真实回测；覆盖股票池编辑、MA120 切换、后台进度、曲线切换、明细、参数恢复、历史和缓存入口。

## 截面动量与稳定性研究

更新 Python 回测代码后，需要停止原服务并重新执行仓库根目录的 `./start.sh`；仅刷新网页只能更新静态界面。页面会检查实际后台的研究功能版本，旧后台会提示重启并阻止提交新参数，避免静默丢弃配置。修改左侧设置不会改变已经生成的历史结果，需重新运行回测。

网页中勾选「截面动量策略」，设置收益回看长度、调仓间隔和持有前 N 只。两个时间参数的单位均为**股票池行情日**（股票池日线索引的行数），不是自然日。示例：126 日回看、每 21 日调仓、选择前 3 只。排名使用 `当日复权收盘价 / L 个行情日前复权收盘价 - 1`，按收益从高到低排序；收益相同时按股票代码排序。即使全部收益为负，也选择相对收益较高的股票，不设置绝对动量过滤。

选中的股票各占 `1/N`，未选中股票目标为 0；此策略忽略股票池编辑器中的固定权重，固定权重仍用于买入持有基准及其他策略。回看窗口中有任何缺失报价的股票不参加排名；合格股票不足 N 只时，空缺份额保留现金。N 不能超过股票池大小。初始回看数据不足时持有现金，首次有足够行情的收盘日排名，此后每隔指定行情日重新排名。信号在**下一个有报价的收盘日**成交，计入单边费用，不允许读取信号日之后的价格排名；报价缺失时待执行订单沿用引擎的等待及替换规则。

内置 `us_technology`、`cn_large_caps`、`cn_banks` 三组固定股票池示例，可在「快速载入」选择，也可直接编辑并保存自己的股票池。这些只是研究配置，未重建历史成分、退市股票和上市时点的历史可选全集，存在幸存者偏差；不是股票推荐。

### 独立子区间

在「稳定性研究」设置子区间数量：`0` 关闭，`2～50` 启用，每段至少需要两个行情日。5 年行情设为 5 段时，按实际行情日近似等分，前几段可能多 1 日，不保证按日历年对齐；日期、日数会显示在报告中。

每段**独立从初始资金开始建仓**，计入该段费用。段前行情只用于预热信号，不带入以前的账户持仓和盈亏；首段没有额外的区间外行情，均线和动量仍需正常预热。动量从该段首个可用信号开始安排调仓。分段末不强制清仓，与全区间口径一致。因此不能把独立子区间收益相乘当作全程连续持有的收益。

每段报告累计收益、年化收益、最大回撤、手续费、成交数、相同初始资金和配置权重的买入持有收益、超额收益。汇总报告收益、年化收益、最大回撤和超额收益各自的均值、总体标准差（`ddof=0`）、最差/最好值、正值占比，并报告无交易区间占比。界面中的「盈利区间占比」为收益严格大于 0 的区间占比，「跑赢持有占比」为超额收益严格大于 0 的占比。短区间年化值可能很极端，应结合原始收益和回撤判断。

标准差表示区间之间的差异，并非日收益波动率。低标准差也可能来自持续亏损或从不交易，需结合最差收益、盈利占比和成交数判断。等分子区间只是有限的历史样本检查，**不能证明任意起止日期或未来都有效**。

### 参数扰动

勾选「参数扰动分析」，设置相对扰动幅度（默认 10%）：

- 均线策略分别改变买入偏离比例、卖出偏离比例，另一个保持不变。例如买入 5%、卖出 8%，买入侧变体为 4.5% / 5.5%，卖出侧变体为 7.2% / 8.8%。
- 动量策略分别改变回看长度、调仓间隔，N 保持不变。整数参数至少增减 1 日；表中显示实际参数值。

这是单因素分析，每个适用策略有一组基准配置和四组变体，并非参数网格搜索或自动选择最优参数。每个变体报告全区间收益、年化、回撤、相对基准的收益变化（百分点 `pp`）、费用与成交数；启用子区间分析时，也对各变体独立分段回测，报告子区间收益标准差、最差收益及盈利占比。汇总显示变体间收益标准差及最差收益变化。若参数越界（如 1 日减为 0 日），保留「invalid」行及原因，不截断到合法值或偷偷复用原参数。

「扰动最差收益变化」是有效变体的累计收益率减去基准收益率的最小值；负值表示效果下降。例如基准收益 20%、变体收益 5%，变化为 -15 pp。小幅参数变化就显著恶化收益或回撤，说明历史表现对参数敏感；此结果仍是样本内诊断，不是样本外有效性证明。

### 命令行与结果文件

本节命令从 `apps/investment/` 执行；使用仓库统一环境时，将 `uv run --locked python` 替换为 `../../.venv/bin/python`。

```bash
uv run --locked python main.py portfolio_backtest \
  --pool configs/pools/us_technology.json --strategy buy_hold cross_sectional_momentum \
  --momentum-lookback 126 --momentum-interval 21 --momentum-top-n 3 \
  --subperiod-count 5 --sensitivity --perturbation 0.1 --fee-rate 0.0003 --no-show

uv run --locked python main.py portfolio_backtest \
  --pool configs/pools/cn_large_caps.json --strategy ma_band \
  --ma-window 60 --buy-threshold 0.05 --sell-threshold 0.08 \
  --subperiod-count 5 --sensitivity --perturbation 0.1 --no-show

uv run --locked python main.py single_stock_backtest --ticker 600036.SS \
  --buy-threshold 0.05 --sell-threshold 0.08 --subperiod-count 5 --sensitivity --no-show
```

旧 `--threshold` 继续生效，作为未单独指定的买入/卖出比例默认值。旧网页草稿和历史配置也会自动沿用原来的对称比例。`portfolio_backtest --strategy all` 现在包含截面动量在内的四种策略。

新增文件位于每个策略的输出目录，网页可查看或下载 CSV，完整 ZIP 同样包含：

| 文件 | 内容 |
| --- | --- |
| `subperiods.csv` | 独立子区间结果，启用分段时生成 |
| `sensitivity.csv` | 基准配置、参数变体、效果差异及无效参数原因，启用适用的扰动分析时生成 |
| `robustness.json` | 子区间离散度、扰动统计及分析口径 |

全区间 `comparison.csv` 和策略 `summary.json` 还会带上子区间收益标准差、最差子区间收益、盈利区间占比、扰动最差收益变化（启用对应分析时）。旧记录没有这些文件时，界面显示未启用或无报告，不伪造结果。开启研究会额外运行多次回测，任务仍在后台串行执行，行情只读取一次，各变体复用同一行情快照。
