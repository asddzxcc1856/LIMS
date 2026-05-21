// @vitest-environment jsdom
/**
 * Component tests for SampleSplitDialog (分貨對話框).
 *
 * The dialog's contract:
 *   - Opening triggers a fetch of existing samples
 *   - addRow / removeRow mutate the local splits array
 *   - confirm() filters blank sub_codes, calls splitOrderSamples with the
 *     cleaned payload, and emits 'split-saved' on success.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { nextTick } from 'vue'
import { createI18n } from 'vue-i18n'

vi.mock('../src/api/orders', () => ({
  fetchOrderSamples: vi.fn(),
  splitOrderSamples: vi.fn(),
}))
vi.mock('ant-design-vue', () => ({
  message: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}))

import { fetchOrderSamples, splitOrderSamples } from '../src/api/orders'
import { message } from 'ant-design-vue'
import SampleSplitDialog from '../src/components/SampleSplitDialog.vue'
import zhTW from '../src/i18n/zh-TW'

function makeI18n() {
  return createI18n({
    legacy: false,
    locale: 'zh-TW',
    fallbackLocale: 'zh-TW',
    messages: { 'zh-TW': zhTW },
  })
}

const STUBS = [
  'a-modal', 'a-alert', 'a-table', 'a-spin', 'a-divider', 'a-form',
  'a-input', 'a-input-number', 'a-button',
  'MinusCircleOutlined', 'PlusOutlined',
]

async function mountDialog(props = {}) {
  const wrapper = mount(SampleSplitDialog, {
    props: {
      open: false,
      order: { id: 'order-1', order_no: 'LAB-20260518-0001' },
      ...props,
    },
    global: { plugins: [makeI18n()], stubs: STUBS },
  })
  await flushPromises()
  return wrapper
}

describe('SampleSplitDialog', () => {
  beforeEach(() => {
    fetchOrderSamples.mockResolvedValue({
      data: [
        { id: 's1', sub_code: 'A', full_code: 'LOT-001-A', wafer_count: 3, notes: '' },
      ],
    })
    splitOrderSamples.mockResolvedValue({
      data: [
        { id: 's2', sub_code: 'B', full_code: 'LOT-001-B', wafer_count: 2, notes: '' },
      ],
    })
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('loads existing samples when opened', async () => {
    const wrapper = await mountDialog()
    // Act — flip open to true so the watcher fires
    await wrapper.setProps({ open: true })
    await flushPromises()
    // Assert
    expect(fetchOrderSamples).toHaveBeenCalledWith('order-1')
    expect(wrapper.vm.existingSamples).toHaveLength(1)
    expect(wrapper.vm.existingSamples[0].sub_code).toBe('A')
  })

  it('starts with a single empty row + addRow/removeRow mutate the list', async () => {
    const wrapper = await mountDialog()
    await wrapper.setProps({ open: true })
    await flushPromises()

    expect(wrapper.vm.splits).toHaveLength(1)
    wrapper.vm.addRow()
    await nextTick()
    expect(wrapper.vm.splits).toHaveLength(2)

    wrapper.vm.removeRow(0)
    await nextTick()
    expect(wrapper.vm.splits).toHaveLength(1)
  })

  it('removeRow refuses to drop the last row', async () => {
    const wrapper = await mountDialog()
    await wrapper.setProps({ open: true })
    await flushPromises()
    // The dialog enforces at least one row remains
    wrapper.vm.removeRow(0)
    await nextTick()
    expect(wrapper.vm.splits).toHaveLength(1)
  })

  it('confirm() warns when every row is blank', async () => {
    const wrapper = await mountDialog()
    await wrapper.setProps({ open: true })
    await flushPromises()
    // Act — blank sub_code on the only row
    wrapper.vm.splits[0].sub_code = '   '
    await wrapper.vm.confirm()
    // Assert
    expect(message.warning).toHaveBeenCalled()
    expect(splitOrderSamples).not.toHaveBeenCalled()
  })

  it('confirm() sends cleaned rows and emits split-saved', async () => {
    const wrapper = await mountDialog()
    await wrapper.setProps({ open: true })
    await flushPromises()

    // Beforeach seeds 1 existing sample at 3 wafers; new splits must
    // sum to 22 so the grand total lands on the 25-wafer cap. Blank
    // rows are still filtered.
    wrapper.vm.splits = [
      { sub_code: ' A ', wafer_count: 12, notes: 'lead' },
      { sub_code: '', wafer_count: 1, notes: 'blank-row-should-be-filtered' },
      { sub_code: 'B', wafer_count: '10', notes: '' },
    ]
    // Act
    await wrapper.vm.confirm()
    await flushPromises()
    // Assert — second row dropped, sub_code trimmed, numerics coerced
    expect(splitOrderSamples).toHaveBeenCalledWith('order-1', {
      splits: [
        { sub_code: 'A', wafer_count: 12, notes: 'lead' },
        { sub_code: 'B', wafer_count: 10, notes: '' },
      ],
    })
    expect(wrapper.emitted('split-saved')).toBeTruthy()
    // Drawer closes on success
    expect(wrapper.emitted('update:open')?.at(-1)).toEqual([false])
  })

  it('confirm() surfaces backend error message', async () => {
    splitOrderSamples.mockRejectedValueOnce({
      response: { data: { detail: 'sub_code already used on this order' } },
    })
    const wrapper = await mountDialog()
    await wrapper.setProps({ open: true })
    await flushPromises()
    // Beforeach seeds 1 existing sample at 3 wafers; this row plus
    // existing must add up to 25 so the cap gate lets the call through
    // and the backend's "sub_code already used" error can surface.
    wrapper.vm.splits = [{ sub_code: 'A', wafer_count: 22, notes: '' }]
    // Act
    await wrapper.vm.confirm()
    await flushPromises()
    // Assert
    expect(message.error).toHaveBeenCalledWith('sub_code already used on this order')
  })
})
