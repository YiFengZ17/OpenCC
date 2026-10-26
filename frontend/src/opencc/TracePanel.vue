<script setup lang="ts">
import { ref, shallowRef, computed, onMounted, onBeforeUnmount } from 'vue'
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
import { runProbe, verdict, type Probe, type TraceProtocol } from './trace'
import catalog from './catalog.json'
import bankURL from './vendor/modeltrace/unified_bank.json?url'
const keys = ref<ApiKey[]>([]),
  keyId = ref<number>(),
  model = ref(''),
  protocol = ref<TraceProtocol>('anthropic'),
  options = ref<string[]>([])
const running = ref(false),
  consent = ref(false),
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
const percent = (n: number) => (n * 100).toFixed(1) + '%'
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
    !consent.value ||
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
      progress.value = `正在发送第 ${i + 1} / 3 次测试请求`
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
    source: 'https://github.com/xqy2006/ModelTrace',
    commit: '6cd4a8ff0f3f4e49d6d6969dd2fbadfa1569fde2',
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
  <div class="oc-info oc-trace-intro">
    <strong>ModelTrace 模型归因检测</strong>
    <p>
      ModelTrace 是一个开源模型归因工具。它让待测模型完成三条独立的长整数生成任务，
      提取数字分布与序列特征，再与参考指纹比较，给出最相似的模型家族和版本。
      本站接入的指纹库包含 {{ ids.length }} 个型号，可用于检查接口返回的模型行为是否与所选型号相符。
    </p>
    <a
      href="https://github.com/xqy2006/ModelTrace"
      target="_blank"
      rel="noopener noreferrer"
      >GitHub · xqy2006/ModelTrace ↗</a
    >
    <p>
      算法与指纹库均可查看源码。你可以下载本次检测报告，或使用原项目独立复测。
      OpenCC 使用其开源实现，未获得项目方对本站模型的认证。
    </p>
  </div>
  <div v-if="error" class="oc-error" role="alert">{{ error }}</div>
  <div class="oc-two-column">
    <section class="oc-panel">
      <div class="oc-panel-head">
        <h2>检测配置</h2>
        <span class="oc-tag">本地计算</span>
      </div>
      <fieldset :disabled="running">
        <label class="oc-field"
          >模型 ID<input
            v-model="model"
            list="trace-models"
            placeholder="输入需要检测的完整模型 ID" /><datalist
            id="trace-models"
          >
            <option v-for="m in options" :key="m" :value="m" /></datalist
        ></label>
        <p v-if="model && !ids.includes(model)" class="oc-hint">
          此型号不在当前指纹库中，检测后无法核验具体版本。Grok 暂无参考指纹。
        </p>
        <div class="oc-tabs oc-trace-modes">
          <button
            :class="{ selected: !manual }"
            @click="switchMode(false)"
          >
            API 自动检测</button
          ><button
            :class="{ selected: manual }"
            @click="switchMode(true)"
          >
            手动粘贴检测
          </button>
        </div>
        <template v-if="!manual"
          ><label class="oc-field"
            >本站 API 密钥<select v-model="keyId">
              <option v-for="k in keys" :key="k.id" :value="k.id">
                {{ k.name }} · {{ k.group?.name || '默认分组' }}
              </option>
            </select></label
          >
          <p v-if="!keys.length" class="oc-hint">
            没有可用密钥。请先在 API 密钥页面创建。
          </p>
          <label class="oc-field"
            >接口格式<select v-model="protocol">
              <option value="anthropic">Anthropic Messages</option>
              <option value="openai">OpenAI Chat Completions</option>
              <option value="responses">OpenAI Responses</option>
            </select></label
          ><label class="oc-consent"
            ><input v-model="consent" type="checkbox" />我了解本次检测会发送 3
            次请求，每次输出上限 4096 Tokens，按所选模型价格从余额扣费。</label
          ><button
            class="oc-button primary wide"
            :disabled="!consent || !selectedKey || !model.trim() || !bank"
            @click="start"
          >
            开始检测
          </button></template
        >
      </fieldset>
      <button v-if="running" class="oc-button wide" @click="cancel">
        停止检测
      </button>
      <p v-if="running" class="oc-hint" role="status">{{ progress }}</p>
    </section>
    <section class="oc-panel oc-trace-notes">
      <h2>怎么使用</h2>
      <ol>
        <li>填写完整模型 ID，选择有权调用该模型的本站密钥和接口格式。</li>
        <li>确认调用费用后点击“开始检测”，等待三轮请求完成。</li>
        <li>查看最相似候选、库内概率和请求记录，可下载报告留存。</li>
      </ol>
      <p>也可切换“手动粘贴检测”：把三条提示词分别发送给同一模型，每次使用新对话，再粘贴完整输出。</p>
      <h2>如何理解结果</h2>
      <p>
        结果可为渠道一致性检查提供线索。库内概率只比较已收录候选，不能当作“纯度”或来源证明。
        未收录型号也可能匹配到已有候选；系统提示词会影响输出，原项目提醒 Claude Code 环境可能存在较大偏差。
      </p>
      <ul>
        <li>请求使用你选择的本站密钥，经过正常的模型转发与计费流程。</li>
        <li>一次测试包含三条独立提示词，不携带历史对话。</li>
        <li>输出截断、请求失败或有效数字不足，会标记为无效样本。</li>
        <li>密钥不会发送给 ModelTrace 项目方。指纹计算在你的浏览器内完成。</li>
        <li>指纹库未收录的模型也可能与已有候选相似，不能据此认定实际型号。</li>
      </ul>
      <details>
        <summary>查看指纹库型号（{{ ids.length }}）</summary>
        <p class="oc-bank-list">{{ ids.join('\n') }}</p>
      </details>
      <small>指纹库版本：6cd4a8ff · MIT License</small>
    </section>
  </div>
  <section v-if="manual" class="oc-panel">
    <div class="oc-panel-head">
      <h2>手动测试</h2>
      <button class="oc-button small" @click="resetChallenges">
        重新生成提示词
      </button>
    </div>
    <p class="oc-hint">
      将三条提示词分别发送给同一模型，每次开启独立对话，再粘贴完整输出。
    </p>
    <div v-for="(c, i) in challenges" :key="c.id" class="oc-manual-probe">
      <h3>测试 {{ i + 1 }} · {{ c.expected_count }} 个数字</h3>
      <p>{{ c.prompt }}</p>
      <button class="oc-button small" @click="copyPrompt(c.prompt)">
        复制提示词</button
      ><label class="oc-field"
        >模型完整输出<textarea
          v-model="manualTexts[i]"
          rows="4"
          maxlength="100000"
          placeholder="粘贴本次测试的完整输出"
        />
      </label>
    </div>
    <button
      class="oc-button primary"
      :disabled="!model.trim() || !manualTexts.every((t) => t.trim())"
      @click="analyzeManual"
    >
      计算检测结果
    </button>
  </section>
  <section v-if="probes.length && !manual" class="oc-panel">
    <h2>请求记录</h2>
    <div v-for="(p, i) in probes" :key="i" class="oc-probe-row">
      <span>测试 {{ i + 1 }}</span
      ><span :class="['oc-tag', p.valid ? '' : 'amber']">{{
        p.valid ? '有效样本' : p.error
      }}</span
      ><code>{{ p.request_id || '—' }}</code
      ><small>{{ (p.duration_ms / 1000).toFixed(1) }} 秒</small>
    </div>
  </section>
  <section v-if="result" class="oc-panel">
    <div class="oc-panel-head">
      <h2>检测结果</h2>
      <button class="oc-button small" @click="download">
        <Icon name="order" />下载报告
      </button>
    </div>
    <div class="oc-trace-verdict">{{ conclusion }}</div>
    <p class="oc-hint">
      所选型号：{{ reportModel }} · 有效样本：{{ result.used_outputs }} / 3 ·
      {{
        manualReport ? '手动粘贴的输出，未验证 API 来源' : '本站 API 自动测试'
      }}
    </p>
    <div class="oc-trace-summary">
      <div>
        <small>最相似候选</small><strong>{{ result.prediction_name }}</strong>
      </div>
      <div>
        <small>候选库内概率</small
        ><strong>{{ percent(result.probability) }}</strong>
      </div>
      <div>
        <small>候选家族</small
        ><strong>{{ result.family_prediction_name }}</strong>
      </div>
    </div>
    <p class="oc-hint">
      该概率只在当前候选库内比较，不代表模型有对应百分比的“纯度”。型号一致也不能证明所有请求都使用同一模型。
    </p>
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
  </section>
</template>
<style scoped>
.oc-trace-intro p {
  margin: 8px 0;
  line-height: 1.8;
}
.oc-trace-intro a {
  font-size: 13.5px;
  text-decoration: underline;
  text-underline-offset: 3px;
}
.oc-trace-modes {
  margin: 4px 0 20px;
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
  padding: 16px 18px;
  background: var(--oc-brand-soft);
  border: 1px solid var(--oc-brand-line);
  border-radius: 12px;
  font-size: 16px;
  font-weight: 600;
  color: var(--oc-ink);
  line-height: 1.7;
}
.oc-trace-summary {
  display: grid;
  grid-template-columns: 2fr 1fr 1fr;
  gap: 16px;
  margin: 22px 0;
}
.oc-trace-summary > div {
  padding: 14px 16px;
  background: var(--oc-surface-2);
  border: 1px solid var(--oc-line);
  border-radius: 12px;
  min-width: 0;
}
.oc-trace-summary small {
  display: block;
  font-size: 12.5px;
  font-weight: 600;
  color: var(--oc-muted);
}
.oc-trace-summary strong {
  display: block;
  overflow-wrap: anywhere;
  font-size: 20px;
  margin-top: 6px;
  font-weight: 700;
  letter-spacing: -0.01em;
  font-variant-numeric: tabular-nums;
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
@media (max-width: 720px) {
  .oc-trace-summary {
    grid-template-columns: 1fr;
  }
  .oc-trace-summary strong {
    font-size: 18px;
  }
  .oc-probe-row small {
    margin-left: 0;
  }
}
</style>
