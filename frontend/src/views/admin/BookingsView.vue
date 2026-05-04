<template>
  <CrudTable
    :resource="adminBookings"
    :resource-label="t('admin.pages.bookings.label')"
    :title="t('admin.pages.bookings.title')"
    :subtitle="t('admin.pages.bookings.subtitle')"
    :search-placeholder="t('admin.pages.bookings.search')"
    default-ordering="-started_at"
    :columns="columns"
    :form-fields="formFields"
  />
</template>

<script setup>
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import CrudTable from '../../components/admin/CrudTable.vue'
import {
  adminBookings,
  adminEquipment,
  adminOrderStages,
  adminOrders,
} from '../../api/admin'

const { t } = useI18n()

const columns = computed(() => [
  { title: t('orders.orderNo'), dataIndex: 'order_no', width: 200, fixed: 'left' },
  { title: t('orders.equipmentCode'), dataIndex: 'equipment_code', width: 160 },
  { title: t('review.startTime'), dataIndex: 'started_at', width: 180, sorter: true,
    customRender: ({ value }) => value ? value.replace('T', ' ').slice(0, 19) : '—',
  },
  { title: t('review.endTime'), dataIndex: 'ended_at', width: 180, sorter: true,
    customRender: ({ value }) => value ? value.replace('T', ' ').slice(0, 19) : '—',
  },
])

const formFields = computed(() => [
  { name: 'order', label: t('admin.nav.orders'), type: 'select', required: true,
    optionsResource: adminOrders, optionLabel: 'order_no', span: 12 },
  { name: 'equipment', label: t('admin.nav.equipment'), type: 'select', required: true,
    optionsResource: adminEquipment, optionLabel: 'code', span: 12 },
  { name: 'stage', label: t('admin.nav.orderStages'), type: 'select',
    optionsResource: adminOrderStages, optionLabel: 'order_no',
    nullableEmpty: true, span: 12 },
  { name: 'started_at', label: t('review.startTime'), type: 'datetime', required: true, span: 12 },
  { name: 'ended_at', label: t('review.endTime'), type: 'datetime', required: true, span: 12 },
])
</script>
