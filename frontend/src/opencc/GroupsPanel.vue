<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { userGroupsAPI } from '@/api/groups'
import { modelPlazaAPI } from '@/api/modelPlaza'
import type { GroupPlatform } from '@/types'
import PlatformIcon from '@/components/common/PlatformIcon.vue'
type Channel = { id: number; name: string; platform: GroupPlatform; rate_multiplier: number; user_rate_multiplier?: number | null; credit_billing?: { enabled: boolean; unit_price: number }; models?: { name: string }[] }
const groups = ref<Channel[]>([]), available = ref<number[]>([]), pending = ref(true), error = ref('')
// Only site-configured groups are shown. Upstream group multipliers are our
// purchase cost and must not reach members.
onMounted(async () => {
  try {
    const [catalog, permissions] = await Promise.all([modelPlazaAPI.getModelPlaza(), userGroupsAPI.getAvailable()])
    pending.value = !catalog.groups.length
    groups.value = catalog.groups as Channel[]
    available.value = permissions.map(g => g.id)
  } catch { error.value = '暂时无法读取分组，请稍后重试。' }
})
</script>
<template>
  <div class="oc-info"><strong>按分组选择模型通道</strong><p>每把 API 密钥绑定一个分组，模型范围、价格和调用权限随分组确定。同名模型在不同分组中可能有不同费用。</p><p v-if="pending && !error">管理员尚未配置分组。</p></div>
  <p v-if="error" class="oc-error">{{ error }}</p>
  <div class="oc-provider-grid">
    <section v-for="g in groups" :key="g.id" class="oc-panel">
      <PlatformIcon :platform="g.platform" size="lg" />
      <h2>{{ g.name }}</h2>
      <p v-if="g.credit_billing?.enabled"><strong>Token 单价待公布</strong><br />本站按输入、输出和缓存 Token 分别计费，单位为 ¥ / 1M Tokens。</p>
      <p v-else><strong>{{ g.user_rate_multiplier ?? g.rate_multiplier }}×</strong> 分组倍率<br />具体模型单价、缓存和图片费用请查看价格表。</p>
      <p class="oc-hint">{{ g.models?.length || 0 }} 个目录型号 · {{ pending ? '待接入' : available.includes(g.id) ? '账户可用' : '暂无权限' }}</p>
      <details><summary>查看模型</summary><p style="overflow-wrap:anywhere">{{ g.models?.map(m => m.name).join('、') || '暂无模型目录' }}</p></details>
      <RouterLink v-if="!pending && available.includes(g.id)" class="oc-button" to="/keys">创建密钥</RouterLink>
      <RouterLink class="oc-text-link" to="/pricing">查看模型价格 →</RouterLink>
    </section>
  </div>
  <p class="oc-hint">分组名称沿用供应方标识。名称中的“满血”等描述不代表本站对模型真实性作出保证，可通过模型检测自行核验。</p>
</template>
