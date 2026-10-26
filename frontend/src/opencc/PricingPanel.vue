<script setup lang="ts">
import { onMounted, ref, computed } from 'vue'
import {
  modelPlazaAPI,
  type ModelPlazaGroup,
  type PlazaModel
} from '@/api/modelPlaza'
import { pointPrice, priceRate, intervalPrice } from './pricing'
import snapshot from './upstream-pricing.json'
const groups = ref<ModelPlazaGroup[]>([]),
  source = ref(''),
  query = ref(''),
  loading = ref(true),
  error = ref('')
const visible = computed(() =>
  groups.value
    .map((g) => ({
      ...g,
      models: g.models.filter((m) =>
        m.name.toLowerCase().includes(query.value.toLowerCase())
      )
    }))
    .filter((g) => g.models.length)
)
const fmt = (v: number | null) =>
  v == null
    ? '—'
    : '¥' + new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 6 }).format(v)
const price = (
  g: ModelPlazaGroup,
  m: PlazaModel,
  v: number | null | undefined,
  unit = 1_000_000
) => fmt(pointPrice(v, priceRate(g, m), unit))
async function load() {
  loading.value = true
  error.value = ''
  try {
    const d = await modelPlazaAPI.getModelPlaza()
    if (d.groups.length) {
      groups.value = d.groups
      source.value = '本站配置'
    } else {
      groups.value = snapshot.data.groups as unknown as ModelPlazaGroup[]
      source.value = `上游公开价格快照 · ${snapshot.fetched_at}`
    }
  } catch {
    error.value =
      '无法读取本站价格。以下为上游公开价格快照，尚未确认本站渠道是否可用。'
    groups.value = snapshot.data.groups as unknown as ModelPlazaGroup[]
    source.value = `上游公开价格快照 · ${snapshot.fetched_at}`
  } finally {
    loading.value = false
  }
}
onMounted(load)
</script>
<template>
  <div class="oc-info">
    <strong>模型调用价格</strong>
    <p>
      表中价格已乘分组倍率；未包含另列的时段倍率。
    </p>
    <small>{{ source }} · 空值“—”表示未提供价格，并非免费。</small>
  </div>
  <div v-if="error" class="oc-error">
    {{ error }}<button @click="load">重试</button>
  </div>
  <div class="oc-toolbar">
    <label class="oc-search"
      ><input
        v-model="query"
        placeholder="搜索模型名称"
        aria-label="搜索价格表" /></label
    ><span class="oc-hint">Token 价格单位：¥ / 百万 Tokens</span>
  </div>
  <div v-if="loading" class="oc-loading" role="status">正在加载价格</div>
  <section v-for="g in visible" :key="g.id" class="oc-panel oc-price-group">
    <div class="oc-panel-head">
      <h2>{{ g.name }}</h2>
      <span v-if="!g.credit_billing?.enabled" class="oc-tag"
        >倍率 {{ g.user_rate_multiplier ?? g.rate_multiplier }}×</span
      >
    </div>
    <div v-if="g.credit_billing?.enabled" class="oc-info">
      <strong>本站 Token 单价待公布</strong>
      <p>本站将按输入、输出、缓存读取及缓存写入用量分别计费，单位为 ¥ / 1M Tokens。此上游目录尚无本站可用的 Token 报价。</p>
    </div>
    <p v-if="!g.credit_billing?.enabled && g.peak_rate_enabled" class="oc-hint">
      高峰 {{ g.peak_start }}–{{ g.peak_end }}，另乘
      {{ g.peak_rate_multiplier }}×。
    </p>
    <div v-if="!g.credit_billing?.enabled" class="oc-table-wrap">
      <table>
        <thead>
          <tr>
            <th>模型</th>
            <th>输入</th>
            <th>输出</th>
            <th>缓存读取</th>
            <th>缓存写入 5m</th>
            <th>缓存写入 1h</th>
          </tr>
        </thead>
        <tbody>
          <template v-for="m in g.models" :key="m.name"
            ><tr>
              <td>
                <code>{{ m.name }}</code
                ><small v-if="m.pricing?.billing_mode !== 'token'">{{
                  m.pricing?.billing_mode === 'image' ? '按图计费' : '独立计费'
                }}</small>
              </td>
              <template v-if="m.pricing?.billing_mode === 'token'"
                ><td>{{ price(g, m, m.pricing?.input_price) }}</td>
                <td>{{ price(g, m, m.pricing?.output_price) }}</td>
                <td>{{ price(g, m, m.pricing?.cache_read_price) }}</td>
                <td>{{ price(g, m, m.pricing?.cache_write_price) }}</td>
                <td>
                  {{ price(g, m, m.pricing?.cache_write_1h_price) }}
                </td></template
              >
              <td v-else colspan="5">
                {{ price(g, m, m.pricing?.per_request_price, 1) }} /
                {{ m.pricing?.billing_mode === 'image' ? '张' : '次' }}
              </td>
            </tr>
            <tr
              v-if="
                (g.long_context_pricing_enabled &&
                  m.pricing?.intervals?.length) ||
                m.time_pricing?.periods?.length ||
                m.pricing?.reasoning_effort_multipliers
              "
            >
              <td colspan="6" class="oc-price-rules">
                <details>
                  <summary>查看阶梯价格与附加倍率</summary>
                  <p v-if="g.long_context_pricing_enabled">
                    长上下文计价：{{
                      m.long_context_basis === 'marginal'
                        ? '超出部分分段计费'
                        : '按请求所在档位计费'
                    }}
                  </p>
                  <div v-if="g.long_context_pricing_enabled">
                    <p v-for="(tier, i) in m.pricing?.intervals" :key="i">
                      {{
                        tier.tier_label ||
                        `${tier.min_tokens}–${tier.max_tokens ?? '不限'}`
                      }}
                      Tokens：输入
                      {{
                        price(
                          g,
                          m,
                          intervalPrice(
                            m.pricing?.input_price,
                            tier,
                            'input_price'
                          )
                        )
                      }}
                      / 输出
                      {{
                        price(
                          g,
                          m,
                          intervalPrice(
                            m.pricing?.output_price,
                            tier,
                            'output_price'
                          )
                        )
                      }}
                      / 缓存读
                      {{
                        price(
                          g,
                          m,
                          intervalPrice(
                            m.pricing?.cache_read_price,
                            tier,
                            'cache_read_price'
                          )
                        )
                      }}
                      / 缓存写
                      {{
                        price(
                          g,
                          m,
                          intervalPrice(
                            m.pricing?.cache_write_price,
                            tier,
                            'cache_write_price'
                          )
                        )
                      }}
                    </p>
                  </div>
                  <p v-for="(t, i) in m.time_pricing?.periods" :key="i">
                    {{ m.time_pricing?.timezone }}
                    {{ m.time_pricing?.weekdays_only ? '工作日' : '' }}
                    {{ t.start_time }}–{{ t.end_time }}：表内价格 ×
                    {{ t.multiplier }}
                  </p>
                  <p
                    v-for="(multiplier, effort) in m.pricing
                      ?.reasoning_effort_multipliers"
                    :key="effort"
                  >
                    推理强度 {{ effort }}：表内价格 × {{ multiplier }}
                  </p>
                </details>
              </td>
            </tr></template
          >
        </tbody>
      </table>
    </div>
  </section>
  <div v-if="!visible.length && !loading" class="oc-empty">
    没有匹配的模型。
  </div>
</template>
<style scoped>
.oc-info p {
  margin: 8px 0;
}
.oc-info small {
  font-size: 12.5px;
  color: var(--oc-muted);
}
.oc-price-group {
  padding: 0;
  overflow: hidden;
}
.oc-price-group > .oc-panel-head {
  padding: 20px 24px 0;
}
.oc-price-group > .oc-hint {
  padding: 0 24px 14px;
  margin-top: 0 !important;
}
.oc-price-rules {
  white-space: normal !important;
  background: var(--oc-surface-2);
}
.oc-price-rules details {
  font-size: 13px;
  color: var(--oc-ink-2);
}
.oc-price-rules p {
  margin: 8px 0;
  line-height: 1.7;
}
.oc-price-rules summary {
  cursor: pointer;
  font-weight: 600;
  color: var(--oc-brand-ink);
}
</style>
