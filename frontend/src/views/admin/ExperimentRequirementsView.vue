<template>
  <CrudTable
    :resource="adminExperimentRequirements"
    resource-label="實驗需求"
    title="實驗設備需求"
    subtitle="定義每個實驗在每個步驟所需的設備類型與數量"
    search-placeholder="依實驗或設備類型名稱搜尋"
    default-ordering="step_order"
    :columns="columns"
    :form-fields="formFields"
  />
</template>

<script setup>
import CrudTable from '../../components/admin/CrudTable.vue'
import {
  adminEquipmentTypes,
  adminExperimentRequirements,
  adminExperiments,
} from '../../api/admin'

const columns = [
  { title: '實驗', dataIndex: 'experiment_name', width: 220 },
  { title: '設備類型', dataIndex: 'equipment_type_name', width: 180 },
  { title: '數量', dataIndex: 'quantity', width: 100 },
  { title: '步驟順序', dataIndex: 'step_order', width: 120, sorter: true },
]

const formFields = [
  { name: 'experiment', label: '實驗', type: 'select', required: true,
    optionsResource: adminExperiments, optionLabel: 'name', span: 12 },
  { name: 'equipment_type', label: '設備類型', type: 'select', required: true,
    optionsResource: adminEquipmentTypes, optionLabel: 'name', span: 12 },
  { name: 'quantity', label: '需求數量', type: 'number', required: true,
    defaultValue: 1, span: 12,
    rules: [{ type: 'number', min: 1, message: '至少為 1' }] },
  { name: 'step_order', label: '步驟順序', type: 'number', required: true,
    defaultValue: 1, span: 12,
    help: '數字越小越先執行,接力流程依此順序流轉' },
]
</script>
