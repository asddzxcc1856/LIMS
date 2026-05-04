<template>
  <CrudTable
    :resource="adminFabs"
    :resource-label="t('admin.pages.fabs.label')"
    :title="t('admin.pages.fabs.title')"
    :subtitle="t('admin.pages.fabs.subtitle')"
    :search-placeholder="t('admin.pages.fabs.search')"
    default-ordering="fab_name"
    :columns="columns"
    :form-fields="formFields"
  />
</template>

<script setup>
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import CrudTable from '../../components/admin/CrudTable.vue'
import { adminFabs } from '../../api/admin'

const { t } = useI18n()

const columns = computed(() => [
  { title: 'ID', dataIndex: 'id', width: 320 },
  { title: 'FAB', dataIndex: 'fab_name', sorter: true },
  { title: t('admin.nav.departments'), dataIndex: 'department_count', width: 120 },
])

const formFields = [
  {
    name: 'fab_name',
    label: 'FAB',
    type: 'text',
    required: true,
    placeholder: 'FAB12A',
  },
]
</script>
