<template>
  <CrudTable
    :resource="adminExperiments"
    resource-label="實驗類型"
    title="實驗類型"
    subtitle="送樣表單上呈現的實驗選項目錄"
    search-placeholder="依名稱或備註搜尋"
    default-ordering="name"
    :columns="columns"
    :form-fields="formFields"
  />
</template>

<script setup>
import CrudTable from '../../components/admin/CrudTable.vue'
import { adminExperiments } from '../../api/admin'

const columns = [
  { title: '名稱', dataIndex: 'name', sorter: true, width: 240 },
  { title: '備註', dataIndex: 'remark', ellipsis: true },
  { title: '需求設備種類數', dataIndex: 'requirement_count', width: 160 },
]

const formFields = [
  { name: 'name', label: '實驗名稱', type: 'text', required: true,
    placeholder: '例如: SEM-Inspection-01' },
  { name: 'remark', label: '備註', type: 'textarea',
    placeholder: '此實驗的詳細說明 (可選)' },
]
</script>
