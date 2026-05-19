/**
 * useBreakpoint — reactive viewport breakpoints driven by matchMedia.
 *
 * Returns refs that components can branch on. Ant Design Vue ships its
 * own Grid.useBreakpoint, but it only tracks the antd breakpoints that
 * the design-system enums — we also need a simple `isMobile` /
 * `isTablet` boolean for header collapse, drawer width, etc., so this
 * is the smallest shared primitive.
 *
 * Breakpoint thresholds match the antd defaults (xs <576, sm <768,
 * md <992, lg <1200, xl <1600) so any media query in scoped CSS stays
 * in lockstep.
 */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

export function useBreakpoint() {
  const width = ref(typeof window !== 'undefined' ? window.innerWidth : 1200)
  let mediaList = []

  const onResize = () => {
    if (typeof window !== 'undefined') width.value = window.innerWidth
  }

  onMounted(() => {
    if (typeof window === 'undefined') return
    window.addEventListener('resize', onResize)
    // matchMedia listeners give us a cheap event on actual breakpoint
    // crossings; resize alone is still hooked because some browsers
    // delay media events on programmatic resizes. Guard against test
    // environments (jsdom) where matchMedia is stubbed or returns
    // undefined for some queries.
    if (typeof window.matchMedia !== 'function') return
    const queries = ['(max-width: 575.9px)', '(max-width: 767.9px)', '(max-width: 991.9px)']
    mediaList = queries
      .map((q) => window.matchMedia(q))
      .filter(Boolean)
    mediaList.forEach((m) => m.addEventListener?.('change', onResize))
  })

  onBeforeUnmount(() => {
    if (typeof window === 'undefined') return
    window.removeEventListener('resize', onResize)
    mediaList.forEach((m) => m?.removeEventListener?.('change', onResize))
  })

  const isMobile = computed(() => width.value < 768)
  const isTablet = computed(() => width.value >= 768 && width.value < 1200)
  const isDesktop = computed(() => width.value >= 1200)

  return {
    width,
    isMobile,
    isTablet,
    isDesktop,
  }
}
