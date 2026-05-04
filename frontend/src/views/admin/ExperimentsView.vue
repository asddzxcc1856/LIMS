<template>
  <CrudTable
    :resource="adminExperiments"
    :resource-label="t('admin.pages.experiments.label')"
    :title="t('admin.pages.experiments.title')"
    :subtitle="t('admin.pages.experiments.subtitle')"
    :search-placeholder="t('admin.pages.experiments.search')"
    default-ordering="name"
    :columns="columns"
    :form-fields="formFields"
  />
</template>

<script setup>
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import CrudTable from '../../components/admin/CrudTable.vue'
import { adminExperiments } from '../../api/admin'

const { t } = useI18n()

const columns = computed(() => [
  { title: t('orders.experiment'), dataIndex: 'name', sorter: true, width: 240 },
  { title: t('orders.remark'), dataIndex: 'remark', ellipsis: true },
  { title: t('admin.nav.equipmentTypes'), dataIndex: 'requirement_count', width: 160 },
])

const formFields = computed(() => [
  { name: 'name', label: t('orders.experiment'), type: 'text', required: true,
    placeholder: 'SEM-Inspection-01' },
  { name: 'remark', label: t('orders.remark'), type: 'textarea' },
])
</script>
