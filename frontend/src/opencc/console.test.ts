import { describe, it, expect } from 'vitest'
import { providerOf, safeHttps, money, consoleConfig } from './config'
describe('OpenCC adapter boundaries', () => {
  it('does not include another vendor or misclassify an arbitrary name', () => {
    expect(providerOf('claude-opus-4-6')).toBe('Claude')
    expect(providerOf('gpt-image-2')).toBe('GPT')
    expect(providerOf('grok-4.5')).toBe('Grok')
    expect(providerOf('gemini-3')).toBeNull()
  })
  it('rejects unsafe checkout URLs', () => {
    expect(safeHttps('javascript:alert(1)')).toBe('')
    expect(safeHttps('https://name:pass@example.com')).toBe('')
    expect(safeHttps('//example.com')).toBe('')
    expect(safeHttps('https://shop.example/item/10')).toBe(
      'https://shop.example/item/10'
    )
  })
  it('converts ledger units rather than only replacing the dollar sign', () => {
    consoleConfig.cny_per_credit = 7
    expect(money(2)).toContain('14.00')
    consoleConfig.cny_per_credit = 1
    expect(money(10)).toBe('¥10.00')
  })
})
