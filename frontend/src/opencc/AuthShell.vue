<script setup lang="ts">
import { onMounted } from 'vue'
import { useAppStore } from '@/stores'
import './console.css'
const appStore = useAppStore()
const demo = import.meta.env.VITE_OPENCC_DEMO === 'true'
onMounted(() => appStore.fetchPublicSettings())
</script>
<template>
  <main class="oc-auth-page">
    <section class="oc-auth-story">
      <RouterLink to="/home" class="oc-auth-brand">&lt; / &gt; OpenCC</RouterLink>
      <div><span class="oc-eyebrow">YOUR MODEL WORKSPACE</span><h1>连接模型，<br />开始工作。</h1><p>管理 API 密钥、查看用量，<br />把模型接入你常用的工具。</p></div>
      <RouterLink to="/help">接入文档 ↗</RouterLink>
    </section>
    <section class="oc-auth-form">
      <RouterLink to="/home" class="oc-auth-back">← 返回首页</RouterLink>
      <div class="oc-auth-card"><p v-if="demo" class="oc-auth-demo">本地预览：用于查看表单，尚未连接账户数据库。</p><slot /></div>
      <div class="oc-auth-footer"><slot name="footer" /></div>
      <p class="oc-auth-copyright">© {{ new Date().getFullYear() }} OpenCC</p>
    </section>
  </main>
</template>
<style scoped>
.oc-auth-page{min-height:100vh;display:grid;grid-template-columns:minmax(300px,0.9fr) minmax(400px,1.1fr);background:#f7f9f6;color:#18372a}
.oc-auth-story{padding:56px 12%;background:#132f25;color:#e6f3e8;display:flex;flex-direction:column;justify-content:space-between;gap:70px}
.oc-auth-brand{font-size:28px;font-weight:700;letter-spacing:-1px}.oc-auth-story h1{font-size:clamp(38px,4vw,64px);line-height:1.25;font-weight:650;margin:24px 0}.oc-auth-story p{font-size:17px;line-height:1.9;color:#b4cbbc}.oc-auth-story a:last-child{color:#c4dfcc}
.oc-auth-form{padding:40px 24px;display:flex;flex-direction:column;justify-content:center;align-items:center}.oc-auth-back{width:100%;max-width:440px;margin-bottom:28px;color:#456654}.oc-auth-card{width:100%;max-width:440px;background:white;padding:32px;border:1px solid #dce5dc;border-radius:20px;box-shadow:0 12px 45px #18372a08}.oc-auth-footer{margin-top:24px;font-size:14px}.oc-auth-copyright{margin-top:40px;font-size:12px;color:#6f8175}
.oc-auth-card :deep(input){font-size:15px;background:#fff;color:#18372a;border-color:#cedbce}.oc-auth-card :deep(.input-label){font-size:14px;color:#18372a}.oc-auth-card :deep(h2){color:#18372a}
.oc-auth-demo{font-size:12px;line-height:1.7;padding:10px 12px;margin-bottom:20px;background:#fff8e7;color:#816222;border-radius:8px}
@media(max-width:800px){.oc-auth-page{display:block}.oc-auth-story{padding:24px;gap:18px}.oc-auth-story h1{font-size:30px;margin:12px 0}.oc-auth-story p,.oc-auth-story>a:last-child{display:none}.oc-auth-story .oc-eyebrow{display:none}.oc-auth-form{padding:24px 16px}.oc-auth-card{padding:24px}.oc-auth-story h1 br{display:none}}
</style>
