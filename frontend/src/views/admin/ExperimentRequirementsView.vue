<template>
  <CrudTable
    :resource="adminExperimentRequirements"
    :resource-label="t('admin.pages.experimentRequirements.label')"
    :title="t('admin.pages.experimentRequirements.title')"
    :subtitle="t('admin.pages.experimentRequirements.subtitle')"
    :search-placeholder="t('admin.pages.experimentRequirements.search')"
    default-ordering="step_order"
    :columns="columns"
    :form-fields="formFields"
  />
</template>

<script setup>
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import CrudTable from '../../components/admin/CrudTable.vue'
import {
  adminEquipmentTypes,
  adminExperimentRequirements,
  adminExperiments,
} from '../../api/admin'

const { t } = useI18n()

const columns = computed(() => [
  { title: t('orders.experiment'), dataIndex: 'experiment_name', width: 220 },
  { title: t('orders.equipmentType'), dataIndex: 'equipment_type_name', width: 180 },
  { title: t('createOrder.quantity'), dataIndex: 'quantity', width: 100 },
  { title: t('review.step'), dataIndex: 'step_order', width: 120, sorter: true },
])

const formFields = computed(() => [
  { name: 'experiment', label: t('orders.experiment'), type: 'select', required: true,
    optionsResource: adminExperiments, optionLabel: 'name', span: 12 },
  { name: 'equipment_type', label: t('orders.equipmentType'), type: 'select', required: true,
    optionsResource: adminEquipmentTypes, optionLabel: 'name', span: 12 },
  { name: 'quantity', label: t('createOrder.quantity'), type: 'number', required: true,
    defaultValue: 1, span: 12 },
  { name: 'step_order', label: t('review.step'), type: 'number', required: true,
    defaultValue: 1, span: 12 },
])
</script>
