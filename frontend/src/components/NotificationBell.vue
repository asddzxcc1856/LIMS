<template>
  <span class="notify-bell">
    <a-badge :count="unreadCount" :overflow-count="99" :offset="[-4, 4]">
      <a-button type="text" @click="open">
        <template #icon><BellOutlined /></template>
      </a-button>
    </a-badge>

    <a-drawer
      v-model:open="drawerOpen"
      :title="t('notifications.title')"
      placement="right"
      :width="drawerWidth"
      destroy-on-close
    >
      <template #extra>
        <a-button
          size="small"
          :disabled="!unreadCount"
          @click="markAllRead"
        >
          <template #icon><CheckOutlined /></template>
          {{ t('notifications.markAllRead') }}
        </a-button>
      </template>

      <a-spin :spinning="loading">
        <a-empty
          v-if="!loading && rows.length === 0"
          :description="t('notifications.empty')"
        />
        <a-list v-else :data-source="rows" item-layout="vertical" size="small">
          <template #renderItem="{ item }">
            <a-list-item
              :class="['notify-item', { 'is-unread': !item.is_read }]"
              @click="markRead(item)"
            >
              <a-list-item-meta>
                <template #title>
                  <span class="notify-title">
                    <a-tag :color="levelColor(item.level)" class="lvl-tag">
                      {{ item.level_display }}
                    </a-tag>
                    {{ item.title }}
                  </span>
                </template>
                <template #description>
                  <div class="notify-meta">
                    <span>{{ kindLabel(item.kind) }}</span>
                    <span class="muted">·</span>
                    <span class="muted">{{ formatTime(item.created_at) }}</span>
                  </div>
                  <div v-if="item.body" class="notify-body">{{ item.body }}</div>
                </template>
              </a-list-item-meta>
            </a-list-item>
          </template>
        </a-list>
      </a-spin>
    </a-drawer>
  </span>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { BellOutlined, CheckOutlined } from '@ant-design/icons-vue'
import dayjs from 'dayjs'
import {
  fetchNotifications,
  fetchNotificationSummary,
  markAllNotificationsRead,
  markNotificationRead,
} from '../api/admin'
import { useBreakpoint } from '../composables/useBreakpoint'

const { isMobile } = useBreakpoint()
const drawerWidth = computed(() => (isMobile.value ? '95vw' : 420))

const { t } = useI18n()

const drawerOpen = ref(false)
const loading = ref(false)
const rows = ref([])
const unreadCount = ref(0)
let pollTimer = null

const POLL_INTERVAL_MS = 60_000  // header badge poll cadence

async function refreshSummary() {
  try {
    const { data } = await fetchNotificationSummary()
    unreadCount.value = data.unread || 0
  } catch {
    /* unauthenticated or backend hiccup — silently skip the tick */
  }
}

async function loadRows() {
  loading.value = true
  try {
    const { data } = await fetchNotifications({ page_size: 50 })
    rows.value = data.results || data || []
  } finally {
    loading.value = false
  }
}

function open() {
  drawerOpen.value = true
  loadRows()
}

async function markRead(row) {
  if (row.is_read) return
  try {
    await markNotificationRead(row.id)
    row.is_read = true
    if (unreadCount.value > 0) unreadCount.value -= 1
  } catch {
    /* swallow — list still works */
  }
}

async function markAllRead() {
  await markAllNotificationsRead()
  rows.value = rows.value.map((r) => ({ ...r, is_read: true }))
  unreadCount.value = 0
}

function levelColor(level) {
  return {
    info: 'blue',
    warning: 'orange',
    critical: 'red',
  }[level] || 'default'
}

function kindLabel(kind) {
  return t(`notifications.kind.${kind}`, kind)
}

function formatTime(value) {
  if (!value) return '—'
  return dayjs(value).format('YYYY-MM-DD HH:mm')
}

onMounted(() => {
  refreshSummary()
  pollTimer = setInterval(refreshSummary, POLL_INTERVAL_MS)
})

onBeforeUnmount(() => {
  if (pollTimer) clearInterval(pollTimer)
})
</script>

<style scoped>
.notify-bell {
  display: inline-flex;
  align-items: center;
}
.notify-item {
  cursor: pointer;
  padding: 10px 12px;
  border-radius: 4px;
  transition: background 0.15s ease;
}
.notify-item:hover {
  background: rgba(24, 144, 255, 0.06);
}
.notify-item.is-unread {
  background: rgba(24, 144, 255, 0.08);
}
.notify-title {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-weight: 500;
}
.lvl-tag {
  font-size: 11px;
}
.notify-meta {
  font-size: 12px;
  color: var(--c-text-muted);
  display: flex;
  gap: 6px;
  align-items: center;
}
.notify-body {
  margin-top: 4px;
  font-size: 13px;
  white-space: pre-wrap;
  color: var(--c-text);
}
.muted {
  color: var(--c-text-muted);
}
</style>
