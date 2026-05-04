<template>
  <CrudTable
    :resource="adminOrders"
    :resource-label="t('admin.pages.orders.label')"
    :title="t('admin.pages.orders.title')"
    :subtitle="t('admin.pages.orders.subtitle')"
    :search-placeholder="t('admin.pages.orders.search')"
    default-ordering="-created_at"
    :columns="columns"
    :form-fields="formFields"
  />
</template>

<script setup>
import { computed, h } from 'vue'
import { useI18n } from 'vue-i18n'
import { Tag } from 'ant-design-vue'
import CrudTable from '../../components/admin/CrudTable.vue'
import {
  adminDepartments,
  adminExperiments,
  adminOrders,
  adminUsers,
} from '../../api/admin'

const { t } = useI18n()

const statusOptions = computed(() => [
  { value: 'created', label: t('orders.statusLabels.created') },
  { value: 'waiting', label: t('orders.statusLabels.waiting') },
  { value: 'in_progress', label: t('orders.statusLabels.in_progress') },
  { value: 'done', label: t('orders.statusLabels.done') },
  { value: 'rejected', label: t('orders.statusLabels.rejected') },
])
const statusColor = {
  created: 'default', waiting: 'warning',
  in_progress: 'processing', done: 'success', rejected: 'error',
}

const columns = computed(() => [
  { title: t('orders.orderNo'), dataIndex: 'order_no', width: 200, fixed: 'left' },
  { title: t('orders.experiment'), dataIndex: 'experiment_name', width: 180 },
  { title: t('review.requester'), dataIndex: 'requester_username', width: 140 },
  { title: t('admin.nav.departments'), dataIndex: 'department_name', width: 140 },
  { title: t('orders.lotId'), dataIndex: 'lot_id', width: 120 },
  { title: t('orders.status'), dataIndex: 'status', width: 120, sorter: true,
    customRender: ({ value }) =>
      h(Tag, { color: statusColor[value] || 'default' }, () =>
        statusOptions.value.find((o) => o.value === value)?.label || value,
      ),
  },
  { title: t('orders.urgent'), dataIndex: 'is_urgent', width: 80, sorter: true,
    customRender: ({ value }) =>
      h(Tag, { color: value ? 'red' : 'default' }, () =>
        value ? t('orders.urgent') : t('orders.normal'),
      ),
  },
  { title: t('review.assignee'), dataIndex: 'assignee_username', width: 140,
    customRender: ({ value }) => value || '—' },
  { title: t('orders.createdAt'), dataIndex: 'created_at', width: 170, sorter: true,
    customRender: ({ value }) => value ? value.replace('T', ' ').slice(0, 19) : '—',
  },
  { title: t('admin.nav.orderStages'), dataIndex: 'stage_count', width: 90 },
])

const formFields = computed(() => [
  { name: 'department', label: t('admin.nav.departments'), type: 'select', required: true,
    optionsResource: adminDepartments, optionLabel: 'name', span: 12 },
  { name: 'experiment', label: t('orders.experiment'), type: 'select', required: true,
    optionsResource: adminExperiments, optionLabel: 'name', span: 12 },
  { name: 'user', label: t('review.requester'), type: 'select', required: true,
    optionsResource: adminUsers, optionLabel: 'username', span: 12 },
  { name: 'assignee', label: t('review.assignee'), type: 'select',
    optionsResource: adminUsers, optionLabel: 'username',
    nullableEmpty: true, span: 12 },
  { name: 'lot_id', label: t('orders.lotId'), type: 'text', span: 12 },
  { name: 'status', label: t('orders.status'), type: 'select', required: true,
    options: statusOptions.value, defaultValue: 'waiting', span: 12 },
  { name: 'is_urgent', label: t('orders.urgent'), type: 'switch', span: 12 },
  { name: 'schedule_start', label: t('review.scheduleStart'), type: 'datetime', span: 12 },
  { name: 'schedule_end', label: t('review.scheduleEnd'), type: 'datetime', span: 12 },
  { name: 'rejection_reason', label: t('orders.rejectReason'), type: 'textarea' },
  { name: 'remark', label: t('orders.remark'), type: 'textarea' },
])
</script>
