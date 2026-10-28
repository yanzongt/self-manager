<script setup lang="ts">
import type { BacktestConfig } from "../model";
import StockPool from "./StockPool.vue";
import type { Preset } from "../model";
const config = defineModel<BacktestConfig>({ required: true });
defineProps<{ running: boolean; presets: Preset[] }>();
const emit = defineEmits<{
  submit: [];
  savePool: [name: string];
  preset: [name: string];
}>();
</script>
<template>
  <form @submit.prevent="emit('submit')" id="backtest-form">
    <StockPool
      v-model="config.pool"
      :presets="presets"
      @save="emit('savePool', $event)"
      @preset="emit('preset', $event)"
    />

    <section class="config-section">
      <div class="section-title">
        <h3><span class="step-number">02</span>交易策略</h3>
        <span class="muted small">可多选比较</span>
      </div>
      <label class="strategy-option"
        ><input
          class=""
          name="strategy"
          type="checkbox"
          v-model="config.strategies"
          value="buy_hold" /><span class="strategy-icon blue"></span
        ><span><strong>买入持有</strong><small>初始买入，持续持有</small></span
        ><span class="option-check"></span
      ></label>
      <label class="strategy-option"
        ><input
          class=""
          name="strategy"
          type="checkbox"
          v-model="config.strategies"
          value="ma_band" /><span class="strategy-icon green"></span
        ><span
          ><strong>MA 均线策略</strong><small>偏离均线，择时买卖</small></span
        ><span class="option-check"></span
      ></label>
      <div
        class="strategy-settings"
        id="ma-options"
        v-if="config.strategies.includes('ma_band')"
      >
        <div class="field">
          <label for="ma-trade-mode">买卖执行方式</label
          ><select
            class="sm-control"
            id="ma-trade-mode"
            v-model="config.ma_trade_mode"
          >
            <option value="full_position">全仓进出（原模式）</option>
            <option value="independent">独立买卖（连续加仓、分批卖出）</option>
          </select>
        </div>
        <div
          id="ma-independent-options"
          v-if="config.ma_trade_mode === 'independent'"
        >
          <div class="field">
            <label for="ma-buy-budget-mode">买入预算方式</label
            ><select
              class="sm-control"
              id="ma-buy-budget-mode"
              v-model="config.ma_buy_budget_mode"
            >
              <option value="fixed">固定买入总预算</option>
              <option value="cash_plus_extra">
                全部可用现金＋额外追加金额
              </option>
            </select>
          </div>
          <div
            id="ma-extra-options"
            v-if="config.ma_buy_budget_mode === 'cash_plus_extra'"
          >
            <div class="field">
              <label for="ma-extra-amount"
                >每个买入日额外追加金额 <span>可设为 0</span></label
              ><input
                class="sm-control"
                id="ma-extra-amount"
                min="0"
                required
                step="any"
                type="number"
                v-model.number="config.ma_extra_amount"
              />
            </div>
            <p class="rule-note">
              实际成交日先卖后买，用全部可用现金加额外金额买入；当天多只股票共用一次追加，按触发股票的相对权重分配。无可成交买单时不追加。
            </p>
          </div>
          <div
            class="field"
            id="ma-funding-field"
            v-if="config.ma_buy_budget_mode === 'fixed'"
          >
            <label for="ma-funding-mode">买入资金来源</label
            ><select
              class="sm-control"
              id="ma-funding-mode"
              v-model="config.ma_funding_mode"
            >
              <option value="cash">仅使用账户现金</option>
              <option value="auto_contribute">现金不足时自动追加资金</option>
            </select>
          </div>
          <div
            class="field"
            id="ma-fixed-budget-field"
            v-if="config.ma_buy_budget_mode === 'fixed'"
          >
            <label for="ma-buy-amount"
              >每次买入总预算 <span>含费用，按池权重分配</span></label
            ><input
              class="sm-control"
              id="ma-buy-amount"
              min="0.01"
              required
              step="any"
              type="number"
              v-model.number="config.ma_buy_amount"
            />
          </div>
          <div class="field">
            <label for="ma-sell-fraction">每次卖出持仓比例</label>
            <div class="input-unit">
              <input
                :value="Number((config.ma_sell_fraction * 100).toFixed(6))"
                @input="
                  config.ma_sell_fraction =
                    Number(($event.target as HTMLInputElement).value) / 100
                "
                class="sm-control"
                id="ma-sell-fraction"
                max="100"
                min="0.01"
                required
                step="any"
                type="number"
              /><span>%</span>
            </div>
          </div>
          <p class="rule-note">
            每个收盘日独立检查买卖条件，满足买入条件可连续加仓，满足卖出条件可连续减仓，下一有效收盘成交。资金来源可选择仅使用账户现金，或自动追加不足金额以足额买入；无持仓时忽略卖出条件，不做空。自动追加会计入投入本金，收益和回撤剔除入金影响。
          </p>
        </div>
        <div class="field">
          <label for="ma-window">均线窗口 <span>交易日</span></label
          ><input
            class="sm-control"
            id="ma-window"
            max="5000"
            min="1"
            required
            type="number"
            v-model.number="config.ma_window"
          />
        </div>
        <div aria-label="均线快捷选择" class="ma-presets">
          <button
            @click="config.ma_window = 30"
            class="sm-button"
            :class="{ 'sm-button-primary': config.ma_window === 30 }"
            data-ma="30"
            type="button"
          >
            MA30</button
          ><button
            @click="config.ma_window = 60"
            class="sm-button"
            :class="{ 'sm-button-primary': config.ma_window === 60 }"
            data-ma="60"
            type="button"
          >
            MA60</button
          ><button
            @click="config.ma_window = 120"
            class="sm-button"
            :class="{ 'sm-button-primary': config.ma_window === 120 }"
            data-ma="120"
            type="button"
          >
            MA120</button
          ><button
            @click="config.ma_window = 250"
            class="sm-button"
            :class="{ 'sm-button-primary': config.ma_window === 250 }"
            data-ma="250"
            type="button"
          >
            MA250
          </button>
        </div>
        <div class="field">
          <label for="threshold">买入偏离比例</label>
          <div class="input-unit">
            <input
              :value="Number((config.buy_threshold * 100).toFixed(6))"
              @input="
                config.buy_threshold =
                  Number(($event.target as HTMLInputElement).value) / 100
              "
              class="sm-control"
              id="threshold"
              max="99.99"
              min="0.01"
              required
              step="0.01"
              type="number"
            /><span>%</span>
          </div>
        </div>
        <label class="small"
          ><input
            class=""
            id="ma-buy-first-only"
            type="checkbox"
            v-model="config.ma_buy_first_only"
          />
          买入仅首次达到时交易（退出条件后才可再次触发）</label
        >
        <div class="field">
          <label for="sell-threshold">卖出偏离比例</label>
          <div class="input-unit">
            <input
              :value="Number((config.sell_threshold * 100).toFixed(6))"
              @input="
                config.sell_threshold =
                  Number(($event.target as HTMLInputElement).value) / 100
              "
              class="sm-control"
              id="sell-threshold"
              max="99.99"
              min="0.01"
              required
              step="0.01"
              type="number"
            /><span>%</span>
          </div>
        </div>
        <label class="small"
          ><input
            class=""
            id="ma-sell-first-only"
            type="checkbox"
            v-model="config.ma_sell_first_only"
          />
          卖出仅首次达到时交易（退出条件后才可再次触发）</label
        >
        <p class="rule-note" id="ma-rule">
          低于 MA{{ config.ma_window }} 的
          {{ Number(((1 - config.buy_threshold) * 100).toFixed(4)) }}%
          买入，高于
          {{ Number(((1 + config.sell_threshold) * 100).toFixed(4)) }}% 卖出。
        </p>
      </div>
      <label class="strategy-option"
        ><input
          class=""
          name="strategy"
          type="checkbox"
          v-model="config.strategies"
          value="fixed_weight" /><span class="strategy-icon amber"></span
        ><span
          ><strong>固定权重再平衡</strong><small>定期恢复配置权重</small></span
        ><span class="option-check"></span
      ></label>
      <div
        class="strategy-settings"
        id="rebalance-options"
        v-if="config.strategies.includes('fixed_weight')"
      >
        <div class="field">
          <label for="frequency">再平衡频率</label
          ><select
            class="sm-control"
            id="frequency"
            v-model="config.rebalance_frequency"
          >
            <option value="monthly">每月</option>
            <option value="quarterly">每季度</option>
            <option value="semiannual">每半年</option>
            <option value="annual">每年</option>
            <option value="each_observation">每个交易日</option>
          </select>
        </div>
      </div>
      <label class="strategy-option">
        <input
          class=""
          name="strategy"
          type="checkbox"
          v-model="config.strategies"
          value="cross_sectional_momentum"
        />
        <span class="strategy-icon blue"></span>
        <span
          ><strong>截面动量策略</strong
          ><small>定期买入过去收益前 N 名</small></span
        ><span class="option-check"></span>
      </label>
      <div
        class="strategy-settings"
        id="momentum-options"
        v-if="config.strategies.includes('cross_sectional_momentum')"
      >
        <div class="field">
          <label for="momentum-lookback">收益回看长度 <span>行情日</span></label
          ><input
            class="sm-control"
            id="momentum-lookback"
            max="5000"
            min="1"
            required
            type="number"
            v-model.number="config.momentum_lookback"
          />
        </div>
        <div class="field">
          <label for="momentum-interval">调仓间隔 <span>行情日</span></label
          ><input
            class="sm-control"
            id="momentum-interval"
            max="5000"
            min="1"
            required
            type="number"
            v-model.number="config.momentum_interval"
          />
        </div>
        <div class="field">
          <label for="momentum-top-n">持有前 N 只</label
          ><input
            class="sm-control"
            id="momentum-top-n"
            max="50"
            min="1"
            required
            type="number"
            v-model.number="config.momentum_top_n"
          />
        </div>
        <p class="rule-note">
          收盘排名，下一有效收盘成交。入选股票各占
          1/N，不使用上方固定权重；合格股票不足 N
          只时空缺份额留现金。回看期内缺失行情的股票不参与排名。
        </p>
      </div>
      <label class="strategy-option">
        <input
          class=""
          name="strategy"
          type="checkbox"
          v-model="config.strategies"
          value="dca"
        />
        <span class="strategy-icon amber"></span>
        <span
          ><strong>定投策略</strong
          ><small>定期追加资金，按权重买入</small></span
        ><span class="option-check"></span>
      </label>
      <div
        class="strategy-settings"
        id="dca-options"
        v-if="config.strategies.includes('dca')"
      >
        <div class="field">
          <label for="dca-amount">每期追加金额 <span>含买入费用</span></label
          ><input
            class="sm-control"
            id="dca-amount"
            min="0.01"
            required
            step="any"
            type="number"
            v-model.number="config.dca_amount"
          />
        </div>
        <div class="field">
          <label for="dca-frequency">定投周期</label
          ><select
            class="sm-control"
            id="dca-frequency"
            v-model="config.dca_frequency"
          >
            <option value="weekly">每周</option>
            <option value="monthly">每月</option>
            <option value="quarterly">每季度</option>
            <option value="annual">每年</option>
            <option value="each_observation">每个行情日</option>
          </select>
        </div>
        <p class="rule-note">
          首日按股票池权重投入初始资金，之后在新周期的首个行情日追加固定金额，只买入、不卖出。无报价的份额留现金等待成交。收益率与回撤采用时间加权口径，剔除追加本金影响。
        </p>
      </div>
    </section>
    <section class="config-section">
      <div class="section-title">
        <h3><span class="step-number">03</span>回测条件</h3>
      </div>
      <div class="two-fields">
        <div class="field">
          <label for="period">历史范围</label
          ><select class="sm-control" id="period" v-model="config.period">
            <option value="1y">最近 1 年</option>
            <option value="3y">最近 3 年</option>
            <option value="5y">最近 5 年</option>
            <option value="10y">最近 10 年</option>
            <option value="max">全部历史</option>
            <option value="ytd">今年以来</option>
          </select>
        </div>
        <div class="field">
          <label for="initial-cash">初始资金</label
          ><input
            class="sm-control"
            id="initial-cash"
            min="1"
            required
            step="any"
            type="number"
            v-model.number="config.initial_cash"
          />
        </div>
      </div>
      <div class="field">
        <label for="fee-rate"
          >单边手续费 <span>买入 / 卖出分别计费</span></label
        >
        <div class="input-unit">
          <input
            :value="Number((config.fee_rate * 100).toFixed(6))"
            @input="
              config.fee_rate =
                Number(($event.target as HTMLInputElement).value) / 100
            "
            class="sm-control"
            id="fee-rate"
            max="99.99"
            min="0"
            required
            step="0.001"
            type="number"
          /><span>%</span>
        </div>
      </div>
      <div class="field">
        <label for="data-mode">行情读取方式</label
        ><select class="sm-control" id="data-mode" v-model="config.data_mode">
          <option value="cache">优先使用本地缓存</option>
          <option value="refresh">重新下载并更新缓存</option>
          <option value="offline">仅使用缓存 · 完全离线</option>
        </select>
      </div>
      <p class="small muted data-hint">
        缓存不会自动更新。首次使用的股票会下载完整历史。
      </p>
    </section>
    <section class="config-section">
      <div class="section-title">
        <h3><span class="step-number">04</span>稳定性研究</h3>
      </div>
      <div class="field">
        <label for="subperiod-count">独立子区间数量</label
        ><input
          class="sm-control"
          id="subperiod-count"
          max="50"
          min="0"
          required
          type="number"
          v-model.number="config.subperiod_count"
        />
      </div>
      <p class="rule-note">
        0 为关闭，2～50
        为启用。按行情日等分，每段重新建仓并计入费用；利用起点之前的行情预热信号。
      </p>
      <label class="strategy-option"
        ><input
          class=""
          id="sensitivity-enabled"
          type="checkbox"
          v-model="config.sensitivity_enabled" /><span
          ><strong>参数扰动分析</strong
          ><small>单独改变每个参数，比较效果</small></span
        ><span class="option-check"></span
      ></label>
      <div class="field">
        <label for="perturbation">相对扰动幅度</label>
        <div class="input-unit">
          <input
            :value="Number((config.perturbation * 100).toFixed(6))"
            @input="
              config.perturbation =
                Number(($event.target as HTMLInputElement).value) / 100
            "
            :disabled="!config.sensitivity_enabled"
            class="sm-control"
            id="perturbation"
            max="99.99"
            min="0.01"
            required
            step="0.01"
            type="number"
          /><span>%</span>
        </div>
      </div>
      <p class="rule-note">
        例如 5% 偏离比例在 ±10% 扰动后为 4.5%、5.5%。行情日参数至少改变 1
        日。启用后会额外运行多组回测。
      </p>
    </section>
    <div class="run-controls">
      <button
        :disabled="running"
        class="sm-button sm-button-primary run-button"
        id="run-button"
        type="submit"
      >
        <span>{{ running ? "正在回测…" : "运行回测" }}</span>
      </button>
      <p>各策略独立账户 · 同区间 · 同初始资金，定投另有周期入金</p>
    </div>
  </form>
</template>
