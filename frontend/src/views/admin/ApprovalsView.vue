<template>
  <CrudTable
    :resource="adminApprovals"
    :resource-label="t('admin.pages.approvals.label')"
    :title="t('admin.pages.approvals.title')"
    :subtitle="t('admin.pages.approvals.subtitle')"
    :search-placeholder="t('admin.pages.approvals.search')"
    default-ordering="-decided_at"
    :columns="columns"
    :form-fields="formFields"
  />
</template>

<script setup>
import { computed, h } from 'vue'
import { useI18n } from 'vue-i18n'
import { Tag } from 'ant-design-vue'
import dayjs from 'dayjs'
import CrudTable from '../../components/admin/CrudTable.vue'
import { adminApprovals } from '../../api/admin'

const { t } = useI18n()

const decisionColor = { approved: 'success', rejected: 'error' }

const columns = computed(() => [
  { title: t('admin.pages.approvals.colTime'), dataIndex: 'decided_at', width: 170,
    sorter: true,
    customRender: ({ value }) =>
      value ? dayjs(value).format('YYYY-MM-DD HH:mm:ss') : '—' },
  { title: t('admin.pages.approvals.colDecision'), dataIndex: 'decision', width: 110,
    customRender: ({ value, record }) =>
      h(Tag, { color: decisionColor[value] || 'default' }, () => record.decision_display) },
  { title: t('admin.pages.approvals.colOrder'), dataIndex: 'stage_order_no', width: 220 },
  { title: t('admin.pages.approvals.colActor'), dataIndex: 'actor_username', width: 160 },
  { title: t('admin.pages.approvals.colComment'), dataIndex: 'comment', ellipsis: true },
])

const formFields = computed(() => [
  { name: 'stage', label: t('admin.pages.approvals.fieldStage'), type: 'text', required: true,
    help: t('admin.pages.approvals.fieldStageHelp') },
  { name: 'decision', label: t('admin.pages.approvals.fieldDecision'), type: 'select',
    required: true, defaultValue: 'approved',
    options: [
      { value: 'approved', label: t('admin.pages.approvals.approved') },
      { value: 'rejected', label: t('admin.pages.approvals.rejected') },
    ] },
  { name: 'comment', label: t('admin.pages.approvals.fieldComment'), type: 'textarea',
    span: 24 },
])
</script>
