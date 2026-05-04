<template>
  <CrudTable
    :resource="adminEquipmentTypes"
    :resource-label="t('admin.pages.equipmentTypes.label')"
    :title="t('admin.pages.equipmentTypes.title')"
    :subtitle="t('admin.pages.equipmentTypes.subtitle')"
    :search-placeholder="t('admin.pages.equipmentTypes.search')"
    default-ordering="name"
    :columns="columns"
    :form-fields="formFields"
  />
</template>

<script setup>
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import CrudTable from '../../components/admin/CrudTable.vue'
import { adminEquipmentTypes } from '../../api/admin'

const { t } = useI18n()

const columns = computed(() => [
  { title: t('orders.equipmentType'), dataIndex: 'name', sorter: true, width: 280 },
  { title: t('admin.nav.equipment'), dataIndex: 'equipment_count', width: 160 },
])

const formFields = computed(() => [
  { name: 'name', label: t('orders.equipmentType'), type: 'text', required: true,
    placeholder: 'SEM, AFM, XPS' },
])
</script>
