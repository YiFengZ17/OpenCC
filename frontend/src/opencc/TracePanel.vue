<script setup lang="ts">
import { ref, shallowRef, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import { keysAPI } from '@/api/keys'
import { modelPlazaAPI } from '@/api/modelPlaza'
import type { ApiKey } from '@/types'
import Icon from './Icon.vue'
import {
  generateChallenges,
  type Challenge
} from './vendor/modeltrace/challenge-browser.js'
import {
  analyzeGlobalOutputs,
  type Bank,
  type TraceResult
} from './vendor/modeltrace/fingerprint-core.js'
import {
  runProbe,
  verdict,
  verdictTone,
  protocolFor,
  defaultModel,
  type Probe,
  type TraceProtocol
} from './trace'
import catalog from './catalog.json'
import bankURL from './vendor/modeltrace/unified_bank.json?url'
const keys = ref<ApiKey[]>([]),
  keyId = ref<number>(),
  model = ref(''),
  protocol = ref<TraceProtocol>('anthropic'),
  options = ref<string[]>([])
const SOURCE = 'https://github.com/xqy2006/ModelTrace'
const COMMIT = '6cd4a8ff0f3f4e49d6d6969dd2fbadfa1569fde2'
const running = ref(false),
  protocolTouched = ref(false),
  error = ref(''),
  progress = ref(''),
  result = ref<TraceResult>(),
  probes = ref<Probe[]>([]),
  challenges = ref<Challenge[]>([]),
  bank = shallowRef<Bank>()
const manual = ref(false),
  manualTexts = ref(['', '', '']),
  reportModel = ref(''),
  manualReport = ref(false)
let controller: AbortController | undefined
let cancelled = false
const selectedKey = computed(() => keys.value.find((k) => k.id === keyId.value))
const ids = computed(() => bank.value?.models.map((m) => m.id) || [])
const conclusion = computed(() =>
  result.value
    ? verdict(
        reportModel.value,
        ids.value,
        result.value.prediction,
        result.value.used_outputs
      )
    : ''
)
const tone = computed(() =>
  result.value
    ? verdictTone(
        reportModel.value,
        ids.value,
        result.value.prediction,
        result.value.used_outputs
      )
    : 'unknown'
)
const verifiable = computed(() => ids.value.includes(model.value.trim()))
const percent = (n: number) => (n * 100).toFixed(1) + '%'
// Follow the model's natural API format until the user picks one by hand.
watch(model, (m) => {
  if (!protocolTouched.value) protocol.value = protocolFor(m.trim())
})
async function initialize() {
  error.value = ''
  try {
    const response = await fetch(bankURL)
    if (!response.ok) throw new Error('Fingerprint bank unavailable')
    bank.value = (await response.json()) as Bank
    const all: ApiKey[] = []
    let page = 1
    while (page <= 10) {
      const k = await keysAPI.list(page, 100)
      all.push(...k.items)
      if (all.length >= k.total || !k.items.length) break
      page++
    }
    keys.value = all.filter((k) => k.status === 'active')
    keyId.value = keys.value[0]?.id
    const data = await modelPlazaAPI.getModelPlaza()
    options.value = [
      ...new Set(data.groups.flatMap((g) => g.models.map((m) => m.name)))
    ]
    if (!options.value.length) options.value = catalog.models
    model.value = defaultModel(options.value, ids.value)
    resetChallenges()
  } catch {
    error.value = '检测数据加载失败，请刷新重试。'
  }
}
function resetChallenges() {
  challenges.value = generateChallenges(3)
  manualTexts.value = ['', '', '']
  result.value = undefined
  probes.value = []
}
async function start() {
  if (
    running.value ||
    !selectedKey.value ||
    !model.value.trim() ||
    !bank.value
  )
    return
  running.value = true
  error.value = ''
  result.value = undefined
  probes.value = []
  cancelled = false
  reportModel.value = model.value.trim()
  manualReport.value = false
  const testKey = selectedKey.value.key,
    testProtocol = protocol.value
  challenges.value = generateChallenges(3)
  try {
    for (let i = 0; i < 3; i++) {
      if (cancelled) break
      progress.value = `第 ${i + 1} / 3 轮：等待模型回答`
      const c = challenges.value[i]
      const current = new AbortController()
      controller = current
      const timeout = setTimeout(() => current.abort(), 120000)
      try {
        probes.value.push(
          await runProbe(
            reportModel.value,
            testKey,
            c.prompt,
            c.expected_count,
            testProtocol,
            current.signal
          )
        )
      } catch (e) {
        probes.value.push({
          text: '',
          expected_count: c.expected_count,
          request_id: '',
          duration_ms: 0,
          valid: false,
          error: current.signal.aborted
            ? cancelled
              ? '已取消'
              : '请求超时'
            : e instanceof Error
              ? e.message
              : '请求失败'
        })
      } finally {
        clearTimeout(timeout)
      }
    }
    const accepted = probes.value.filter((p) => p.valid)
    if (accepted.length)
      result.value = analyzeGlobalOutputs(accepted, bank.value)
    if (cancelled) error.value = '检测已取消。已发出的请求可能仍产生费用。'
    else if (accepted.length < 3)
      error.value = '未取得三份有效回答，结果不完整。请检查失败原因后重新检测。'
  } catch {
    error.value = '指纹计算失败，请重新检测。'
  } finally {
    running.value = false
    progress.value = ''
    controller = undefined
  }
}
function analyzeManual() {
  if (!bank.value) return
  error.value = ''
  result.value = undefined
  reportModel.value = model.value.trim()
  manualReport.value = true
  try {
    result.value = analyzeGlobalOutputs(
      challenges.value.map((c, i) => ({ ...c, text: manualTexts.value[i] })),
      bank.value
    )
  } catch (e) {
    error.value = e instanceof Error ? e.message : '无法计算'
  }
}
function cancel() {
  cancelled = true
  controller?.abort()
}
onMounted(initialize)
onBeforeUnmount(() => {
  cancel()
  keys.value = []
})
async function copyPrompt(p: string) {
  try {
    await navigator.clipboard.writeText(p)
  } catch {
    error.value = '复制失败，请手动选择提示词。'
  }
}
function download() {
  if (!result.value) return
  const report = {
    tool: 'ModelTrace',
    source: SOURCE,
    commit: COMMIT,
    created_at: new Date().toISOString(),
    requested_model: reportModel.value,
    mode: manualReport.value ? 'manual' : 'api',
    conclusion: conclusion.value,
    limitation: '候选库内的统计归因，不是模型来源或纯度保证。',
    result: result.value,
    probes: probes.value.map((p) => ({
      request_id: p.request_id,
      valid: p.valid,
      error: p.error,
      duration_ms: p.duration_ms
    }))
  }
  const url = URL.createObjectURL(
    new Blob([JSON.stringify(report, null, 2)], { type: 'application/json' })
  )
  const a = document.createElement('a')
  a.href = url
  a.download = 'opencc-modeltrace.json'
  a.click()
  URL.revokeObjectURL(url)
}
function switchMode(value:boolean){manual.value=value;error.value='';resetChallenges()}
</script>
<template>
  <section class="oc-trace-hero">
    <span class="oc-eyebrow">ModelTrace · 开源模型指纹检测</span>
    <h2>这个模型，真的是它自称的那个吗？</h2>
    <p>
      不用相信我们的说法，自己测一下。ModelTrace 让模型做三道“随手写一长串数字”的题，每个模型写数字的习惯都不一样，就像指纹。把结果和 {{ ids.length || 18 }}
      个已知模型的指纹比一比，就知道接口背后大概率是谁。</p>
    <div class="oc-trace-badges">
      <a :href="SOURCE" target="_blank" rel="noopener noreferrer"
        ><b>第三方开源</b><span>xqy2006/ModelTrace · MIT ↗</span></a
      ><a :href="`${SOURCE}/tree/${COMMIT}`" target="_blank" rel="noopener noreferrer"
        ><b>代码原样引入</b><span>固定版本 {{ COMMIT.slice(0, 7) }}，可逐字比对 ↗</span></a
      ><span
        ><b>在你的浏览器里计算</b><span>指纹比对不经过我们的服务器</span></span
      ><span><b>报告可复核</b><span>下载报告，用原项目独立复测</span></span>
    </div>
  </section>
  <div v-if="error" class="oc-error" role="alert">{{ error }}</div>
  <section v-if="!manual" class="oc-panel oc-trace-run">
    <div class="oc-panel-head">
      <h2>一键检测</h2>
      <button class="oc-text-link" @click="switchMode(true)">没有密钥？手动粘贴检测 →</button>
    </div>
    <fieldset :disabled="running">
      <label class="oc-field"
        >要检测的模型<input
          v-model="model"
          list="trace-models"
          placeholder="例如 claude-sonnet-4-6" /><datalist id="trace-models">
          <option v-for="m in options" :key="m" :value="m" /></datalist
      ></label>
      <p class="oc-hint">
        <template v-if="!model.trim()">选择或输入完整的模型 ID。</template>
        <template v-else-if="verifiable">✓ 指纹库收录了这个型号，可以核验到具体版本。</template>
        <template v-else>指纹库还没有这个型号，只能看出最接近哪个已知模型，无法核验版本。</template>
      </p>
      <details class="oc-trace-advanced">
        <summary>高级设置 · {{ selectedKey?.name || '未选择密钥' }} · {{ protocol === 'anthropic' ? 'Anthropic Messages' : protocol === 'responses' ? 'OpenAI Responses' : 'OpenAI Chat Completions' }}</summary>
        <label class="oc-field"
          >使用哪把本站密钥<select v-model="keyId">
            <option v-for="k in keys" :key="k.id" :value="k.id">
              {{ k.name }} · {{ k.group?.name || '默认分组' }}
            </option>
          </select></label
        ><label class="oc-field"
          >接口格式<select v-model="protocol" @change="protocolTouched = true">
            <option value="anthropic">Anthropic Messages</option>
            <option value="openai">OpenAI Chat Completions</option>
            <option value="responses">OpenAI Responses</option>
          </select></label
        >
      </details>
      <p v-if="!keys.length" class="oc-hint">
        还没有可用的密钥。<RouterLink to="/keys" class="oc-text-link">先去创建一把 →</RouterLink>
      </p>
      <button
        class="oc-button primary wide"
        :disabled="!selectedKey || !model.trim() || !bank"
        @click="start"
      >
        开始检测</button>
      <p class="oc-hint oc-trace-cost">
        会用这把密钥发 3 次请求（每次最多 4096 个输出 Token），和平时调用一样计费，大约 1 分钟。</p>
    </fieldset>
    <div v-if="running || probes.length" class="oc-trace-steps" role="status">
      <span
        v-for="i in 3"
        :key="i"
        :class="{
          done: probes[i - 1]?.valid,
          bad: probes[i - 1] && !probes[i - 1].valid,
          active: running && probes.length === i - 1
        }"
        ><i>{{ probes[i - 1] ? (probes[i - 1].valid ? '✓' : '!') : i }}</i>第 {{ i }} 轮</span
      >
    </div>
    <ul v-if="!running && probes.some((p) => !p.valid)" class="oc-trace-failures">
      <template v-for="(p, i) in probes" :key="i"
        ><li v-if="!p.valid">第 {{ i + 1 }} 轮：{{ p.error }}</li></template
      >
    </ul>
    <p v-if="running" class="oc-hint">{{ progress }}</p>
    <button v-if="running" class="oc-button wide" @click="cancel">停止检测</button>
  </section>
  <section v-if="manual" class="oc-panel">
    <div class="oc-panel-head">
      <h2>手动粘贴检测</h2>
      <button class="oc-text-link" @click="switchMode(false)">← 返回一键检测</button>
    </div>
    <p class="oc-hint">
      适合在别的客户端里测试：把下面三条提示词分别发给同一个模型，每条都开新对话，再把完整回答贴回来。手动粘贴的内容无法证明来自哪个接口，报告里会注明。</p>
    <label class="oc-field"
      >模型 ID<input v-model="model" list="trace-models" placeholder="例如 claude-sonnet-4-6"
    /></label>
    <div v-for="(c, i) in challenges" :key="c.id" class="oc-manual-probe">
      <h3>第 {{ i + 1 }} 题 · 约 {{ c.expected_count }} 个数字</h3>
      <p>{{ c.prompt }}</p>
      <button class="oc-button small" @click="copyPrompt(c.prompt)">复制提示词</button
      ><label class="oc-field"
        >模型的完整回答<textarea
          v-model="manualTexts[i]"
          rows="4"
          maxlength="100000"
          placeholder="粘贴这一题的完整回答"
        />
      </label>
    </div>
    <div class="oc-hero-actions">
      <button
        class="oc-button primary"
        :disabled="!model.trim() || !manualTexts.every((t) => t.trim())"
        @click="analyzeManual"
      >
        计算结果</button
      ><button class="oc-button" @click="resetChallenges">换一组题目</button>
    </div>
  </section>
  <section v-if="result" class="oc-panel">
    <div class="oc-panel-head">
      <h2>检测结果</h2>
      <button class="oc-button small" @click="download">
        <Icon name="order" />下载报告</button>
    </div>
    <div :class="['oc-trace-verdict', tone]">
      <b>{{ tone === 'match' ? '✓' : tone === 'mismatch' ? '✕' : '?' }}</b>
      <div>
        <strong>{{ conclusion }}</strong>
        <small
          >你选的是 {{ reportModel }}，最像 {{ result.prediction_name }}（库内概率{{ percent(result.probability) }}）· 有效样本 {{ result.used_outputs }} / 3 ·
          {{ manualReport ? '手动粘贴' : '本站接口实测' }}</small
        >
      </div>
    </div>
    <p v-if="tone === 'mismatch'" class="oc-hint">
      偶尔一次不一致可能是随机波动，建议隔一会儿再测一次；多次不一致请保留报告联系我们。</p>
    <details class="oc-trace-details">
      <summary>查看全部候选和请求记录</summary>
      <div class="oc-table-wrap">
        <table>
          <thead>
            <tr>
              <th>候选模型</th>
              <th>库内概率</th>
              <th>分布相似度</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in result.results" :key="r.model">
              <td>{{ r.display_name }}</td>
              <td>{{ percent(r.probability) }}</td>
              <td>{{ percent(r.profile_similarity) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-for="(p, i) in probes" :key="i" class="oc-probe-row">
        <span>第 {{ i + 1 }} 轮</span
        ><span :class="['oc-tag', p.valid ? '' : 'amber']">{{ p.valid ? '有效样本' : p.error }}</span
        ><code>{{ p.request_id || '—' }}</code
        ><small>{{ (p.duration_ms / 1000).toFixed(1) }} 秒</small>
      </div>
    </details>
  </section>
  <section class="oc-panel oc-trace-notes">
    <h2>为什么可以相信这个结果</h2>
    <ul>
      <li>
        <b>工具不是我们写的。</b>ModelTrace 是独立的开源项目，算法、题目生成和指纹库都按原样引入，<a :href="`${SOURCE}/tree/${COMMIT}`" target="_blank" rel="noopener noreferrer">固定在 {{ COMMIT.slice(0, 7) }} 版本</a>，任何人都能比对代码。</li>
      <li><b>题目每次随机抽取。</b>每次从题库里随机组合三道题，接口很难提前知道这一次考什么。</li>
      <li><b>计算在你的浏览器里完成。</b>我们只负责把请求转给模型，比对过程不经过我们的服务器。</li>
      <li><b>密钥只发给本站接口。</b>不会发给 ModelTrace 项目方或任何第三方地址。</li>
      <li><b>结果可以独立复核。</b>下载报告后，可以用原项目对同一个接口再测一次。</li>
    </ul>
    <details>
      <summary>结果的边界（请读一下）</summary>
      <p>
        库内概率只在已收录的 {{ ids.length }} 个模型之间比较，不是“纯度百分比”。没收录的模型可能被归到最像的已知模型上；系统提示词会影响输出，原项目提醒 Claude Code 等环境下偏差可能较大。一次检测一致，也不能保证每一次请求都来自同一个模型，所以我们建议定期复测。</p>
      <p class="oc-bank-list">{{ ids.join('\n') }}</p>
    </details>
    <small>ModelTrace {{ COMMIT.slice(0, 7) }} · MIT License · OpenCC 使用其开源实现，未经项目方认证或背书</small>
  </section>
</template>
<style scoped>
.oc-trace-hero {
  padding: 28px 30px;
  border-radius: var(--oc-radius);
  background: var(--oc-hero-bg);
  color: var(--oc-hero-card-ink);
  margin-bottom: 20px;
}
.oc-trace-hero .oc-eyebrow {
  color: var(--oc-hero-card-muted);
}
.oc-trace-hero h2 {
  font-size: 26px;
  line-height: 1.35;
  margin: 10px 0 12px;
  color: var(--oc-hero-card-ink);
}
.oc-trace-hero > p {
  max-width: 760px;
  line-height: 1.85;
  color: var(--oc-hero-card-muted);
}
.oc-trace-badges {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  margin-top: 22px;
}
.oc-trace-badges > * {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 12px 14px;
  border-radius: 12px;
  border: 1px solid rgb(255 255 255 / 0.14);
  background: rgb(255 255 255 / 0.06);
  color: inherit;
  text-decoration: none;
}
.oc-trace-badges a:hover {
  background: rgb(255 255 255 / 0.12);
}
.oc-trace-badges b {
  font-size: 14px;
}
.oc-trace-badges > * > span {
  font-size: 12.5px;
  color: var(--oc-hero-card-muted);
}
.oc-trace-run fieldset {
  border: 0;
  padding: 0;
  margin: 0;
}
.oc-trace-advanced {
  margin: 14px 0;
  font-size: 14px;
  color: var(--oc-ink-2);
}
.oc-trace-advanced summary,
.oc-trace-details summary {
  cursor: pointer;
  font-weight: 600;
  color: var(--oc-brand-ink);
}
.oc-trace-advanced .oc-field {
  margin-top: 12px;
}
.oc-trace-cost {
  text-align: center;
  margin-top: 10px;
}
.oc-trace-steps {
  display: flex;
  gap: 10px;
  margin-top: 18px;
}
.oc-trace-steps span {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  border-radius: 10px;
  border: 1px solid var(--oc-line);
  background: var(--oc-surface-2);
  font-size: 13.5px;
  color: var(--oc-muted);
}
.oc-trace-steps i {
  font-style: normal;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  font-size: 12px;
  font-weight: 700;
  background: var(--oc-surface-3);
}
.oc-trace-steps .active {
  border-color: var(--oc-brand-line);
  color: var(--oc-brand-ink);
}
.oc-trace-steps .active i {
  animation: oc-trace-pulse 1.2s ease-in-out infinite;
  background: var(--oc-brand-soft);
}
.oc-trace-steps .done {
  border-color: var(--oc-brand-line);
  background: var(--oc-brand-soft);
  color: var(--oc-brand-ink);
}
.oc-trace-steps .done i {
  background: var(--oc-brand);
  color: var(--oc-on-brand);
}
.oc-trace-steps .bad {
  border-color: var(--oc-warn-line);
  background: var(--oc-warn-bg);
  color: var(--oc-warn-ink);
}
@keyframes oc-trace-pulse {
  50% {
    opacity: 0.45;
  }
}
@media (prefers-reduced-motion: reduce) {
  .oc-trace-steps .active i {
    animation: none;
  }
}
.oc-trace-failures {
  margin: 12px 0 0;
  padding: 10px 14px 10px 30px;
  list-style: disc;
  border-radius: 10px;
  background: var(--oc-warn-bg);
  border: 1px solid var(--oc-warn-line);
  color: var(--oc-warn-ink);
  font-size: 13.5px;
  line-height: 1.8;
}
.oc-trace-details {
  margin-top: 18px;
  font-size: 14px;
}
.oc-trace-details .oc-table-wrap {
  margin: 14px 0;
}
.oc-trace-notes h2 {
  margin-bottom: 10px;
}
.oc-trace-notes h2:not(:first-child) {
  margin-top: 24px;
}
.oc-trace-notes p {
  font-size: 14px;
  line-height: 1.8;
  color: var(--oc-ink-2);
  margin-top: 8px;
}
.oc-trace-notes ol,
.oc-trace-notes ul {
  padding-left: 20px;
  color: var(--oc-ink-2);
  font-size: 14px;
  line-height: 1.8;
}
.oc-trace-notes ol {
  list-style: decimal;
}
.oc-trace-notes ul {
  list-style: disc;
}
.oc-trace-notes li {
  margin-top: 8px;
}
.oc-trace-notes ::marker {
  color: var(--oc-brand);
}
.oc-trace-notes details {
  font-size: 14px;
  margin: 20px 0;
  color: var(--oc-ink-2);
}
.oc-trace-notes summary {
  cursor: pointer;
  font-weight: 600;
  color: var(--oc-brand-ink);
}
.oc-trace-notes > small {
  font-size: 12px;
  color: var(--oc-muted);
}
.oc-bank-list {
  white-space: pre-line;
  font: 12.5px/1.9 var(--oc-mono);
  margin-top: 12px;
  max-height: 260px;
  overflow: auto;
  padding: 12px 14px;
  background: var(--oc-surface-2);
  border: 1px solid var(--oc-line);
  border-radius: 10px;
}
.oc-trace-verdict {
  display: flex;
  gap: 16px;
  align-items: center;
  padding: 18px 20px;
  border-radius: 12px;
  border: 1px solid var(--oc-warn-line);
  background: var(--oc-warn-bg);
  color: var(--oc-warn-ink);
}
.oc-trace-verdict > b {
  flex: none;
  width: 40px;
  height: 40px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  font-size: 20px;
  background: var(--oc-surface);
}
.oc-trace-verdict strong {
  display: block;
  font-size: 18px;
  color: var(--oc-ink);
}
.oc-trace-verdict small {
  display: block;
  margin-top: 4px;
  font-size: 13.5px;
  line-height: 1.7;
  color: var(--oc-ink-2);
  overflow-wrap: anywhere;
}
.oc-trace-verdict.match {
  border-color: var(--oc-brand-line);
  background: var(--oc-brand-soft);
  color: var(--oc-brand-ink);
}
.oc-trace-verdict.mismatch {
  border-color: var(--oc-danger-line);
  background: var(--oc-danger-bg);
  color: var(--oc-danger);
}
.oc-trace-notes li b {
  color: var(--oc-ink);
}
.oc-trace-notes a {
  text-decoration: underline;
  text-underline-offset: 3px;
}
.oc-probe-row {
  display: flex;
  gap: 14px;
  align-items: center;
  flex-wrap: wrap;
  padding: 14px 0;
  border-bottom: 1px solid var(--oc-line);
  font-size: 14px;
}
.oc-probe-row:last-child {
  border-bottom: 0;
}
.oc-probe-row code {
  font-size: 12.5px;
  color: var(--oc-muted);
}
.oc-probe-row small {
  margin-left: auto;
  color: var(--oc-muted);
  font-size: 13px;
}
.oc-manual-probe {
  padding: 22px 0;
  border-bottom: 1px solid var(--oc-line);
  margin-bottom: 18px;
}
.oc-manual-probe h3 {
  font-size: 15px;
}
.oc-manual-probe p {
  font-size: 13.5px;
  line-height: 1.8;
  color: var(--oc-ink-2);
  margin: 12px 0;
  padding: 12px 14px;
  background: var(--oc-surface-2);
  border: 1px solid var(--oc-line);
  border-radius: 10px;
  overflow-wrap: anywhere;
}
.oc-manual-probe .oc-field {
  margin-top: 16px;
}
@media (max-width: 900px) {
  .oc-trace-badges {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
@media (max-width: 720px) {
  .oc-trace-hero {
    padding: 22px 18px;
  }
  .oc-trace-hero h2 {
    font-size: 21px;
  }
  .oc-trace-badges {
    grid-template-columns: 1fr;
  }
  .oc-trace-steps {
    flex-direction: column;
  }
  .oc-probe-row small {
    margin-left: 0;
  }
}
</style>
