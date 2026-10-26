import type { RouteRecordRaw } from 'vue-router'

// OpenCC overlays the user-facing pages of Sub2API without editing the upstream
// route table, so upstream router changes merge cleanly.
const workspace = () => import('@/opencc/WorkspaceView.vue')

const added: RouteRecordRaw[] = [
  { path: '/help', name: 'OpenCCHelp', component: workspace, meta: { requiresAuth: false, title: '接入文档' } },
  { path: '/announcements', name: 'OpenCCAnnouncements', component: workspace, meta: { requiresAuth: true, title: '站内公告' } },
  { path: '/model-test', name: 'OpenCCTrace', component: workspace, meta: { requiresAuth: true, title: '模型检测' } },
  { path: '/pricing', name: 'OpenCCPricing', component: workspace, meta: { requiresAuth: false, title: '模型计费规则' } }
]

// Route name → page title. Each listed route is rendered by WorkspaceView.
const replaced: Record<string, string> = {
  Home: '首页',
  ModelPlaza: '模型广场',
  Dashboard: '账户工作台',
  Keys: 'API 密钥',
  Usage: '用量明细',
  Redeem: '账户充值',
  OrderList: '兑换记录'
}

export function applyOpenCCRoutes(routes: RouteRecordRaw[]): RouteRecordRaw[] {
  for (const route of routes) {
    const title = typeof route.name === 'string' ? replaced[route.name] : undefined
    if (!title) continue
    const meta = { ...route.meta, title }
    delete meta.titleKey
    // Orders here are card redemptions, not online payments.
    delete meta.requiresPayment
    Object.assign(route, { component: workspace, meta })
  }
  return [...added, ...routes]
}

export const openccRouteNames = Object.keys(replaced)
