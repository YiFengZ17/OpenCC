// Local Vite development middleware only. Never bundled or used by the Go server.
import type { Plugin } from 'vite'
import { readFileSync } from 'node:fs'
const notice =
  '我司检测到您的 IP 地址来源于中国大陆，此在我们所授权的可访问的服务地区以外，仅授权大陆模型转发权限。我司不会以任何形式存储您的信息，仅提供面向模型服务提供商的转发能力。请您务必知晓我司用户协议与您所在地区的相关法规并取得相关授权，我司不对您的任何行为负责。'
const settings = {
  site_name: 'OpenCC',
  site_logo: '/logo.svg',
  site_subtitle: '模型 API 工作空间',
  registration_enabled: true,
  email_verify_enabled: false,
  model_plaza_enabled: true,
  model_plaza_require_auth: false,
  subscription_enabled: false,
  payment_enabled: false,
  backend_mode_enabled: false,
  turnstile_enabled: false,
  custom_menu_items: [],
  oauth_providers: []
}
export function openccDemo(): Plugin {
  const user = {
    id: 1,
    username: 'Explorer',
    email: 'demo@example.invalid',
    role: 'user',
    status: 'active',
    balance: 128.5,
    concurrency: 5,
    created_at: '2026-10-23T01:00:00Z'
  }
  const groups = [{"id": 1, "name": "claude 满血kiro 纯满血", "platform": "anthropic", "rate_multiplier": 0.8}, {"id": 2, "name": "ChatGPT-Pro【稳定】", "platform": "openai", "rate_multiplier": 0.22}, {"id": 3, "name": "ChatGPT-Pro【企业】", "platform": "openai", "rate_multiplier": 0.25}, {"id": 4, "name": "ChatGPT-ProMax【企业】", "platform": "openai", "rate_multiplier": 0.36}, {"id": 5, "name": "grok", "platform": "grok", "rate_multiplier": 0.15}]
  let keys = [
    {
      id: 1,
      name: '我的研究助手',
      key: 'sk-opencc-demo-not-a-real-key-0001',
      user_id: 1,
      group_id: 1,
      group: groups[0],
      status: 'active',
      quota: 100,
      quota_used: 21.5,
      created_at: '2026-10-22T08:30:00Z'
    },
    {
      id: 2,
      name: '日常代码工作台',
      key: 'sk-opencc-demo-not-a-real-key-0002',
      user_id: 1,
      group_id: 2,
      group: groups[1],
      status: 'active',
      quota: 0,
      quota_used: 3.86,
      created_at: '2026-10-21T06:15:00Z'
    }
  ]
  let nextId = 3,
    region = 'US'
  const usedCodes = new Set<string>()
  const history = [
    {
      id: 1,
      type: 'balance',
      value: 100,
      status: 'used',
      used_at: '2026-10-22T09:30:00Z',
      created_at: '2026-10-22T09:30:00Z'
    }
  ]
  const names = JSON.parse(
    readFileSync(new URL('./src/opencc/catalog.json', import.meta.url), 'utf8')
  ).models as string[]
  const logs = Array.from({ length: 24 }, (_, i) => ({
    id: i + 1,
    request_id: `req_demo_${String(24 - i).padStart(8, '0')}`,
    model: names[i % names.length],
    input_tokens: 1240 + i * 170,
    output_tokens: 360 + i * 29,
    actual_cost: 0.018 + i * 0.0027,
    duration_ms: 1420 + i * 120,
    created_at: new Date(Date.UTC(2026, 9, 23, 9, 42 - i * 5)).toISOString()
  }))
  const announcements = [
    {
      id: 1,
      title: '欢迎来到 OpenCC',
      content:
        '这是本地预览公告。完成渠道配置后，你可以在后台发布服务通知、模型更新和维护计划。',
      created_at: '2026-10-23T02:00:00Z',
      read_at: null as string | null
    }
  ]
  const paginate = (items: unknown[], u: URL) => {
    const page = Number(u.searchParams.get('page') || 1),
      size = Number(u.searchParams.get('page_size') || 15)
    return {
      items: items.slice((page - 1) * size, page * size),
      page,
      page_size: size,
      total: items.length,
      total_pages: Math.ceil(items.length / size)
    }
  }
  return {
    name: 'opencc-local-demo',
    apply: 'serve',
    transformIndexHtml(html) {
      return html.replace(
        '</head>',
        `<script>window.__APP_CONFIG__=${JSON.stringify(settings)};if(!['/login','/register'].includes(location.pathname)){localStorage.setItem('auth_token','opencc-local-demo-only');localStorage.setItem('auth_user',${JSON.stringify(JSON.stringify(user))});}else{localStorage.removeItem('auth_token');localStorage.removeItem('auth_user');}</script></head>`
      )
    },
    configureServer(server) {
      server.middlewares.use(async (req, res, next) => {
        const u = new URL(req.url || '/', 'http://localhost')
        const p = u.pathname
        if (
          !p.startsWith('/api/') &&
          !p.startsWith('/v1/') &&
          !p.startsWith('/setup/') &&
          !p.startsWith('/__opencc-demo/')
        )
          return next()
        const send = (data: unknown, status = 200) => {
          res.statusCode = status
          res.setHeader('Content-Type', 'application/json')
          res.setHeader('Cache-Control', 'private, no-store')
          res.end(
            JSON.stringify({
              code: status === 200 ? 0 : status,
              ...(status === 200 ? { data } : { message: String(data) })
            })
          )
        }
        if (p.startsWith('/v1/'))
          return send(
            '本地演示不发送真实模型请求。请在接入上游后使用自动检测，或使用手动粘贴检测。',
            503
          )
        let body: Record<string, any> = {}
        if (req.method !== 'GET') {
          let raw = ''
          for await (const chunk of req) {
            raw += String(chunk)
            if (raw.length > 8192) return send('Payload too large', 413)
          }
          try {
            body = JSON.parse(raw || '{}')
          } catch {
            return send('Invalid JSON', 400)
          }
        }
        if (p === '/__opencc-demo/region' && req.method === 'POST') {
          region = String(body.country || 'XX')
          return send({ country: region })
        }
        if (p === '/setup/status') return send({ needs_setup: false })
        if (p === '/api/v1/settings/public') return send(settings)
        if (p === '/api/v1/opencc/config')
          return send({
            brand: 'OpenCC',
            cny_per_credit: 1,
            amounts: [10, 50, 100, 200],
            shop_urls: {},
            support_url: '',
            gateway_url: ''
          })
        if (p === '/api/v1/opencc/region')
          return send({
            status: region === 'XX' ? 'unknown' : 'known',
            showNotice: region === 'CN',
            text: region === 'CN' ? notice : ''
          })
        if (p === '/api/v1/auth/me')
          return send({ ...user, run_mode: 'standard' })
        if (p === '/api/v1/auth/logout') return send({})
        if (p === '/api/v1/groups/available') return send(groups)
        if (p === '/api/v1/groups/rates') return send({})
        if (p === '/api/v1/model-plaza')
          return send({
            description: '本地演示目录，非真实服务价格。',
            groups: []
          })
        if (p === '/api/v1/keys') {
          if (req.method === 'POST') {
            const name = String(body.name || '').trim(),
              group = groups.find((g) => g.id === body.group_id)
            if (!name || !group) return send('请选择分组并填写名称', 400)
            const k = {
              id: nextId++,
              name,
              key: `sk-opencc-demo-not-a-real-key-${nextId}`,
              user_id: 1,
              group_id: group.id,
              group,
              status: 'active',
              quota: Number(body.quota) || 0,
              quota_used: 0,
              created_at: new Date().toISOString()
            }
            keys.push(k)
            return send(k)
          }
          return send(paginate(keys, u))
        }
        if (/^\/api\/v1\/keys\/\d+$/.test(p)) {
          const id = Number(p.split('/').pop()),
            k = keys.find((k) => k.id === id)
          if (!k) return send('Key not found', 404)
          if (req.method === 'DELETE') {
            keys = keys.filter((k) => k.id !== id)
            return send({})
          }
          if (req.method === 'PUT' || req.method === 'PATCH') {
            if (body.status) k.status = body.status
            return send(k)
          }
          return send(k)
        }
        if (p === '/api/v1/usage/dashboard/stats')
          return send({
            total_requests: 1248,
            today_requests: 86,
            today_tokens: 142830,
            today_actual_cost: 2.486,
            total_actual_cost: 21.5,
            active_api_keys: keys.filter((k) => k.status === 'active').length
          })
        if (p === '/api/v1/usage')
          return send(
            paginate(
              logs.filter(
                (l) =>
                  !u.searchParams.get('model') ||
                  l.model === u.searchParams.get('model')
              ),
              u
            )
          )
        if (p === '/api/v1/redeem' && req.method === 'POST') {
          if (body.code !== 'OPENCC-DEMO-10')
            return send('演示充值码为 OPENCC-DEMO-10，仅用于本地测试', 400)
          if (usedCodes.has(body.code)) return send('该充值码已经使用', 409)
          usedCodes.add(body.code)
          user.balance += 10
          history.unshift({
            id: history.length + 1,
            type: 'balance',
            value: 10,
            status: 'used',
            used_at: new Date().toISOString(),
            created_at: new Date().toISOString()
          })
          return send({
            message: '演示兑换成功',
            type: 'balance',
            value: 10,
            new_balance: user.balance
          })
        }
        if (p === '/api/v1/redeem/history') return send(paginate(history, u))
        if (p === '/api/v1/payment/orders/my') {
          const items = [
            {
              id: 1,
              out_trade_no: 'DEMO202610220001',
              amount: 50,
              pay_amount: 50,
              currency: 'CNY',
              status: 'COMPLETED',
              created_at: '2026-10-22T08:30:00Z'
            }
          ]
          return send(
            paginate(
              items.filter(
                (o) =>
                  !u.searchParams.get('status') ||
                  o.status === u.searchParams.get('status')
              ),
              u
            )
          )
        }
        if (p === '/api/v1/announcements') return send(announcements)
        if (/^\/api\/v1\/announcements\/\d+\/read$/.test(p)) {
          announcements[0].read_at = new Date().toISOString()
          return send({ message: '已读' })
        }
        if (p.startsWith('/api/v1/subscriptions')) return send([])
        return send('此接口未包含在本地演示中', 404)
      })
    }
  }
}
