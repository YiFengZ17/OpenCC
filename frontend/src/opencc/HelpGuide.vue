<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { gatewayURL } from './config'
const query = ref(''), active = ref('start')
const articles = [
  {id:'start',title:'快速开始',text:'注册账户，用卡密充值，再创建 API 密钥。选择模型分组，复制该分组的完整模型 ID，在客户端填写地址与密钥。发送简短请求后查看用量明细。'},
  {id:'keys',title:'账户与 API 密钥',text:'账户密码用于登录，API 密钥用于调用。建议为不同项目创建独立密钥，设置金额限额。停用密钥后，该密钥不能继续发起请求。切勿把密钥放进公开代码或截图。'},
  {id:'clients',title:'客户端与接口地址',text:'按客户端支持的协议选择地址。Base URL 是基础地址，完整 Endpoint 包含具体路径；自动补路径的客户端不要重复填写 /v1。'},
  {id:'codex',title:'Codex 接入',text:'在 CC Switch 中切换到 Codex，添加 OpenCC 自定义供应商，使用 OpenAI Responses 协议。填写下方基础地址、本站密钥和分组可用模型，保存并启用后重启客户端。Windows 原生客户端和 WSL 使用各自的用户配置目录。'},
  {id:'claude',title:'Claude Code / CC Switch',text:'Claude Code 使用 Anthropic Messages。按下方 CC Switch 教程配置根地址和 Claude 分组密钥，选择该分组开放的模型；配置生效后发送一次请求，并在用量明细核对。'},
  {id:'billing',title:'模型与计费',text:'文本模型统一按每百万 Token 报价，分别计算普通输入、输出、缓存读取和缓存写入。缓存命中率用于查看使用情况，费用依据实际缓存 Token 数计算。价格表已包含所示分组倍率，不需再次乘倍率。图片等非文本服务以对应计费单位为准。'},
  {id:'recharge',title:'卡密充值',text:'购买卡密后，进入账户充值页输入完整卡密。每张只能兑换一次。到账金额计入人民币余额，兑换记录可查。未到账时核对兑换提示和记录，请勿重复购买以解决同一问题。'},
  {id:'usage',title:'用量与账单',text:'根据请求时间、模型和请求编号核对用量明细。客户端超时不代表模型没有执行，重试前先查看账单。价格表用于估算，实际费用以请求结算记录为准。'},
  {id:'errors',title:'故障排查',text:'400 检查参数；401 检查密钥；403 检查分组权限；404 检查路径和模型 ID；429 降低并发并稍后重试；5xx 保留请求编号反馈。返回网页而非 JSON 时检查接口路径。'},
  {id:'support',title:'安全与支持',text:'反馈时提供发生时间、客户端版本、协议、模型 ID、分组、状态码及请求编号。删除密钥、密码和私人对话内容后再分享。'}
]
const visible = computed(()=>articles.filter(a=>(a.title+a.text).includes(query.value)))
watch(visible, matches => {
  if (matches.length && !matches.some(a => a.id === active.value)) active.value = matches[0].id
})
const selected = computed(()=>articles.find(a=>a.id===active.value)!)
</script>
<template>
  <section class="oc-panel">
    <h2>使用指南</h2>
    <label class="oc-field">搜索文档<input v-model="query" placeholder="搜索密钥、计费、报错…" /></label>
    <nav class="oc-tabs" aria-label="帮助文档目录" style="flex-wrap:wrap">
      <button v-for="a in visible" :key="a.id" :class="{selected:active===a.id}" @click="active=a.id">{{ a.title }}</button>
    </nav>
    <p v-if="!visible.length" class="oc-hint">没有找到相关文档。</p>
    <article v-if="visible.length" style="padding-top:20px;line-height:1.9"><h3>{{ selected.title }}</h3><p>{{ selected.text }}</p>
      <div v-if="['clients','codex'].includes(active)" class="oc-table-wrap"><table><thead><tr><th>协议</th><th>Base URL</th><th>完整路径</th></tr></thead><tbody>
        <tr><td>Chat Completions</td><td><code>{{ gatewayURL() }}/v1</code></td><td>/v1/chat/completions</td></tr>
        <tr><td>Responses / Codex</td><td><code>{{ gatewayURL() }}/v1</code></td><td>/v1/responses</td></tr>
        <tr><td>Messages / Claude</td><td><code>{{ gatewayURL() }}</code></td><td>/v1/messages</td></tr>
      </tbody></table></div>
      <p v-if="active==='billing'">示例：输入 ¥2 / 百万 Tokens、输出 ¥8 / 百万 Tokens，1000 个普通输入和 500 个输出预计 ¥0.006；缓存部分按对应单价另计，不能与普通输入重复计费。示例不包含额外计费条件。</p>
      <a v-if="active==='claude'" href="#cc-switch" class="oc-text-link">查看 CC Switch 完整教程 ↓</a>
      <RouterLink v-if="active==='billing'" to="/pricing" class="oc-text-link">查看价格表 →</RouterLink>
    </article>
  </section>
</template>
