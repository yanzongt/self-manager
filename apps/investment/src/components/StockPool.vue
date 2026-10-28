<script setup lang="ts">
import { ref } from "vue";
import type { Stock, Preset } from "../model";
const pool = defineModel<Stock[]>({ required: true });
defineProps<{ presets: Preset[] }>();
const emit = defineEmits<{ save: [name: string]; preset: [name: string] }>();
const name = ref(""),
  preset = ref("");
function equal() {
  const weight = Math.floor(1e8 / pool.value.length) / 1e8;
  pool.value.forEach((s) => (s.weight = weight));
}
function clear() {
  if (confirm("新建将清空当前编辑的股票池，是否继续？")) {
    pool.value = [{ ticker: "", name: "", weight: 1 }];
    name.value = "";
    preset.value = "";
  }
}
</script>
<template>
  <section class="config-section">
    <div class="section-title">
      <h3>01 股票池</h3>
      <button
        id="equal-weights"
        type="button"
        class="text-button"
        @click="equal"
      >
        等权分配
      </button>
    </div>
    <div id="pool-rows">
      <div v-for="(stock, index) in pool" :key="index" class="pool-row">
        <label
          >股票代码<input
            v-model="stock.ticker"
            class="sm-control stock-ticker"
            :aria-label="`股票 ${index + 1} 代码`"
            placeholder="600036.SS"
            required
            maxlength="30" /></label
        ><label
          >名称<input
            v-model="stock.name"
            class="sm-control stock-name"
            :aria-label="`股票 ${index + 1} 名称`"
            placeholder="股票名称"
            maxlength="100" /></label
        ><label
          >权重 %<input
            class="sm-control stock-weight"
            :aria-label="`股票 ${index + 1} 权重`"
            :value="Number((stock.weight * 100).toFixed(6))"
            type="number"
            min="0"
            max="100"
            step="any"
            required
            @input="
              stock.weight =
                Number(($event.target as HTMLInputElement).value) / 100
            " /></label
        ><button
          class="text-button danger remove-stock"
          :aria-label="`移除股票 ${index + 1}`"
          type="button"
          @click="pool.splice(index, 1)"
        >
          ×
        </button>
      </div>
    </div>
    <button
      id="add-stock"
      class="sm-button"
      type="button"
      :disabled="pool.length >= 50"
      @click="pool.push({ ticker: '', name: '', weight: 0 })"
    >
      ＋ 添加股票
    </button>
    <div class="pool-footer">
      <span id="pool-count">{{ pool.length }} 只股票</span
      ><span
        >剩余现金
        <b id="cash-weight"
          >{{
            ((1 - pool.reduce((sum, s) => sum + s.weight, 0)) * 100).toFixed(2)
          }}%</b
        ></span
      >
    </div>
    <label
      >股票池名称<input
        id="pool-name"
        v-model="name"
        class="sm-control"
        maxlength="80"
        placeholder="例如：长期配置"
    /></label>
    <div class="actions">
      <button id="new-pool" class="text-button" type="button" @click="clear">
        新建股票池</button
      ><button
        id="save-pool"
        class="text-button"
        type="button"
        @click="emit('save', name)"
      >
        保存股票池
      </button>
    </div>
    <label
      >快速载入<select
        id="pool-preset"
        v-model="preset"
        class="sm-control"
        @change="
          emit('preset', preset);
          name = presets.find((p) => p.name === preset)?.saved ? preset : '';
        "
      >
        <option value="">选择股票池模板</option>
        <option v-for="p in presets" :key="p.name" :value="p.name">
          {{ p.saved ? "已保存：" : "" }}{{ p.name }}
        </option>
      </select></label
    >
  </section>
</template>
