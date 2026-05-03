<template>
  <CrudTable
    :resource="adminFabs"
    resource-label="FAB"
    title="FAB 工廠"
    subtitle="管理 FAB 廠區基本資料"
    search-placeholder="依 FAB 名稱搜尋"
    default-ordering="fab_name"
    :columns="columns"
    :form-fields="formFields"
  />
</template>

<script setup>
import CrudTable from '../../components/admin/CrudTable.vue'
import { adminFabs } from '../../api/admin'

const columns = [
  { title: 'ID', dataIndex: 'id', width: 320 },
  { title: 'FAB 名稱', dataIndex: 'fab_name', sorter: true },
  { title: '部門數', dataIndex: 'department_count', width: 120 },
]

const formFields = [
  {
    name: 'fab_name',
    label: 'FAB 名稱',
    type: 'text',
    required: true,
    placeholder: '例如: FAB12A',
  },
]
</script>
