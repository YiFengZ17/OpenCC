<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref } from 'vue'
import { useRouter } from 'vue-router'
import { apiClient } from '@/api/client'
const text = ref('')
let controller: AbortController | undefined
let sequence = 0
async function refresh() {
  const current = ++sequence
  controller?.abort()
  const activeController = new AbortController()
  controller = activeController
  text.value = ''
  const timeout = setTimeout(() => activeController.abort(), 5000)
  try {
    const { data } = await apiClient.get<{ showNotice: boolean; text: string }>(
      '/opencc/region',
      { signal: activeController.signal }
    )
    if (current === sequence) text.value = data.showNotice ? data.text : ''
  } catch {
    /* unknown is not CN */
  } finally {
    clearTimeout(timeout)
  }
}
function visibility() {
  if (document.visibilityState === 'visible') void refresh()
}
const removeHook = useRouter().afterEach(() => void refresh())
onMounted(() => {
  void refresh()
  document.addEventListener('visibilitychange', visibility)
})
onBeforeUnmount(() => {
  sequence++
  controller?.abort()
  removeHook()
  document.removeEventListener('visibilitychange', visibility)
})
</script>
<template>
  <aside v-if="text" class="oc-region" role="status">
    <strong>服务地区提示</strong>
    <p>{{ text }}</p>
  </aside>
</template>
<style scoped>
.oc-region {
  position: relative;
  z-index: 80;
  background: #fff4de;
  border-bottom: 1px solid #ecd7aa;
  color: #66501c;
  padding: 15px 24px;
  font-size: 13px;
  line-height: 1.9;
}
.oc-region strong {
  display: block;
  font-weight: 700;
  margin-bottom: 3px;
}
.oc-region p {
  max-width: 1280px;
  margin: 0 auto;
}
</style>
