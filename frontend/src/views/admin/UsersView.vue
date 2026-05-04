<template>
  <CrudTable
    :resource="adminUsers"
    :resource-label="t('admin.pages.users.label')"
    :title="t('admin.pages.users.title')"
    :subtitle="t('admin.pages.users.subtitle')"
    :search-placeholder="t('admin.pages.users.search')"
    default-ordering="username"
    :columns="columns"
    :form-fields="formFields"
  />
</template>

<script setup>
import { computed, h } from 'vue'
import { useI18n } from 'vue-i18n'
import { Tag } from 'ant-design-vue'
import CrudTable from '../../components/admin/CrudTable.vue'
import { adminDepartments, adminUsers } from '../../api/admin'

const { t } = useI18n()

const roleOptions = computed(() => [
  { value: 'superuser', label: t('roles.superuser') },
  { value: 'lab_manager', label: t('roles.lab_manager') },
  { value: 'lab_member', label: t('roles.lab_member') },
  { value: 'regular_employee', label: t('roles.regular_employee') },
])
const statusOptions = computed(() => [
  { value: 'active', label: t('common.yes') },
  { value: 'suspended', label: t('common.no') },
])
const roleColor = {
  superuser: 'red',
  lab_manager: 'geekblue',
  lab_member: 'cyan',
  regular_employee: 'default',
}

const columns = computed(() => [
  { title: t('auth.username'), dataIndex: 'username', sorter: true, width: 160, fixed: 'left' },
  { title: t('auth.email'), dataIndex: 'email', width: 220 },
  {
    title: t('auth.role'),
    dataIndex: 'role',
    width: 130,
    sorter: true,
    customRender: ({ value }) =>
      h(Tag, { color: roleColor[value] || 'default' }, () =>
        roleOptions.value.find((o) => o.value === value)?.label || value,
      ),
  },
  {
    title: t('orders.status'),
    dataIndex: 'status',
    width: 100,
    customRender: ({ value }) =>
      h(Tag, { color: value === 'active' ? 'success' : 'error' }, () =>
        value === 'active' ? t('common.yes') : t('common.no'),
      ),
  },
  { title: 'FAB / ' + t('admin.nav.departments'), dataIndex: 'department_name', width: 180,
    customRender: ({ record }) =>
      record.department_name
        ? `${record.fab_name || ''} - ${record.department_name}`
        : '—',
  },
  { title: t('orders.createdAt'), dataIndex: 'joined_at', width: 170,
    customRender: ({ value }) => value ? value.replace('T', ' ').slice(0, 19) : '—',
  },
])

const formFields = computed(() => [
  { name: 'username', label: t('auth.username'), type: 'text', required: true, span: 12,
    rules: [{ required: true, min: 3, message: t('auth.minUsername') }] },
  { name: 'email', label: t('auth.email'), type: 'text', span: 12,
    rules: [{ type: 'email', message: t('auth.requireEmail') }] },
  { name: 'first_name', label: t('auth.fullName'), type: 'text', span: 12 },
  { name: 'last_name', label: t('auth.fullName'), type: 'text', span: 12 },
  { name: 'password', label: t('auth.password'), type: 'password', writeOnly: true,
    placeholder: t('auth.minPassword') },
  { name: 'role', label: t('auth.role'), type: 'select', required: true, options: roleOptions.value, span: 12 },
  { name: 'status', label: t('orders.status'), type: 'select', required: true, options: statusOptions.value, span: 12,
    defaultValue: 'active' },
  { name: 'department', label: t('admin.nav.departments'), type: 'select',
    optionsResource: adminDepartments, optionLabel: 'name',
    nullableEmpty: true, span: 12 },
  { name: 'is_staff', label: 'Staff', type: 'switch', span: 12 },
  { name: 'is_superuser', label: 'Superuser', type: 'switch', span: 12 },
  { name: 'is_active', label: 'Active', type: 'switch', span: 12,
    defaultValue: true },
])
</script>
