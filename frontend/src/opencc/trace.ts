import { parseNumbers } from './vendor/modeltrace/fingerprint-core.js'
export type TraceProtocol = 'anthropic' | 'openai' | 'responses'
export interface Probe {
  text: string
  expected_count: number
  request_id: string
  duration_ms: number
  valid: boolean
  error: string
}
// Keys are sent only to this site's own gateway, never to ModelTrace or an arbitrary URL.
export async function runProbe(
  model: string,
  key: string,
  prompt: string,
  count: number,
  protocol: TraceProtocol,
  signal: AbortSignal,
  request: typeof fetch = fetch
): Promise<Probe> {
  const started = Date.now()
  const endpoint =
    protocol === 'anthropic'
      ? '/v1/messages'
      : protocol === 'responses'
        ? '/v1/responses'
        : '/v1/chat/completions'
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (protocol === 'anthropic') {
    headers['x-api-key'] = key
    headers['anthropic-version'] = '2023-06-01'
  } else headers.Authorization = `Bearer ${key}`
  const body =
    protocol === 'responses'
      ? {
          model,
          input: prompt,
          max_output_tokens: 4096,
          store: false,
          stream: false
        }
      : protocol === 'anthropic'
        ? {
            model,
            max_tokens: 4096,
            messages: [{ role: 'user', content: prompt }],
            stream: false
          }
        : {
            model,
            max_completion_tokens: 4096,
            messages: [{ role: 'user', content: prompt }],
            stream: false
          }
  const response = await request(endpoint, {
    method: 'POST',
    headers,
    body: JSON.stringify(body),
    signal,
    credentials: 'omit',
    redirect: 'error',
    cache: 'no-store'
  })
  if (!response.ok)
    throw new Error(
      `请求失败（HTTP ${response.status}）。请检查密钥、模型权限、余额和接口格式。`
    )
  const raw = await response.text()
  if (raw.length > 1048576) throw new Error('返回内容过大，本次测试已停止。')
  let data
  try {
    data = JSON.parse(raw)
  } catch {
    throw new Error('接口返回了非 JSON 内容，请核对接口格式。')
  }
  let text = '',
    truncated = false
  if (protocol === 'anthropic') {
    text = (data.content || [])
      .filter((b: { type: string }) => b.type === 'text')
      .map((b: { text: string }) => b.text)
      .join('\n')
    truncated = data.stop_reason === 'max_tokens'
  } else if (protocol === 'responses') {
    text = (data.output || [])
      .flatMap(
        (o: { content?: { type: string; text: string }[] }) => o.content || []
      )
      .filter((c: { type: string }) => c.type === 'output_text')
      .map((c: { text: string }) => c.text)
      .join('\n')
    truncated = data.status === 'incomplete'
  } else {
    text = data.choices?.[0]?.message?.content || ''
    truncated = data.choices?.[0]?.finish_reason === 'length'
  }
  const enough =
    parseNumbers(text).length >= Math.max(80, Math.ceil(count * 0.55))
  return {
    text,
    expected_count: count,
    request_id:
      response.headers.get('x-request-id') ||
      response.headers.get('request-id') ||
      '',
    duration_ms: Date.now() - started,
    valid: !truncated && enough,
    error: truncated
      ? '输出被截断，不计入检测'
      : enough
        ? ''
        : '有效数字不足，不计入检测'
  }
}
export function verdict(
  claim: string,
  bankIds: string[],
  prediction: string,
  valid: number
): string {
  if (!bankIds.includes(claim)) return '指纹库未收录此型号，无法核验版本'
  if (valid < 3) return '有效样本不足，请重新检测'
  return claim === prediction
    ? '检测结果与所选型号一致'
    : '检测结果与所选型号不一致，建议复测'
}
export type VerdictTone = 'match' | 'mismatch' | 'unknown'
// Same rules as verdict(), as a state the page can colour.
export function verdictTone(
  claim: string,
  bankIds: string[],
  prediction: string,
  valid: number
): VerdictTone {
  if (!bankIds.includes(claim) || valid < 3) return 'unknown'
  return claim === prediction ? 'match' : 'mismatch'
}
// Claude models answer on Anthropic Messages; everything else on Chat Completions.
export function protocolFor(model: string): TraceProtocol {
  return model.startsWith('claude-') ? 'anthropic' : 'openai'
}
// Prefer a model the fingerprint bank can verify, Claude Sonnet first.
export function defaultModel(options: string[], bankIds: string[]): string {
  const verifiable = options.filter((m) => bankIds.includes(m))
  return (
    verifiable.find((m) => m.startsWith('claude-sonnet')) ??
    verifiable[0] ??
    options[0] ??
    ''
  )
}
