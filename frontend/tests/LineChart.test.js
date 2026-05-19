// @vitest-environment jsdom
/**
 * Component tests for the lightweight SVG LineChart.
 *
 * No backend mocks — we drive it purely with props and inspect the rendered
 * polyline / circle points to confirm the maths.
 */
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import LineChart from '../src/components/charts/LineChart.vue'

describe('LineChart', () => {
  it('renders empty SVG when no data is supplied', () => {
    const wrapper = mount(LineChart, {
      props: { data: [], series: [{ name: 'A', key: 'v' }] },
    })
    expect(wrapper.find('svg').exists()).toBe(true)
    expect(wrapper.findAll('polyline')).toHaveLength(1)  // empty polyline string
  })

  it('plots one polyline per series with N points each', () => {
    const data = [
      { date: 'd1', a: 10, b: 1 },
      { date: 'd2', a: 20, b: 2 },
      { date: 'd3', a: 30, b: 3 },
    ]
    const wrapper = mount(LineChart, {
      props: {
        data,
        series: [
          { name: 'A', key: 'a' },
          { name: 'B', key: 'b' },
        ],
      },
    })
    const polylines = wrapper.findAll('polyline')
    expect(polylines).toHaveLength(2)
    // Each polyline should have N space-separated points
    expect(polylines[0].attributes('points').split(/\s+/)).toHaveLength(data.length)
    // Circles render one per data point per series
    expect(wrapper.findAll('circle')).toHaveLength(data.length * 2)
  })

  it('renders a legend when multiple series are supplied', () => {
    const wrapper = mount(LineChart, {
      props: {
        data: [{ date: 'd', a: 1, b: 1 }],
        series: [
          { name: 'A', key: 'a' },
          { name: 'B', key: 'b' },
        ],
      },
    })
    const items = wrapper.findAll('.legend-item')
    expect(items).toHaveLength(2)
  })

  it('respects an explicit yMax for percentage scales', () => {
    // A point at value=50 with yMax=100 should land at the vertical midpoint
    // of the chart's plot area (within rounding of the SVG height).
    const wrapper = mount(LineChart, {
      props: {
        data: [{ date: 'd', v: 50 }],
        series: [{ name: 'V', key: 'v' }],
        yMax: 100,
        height: 240,
      },
    })
    const cy = parseFloat(wrapper.find('circle').attributes('cy'))
    // Midpoint of usable plotting area (padding-top=12, padding-bottom=28).
    expect(cy).toBeGreaterThan(110)
    expect(cy).toBeLessThan(130)
  })
})
