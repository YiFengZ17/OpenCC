import { describe, it, expect, vi } from 'vitest'
import { runProbe, verdict } from './trace'
import {
  parseNumbers,
  analyzeGlobalOutputs,
  type Bank
} from './vendor/modeltrace/fingerprint-core.js'
import bankData from './vendor/modeltrace/unified_bank.json'
import { pointPrice, priceRate } from './pricing'
import snapshot from './upstream-pricing.json'
import type { ModelPlazaGroup } from '@/api/modelPlaza'
const sequence = Array.from({ length: 310 }, (_, i) => (i % 355) + 1).join(',')
describe('ModelTrace integration', () => {
  it('keeps unknown models and partial samples out of positive conclusions', () => {
    expect(verdict('grok-4.5', ['gpt-5.4'], 'gpt-5.4', 3)).toContain('未收录')
    expect(verdict('gpt-5.4', ['gpt-5.4'], 'gpt-5.4', 2)).toContain('不足')
    expect(verdict('gpt-5.4', ['gpt-5.4'], 'claude-opus-4-6', 3)).toContain(
      '不一致'
    )
  })
  it('runs the upstream engine and produces normalized candidate probabilities', () => {
    const bank = bankData as unknown as Bank
    const r = analyzeGlobalOutputs(
      Array(3).fill({ text: sequence, expected_count: 310 }),
      bank
    )
    expect(r.used_outputs).toBe(3)
    expect(r.results.reduce((n, r) => n + r.probability, 0)).toBeCloseTo(1, 10)
    expect(r.results).toHaveLength(bank.models.length)
    expect(() =>
      analyzeGlobalOutputs([{ text: '无法完成', expected_count: 300 }], bank)
    ).toThrow()
  })
  it('parses the longest uninterrupted numeric sequence', () => {
    expect(parseNumbers('任务 3 次，输出：1, 12, 355, 500。附注 2')).toEqual([
      1, 12, 355
    ])
  })
  it('sends only to the same-origin gateway, without session cookies or redirects', async () => {
    const request = vi
      .fn()
      .mockResolvedValue(
        new Response(
          JSON.stringify({
            content: [{ type: 'text', text: sequence }],
            stop_reason: 'end_turn'
          }),
          { status: 200, headers: { 'x-request-id': 'test-request' } }
        )
      )
    const result = await runProbe(
      'claude-opus-4-6',
      'local-test-key',
      'probe',
      310,
      'anthropic',
      new AbortController().signal,
      request
    )
    expect(result.valid).toBe(true)
    expect(result.request_id).toBe('test-request')
    const [url, options] = request.mock.calls[0]
    expect(url).toBe('/v1/messages')
    expect(options.credentials).toBe('omit')
    expect(options.redirect).toBe('error')
    expect(options.headers['x-api-key']).toBe('local-test-key')
    expect(JSON.parse(options.body).max_tokens).toBe(4096)
  })
  it('rejects truncated outputs even if they contain enough digits', async () => {
    const request = vi
      .fn()
      .mockResolvedValue(
        new Response(
          JSON.stringify({
            choices: [
              { message: { content: sequence }, finish_reason: 'length' }
            ]
          })
        )
      )
    const r = await runProbe(
      'gpt-5.4',
      'test',
      'probe',
      310,
      'openai',
      new AbortController().signal,
      request
    )
    expect(r.valid).toBe(false)
    expect(r.error).toContain('截断')
  })
  it('handles Responses output without treating reasoning as sample text', async () => {
    const request = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          status: 'completed',
          output: [
            { type: 'reasoning', summary: [{ text: '123' }] },
            {
              type: 'message',
              content: [{ type: 'output_text', text: sequence }]
            }
          ]
        })
      )
    )
    const r = await runProbe(
      'gpt-5.4',
      'test',
      'probe',
      310,
      'responses',
      new AbortController().signal,
      request
    )
    expect(r.valid).toBe(true)
    expect(r.text).toBe(sequence)
  })
  it('does not echo upstream errors that may contain secrets', async () => {
    const request = vi
      .fn()
      .mockResolvedValue(new Response('secret-key', { status: 401 }))
    await expect(
      runProbe(
        'x',
        'test',
        'p',
        310,
        'openai',
        new AbortController().signal,
        request
      )
    ).rejects.toThrow('HTTP 401')
  })
})
describe('temporary points pricing', () => {
  it('keeps the USD numerical value, applies group rate and correct unit', () => {
    expect(pointPrice(0.000002, 0.15)).toBeCloseTo(0.3)
    expect(pointPrice(null, 0.15)).toBeNull()
    expect(pointPrice(0.04, 1, 1)).toBe(0.04)
  })
  it('retains every upstream group multiplier and media override', () => {
    for (const g of snapshot.data.groups as unknown as ModelPlazaGroup[]) {
      for (const m of g.models) {
        const expected =
          m.pricing?.billing_mode === 'image' && g.image_rate_independent
            ? g.image_rate_multiplier
            : g.rate_multiplier
        expect(priceRate(g, m)).toBe(expected)
      }
    }
  })
})
