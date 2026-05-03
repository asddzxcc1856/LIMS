<template>
  <CrudTable
    :resource="adminUsers"
    resource-label="使用者"
    title="使用者"
    subtitle="管理帳號、角色與密碼。新增時必填密碼;編輯時留空則不變更"
    search-placeholder="依 username / email / 姓名搜尋"
    default-ordering="username"
    :columns="columns"
    :form-fields="formFields"
  />
</template>

<script setup>
import { h } from 'vue'
import { Tag } from 'ant-design-vue'
import CrudTable from '../../components/admin/CrudTable.vue'
import { adminDepartments, adminUsers } from '../../api/admin'

const roleOptions = [
  { value: 'superuser', label: '系統管理員' },
  { value: 'lab_manager', label: '實驗室經理' },
  { value: 'lab_member', label: '實驗室成員' },
  { value: 'regular_employee', label: '一般員工' },
]
const statusOptions = [
  { value: 'active', label: '啟用' },
  { value: 'suspended', label: '停權' },
]
const roleColor = {
  superuser: 'red',
  lab_manager: 'geekblue',
  lab_member: 'cyan',
  regular_employee: 'default',
}

const columns = [
  { title: 'Username', dataIndex: 'username', sorter: true, width: 160, fixed: 'left' },
  { title: 'Email', dataIndex: 'email', width: 220 },
  {
    title: '角色',
    dataIndex: 'role',
    width: 130,
    sorter: true,
    customRender: ({ value }) =>
      h(Tag, { color: roleColor[value] || 'default' }, () =>
        roleOptions.find((o) => o.value === value)?.label || value,
      ),
  },
  {
    title: '狀態',
    dataIndex: 'status',
    width: 100,
    customRender: ({ value }) =>
      h(Tag, { color: value === 'active' ? 'success' : 'error' }, () =>
        value === 'active' ? '啟用' : '停權',
      ),
  },
  { title: 'FAB / 部門', dataIndex: 'department_name', width: 180,
    customRender: ({ record }) =>
      record.department_name
        ? `${record.fab_name || ''} - ${record.department_name}`
        : '—',
  },
  { title: '加入時間', dataIndex: 'joined_at', width: 170,
    customRender: ({ value }) => value ? value.replace('T', ' ').slice(0, 19) : '—',
  },
]

const formFields = [
  { name: 'username', label: 'Username', type: 'text', required: true, span: 12,
    rules: [{ required: true, min: 3, message: 'Username 至少 3 字元' }] },
  { name: 'email', label: 'Email', type: 'text', span: 12,
    rules: [{ type: 'email', message: '需為合法 Email' }] },
  { name: 'first_name', label: '名', type: 'text', span: 12 },
  { name: 'last_name', label: '姓', type: 'text', span: 12 },
  { name: 'password', label: '密碼', type: 'password', writeOnly: true,
    placeholder: '至少 8 字元;編輯時留空表示不變更',
    help: '密碼僅在儲存時送出,後端會自動雜湊;讀取時不會回傳' },
  { name: 'role', label: '角色', type: 'select', required: true, options: roleOptions, span: 12 },
  { name: 'status', label: '狀態', type: 'select', required: true, options: statusOptions, span: 12,
    defaultValue: 'active' },
  { name: 'department', label: '部門', type: 'select',
    optionsResource: adminDepartments, optionLabel: 'name',
    nullableEmpty: true, span: 12 },
  { name: 'is_staff', label: 'Staff', type: 'switch', span: 12 },
  { name: 'is_superuser', label: 'Superuser', type: 'switch', span: 12 },
  { name: 'is_active', label: '啟用 (Django auth)', type: 'switch', span: 12,
    defaultValue: true },
]
</script>
