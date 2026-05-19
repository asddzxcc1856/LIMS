<template>
  <div class="line-chart">
    <svg
      :viewBox="`0 0 ${width} ${height}`"
      preserveAspectRatio="none"
      role="img"
      :aria-label="ariaLabel"
    >
      <!-- Y-axis gridlines -->
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

      <!-- Y-axis labels -->
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

      <!-- Each series -->
      <g
        v-for="(s, idx) in normalizedSeries"
        :key="s.name || idx"
        :class="['series', `series-${idx}`]"
      >
        <polyline
          :points="s.linePoints"
          fill="none"
          :stroke="s.color"
          stroke-width="2"
          vector-effect="non-scaling-stroke"
        />
        <circle
          v-for="(pt, j) in s.points"
          :key="j"
          :cx="pt.x"
          :cy="pt.y"
          r="3"
          :fill="s.color"
        >
          <title>{{ s.name }} — {{ data[j]?.[xKey] }}: {{ pt.value }}</title>
        </circle>
      </g>

      <!-- X-axis labels -->
      <g class="x-labels">
        <text
          v-for="(point, i) in xLabels"
          :key="i"
          :x="point.x"
          :y="height - 8"
          text-anchor="middle"
        >{{ point.text }}</text>
      </g>
    </svg>

    <div v-if="series.length > 1" class="legend">
      <span
        v-for="(s, idx) in normalizedSeries"
        :key="s.name || idx"
        class="legend-item"
      >
        <span class="legend-dot" :style="{ background: s.color }"></span>
        {{ s.name }}
      </span>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const DEFAULT_COLORS = ['#1890ff', '#52c41a', '#fa8c16', '#f5222d', '#722ed1']

const props = defineProps({
  /** Rows shaped like ``{ <xKey>: '2026-05-10', <field>: 42, … }``. */
  data: { type: Array, default: () => [] },
  /** Field on each row used for x-axis labels (defaults to ``date``). */
  xKey: { type: String, default: 'date' },
  /** Series definitions: ``{ name, key, color }``. ``key`` is the row field. */
  series: { type: Array, required: true },
  width: { type: Number, default: 600 },
  height: { type: Number, default: 240 },
  /** Pin the Y-axis upper bound (e.g. 100 for percentages). */
  yMax: { type: Number, default: null },
  /** Format Y-axis labels — e.g. ``v => `${v}%```. */
  yFormat: { type: Function, default: (v) => String(v) },
  ariaLabel: { type: String, default: 'Trend chart' },
})

const padding = { top: 12, right: 16, bottom: 28, left: 44 }

const xCoord = (i) => {
  const usable = props.width - padding.left - padding.right
  if (props.data.length <= 1) return padding.left + usable / 2
  return padding.left + (usable * i) / (props.data.length - 1)
}

const maxY = computed(() => {
  if (props.yMax != null) return props.yMax
  let m = 0
  for (const row of props.data) {
    for (const s of props.series) {
      const v = Number(row[s.key]) || 0
      if (v > m) m = v
    }
  }
  return m || 1
})

const yCoord = (v) => {
  const usable = props.height - padding.top - padding.bottom
  const safe = Math.max(0, Math.min(v, maxY.value))
  return padding.top + usable * (1 - safe / maxY.value)
}

const normalizedSeries = computed(() =>
  props.series.map((s, idx) => {
    const color = s.color || DEFAULT_COLORS[idx % DEFAULT_COLORS.length]
    const points = props.data.map((row, i) => ({
      x: xCoord(i),
      y: yCoord(Number(row[s.key]) || 0),
      value: row[s.key],
    }))
    return {
      ...s,
      color,
      points,
      linePoints: points.map((p) => `${p.x},${p.y}`).join(' '),
    }
  }),
)

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
    const value = Math.round(fraction * maxY.value * 100) / 100
    return { y: gridLines.value[i], text: props.yFormat(value) }
  })
})

const xLabels = computed(() => {
  if (props.data.length <= 6) {
    return props.data.map((row, i) => ({ x: xCoord(i), text: row[props.xKey] }))
  }
  // Down-sample so the axis stays legible — 6 labels max
  const step = Math.ceil(props.data.length / 6)
  return props.data
    .map((row, i) => ({ x: xCoord(i), text: row[props.xKey], i }))
    .filter((p) => p.i % step === 0)
})
</script>

<style scoped>
.line-chart {
  width: 100%;
}
.line-chart svg {
  width: 100%;
  height: auto;
  display: block;
}
.grid line {
  stroke: rgba(120, 120, 120, 0.18);
  stroke-width: 1;
}
.y-labels text,
.x-labels text {
  font-size: 11px;
  fill: var(--c-text-muted, #8c8c8c);
}
.legend {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  margin-top: 8px;
  font-size: 12px;
  color: var(--c-text-muted, #8c8c8c);
}
.legend-dot {
  display: inline-block;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  margin-right: 6px;
  vertical-align: middle;
}
</style>
