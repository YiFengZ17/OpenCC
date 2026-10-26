<script setup lang="ts">
withDefaults(defineProps<{ name: string; size?: number }>(), { size: 20 })
const icons: Record<string, string> = {
  grid: 'M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z',
  models: 'm12 3 9 5-9 5-9-5 9-5z M3 12l9 5 9-5 M3 16l9 5 9-5',
  key: 'M14 4a6 6 0 1 1-4 10L3 21H1v-4l7-7a6 6 0 0 1 6-6z M16 8h.01',
  chart: 'M4 3v18h17 M9 15v-4 M14 15V7 M19 15v-6',
  wallet: 'M3 7h17v14H3z M3 7V4h14v3 M15 12h6v5h-6z',
  order: 'M6 3h12v18l-3-2-3 2-3-2-3 2V3z M9 8h6 M9 12h6',
  bell: 'M18 8a6 6 0 0 0-12 0v7l-2 3h16l-2-3V8 M9 21h6',
  book: 'M3 4h7l2 2 2-2h7v16h-7l-2 1-2-1H3V4 M12 6v15',
  arrow: 'M5 12h14 M13 6l6 6-6 6',
  copy: 'M9 9h11v12H9z M5 15H3V3h12v2',
  plus: 'M12 5v14 M5 12h14',
  search: 'M21 21l-5-5 M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0',
  chevron: 'm9 5 7 7-7 7',
  refresh: 'M20 7V2l-4 4a8 8 0 1 0 3 11 M20 7h-5',
  logout: 'M9 4H3v16h6 M9 12h12 M17 8l4 4-4 4',
  menu: 'M4 6h16 M4 12h16 M4 18h16',
  close: 'm6 6 12 12 M6 18 18 6',
  check: 'm5 12 4 4L19 6',
  code: 'm8 7-5 5 5 5 M16 7l5 5-5 5 M14 4l-4 16',
  external: 'M14 3h7v7 M21 3 10 14 M10 4H3v17h17v-7',
  user: 'M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8 M4 21v-2a8 8 0 0 1 16 0v2',
  shield: 'm12 2 9 4v6c0 5-9 10-9 10S3 17 3 12V6l9-4z m-4 10 3 3 5-6',
  sun: 'M12 16a4 4 0 1 0 0-8 4 4 0 0 0 0 8z M12 2v2 M12 20v2 M4.9 4.9l1.4 1.4 M17.7 17.7l1.4 1.4 M2 12h2 M20 12h2 M4.9 19.1l1.4-1.4 M17.7 6.3l1.4-1.4',
  moon: 'M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z'
}
</script>
<template>
  <svg
    :width="size"
    :height="size"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="1.65"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
  >
    <path :d="icons[name] || icons.grid" />
  </svg>
</template>
