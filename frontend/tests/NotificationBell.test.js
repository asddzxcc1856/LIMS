// @vitest-environment jsdom
/**
 * Component tests for NotificationBell.
 *
 * Verifies the small state machine around the bell badge + drawer:
 *   - onMounted polls summary and surfaces the unread count
 *   - open() lazy-loads the rows list
 *   - markRead() flips one row, decrements the badge
 *   - markAllRead() zeroes the badge and flips every cached row
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'

vi.mock('../src/api/admin', () => ({
  fetchNotifications: vi.fn(),
  fetchNotificationSummary: vi.fn(),
  markNotificationRead: vi.fn(),
  markAllNotificationsRead: vi.fn(),
}))
vi.mock('ant-design-vue', () => ({
  message: { success: vi.fn(), error: vi.fn() },
}))

import {
  fetchNotifications,
  fetchNotificationSummary,
  markAllNotificationsRead,
  markNotificationRead,
} from '../src/api/admin'
import NotificationBell from '../src/components/NotificationBell.vue'
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
  'a-badge', 'a-button', 'a-drawer', 'a-empty', 'a-list', 'a-list-item',
  'a-list-item-meta', 'a-tag', 'a-spin',
  'BellOutlined', 'CheckOutlined',
]

async function mountBell() {
  const wrapper = mount(NotificationBell, {
    global: { plugins: [makeI18n()], stubs: STUBS },
  })
  await flushPromises()
  return wrapper
}

describe('NotificationBell', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    fetchNotificationSummary.mockResolvedValue({ data: { unread: 3, critical_unread: 1 } })
    fetchNotifications.mockResolvedValue({
      data: {
        results: [
          { id: 'a', title: 'sample received', body: '', level: 'info',
            level_display: 'Info', kind: 'order_received', is_read: false,
            created_at: '2026-05-18T12:00:00Z' },
          { id: 'b', title: 'eq down', body: 'EQ-001 in maintenance',
            level: 'critical', level_display: 'Critical', kind: 'equipment_alert',
            is_read: true, created_at: '2026-05-18T11:00:00Z' },
        ],
      },
    })
    markNotificationRead.mockResolvedValue({ data: {} })
    markAllNotificationsRead.mockResolvedValue({ data: { updated: 3 } })
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.clearAllMocks()
  })

  it('loads the unread summary on mount', async () => {
    const wrapper = await mountBell()
    expect(fetchNotificationSummary).toHaveBeenCalledTimes(1)
    expect(wrapper.vm.unreadCount).toBe(3)
  })

  it('open() lazy-loads the rows list', async () => {
    const wrapper = await mountBell()
    fetchNotifications.mockClear()
    // Act
    wrapper.vm.open()
    await flushPromises()
    // Assert
    expect(fetchNotifications).toHaveBeenCalledTimes(1)
    expect(wrapper.vm.drawerOpen).toBe(true)
    expect(wrapper.vm.rows).toHaveLength(2)
  })

  it('markRead() flips the row and decrements the badge', async () => {
    const wrapper = await mountBell()
    wrapper.vm.open()
    await flushPromises()
    expect(wrapper.vm.unreadCount).toBe(3)
    // Act — the first row in the cached list is the unread one
    const unread = wrapper.vm.rows[0]
    expect(unread.is_read).toBe(false)
    await wrapper.vm.markRead(unread)
    // Assert
    expect(markNotificationRead).toHaveBeenCalledWith('a')
    expect(unread.is_read).toBe(true)
    expect(wrapper.vm.unreadCount).toBe(2)
  })

  it('markRead() is a no-op on already-read rows', async () => {
    const wrapper = await mountBell()
    wrapper.vm.open()
    await flushPromises()
    // Act
    await wrapper.vm.markRead(wrapper.vm.rows[1])  // already read
    // Assert
    expect(markNotificationRead).not.toHaveBeenCalled()
  })

  it('markAllRead() flips every cached row + zeroes the badge', async () => {
    const wrapper = await mountBell()
    wrapper.vm.open()
    await flushPromises()
    // Act
    await wrapper.vm.markAllRead()
    // Assert
    expect(markAllNotificationsRead).toHaveBeenCalledTimes(1)
    expect(wrapper.vm.unreadCount).toBe(0)
    expect(wrapper.vm.rows.every((r) => r.is_read)).toBe(true)
  })

  it('levelColor returns red for critical alerts', async () => {
    const wrapper = await mountBell()
    expect(wrapper.vm.levelColor('critical')).toBe('red')
    expect(wrapper.vm.levelColor('warning')).toBe('orange')
    expect(wrapper.vm.levelColor('info')).toBe('blue')
  })
})
