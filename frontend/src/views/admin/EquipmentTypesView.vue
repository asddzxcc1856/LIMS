<template>
  <CrudTable
    :resource="adminEquipmentTypes"
    resource-label="設備類型"
    title="設備類型"
    subtitle="如 SEM、AFM、XPS 等設備分類"
    search-placeholder="依名稱搜尋"
    default-ordering="name"
    :columns="columns"
    :form-fields="formFields"
  />
</template>

<script setup>
import CrudTable from '../../components/admin/CrudTable.vue'
import { adminEquipmentTypes } from '../../api/admin'

const columns = [
  { title: '名稱', dataIndex: 'name', sorter: true, width: 280 },
  { title: '隸屬設備數量', dataIndex: 'equipment_count', width: 160 },
]

const formFields = [
  { name: 'name', label: '類型名稱', type: 'text', required: true,
    placeholder: '例如: SEM, AFM, XPS' },
]
</script>
