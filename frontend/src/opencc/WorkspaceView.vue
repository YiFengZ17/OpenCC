<script setup lang="ts">
import GroupsPanel from "./GroupsPanel.vue"
import HelpGuide from "./HelpGuide.vue"
import PlatformIcon from "@/components/common/PlatformIcon.vue"
import {
  computed,
  ref,
  watch,
  nextTick,
  onMounted,
  onBeforeUnmount,
  defineAsyncComponent
} from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { keysAPI } from '@/api/keys'
import { usageAPI, type UserDashboardStats } from '@/api/usage'
import { modelPlazaAPI } from '@/api/modelPlaza'
import { redeemAPI, type RedeemHistoryItem } from '@/api/redeem'
import { paymentAPI } from '@/api/payment'
import announcementsAPI from '@/api/announcements'
import { apiClient } from '@/api/client'
import type { ApiKey, UsageLog, UserAnnouncement } from '@/types'
import Icon from './Icon.vue'
import {
  consoleConfig,
  loadConsoleConfig,
  money,
  number,
  safeHttps,
  providerOf,
  gatewayURL
} from './config'
import catalog from './catalog.json'
import './console.css'

const TracePanel = defineAsyncComponent(() => import('./TracePanel.vue'))
const PricingPanel = defineAsyncComponent(() => import('./PricingPanel.vue'))
const route = useRoute(),
  router = useRouter(),
  auth = useAuthStore()
const demo = import.meta.env.DEV && import.meta.env.VITE_OPENCC_DEMO === 'true'
const nav = [
  { path: '/dashboard', name: '账户工作台', icon: 'grid' },
  { path: '/model-plaza', name: '模型广场', icon: 'models' },
  { path: '/keys', name: 'API 密钥', icon: 'key' },
  { path: '/usage', name: '用量明细', icon: 'chart' },
  { path: '/model-test', name: '模型检测', icon: 'shield' },
  { path: '/groups', name: '模型分组', icon: 'models' },
  { path: '/redeem', name: '账户充值', icon: 'wallet' },
  { path: '/orders', name: '兑换记录', icon: 'order' },
  { path: '/announcements', name: '站内公告', icon: 'bell' },
  { path: '/help', name: '接入文档', icon: 'book' }
]
const page = computed(() => route.path),
  title = computed(
    () =>
      nav.find((n) => n.path === page.value)?.name ||
      (page.value === '/pricing' ? '模型价格' : 'OpenCC API')
  )
const descriptions: Record<string, string> = {
  '/dashboard': '查看余额、用量和密钥。',
  '/model-plaza': '查看支持模型、分组与价格。',
  '/keys': '创建和管理项目使用的 API 密钥。',
  '/usage': '查看每条请求的模型、Token 和费用。',
  '/redeem': '使用卡密充值到账户余额。',
  '/orders': '查看卡密兑换记录和到账金额。',
  '/announcements': '服务公告和维护通知。',
  '/help': '接口地址、配置方法与调用示例。',
  '/model-test': '选择 API 密钥与模型，查看指纹检测结果。',
  '/pricing': '模型价格、计费单位和分组倍率。'
}
const description = computed(() => descriptions[page.value] || '')
const mobile = ref(false),
  busy = ref(false),
  error = ref(''),
  toast = ref(''),
  search = ref(''),
  provider = ref('全部'),
  current = ref(1),
  total = ref(0)
const stats = ref<UserDashboardStats>(),
  keys = ref<ApiKey[]>([]),
  logs = ref<UsageLog[]>([]),
  history = ref<RedeemHistoryItem[]>([]),
  announcements = ref<UserAnnouncement[]>([])
interface Order {
  id: number
  out_trade_no: string
  amount: number
  pay_amount: number
  currency?: string
  status: string
  created_at: string
}
const orders = ref<Order[]>([]),
  orderTab = ref('redeem'),
  orderStatus = ref(''),
  groups = ref<{ id: number; name: string }[]>([])
interface Model {
  name: string
  group: string
  provider: string
  live: boolean
}
const models = ref<Model[]>([]),
  hasCatalog = ref(false)
const filteredModels = computed(() =>
  models.value.filter(
    (m) =>
      (provider.value === '全部' || m.provider === provider.value) &&
      m.name.toLowerCase().includes(search.value.toLowerCase())
  )
)
const code = ref(''),
  saving = ref(false),
  dialog = ref(false),
  keyName = ref(''),
  keyGroup = ref<number | undefined>(),
  keyQuota = ref(0),
  createdKey = ref('')
const date = (s: string) =>
  s ? new Date(s).toLocaleString('zh-CN', { hour12: false }) : '—'
function message(e: unknown) {
  return e instanceof Error
    ? e.message
    : (e as { message?: string })?.message || '请求失败，请稍后重试。'
}
let timer: ReturnType<typeof setTimeout> | undefined
function notify(s: string) {
  toast.value = s
  clearTimeout(timer)
  timer = setTimeout(() => (toast.value = ''), 4000)
}
async function copy(s: string) {
  try {
    await navigator.clipboard.writeText(s)
    notify('已复制到剪贴板')
  } catch {
    error.value = '浏览器无法访问剪贴板，请选中文本手动复制。'
  }
}
// ---- theme (light / dark) -------------------------------------------------
// A stored choice wins; otherwise the OS preference is followed live.
const THEME_KEY = 'opencc_theme'
type Theme = 'light' | 'dark'
const storedTheme = ref<Theme | null>(null),
  systemDark = ref(false)
const isDark = computed(() =>
  storedTheme.value ? storedTheme.value === 'dark' : systemDark.value
)
let colorQuery: MediaQueryList | undefined
const onColorChange = (e: MediaQueryListEvent) => (systemDark.value = e.matches)
function applyTheme() {
  const root = document.documentElement
  if (storedTheme.value) root.setAttribute('data-oc-theme', storedTheme.value)
  else root.removeAttribute('data-oc-theme')
}
function toggleTheme() {
  storedTheme.value = isDark.value ? 'light' : 'dark'
  applyTheme()
  try {
    localStorage.setItem(THEME_KEY, storedTheme.value)
  } catch {
    /* storage unavailable: keep the choice for this session only */
  }
}
onMounted(() => {
  try {
    const v = localStorage.getItem(THEME_KEY)
    if (v === 'light' || v === 'dark') storedTheme.value = v
  } catch {
    /* ignore */
  }
  colorQuery = window.matchMedia?.('(prefers-color-scheme: dark)')
  if (colorQuery) {
    systemDark.value = colorQuery.matches
    colorQuery.addEventListener?.('change', onColorChange)
  }
  applyTheme()
})
onBeforeUnmount(() => {
  colorQuery?.removeEventListener?.('change', onColorChange)
  document.documentElement.removeAttribute('data-oc-theme')
  clearTimeout(timer)
})
const keyNameInput = ref<HTMLInputElement>()
watch(dialog, async (open) => {
  if (!open) return
  await nextTick()
  keyNameInput.value?.focus()
})

let generation = 0
async function load() {
  const g = ++generation,
    p = page.value
  busy.value = true
  error.value = ''
  try {
    await loadConsoleConfig()
    if (p === '/model-plaza' || p === '/home') {
      const result = await modelPlazaAPI.getModelPlaza()
      if (g !== generation) return
      models.value = result.groups
        .flatMap((group) =>
          group.models.map((m) => ({
            name: m.name,
            group: group.name,
            provider: providerOf(m.name) || '',
            live: true
          }))
        )
        .filter((m) => m.provider)
      hasCatalog.value = models.value.length === 0
      if (hasCatalog.value)
        models.value = catalog.models.map((name) => ({
          name,
          group: '接入准备中',
          provider: providerOf(name) || '',
          live: false
        }))
    } else if (p === '/dashboard') {
      const [s, l] = await Promise.all([
        usageAPI.getDashboardStats(),
        usageAPI.query({ page: 1, page_size: 5 })
      ])
      if (g !== generation) return
      stats.value = s
      logs.value = l.items
      await auth.refreshUser()
    } else if (p === '/keys') {
      const [k, gr] = await Promise.all([
        keysAPI.list(current.value, 10),
        apiClient.get<{ id: number; name: string }[]>('/groups/available')
      ])
      if (g !== generation) return
      keys.value = k.items
      total.value = k.total
      groups.value = gr.data
    } else if (p === '/usage') {
      const l = await usageAPI.query({
        page: current.value,
        page_size: 15,
        model: search.value || undefined
      })
      if (g !== generation) return
      logs.value = l.items
      total.value = l.total
    } else if (p === '/redeem') {
      await auth.refreshUser()
    } else if (p === '/orders') {
      if (orderTab.value === 'redeem') {
        const h = await redeemAPI.getHistory(current.value, 15)
        if (g !== generation) return
        history.value = h.items
        total.value = h.total
      } else {
        const { data } = await paymentAPI.getMyOrders({
          page: current.value,
          page_size: 15,
          status: orderStatus.value || undefined
        })
        if (g !== generation) return
        orders.value = data.items
        total.value = data.total
      }
    } else if (p === '/announcements') {
      const a = await announcementsAPI.list()
      if (g !== generation) return
      announcements.value = a
    }
  } catch (e) {
    if (g === generation) error.value = message(e)
  } finally {
    if (g === generation) busy.value = false
  }
}
watch(
  page,
  () => {
    mobile.value = false
    search.value = ''
    current.value = 1
    createdKey.value = ''
    dialog.value = false
    void load()
  },
  { immediate: true }
)
async function paginate(step: number) {
  current.value += step
  await load()
}
async function createKey() {
  if (!keyName.value.trim() || !keyGroup.value) return
  saving.value = true
  error.value = ''
  try {
    const k = await keysAPI.create(
      keyName.value.trim(),
      keyGroup.value,
      undefined,
      undefined,
      undefined,
      keyQuota.value / consoleConfig.cny_per_credit
    )
    createdKey.value = k.key
    dialog.value = false
    keyName.value = ''
    await load()
    notify('密钥已创建，请妥善保存')
  } catch (e) {
    error.value = message(e)
  } finally {
    saving.value = false
  }
}
async function toggleKey(k: ApiKey) {
  saving.value = true
  try {
    await keysAPI.toggleStatus(
      k.id,
      k.status === 'active' ? 'inactive' : 'active'
    )
    await load()
  } catch (e) {
    error.value = message(e)
  } finally {
    saving.value = false
  }
}
async function deleteKey(k: ApiKey) {
  if (
    !window.confirm(
      `删除密钥「${k.name}」后，使用它的应用将无法继续请求。确定删除？`
    )
  )
    return
  saving.value = true
  try {
    await keysAPI.delete(k.id)
    await load()
    notify('密钥已删除')
  } catch (e) {
    error.value = message(e)
  } finally {
    saving.value = false
  }
}
async function redeem() {
  if (!code.value.trim()) return
  saving.value = true
  error.value = ''
  try {
    const r = await redeemAPI.redeem(code.value.trim())
    code.value = ''
    await auth.refreshUser()
    notify(r.message || '兑换成功，余额已到账')
  } catch (e) {
    error.value = message(e)
  } finally {
    saving.value = false
  }
}
async function markRead(a: UserAnnouncement) {
  try {
    await announcementsAPI.markRead(a.id)
    a.read_at = new Date().toISOString()
  } catch (e) {
    error.value = message(e)
  }
}
const statusName = (s: string) =>
  ({
    PENDING: '待支付',
    COMPLETED: '已完成',
    PAID: '已支付',
    EXPIRED: '已过期',
    FAILED: '支付失败',
    CANCELLED: '已取消',
    REFUNDED: '已退款'
  })[s] || s
const sample = computed(
  () =>
    `curl ${gatewayURL()}/v1/messages \\\n  -H "x-api-key: $OPENCC_API_KEY" \\\n  -H "anthropic-version: 2023-06-01" \\\n  -H "content-type: application/json" \\\n  -d '{"model":"MODEL_ID","max_tokens":256,\n       "messages":[{"role":"user","content":"你好"}]}'`
)
function applyFilter(){current.value=1;void load()}
function logout(){auth.logout();void router.push('/home')}
</script>

<template>
  <div class="oc-app">
    <button
      v-if="mobile"
      class="oc-scrim"
      aria-label="关闭导航"
      @click="mobile = false"
    ></button>
    <aside class="oc-sidebar" :class="{ 'is-open': mobile }">
      <RouterLink to="/home" class="oc-brand"
        ><span class="oc-logomark">&lt; / &gt;</span
        ><span
          >OpenCC<span class="oc-brand-sub">MODEL GATEWAY</span></span
        ></RouterLink
      >
      <div class="oc-workspace">
        <span class="oc-avatar">O</span>
        <div>我的工作空间<small>个人账户</small></div>
        <Icon name="chevron" />
      </div>
      <div class="oc-nav-label">工作台 <span>WORKSPACE</span></div>
      <nav aria-label="主导航">
        <template v-for="(n, i) in nav" :key="n.path"
          ><div v-if="i === 5" class="oc-nav-label">
            账单与服务 <span>ACCOUNT</span>
          </div>
          <RouterLink
            :to="n.path"
            :class="['oc-nav-item', { active: page === n.path }]"
            :aria-current="page === n.path ? 'page' : undefined"
            ><Icon :name="n.icon" /><span>{{ n.name }}</span
            ><span v-if="n.path === '/model-plaza'" class="oc-nav-new"
              >NEW</span
            ></RouterLink
          ></template
        >
      </nav>
      <div class="oc-sidebar-bottom">
        <div class="oc-help-card">
          <Icon name="code" /><strong>API 接入</strong>
          <p>查看接口地址、模型与调用示例。</p>
          <RouterLink to="/help">阅读接入指南 <Icon name="arrow" /></RouterLink>
        </div>
        <a
          href="https://github.com/Wei-Shaw/sub2api"
          target="_blank"
          rel="noopener noreferrer"
          class="oc-credit"
          >Powered by Sub2API ↗</a
        >
      </div>
    </aside>
    <div class="oc-main">
      <header class="oc-topbar">
        <div class="oc-breadcrumb">
          <button
            class="oc-icon-button oc-mobile-toggle"
            aria-label="打开导航"
            @click="mobile = true"
          >
            <Icon name="menu" /></button
          ><span>工作空间</span><span>/</span
          ><b>{{ page === '/home' ? '欢迎使用' : title }}</b>
        </div>
        <div class="oc-top-actions">
          <span v-if="demo" class="oc-tag amber">本地演示</span
          ><RouterLink to="/help" class="oc-header-docs">接入文档 ↗</RouterLink
          ><button
            type="button"
            class="oc-icon-button"
            :aria-label="isDark ? '切换到浅色模式' : '切换到深色模式'"
            :title="isDark ? '浅色模式' : '深色模式'"
            @click="toggleTheme"
          >
            <Icon :name="isDark ? 'sun' : 'moon'" /></button
          ><RouterLink
            to="/announcements"
            class="oc-icon-button"
            aria-label="公告"
            ><Icon name="bell" /></RouterLink
          ><RouterLink
            v-if="!auth.isAuthenticated"
            to="/login"
            class="oc-button primary small"
            >登录 / 注册</RouterLink
          ><RouterLink
            v-else
            to="/profile"
            class="oc-avatar"
            aria-label="账户设置"
            >{{
              (auth.user?.username || 'U').slice(0, 1).toUpperCase()
            }}</RouterLink
          >
        </div>
      </header>
      <main class="oc-content">
        <div v-if="demo" class="oc-demo-note">
          预览环境 · 所有账户、余额与订单均为模拟数据，不会发起扣费或模型请求。
        </div>
        <div v-if="error" class="oc-error" role="alert">
          {{ error }} <button @click="load">重新加载</button>
        </div>
        <template v-if="page === '/home'">
          <section class="oc-hero">
            <div>
              <span class="oc-eyebrow"><i></i> OPENCC API</span>
              <h1>OpenCC<br /><span>API 模型服务</span></h1>
              <p>
                支持 Claude、GPT 与 Grok 模型。<br />创建 API
                密钥后，可在兼容客户端中使用。
              </p>
              <div class="oc-hero-actions">
                <RouterLink
                  :to="auth.isAuthenticated ? '/dashboard' : '/register'"
                  class="oc-button primary"
                  >开始使用 <Icon name="arrow" /></RouterLink
                ><RouterLink to="/model-plaza" class="oc-button"
                  >探索模型</RouterLink
                >
              </div>
              <div class="oc-hero-foot">
                <span><Icon name="check" /> 按量计费</span
                ><span><Icon name="check" /> API 密钥管理</span
                ><span><Icon name="check" /> 用量明细</span>
              </div>
            </div>
            <div class="oc-orbit" aria-hidden="true">
              <div class="oc-orbit-ring outer"></div>
              <div class="oc-orbit-ring inner"></div>
              <div class="oc-orbit-center">
                &lt; / &gt;<small>OpenCC</small>
              </div>
              <span class="oc-orbit-node claude">✳<small>Claude</small></span
              ><span class="oc-orbit-node gpt"><PlatformIcon platform="openai" size="lg" /><small>GPT</small></span
              ><span class="oc-orbit-node grok">𝕏<small>Grok</small></span
              ><span class="oc-orbit-dot"></span
              ><code>API / Tokens / Usage</code>
            </div>
          </section>
          <div class="oc-section-heading">
            <div>
              <span class="oc-eyebrow">支持的模型</span>
              <h2>模型与接口</h2>
            </div>
            <RouterLink to="/model-plaza" class="oc-text-link"
              >查看模型广场 <Icon name="arrow"
            /></RouterLink>
          </div>
          <div class="oc-provider-grid">
            <RouterLink
              v-for="(item, i) in [
                {
                  name: 'Claude',
                  desc: 'Anthropic Messages 兼容接口。',
                  mark: '✳'
                },
                {
                  name: 'GPT',
                  desc: 'Chat Completions / Responses 接口。',
                  mark: '◉'
                },
                { name: 'Grok', desc: 'OpenAI 兼容接口。', mark: '𝕏' }
              ]"
              :key="item.name"
              to="/model-plaza"
              class="oc-provider-card"
              ><span :class="['oc-provider-icon', 'p' + i]"><PlatformIcon v-if="item.name === 'GPT'" platform="openai" size="lg" /><template v-else>{{ item.mark }}</template></span
              ><span class="oc-small-label">0{{ i + 1 }} / MODEL FAMILY</span>
              <h3>{{ item.name }}</h3>
              <p>{{ item.desc }}</p>
              <span class="oc-text-link">探索模型 <Icon name="arrow" /></span
            ></RouterLink>
          </div>
          <section class="oc-start-banner">
            <div>
              <span class="oc-eyebrow">接入指南</span>
              <h2>首次使用</h2>
              <p>创建密钥 → 填写接口地址 → 选择模型。</p>
            </div>
            <RouterLink to="/help" class="oc-button"
              >查看三步指南 <Icon name="arrow"
            /></RouterLink>
          </section>
        </template>
        <template v-else>
          <div class="oc-page-heading">
            <div>
              <span class="oc-eyebrow"
                >OPENCC / {{ page.slice(1).toUpperCase() }}</span
              >
              <h1>{{ title }}</h1>
              <p>{{ description }}</p>
            </div>
            <button
              v-if="page === '/keys'"
              class="oc-button primary"
              @click="dialog = true"
            >
              <Icon name="plus" />创建密钥</button
            ><button
              v-else-if="
                page === '/dashboard' || page === '/orders' || page === '/usage'
              "
              class="oc-button"
              :disabled="busy"
              @click="load"
            >
              <Icon name="refresh" />刷新
            </button>
          </div>
          <div v-if="busy" class="oc-loading" role="status">正在同步数据…</div>
          <template v-if="page === '/dashboard'">
            <div class="oc-stat-grid">
              <div class="oc-stat featured">
                <span>可用余额 <Icon name="wallet" /></span
                ><strong>{{ money(auth.user?.balance) }}</strong
                ><RouterLink to="/redeem"
                  >卡密充值 <Icon name="arrow"
                /></RouterLink>
              </div>
              <div class="oc-stat">
                <span>今日消耗 <Icon name="chart" /></span
                ><strong>{{
                  stats ? money(stats.today_actual_cost) : '—'
                }}</strong
                ><small>按实际计费汇总</small>
              </div>
              <div class="oc-stat">
                <span>今日请求 <Icon name="code" /></span
                ><strong
                  >{{ stats ? number(stats.today_requests) : '—'
                  }}<em>次</em></strong
                ><small>{{ number(stats?.today_tokens) }} Tokens</small>
              </div>
              <div class="oc-stat">
                <span>有效密钥 <Icon name="key" /></span
                ><strong
                  >{{ stats ? number(stats.active_api_keys) : '—'
                  }}<em>个</em></strong
                ><RouterLink to="/keys">管理密钥 →</RouterLink>
              </div>
            </div>
            <div class="oc-two-column">
              <section class="oc-panel">
                <div class="oc-panel-head">
                  <h2>快速开始</h2>
                  <span class="oc-tag">3 STEPS</span>
                </div>
                <RouterLink
                  v-for="(s, i) in [
                    {
                      name: '创建 API 密钥',
                      desc: '选择分组并填写名称。',
                      path: '/keys'
                    },
                    {
                      name: '填写连接信息',
                      desc: '配置 Base URL、API Key 和模型 ID。',
                      path: '/help'
                    },
                    {
                      name: '查看调用记录',
                      desc: '核对模型、Token 用量与费用。',
                      path: '/usage'
                    }
                  ]"
                  :key="s.path"
                  :to="s.path"
                  class="oc-step"
                  ><span>{{ i + 1 }}</span>
                  <div>
                    <strong>{{ s.name }}</strong>
                    <p>{{ s.desc }}</p>
                  </div>
                  <Icon name="arrow"
                /></RouterLink>
              </section>
              <section class="oc-panel oc-endpoint">
                <span class="oc-eyebrow">YOUR API ENDPOINT</span>
                <h2>API 接口地址</h2>
                <p>在兼容客户端中配置服务地址。</p>
                <div class="oc-copybox">
                  <code>{{ gatewayURL() }}</code
                  ><button
                    aria-label="复制接入地址"
                    @click="copy(gatewayURL())"
                  >
                    <Icon name="copy" />
                  </button>
                </div>
                <RouterLink to="/help" class="oc-text-link"
                  >查看不同协议的配置方法 <Icon name="arrow"
                /></RouterLink>
                <div class="oc-endpoint-symbol" aria-hidden="true">{ }</div>
              </section>
            </div>
          </template>
          <template v-if="page === '/model-plaza'">
            <div class="oc-toolbar">
              <div class="oc-tabs" role="group" aria-label="模型系列">
                <button
                  v-for="p in ['全部', 'Claude', 'GPT', 'Grok']"
                  :key="p"
                  :class="{ selected: provider === p }"
                  @click="provider = p"
                >
                  {{ p }}
                </button>
              </div>
              <label class="oc-search"
                ><Icon name="search" /><input
                  v-model="search"
                  placeholder="搜索模型名称…"
                  aria-label="搜索模型"
              /></label>
            </div>
            <div v-if="hasCatalog" class="oc-info">
              以下为上游公开目录的参考模型，尚未连接你的实际渠道；可用性与价格以完成配置后的结果为准。
            </div>
            <div class="oc-result-count">
              {{ filteredModels.length }} 个模型 / 渠道
              <RouterLink to="/pricing">完整价格与计费规则 ↗</RouterLink>
            </div>
            <div class="oc-model-grid">
              <article
                v-for="(m, i) in filteredModels"
                :key="m.group + m.name + i"
                class="oc-model-card"
              >
                <div class="oc-model-top">
                  <span
                    :class="[
                      'oc-provider-icon',
                      m.provider === 'Claude'
                        ? 'p0'
                        : m.provider === 'GPT'
                          ? 'p1'
                          : 'p2'
                    ]"
                    ><PlatformIcon v-if="m.provider === 'GPT'" platform="openai" size="lg" /><template v-else>{{ m.provider === 'Claude' ? '✳' : '𝕏' }}</template></span
                  ><span class="oc-tag" :class="{ amber: !m.live }">{{
                    m.live ? '已配置渠道' : '目录参考'
                  }}</span>
                </div>
                <small>{{ m.provider }}</small>
                <h3>{{ m.name }}</h3>
                <p>{{ m.group }}</p>
                <div class="oc-model-bottom">
                  <RouterLink :to="m.live ? '/pricing' : '/help'"
                    >{{ m.live ? '查看计价' : '查看接入说明' }} ↗</RouterLink
                  ><button
                    class="oc-icon-button"
                    aria-label="复制模型 ID"
                    @click="copy(m.name)"
                  >
                    <Icon name="copy" />
                  </button>
                </div>
              </article>
            </div>
            <div v-if="!filteredModels.length && !busy" class="oc-empty">
              没有找到匹配的模型，试试其他名称。
            </div>
          </template>
          <template v-if="page === '/keys'">
            <div v-if="createdKey" class="oc-info">
              新密钥已创建。请保存到环境变量，勿分享或提交到代码仓库。
              <div class="oc-copybox">
                <code>{{ createdKey }}</code
                ><button aria-label="复制新密钥" @click="copy(createdKey)">
                  <Icon name="copy" />
                </button>
              </div>
            </div>
            <section class="oc-panel oc-table-wrap">
              <div
                v-if="busy && !keys.length"
                class="oc-skeleton"
                aria-hidden="true"
              >
                <i v-for="n in 5" :key="n"></i>
              </div>
              <table v-else class="oc-table-cards">
                <thead>
                  <tr>
                    <th>名称 / 创建时间</th>
                    <th>密钥</th>
                    <th>分组</th>
                    <th>状态</th>
                    <th>已用金额 / 限额</th>
                    <th>操作</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="k in keys" :key="k.id">
                    <td data-label="名称">
                      <strong>{{ k.name }}</strong
                      ><small>{{ date(k.created_at) }}</small>
                    </td>
                    <td data-label="密钥">
                      <code
                        >{{ k.key.slice(0, 8) }}••••{{ k.key.slice(-4) }}</code
                      ><button
                        class="oc-icon-button"
                        aria-label="复制密钥"
                        @click="copy(k.key)"
                      >
                        <Icon name="copy" />
                      </button>
                    </td>
                    <td data-label="分组">{{ k.group?.name || '默认分组' }}</td>
                    <td data-label="状态">
                      <span
                        class="oc-tag"
                        :class="{ muted: k.status !== 'active' }"
                        >{{ k.status === 'active' ? '启用' : '停用' }}</span
                      >
                    </td>
                    <td data-label="已用 / 限额">
                      {{ money(k.quota_used) }} /
                      {{ k.quota ? money(k.quota) : '不限额' }}
                    </td>
                    <td data-label="操作">
                      <div class="oc-inline-actions">
                        <button :disabled="saving" @click="toggleKey(k)">
                          {{ k.status === 'active' ? '停用' : '启用' }}</button
                        ><button
                          :disabled="saving"
                          class="danger"
                          @click="deleteKey(k)"
                        >
                          删除
                        </button>
                      </div>
                    </td>
                  </tr>
                </tbody>
              </table>
              <div v-if="!keys.length && !busy" class="oc-empty">
                <Icon name="key" />
                <h3>暂无 API 密钥</h3>
                <p>点击“创建密钥”添加。</p>
                <button class="oc-button primary" @click="dialog = true">
                  创建密钥
                </button>
              </div>
            </section>
          </template>
          <template v-if="page === '/dashboard' || page === '/usage'">
            <section class="oc-panel oc-table-wrap">
              <div class="oc-panel-head">
                <h2>{{ page === '/dashboard' ? '最近调用' : '请求记录' }}</h2>
                <RouterLink
                  v-if="page === '/dashboard'"
                  to="/usage"
                  class="oc-text-link"
                  >全部明细 →</RouterLink
                >
                <form
                  v-else
                  class="oc-search"
                  @submit.prevent="applyFilter"
                >
                  <Icon name="search" /><input
                    v-model="search"
                    placeholder="输入完整模型 ID，回车查询"
                    aria-label="筛选用量模型"
                  /><button type="submit">查询</button>
                </form>
              </div>
              <div
                v-if="busy && !logs.length"
                class="oc-skeleton"
                aria-hidden="true"
              >
                <i v-for="n in 5" :key="n"></i>
              </div>
              <table v-else class="oc-table-cards">
                <thead>
                  <tr>
                    <th>时间 / 请求 ID</th>
                    <th>模型</th>
                    <th>输入 Tokens</th>
                    <th>输出 Tokens</th>
                    <th>耗时</th>
                    <th>费用</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="l in logs" :key="l.id">
                    <td data-label="时间">
                      {{ date(l.created_at)
                      }}<small>{{ l.request_id?.slice(0, 18) || '—' }}</small>
                    </td>
                    <td data-label="模型">
                      <code>{{ l.model }}</code>
                    </td>
                    <td data-label="输入 Tokens">
                      {{ number(l.input_tokens) }}
                    </td>
                    <td data-label="输出 Tokens">
                      {{ number(l.output_tokens) }}
                    </td>
                    <td data-label="耗时">
                      {{
                        l.duration_ms
                          ? `${(l.duration_ms / 1000).toFixed(2)} s`
                          : '—'
                      }}
                    </td>
                    <td data-label="费用">
                      <strong>{{ money(l.actual_cost, 4) }}</strong>
                    </td>
                  </tr>
                </tbody>
              </table>
              <div v-if="!logs.length && !busy" class="oc-empty">
                暂无调用记录。
              </div>
            </section>
          </template>
          <template v-if="page === '/redeem'">
            <div class="oc-two-column recharge">
              <section class="oc-panel">
                <div class="oc-panel-head">
                  <h2>卡密兑换</h2>
                  <span class="oc-tag">人民币余额</span>
                </div>
                <p class="oc-hint">
                  输入购买的卡密，按面额充值到账户余额。每张卡密只能使用一次。
                </p>
                <form @submit.prevent="redeem">
                  <label class="oc-field"
                    >卡密<input
                      v-model="code"
                      autocomplete="off"
                      placeholder="请输入卡密"
                      required
                      maxlength="128" /></label
                  ><button
                    class="oc-button primary wide"
                    :disabled="saving || !code.trim()"
                  >
                    {{ saving ? '正在兑换…' : '确认兑换' }}
                  </button>
                </form>
                <RouterLink to="/orders" class="oc-under-link"
                  >查看兑换记录 →</RouterLink
                >
              </section>
              <div>
                <section class="oc-panel oc-balance-panel">
                  <span>可用余额</span
                  ><strong>{{ money(auth.user?.balance) }}</strong>
                  <p>用于支付模型调用费用</p>
                </section>
                <section class="oc-panel">
                  <div class="oc-panel-head"><h2>购买卡密</h2></div>
                  <div class="oc-card-links">
                    <template v-for="a in consoleConfig.amounts" :key="a"
                      ><a
                        v-if="safeHttps(consoleConfig.shop_urls[String(a)])"
                        :href="safeHttps(consoleConfig.shop_urls[String(a)])"
                        target="_blank"
                        rel="noopener noreferrer"
                        class="oc-button"
                        >¥{{ a }} ↗</a
                      ><button v-else class="oc-button" disabled>
                        ¥{{ a }}
                      </button></template
                    >
                  </div>
                  <p class="oc-hint">
                    购买入口配置后开放。支付及发卡由购买平台处理，本站提供卡密兑换和记录查询。
                  </p>
                </section>
              </div>
            </div>
          </template>
          <TracePanel v-if="page === '/model-test'" />
          <GroupsPanel v-if="page === '/groups'" />
          <PricingPanel v-if="page === '/pricing'" />
          <template v-if="page === '/orders'">
            <section class="oc-panel oc-table-wrap">
              <table v-if="orderTab === 'redeem'" class="oc-table-cards">
                <thead>
                  <tr>
                    <th>记录编号</th>
                    <th>类型</th>
                    <th>到账金额 / 权益</th>
                    <th>兑换时间</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="h in history" :key="h.id">
                    <td data-label="记录编号">#{{ h.id }}</td>
                    <td data-label="类型">
                      {{
                        ['balance', 'admin_balance'].includes(h.type)
                          ? '账户余额'
                          : h.type
                      }}
                    </td>
                    <td data-label="到账金额 / 权益">
                      {{
                        ['balance', 'admin_balance'].includes(h.type)
                          ? money(h.value)
                          : h.type === 'subscription'
                            ? `${h.validity_days} 天订阅`
                            : h.value
                      }}
                    </td>
                    <td data-label="兑换时间">
                      {{ date(h.used_at || h.created_at) }}
                    </td>
                  </tr>
                </tbody>
              </table>
              <table v-else class="oc-table-cards">
                <thead>
                  <tr>
                    <th>订单号</th>
                    <th>充值额度</th>
                    <th>实付</th>
                    <th>状态</th>
                    <th>创建时间</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="o in orders" :key="o.id">
                    <td data-label="订单号">
                      <code>{{ o.out_trade_no || o.id }}</code>
                    </td>
                    <td data-label="充值额度">{{ money(o.amount) }}</td>
                    <td data-label="实付">
                      {{ o.pay_amount }} {{ o.currency || 'CNY' }}
                    </td>
                    <td data-label="状态">
                      <span
                        class="oc-tag"
                        :class="{ amber: o.status === 'PENDING' }"
                        >{{ statusName(o.status) }}</span
                      >
                    </td>
                    <td data-label="创建时间">{{ date(o.created_at) }}</td>
                  </tr>
                </tbody>
              </table>
              <div
                v-if="
                  !(orderTab === 'redeem' ? history.length : orders.length) &&
                  !busy
                "
                class="oc-empty"
              >
                暂无{{ orderTab === 'redeem' ? '兑换' : '支付' }}记录
              </div>
            </section>
          </template>
          <template v-if="page === '/announcements'"
            ><section
              v-for="a in announcements"
              :key="a.id"
              class="oc-panel oc-announcement"
            >
              <span class="oc-tag" :class="{ muted: !!a.read_at }">{{
                a.read_at ? '已读' : '新公告'
              }}</span>
              <h2>{{ a.title }}</h2>
              <small>{{ date(a.created_at) }}</small>
              <p>{{ a.content }}</p>
              <button
                v-if="!a.read_at"
                class="oc-button small"
                @click="markRead(a)"
              >
                标为已读
              </button>
            </section>
            <div v-if="!announcements.length && !busy" class="oc-empty">
              暂无公告
            </div></template
          >
          <template v-if="page === '/help'"
            ><HelpGuide />
            <section id="cc-switch" class="oc-panel oc-faq">
              <span class="oc-eyebrow">CC SWITCH</span>
              <h2>用 CC Switch 接入 Claude Code</h2>
              <p>CC Switch 可以管理 Claude Code 的接口配置。完成下面的设置后，Claude Code 使用你的 OpenCC 密钥调用模型，费用从本站余额扣除。</p>
              <p>
                <a class="oc-text-link" href="https://github.com/farion1231/cc-switch/releases" target="_blank" rel="noopener noreferrer">下载 CC Switch ↗</a>
                · <a class="oc-text-link" href="https://github.com/farion1231/cc-switch/blob/main/docs/user-manual/zh/2-providers/2.1-add.md" target="_blank" rel="noopener noreferrer">项目使用手册 ↗</a>
              </p>
              <div class="oc-doc-step"><b>01</b><div>
                <h3>准备密钥和模型</h3>
                <p>先安装 Claude Code 和 CC Switch。在本站「API 密钥」创建一把 Claude 分组密钥，并从「模型广场」复制该分组可用的完整模型 ID。账户需有可用余额。</p>
                <RouterLink to="/keys" class="oc-text-link">管理 API 密钥 →</RouterLink>
              </div></div>
              <div class="oc-doc-step"><b>02</b><div>
                <h3>添加 OpenCC</h3>
                <p>打开 CC Switch，选择 Claude Code，在「直连」页添加供应商，选择「自定义配置」。按下面填写，按钮名称可能随版本略有不同。</p>
                <div class="oc-table-wrap"><table>
                  <thead><tr><th>配置项</th><th>填写内容</th></tr></thead>
                  <tbody>
                    <tr><td>名称</td><td>OpenCC</td></tr>
                    <tr><td>API 请求地址 / Base URL</td><td><code>{{ gatewayURL() }}</code> <button class="oc-button small" @click="copy(gatewayURL())">复制地址</button></td></tr>
                    <tr><td>API Key</td><td>你在本站创建的密钥</td></tr>
                    <tr><td>接口格式（如有）</td><td>Anthropic Messages</td></tr>
                    <tr><td>模型 / 默认模型（如有）</td><td>该密钥所属分组可用的完整 Claude 模型 ID</td></tr>
                  </tbody>
                </table></div>
                <p>这里填写服务根地址，不要追加 <code>/v1</code> 或 <code>/v1/messages</code>。需要设置 Sonnet、Opus、Haiku 映射时，分别填写该分组支持的对应型号。</p>
              </div></div>
              <div class="oc-doc-step"><b>03</b><div>
                <h3>保存并切换</h3>
                <p>保存后，在 OpenCC 卡片上点击「切换」（部分版本为「启用」），确认显示「使用中」。退出正在运行的 Claude Code，再从终端重新启动。</p>
              </div></div>
              <div class="oc-doc-step"><b>04</b><div>
                <h3>发起一次请求</h3>
                <p>选择已配置的模型，发送一条简短消息，然后在本站「用量明细」核对模型、请求时间和费用。出现记录后，说明请求已经过 OpenCC；模型名称本身不构成真实性证明，需要时可到「模型检测」继续测试。</p>
                <RouterLink to="/usage" class="oc-text-link">查看用量明细 →</RouterLink>
              </div></div>
              <details><summary>切换后没有生效怎么办？</summary>
                <p>确认 OpenCC 卡片为「使用中」，并重启 Claude Code。检查终端是否另外设置了 ANTHROPIC_BASE_URL、ANTHROPIC_AUTH_TOKEN 或 ANTHROPIC_API_KEY，避免旧配置覆盖当前设置。</p>
                <p>如果 Claude Code 在 WSL 中运行，请确认 CC Switch 修改的是对应 WSL 用户的配置；只修改 Windows 用户目录不会自动更新 WSL 内的配置。</p>
              </details>
              <details><summary>出现认证失败或找不到模型怎么办？</summary>
                <p>401 时核对密钥是否完整、有效；找不到模型时核对模型 ID 和密钥分组；余额不足时先充值。不要把本站密钥填入上游网站或其他供应商配置。</p>
              </details>
              <p class="oc-hint">此教程使用 Anthropic Messages 直连配置。CC Switch 的路由、聚合和协议转换属于其他接入方式，请按项目手册另行配置。</p>
            </section>
            <div class="oc-doc-layout">
              <section class="oc-panel">
                <span class="oc-eyebrow">QUICK START</span>
                <h2>快速开始</h2>
                <div class="oc-doc-step">
                  <b>01</b>
                  <div>
                    <h3>创建独立的 API 密钥</h3>
                    <p>
                      进入「API
                      密钥」，选择模型对应的分组并创建密钥。把它保存在本机环境变量或服务端密钥管理器中。
                    </p>
                    <RouterLink to="/keys" class="oc-text-link"
                      >前往创建 →</RouterLink
                    >
                  </div>
                </div>
                <div class="oc-doc-step">
                  <b>02</b>
                  <div>
                    <h3>配置客户端与协议</h3>
                    <p>
                      Claude / Anthropic 客户端的 Base URL：<code>{{
                        gatewayURL()
                      }}</code
                      >。Messages 完整端点为 <code>/v1/messages</code>。
                    </p>
                    <p>
                      OpenAI 兼容客户端的 Base URL：<code
                        >{{ gatewayURL() }}/v1</code
                      >。按客户端要求使用 Chat Completions 或 Responses 协议。
                    </p>
                  </div>
                </div>
                <div class="oc-doc-step">
                  <b>03</b>
                  <div>
                    <h3>选择模型，发起请求</h3>
                    <p>
                      在模型广场复制模型 ID，替换示例中的 MODEL_ID。将密钥设置为
                      OPENCC_API_KEY，完成请求后到用量明细核对结果。
                    </p>
                  </div>
                </div>
              </section>
              <section class="oc-code-panel">
                <div>
                  <span>Anthropic Messages · cURL</span
                  ><button aria-label="复制代码示例" @click="copy(sample)">
                    <Icon name="copy" />
                  </button>
                </div>
                <pre><code>{{sample}}</code></pre>
                <p>
                  密钥仅用于示例变量。请勿将真实密钥写入网页前端或公开仓库。
                </p>
              </section>
            </div>
            <section class="oc-panel oc-faq">
              <h2>常见问题</h2>
              <details>
                <summary>为什么我的请求没有成功？</summary>
                <p>
                  先核对 API 地址、模型 ID、密钥所属分组与余额。401
                  通常表示认证失败；429
                  表示触发频率或并发限制；具体原因以接口返回为准。
                </p>
              </details>
              <details>
                <summary>卡密兑换后在哪里查看余额？</summary>
                <p>
                  购买卡密后在账户充值页兑换。到账后可查看余额和兑换记录。
                </p>
              </details>
              <details>
                <summary>费用如何计算？</summary>
                <p>
                  模型计费可能区分输入、输出、缓存、长上下文等。完整规则以模型广场中对应分组的价格表为准，最终扣费可在用量明细查看。
                </p>
              </details>
            </section></template
          >
          <div
            v-if="['/keys', '/usage', '/orders'].includes(page)"
            class="oc-pagination"
          >
            <span>共 {{ total }} 条记录</span>
            <div>
              <button :disabled="current === 1 || busy" @click="paginate(-1)">
                上一页</button
              ><span>{{ current }}</span
              ><button
                :disabled="
                  current * (page === '/keys' ? 10 : 15) >= total || busy
                "
                @click="paginate(1)"
              >
                下一页
              </button>
            </div>
          </div>
        </template>
        <footer class="oc-footer">
          <span>© {{ new Date().getFullYear() }} OpenCC · API 模型服务</span
          ><span
            ><RouterLink to="/help">使用文档</RouterLink
            ><a
              v-if="safeHttps(consoleConfig.support_url)"
              :href="safeHttps(consoleConfig.support_url)"
              target="_blank"
              rel="noopener noreferrer"
              >联系支持 ↗</a
            ><RouterLink v-if="auth.isAdmin" to="/admin/dashboard"
              >管理后台</RouterLink
            ><button
              v-if="auth.isAuthenticated"
              @click="logout"
            >
              退出登录
            </button></span
          >
        </footer>
      </main>
    </div>
    <div v-if="toast" class="oc-toast" role="status">
      <Icon name="check" />{{ toast }}
    </div>
    <div v-if="dialog" class="oc-modal-backdrop" @click.self="dialog = false">
      <section
        class="oc-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="key-dialog-title"
        @keydown.esc="dialog = false"
      >
        <div class="oc-panel-head">
          <h2 id="key-dialog-title">创建 API 密钥</h2>
          <button
            class="oc-icon-button"
            aria-label="关闭对话框"
            @click="dialog = false"
          >
            <Icon name="close" />
          </button>
        </div>
        <p>为一个项目创建一把密钥，便于独立管理。</p>
        <form @submit.prevent="createKey">
          <label class="oc-field"
            >密钥名称<input
              ref="keyNameInput"
              v-model="keyName"
              required
              maxlength="100"
              placeholder="例如：我的研究助手" /></label
          ><label class="oc-field"
            >模型分组<select v-model="keyGroup" required>
              <option :value="undefined" disabled>请选择分组</option>
              <option v-for="g in groups" :key="g.id" :value="g.id">
                {{ g.name }}
              </option>
            </select></label
          ><label class="oc-field"
            >金额限额（¥，0 表示不设限）<input
              v-model.number="keyQuota"
              type="number"
              min="0"
              step="0.01"
              required
          /></label>
          <p v-if="!groups.length" class="oc-hint">
            当前没有可用分组，请等待渠道配置完成。
          </p>
          <button
            class="oc-button primary wide"
            :disabled="saving || !keyGroup"
          >
            {{ saving ? '正在创建…' : '创建密钥' }}
          </button>
        </form>
      </section>
    </div>
  </div>
</template>
