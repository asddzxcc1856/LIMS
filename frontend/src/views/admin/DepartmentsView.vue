<template>
  <CrudTable
    :resource="adminDepartments"
    :resource-label="t('admin.pages.departments.label')"
    :title="t('admin.pages.departments.title')"
    :subtitle="t('admin.pages.departments.subtitle')"
    :search-placeholder="t('admin.pages.departments.search')"
    default-ordering="name"
    :columns="columns"
    :form-fields="formFields"
  />
</template>

<script setup>
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import CrudTable from '../../components/admin/CrudTable.vue'
import { adminDepartments, adminFabs } from '../../api/admin'

const { t } = useI18n()

const columns = computed(() => [
  { title: 'FAB', dataIndex: 'fab_name', width: 160 },
  { title: t('admin.nav.departments'), dataIndex: 'name', sorter: true },
  { title: t('admin.nav.users'), dataIndex: 'member_count', width: 100 },
])

const formFields = computed(() => [
  {
    name: 'fab',
    label: 'FAB',
    type: 'select',
    required: true,
    optionsResource: adminFabs,
    optionLabel: 'fab_name',
  },
  {
    name: 'name',
    label: t('admin.nav.departments'),
    type: 'text',
    required: true,
    placeholder: 'Photo / Process / QC',
  },
])
</script>
