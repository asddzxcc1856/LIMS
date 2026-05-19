<template>
  <CrudTable
    :resource="adminSamples"
    :resource-label="t('admin.pages.samples.label')"
    :title="t('admin.pages.samples.title')"
    :subtitle="t('admin.pages.samples.subtitle')"
    :search-placeholder="t('admin.pages.samples.search')"
    default-ordering="-created_at"
    :columns="columns"
    :form-fields="formFields"
  />
</template>

<script setup>
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import dayjs from 'dayjs'
import CrudTable from '../../components/admin/CrudTable.vue'
import { adminSamples } from '../../api/admin'

const { t } = useI18n()

const columns = computed(() => [
  { title: t('admin.pages.samples.colCode'), dataIndex: 'full_code', width: 220, sorter: true },
  { title: t('admin.pages.samples.colOrder'), dataIndex: 'order_no', width: 200 },
  { title: t('admin.pages.samples.colCount'), dataIndex: 'wafer_count', width: 90, sorter: true },
  { title: t('admin.pages.samples.colCreator'), dataIndex: 'created_by_username', width: 140 },
  { title: t('admin.pages.samples.colCreated'), dataIndex: 'created_at', width: 170,
    customRender: ({ value }) => (value ? dayjs(value).format('YYYY-MM-DD HH:mm:ss') : '—') },
  { title: t('admin.pages.samples.colNotes'), dataIndex: 'notes', ellipsis: true },
])

const formFields = computed(() => [
  { name: 'order', label: t('admin.pages.samples.fieldOrder'), type: 'text', required: true,
    help: t('admin.pages.samples.fieldOrderHelp') },
  { name: 'sub_code', label: t('admin.pages.samples.fieldSubCode'), type: 'text',
    required: true, span: 12 },
  { name: 'wafer_count', label: t('admin.pages.samples.fieldWaferCount'), type: 'number',
    required: true, defaultValue: 1, span: 12 },
  { name: 'notes', label: t('admin.pages.samples.fieldNotes'), type: 'textarea', span: 24 },
])
</script>
