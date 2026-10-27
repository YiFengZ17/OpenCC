<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { gatewayURL } from './config'
const query = ref(''), active = ref('start')
const articles = [
  {id:'start',title:'快速开始',text:'三步：建一把 API 密钥，把接口地址和密钥填进客户端，选个模型发一句话。在「用量明细」看到记录，就接通了。'},
  {id:'keys',title:'账户与 API 密钥',text:'账户密码用来登录，API 密钥用来调用，两者别混用。建议每个项目一把密钥，必要时设个额度上限；不用了就停用。密钥别放进公开代码，也别截图发群。'},
  {id:'clients',title:'客户端与接口地址',text:'看你的客户端用哪种协议，对照下表填地址。会自动补路径的客户端，别再手动加 /v1。'},
  {id:'codex',title:'Codex 接入',text:'在 CC Switch 里切到 Codex，添加自定义供应商，协议选 OpenAI Responses，填下表的地址、本站密钥和分组里的模型，保存启用后重启 Codex。Windows 和 WSL 的配置是分开的，在哪里用就改哪里。'},
  {id:'claude',title:'Claude Code / CC Switch',text:'Claude Code 走 Anthropic Messages 协议。照下面的 CC Switch 教程填根地址和 Claude 分组的密钥，发一句话后到用量明细核对。'},
  {id:'verify',title:'模型验真',text:'担心接口背后不是你选的模型？到「模型检测」点“开始检测”。它用的是开源项目 ModelTrace：发 3 道随机的数字题，在你的浏览器里和已知模型的指纹比对，约 1 分钟出结论，按正常价格计费。报告可以下载，用原项目自己复核。'},
  {id:'billing',title:'模型与计费',text:'按 Token 用多少扣多少：输入、输出、缓存读取、缓存写入分开计价，单位是每百万 Token。价格表里的价格已经乘过分组倍率，不用再算一遍。图片等服务按各自的单位计费。'},
  {id:'recharge',title:'充值',text:'找管理员充值，或在「账户充值」输入兑换码。每个兑换码只能用一次，到账后余额和兑换记录都能查到。没到账先看兑换记录，别重复兑换。'},
  {id:'usage',title:'用量与账单',text:'每次调用都有一条记录：时间、模型、Token 数、扣了多少钱、请求编号。客户端超时不等于模型没跑，重试前先看一眼用量明细，避免重复扣费。'},
  {id:'errors',title:'报错怎么办',text:'400 参数不对；401 密钥不对；403 这个分组用不了这个模型；404 地址或模型 ID 写错了；429 发太快了，等一下再试；5xx 是服务端的问题，把请求编号发给我们。返回了一个网页而不是 JSON，通常是地址填错了。'},
  {id:'support',title:'找我们帮忙',text:'把发生时间、客户端、协议、模型 ID、分组、状态码和请求编号告诉我们，问题会好查很多。发之前把密钥、密码和私人对话内容删掉。'}
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
    <p class="oc-hint">按主题查，或者直接搜关键词。</p>
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
      <RouterLink v-if="active==='verify'" to="/model-test" class="oc-text-link">去检测一次 →</RouterLink>
    </article>
  </section>
</template>
