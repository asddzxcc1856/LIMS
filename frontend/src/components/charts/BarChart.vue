<template>
  <div class="bar-chart">
    <svg
      :viewBox="`0 0 ${width} ${height}`"
      preserveAspectRatio="none"
      role="img"
      :aria-label="ariaLabel"
    >
      <g class="grid">
        <line
          v-for="(y, i) in gridLines"
          :key="i"
          :x1="padding.left"
          :x2="width - padding.right"
          :y1="y"
          :y2="y"
        />
      </g>
      <g class="y-labels">
        <text
          v-for="(label, i) in yLabels"
          :key="i"
          :x="padding.left - 6"
          :y="label.y"
          text-anchor="end"
          dominant-baseline="middle"
        >{{ label.text }}</text>
      </g>

      <g>
        <rect
          v-for="(bar, i) in bars"
          :key="i"
          :x="bar.x"
          :y="bar.y"
          :width="bar.width"
          :height="bar.height"
          :fill="bar.color"
          rx="3"
        >
          <title>{{ bar.label }}: {{ bar.value }}</title>
        </rect>
        <text
          v-for="(bar, i) in bars"
          :key="`v-${i}`"
          :x="bar.x + bar.width / 2"
          :y="bar.y - 4"
          text-anchor="middle"
          class="bar-value"
        >{{ bar.value }}</text>
      </g>

      <g class="x-labels">
        <text
          v-for="(bar, i) in bars"
          :key="`l-${i}`"
          :x="bar.x + bar.width / 2"
          :y="height - 6"
          text-anchor="middle"
        >{{ bar.label }}</text>
      </g>
    </svg>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  /** Rows like ``{ label, value }`` already sorted in display order. */
  data: { type: Array, default: () => [] },
  width: { type: Number, default: 600 },
  height: { type: Number, default: 240 },
  /** Optional palette override; defaults to a 5-tone Ant-design palette. */
  colors: {
    type: Array,
    default: () => ['#1890ff', '#13c2c2', '#52c41a', '#fa8c16', '#722ed1'],
  },
  ariaLabel: { type: String, default: 'Bar chart' },
})

const padding = { top: 16, right: 12, bottom: 28, left: 44 }

const maxValue = computed(() => {
  const m = props.data.reduce((acc, r) => Math.max(acc, Number(r.value) || 0), 0)
  return m || 1
})

const bars = computed(() => {
  if (!props.data.length) return []
  const usableW = props.width - padding.left - padding.right
  const usableH = props.height - padding.top - padding.bottom
  const slot = usableW / props.data.length
  const barWidth = Math.max(8, slot * 0.6)
  return props.data.map((row, i) => {
    const v = Number(row.value) || 0
    const h = usableH * (v / maxValue.value)
    return {
      x: padding.left + slot * i + (slot - barWidth) / 2,
      y: padding.top + (usableH - h),
      width: barWidth,
      height: h,
      label: row.label,
      value: row.value,
      color: row.color || props.colors[i % props.colors.length],
    }
  })
})

const gridLines = computed(() => {
  const ticks = 4
  const usable = props.height - padding.top - padding.bottom
  return Array.from({ length: ticks + 1 }, (_, i) =>
    padding.top + (usable * i) / ticks,
  )
})

const yLabels = computed(() => {
  const ticks = 4
  return Array.from({ length: ticks + 1 }, (_, i) => {
    const fraction = 1 - i / ticks
    const value = Math.round(fraction * maxValue.value)
    return { y: gridLines.value[i], text: String(value) }
  })
})
</script>

<style scoped>
.bar-chart svg {
  width: 100%;
  height: auto;
  display: block;
}
.grid line {
  stroke: rgba(120, 120, 120, 0.18);
}
.y-labels text,
.x-labels text {
  font-size: 11px;
  fill: var(--c-text-muted, #8c8c8c);
}
.bar-value {
  font-size: 11px;
  fill: var(--c-text-muted, #595959);
}
</style>
