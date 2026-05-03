<template>
  <CrudTable
    :resource="adminDepartments"
    resource-label="部門"
    title="部門"
    subtitle="管理 FAB 之下的部門結構"
    search-placeholder="依部門名稱或 FAB 名稱搜尋"
    default-ordering="name"
    :columns="columns"
    :form-fields="formFields"
  />
</template>

<script setup>
import CrudTable from '../../components/admin/CrudTable.vue'
import { adminDepartments, adminFabs } from '../../api/admin'

const columns = [
  { title: 'FAB', dataIndex: 'fab_name', width: 160 },
  { title: '部門名稱', dataIndex: 'name', sorter: true },
  { title: '成員數', dataIndex: 'member_count', width: 100 },
]

const formFields = [
  {
    name: 'fab',
    label: '所屬 FAB',
    type: 'select',
    required: true,
    optionsResource: adminFabs,
    optionLabel: 'fab_name',
  },
  {
    name: 'name',
    label: '部門名稱',
    type: 'text',
    required: true,
    placeholder: '例如: Photo, Process, QC',
  },
]
</script>
