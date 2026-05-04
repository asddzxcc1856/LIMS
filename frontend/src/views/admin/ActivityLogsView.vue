<template>
  <div class="logs-page">
    <a-page-header :title="t('admin.logs.title')" :sub-title="t('admin.logs.subtitle')">
      <template #extra>
        <a-button @click="resetFilters">
          <template #icon><ClearOutlined /></template>
          {{ t('admin.logs.clearFilters') }}
        </a-button>
        <a-button type="primary" @click="loadData" :loading="loading">
          <template #icon><ReloadOutlined /></template>
          {{ t('admin.logs.applyRefresh') }}
        </a-button>
      </template>
    </a-page-header>

    <a-card :body-style="{ padding: '16px 16px 8px' }" class="filter-card">
      <a-form layout="inline" :model="filters">
        <a-form-item :label="t('admin.logs.filterUsername')">
          <a-input
            v-model:value="filters.username"
            placeholder="username"
            allow-clear
            style="width: 180px"
          />
        </a-form-item>
        <a-form-item :label="t('admin.logs.filterAction')">
          <a-select
            v-model:value="filters.action_type"
            :placeholder="t('common.filter')"
            allow-clear
            style="width: 140px"
            :options="actionOptions"
          />
        </a-form-item>
        <a-form-item :label="t('admin.logs.filterMethod')">
          <a-select
            v-model:value="filters.method"
            :placeholder="t('common.filter')"
            allow-clear
            style="width: 120px"
            :options="methodOptions"
          />
        </a-form-item>
        <a-form-item :label="t('admin.logs.filterStatus')">
          <a-input-number
            v-model:value="filters.status_code"
            placeholder="200, 404 …"
            :min="100"
            :max="599"
            style="width: 120px"
          />
        </a-form-item>
        <a-form-item :label="t('admin.logs.filterPath')">
          <a-input
            v-model:value="filters.path"
            placeholder="/api/admin"
            allow-clear
            style="width: 200px"
          />
        </a-form-item>
        <a-form-item :label="t('admin.logs.filterRange')">
          <a-range-picker
            v-model:value="dateRange"
            show-time
            format="YYYY-MM-DD HH:mm"
            style="width: 360px"
          />
        </a-form-item>
      </a-form>
    </a-card>

    <a-table
      :columns="columns"
      :data-source="rows"
      :loading="loading"
      :pagination="pagination"
      row-key="id"
      bordered
      size="middle"
      :scroll="{ x: 1300 }"
      @change="onTableChange"
    >
      <template #bodyCell="{ column, record }">
        <template v-if="column.dataIndex === 'timestamp'">
          {{ formatDate(record.timestamp) }}
        </template>
        <template v-else-if="column.dataIndex === 'username'">
          <a-tag v-if="record.username" :color="roleColor(record.user_role)">
            <UserOutlined />&nbsp;{{ record.username }}
          </a-tag>
          <span v-else class="muted">{{ t('admin.logs.anonymous') }}</span>
        </template>
        <template v-else-if="column.dataIndex === 'action_type'">
          <a-tag :color="actionColor(record.action_type)">
            {{ record.action_type_display }}
          </a-tag>
        </template>
        <template v-else-if="column.dataIndex === 'http_method'">
          <a-tag :color="methodColor(record.http_method)">{{ record.http_method }}</a-tag>
        </template>
        <template v-else-if="column.dataIndex === 'status_code'">
          <a-tag :color="statusCodeColor(record.status_code)">{{ record.status_code }}</a-tag>
        </template>
        <template v-else-if="column.dataIndex === 'duration_ms'">
          <span :style="{ color: durationColor(record.duration_ms) }">
            {{ record.duration_ms }} ms
          </span>
        </template>
        <template v-else-if="column.dataIndex === '__detail__'">
          <a-button type="link" size="small" @click="openDetail(record)">
            <template #icon><EyeOutlined /></template>
            {{ t('common.detail') }}
          </a-button>
        </template>
      </template>
    </a-table>

    <a-drawer
      v-model:open="detailOpen"
      :title="t('admin.logs.drawerTitle')"
      placement="right"
      width="640"
    >
      <template v-if="detail">
        <a-descriptions :column="1" bordered size="small">
          <a-descriptions-item label="ID">{{ detail.id }}</a-descriptions-item>
          <a-descriptions-item :label="t('admin.logs.colTime')">{{ formatDate(detail.timestamp) }}</a-descriptions-item>
          <a-descriptions-item :label="t('admin.logs.colUser')">
            {{ detail.username || t('admin.logs.anonymous') }}
            <a-tag v-if="detail.user_role" :color="roleColor(detail.user_role)" style="margin-left: 8px">
              {{ detail.user_role }}
            </a-tag>
          </a-descriptions-item>
          <a-descriptions-item :label="t('admin.logs.colAction')">
            <a-tag :color="actionColor(detail.action_type)">{{ detail.action_type_display }}</a-tag>
          </a-descriptions-item>
          <a-descriptions-item :label="t('admin.logs.colMethod')">
            <a-tag :color="methodColor(detail.http_method)">{{ detail.http_method }}</a-tag>
          </a-descriptions-item>
          <a-descriptions-item :label="t('admin.logs.colPath')">
            <code>{{ detail.path }}</code>
          </a-descriptions-item>
          <a-descriptions-item :label="t('admin.logs.colStatus')">
            <a-tag :color="statusCodeColor(detail.status_code)">{{ detail.status_code }}</a-tag>
          </a-descriptions-item>
          <a-descriptions-item :label="t('admin.logs.colDuration')">{{ detail.duration_ms }} ms</a-descriptions-item>
          <a-descriptions-item :label="t('admin.logs.colIp')">{{ detail.ip_address || '—' }}</a-descriptions-item>
          <a-descriptions-item label="User-Agent">
            <code style="font-size: 11px">{{ detail.user_agent || '—' }}</code>
          </a-descriptions-item>
        </a-descriptions>

        <a-divider>{{ t('admin.logs.requestBody') }}</a-divider>
        <a-typography-paragraph>
          <pre class="json-body">{{ formatJson(detail.request_data) }}</pre>
        </a-typography-paragraph>
      </template>
    </a-drawer>
  </div>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import dayjs from 'dayjs'

const { t } = useI18n()
import {
  ClearOutlined,
  EyeOutlined,
  ReloadOutlined,
  UserOutlined,
} from '@ant-design/icons-vue'
import { fetchActivityLogs } from '../../api/admin'

const filters = reactive({
  username: '',
  action_type: undefined,
  method: undefined,
  status_code: null,
  path: '',
})
const dateRange = ref(null)

const rows = ref([])
const loading = ref(false)
const detailOpen = ref(false)
const detail = ref(null)
let ordering = '-timestamp'

const pagination = reactive({
  current: 1,
  pageSize: 25,
  total: 0,
  showSizeChanger: true,
  pageSizeOptions: ['25', '50', '100', '200'],
  showTotal: (total) => t('crud.paginationTotal', { total }),
})

const actionOptions = computed(() => [
  { value: 'login', label: t('admin.actions.login') },
  { value: 'logout', label: t('admin.actions.logout') },
  { value: 'create', label: t('admin.actions.create') },
  { value: 'read', label: t('admin.actions.read') },
  { value: 'update', label: t('admin.actions.update') },
  { value: 'delete', label: t('admin.actions.delete') },
  { value: 'other', label: t('admin.actions.other') },
])

const methodOptions = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE'].map((m) => ({
  value: m,
  label: m,
}))

const columns = computed(() => [
  { title: t('admin.logs.colTime'), dataIndex: 'timestamp', width: 180, sorter: true },
  { title: t('admin.logs.colUser'), dataIndex: 'username', width: 180 },
  { title: t('admin.logs.colAction'), dataIndex: 'action_type', width: 100 },
  { title: t('admin.logs.colMethod'), dataIndex: 'http_method', width: 90 },
  { title: t('admin.logs.colPath'), dataIndex: 'path', ellipsis: true },
  { title: t('admin.logs.colStatus'), dataIndex: 'status_code', width: 90 },
  { title: t('admin.logs.colDuration'), dataIndex: 'duration_ms', width: 110, sorter: true },
  { title: t('admin.logs.colIp'), dataIndex: 'ip_address', width: 130 },
  { title: '', dataIndex: '__detail__', width: 90, fixed: 'right' },
])

watch(
  () => [filters.username, filters.action_type, filters.method, filters.status_code, filters.path, dateRange.value],
  () => {
    pagination.current = 1
  },
  { deep: true },
)

async function loadData() {
  loading.value = true
  try {
    const params = {
      page: pagination.current,
      page_size: pagination.pageSize,
      ordering,
    }
    if (filters.username) params.username = filters.username
    if (filters.action_type) params.action_type = filters.action_type
    if (filters.method) params.method = filters.method
    if (filters.status_code) params.status_code = filters.status_code
    if (filters.path) params.path = filters.path
    if (dateRange.value && dateRange.value.length === 2) {
      params.since = dateRange.value[0].toISOString()
      params.until = dateRange.value[1].toISOString()
    }
    const { data } = await fetchActivityLogs(params)
    rows.value = data.results || []
    pagination.total = data.count || 0
  } finally {
    loading.value = false
  }
}

function onTableChange(pag, _filters, sorter) {
  pagination.current = pag.current
  pagination.pageSize = pag.pageSize
  if (sorter && sorter.field) {
    const dir = sorter.order === 'descend' ? '-' : ''
    ordering = sorter.order ? `${dir}${sorter.field}` : '-timestamp'
  }
  loadData()
}

function resetFilters() {
  filters.username = ''
  filters.action_type = undefined
  filters.method = undefined
  filters.status_code = null
  filters.path = ''
  dateRange.value = null
  pagination.current = 1
  loadData()
}

function openDetail(record) {
  detail.value = record
  detailOpen.value = true
}

function formatDate(value) {
  return value ? dayjs(value).format('YYYY-MM-DD HH:mm:ss') : '—'
}

function formatJson(value) {
  if (value == null) return t('admin.logs.empty')
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value)
  }
}

function actionColor(key) {
  return {
    login: 'cyan', logout: 'default', create: 'green',
    read: 'blue', update: 'orange', delete: 'red', other: 'default',
  }[key] || 'default'
}

function methodColor(method) {
  return {
    GET: 'blue', POST: 'green', PUT: 'orange', PATCH: 'orange', DELETE: 'red',
  }[method] || 'default'
}

function statusCodeColor(code) {
  if (code < 300) return 'success'
  if (code < 400) return 'processing'
  if (code < 500) return 'warning'
  return 'error'
}

function roleColor(role) {
  return {
    superuser: 'red',
    lab_manager: 'geekblue',
    lab_member: 'cyan',
    regular_employee: 'default',
  }[role] || 'default'
}

function durationColor(ms) {
  if (ms > 1000) return '#cf1322'
  if (ms > 300) return '#fa8c16'
  return '#3f8600'
}

loadData()
</script>

<style scoped>
.logs-page {
  padding: 0;
}
.filter-card {
  margin-bottom: 16px;
}
.muted {
  color: var(--c-text-muted);
  font-style: italic;
}
.json-body {
  background: var(--c-row-bg);
  color: var(--c-text);
  padding: 12px;
  border-radius: 4px;
  font-size: 12px;
  max-height: 400px;
  overflow: auto;
}
</style>
