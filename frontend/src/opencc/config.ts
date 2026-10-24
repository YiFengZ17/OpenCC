import { reactive } from 'vue'
import { apiClient } from '@/api/client'
export interface ConsoleConfig {
  brand: string
  cny_per_credit: number
  amounts: number[]
  shop_urls: Record<string, string>
  support_url: string
  gateway_url: string
}
export const consoleConfig = reactive<ConsoleConfig>({
  brand: 'OpenCC',
  cny_per_credit: 1,
  amounts: [10, 50, 100, 200],
  shop_urls: {},
  support_url: '',
  gateway_url: ''
})
export async function loadConsoleConfig() {
  const { data } = await apiClient.get<ConsoleConfig>('/opencc/config')
  Object.assign(consoleConfig, data)
}
export const money = (credits: number | null | undefined, digits = 2) =>
  '¥' + new Intl.NumberFormat('zh-CN', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits
  }).format((credits ?? 0) * consoleConfig.cny_per_credit)
export const number = (n: number | null | undefined) =>
  new Intl.NumberFormat('zh-CN', {
    notation: (n ?? 0) >= 100000 ? 'compact' : 'standard',
    maximumFractionDigits: 1
  }).format(n ?? 0)
export function safeHttps(raw: string | undefined): string {
  try {
    const u = new URL(raw ?? '')
    return u.protocol === 'https:' && !u.username && !u.password ? u.href : ''
  } catch {
    return ''
  }
}
export function providerOf(name: string): 'Claude' | 'GPT' | 'Grok' | null {
  if (name.startsWith('claude-')) return 'Claude'
  if (name.startsWith('gpt-') || name.startsWith('codex-')) return 'GPT'
  if (name.startsWith('grok-')) return 'Grok'
  return null
}
export function gatewayURL() {
  return consoleConfig.gateway_url || window.location.origin
}
