<template>
  <div>
    <CrudTable
      ref="crudRef"
      :resource="adminUsers"
      :resource-label="t('admin.pages.users.label')"
      :title="t('admin.pages.users.title')"
      :subtitle="t('admin.pages.users.subtitle')"
      :search-placeholder="t('admin.pages.users.search')"
      default-ordering="username"
      :columns="columns"
      :form-fields="formFields"
      selectable
      @update:selectedRowKeys="onSelectionChange"
    >
      <template #extra-actions>
        <a-button @click="openBulkCreate">
          <template #icon><UsergroupAddOutlined /></template>
          {{ t('bulkUsers.bulkCreateBtn') }}
        </a-button>
        <a-popconfirm
          v-if="selectedIds.length"
          :title="t('bulkUsers.bulkDeleteConfirm', { n: selectedIds.length })"
          :ok-text="t('crud.delete')"
          ok-type="danger"
          :cancel-text="t('crud.cancel')"
          @confirm="onBulkDelete"
        >
          <a-button danger>
            <template #icon><DeleteOutlined /></template>
            {{ t('bulkUsers.bulkDeleteBtn', { n: selectedIds.length }) }}
          </a-button>
        </a-popconfirm>
      </template>
    </CrudTable>

    <!-- Bulk-create modal -->
    <a-modal
      v-model:open="bulkOpen"
      :title="t('bulkUsers.modalTitle')"
      :confirm-loading="submitting"
      :ok-text="t('bulkUsers.submit')"
      :cancel-text="t('crud.cancel')"
      @ok="submitBulk"
      @cancel="bulkOpen = false"
    >
      <a-form layout="vertical">
        <a-form-item :label="t('bulkUsers.role')" required>
          <a-radio-group v-model:value="form.role" button-style="solid">
            <a-radio-button value="regular_employee">
              {{ t('roles.regular_employee') }}
            </a-radio-button>
            <a-radio-button value="lab_member">
              {{ t('roles.lab_member') }}
            </a-radio-button>
            <a-radio-button value="lab_manager">
              {{ t('roles.lab_manager') }}
            </a-radio-button>
          </a-radio-group>
        </a-form-item>

        <a-form-item :label="t('bulkUsers.count')" required>
          <a-input-number
            v-model:value="form.count"
            :min="1"
            :max="100"
            style="width: 160px"
          />
          <span class="form-hint">{{ t('bulkUsers.countHint') }}</span>
        </a-form-item>

        <a-form-item
          v-if="form.role !== 'regular_employee'"
          :label="t('bulkUsers.department')"
          required
        >
          <a-select
            v-model:value="form.department"
            :placeholder="t('bulkUsers.department')"
            :options="departmentOptions"
            show-search
            option-filter-prop="label"
          />
          <div class="form-hint">{{ t('bulkUsers.departmentHint') }}</div>
        </a-form-item>

        <a-form-item :label="t('bulkUsers.password')">
          <a-input v-model:value="form.password" />
          <div class="form-hint">{{ t('bulkUsers.passwordHint') }}</div>
        </a-form-item>

        <a-alert
          type="info"
          :message="t('bulkUsers.namingHint')"
          show-icon
          style="margin-top: 8px"
        />

        <a-alert
          v-if="error"
          type="error"
          :message="error"
          show-icon
          style="margin-top: 12px"
        />
      </a-form>
    </a-modal>

    <!-- Result modal — shows the freshly created usernames + password -->
    <a-modal
      v-model:open="resultOpen"
      :title="t('bulkUsers.bulkCreatedTitle', { count: result?.count || 0 })"
      :ok-text="t('bulkUsers.closeBtn')"
      :cancel-button-props="{ style: { display: 'none' } }"
      @ok="resultOpen = false"
    >
      <a-descriptions :column="1" bordered size="small">
        <a-descriptions-item :label="t('bulkUsers.passwordLabel')">
          <a-typography-text code copyable>{{ result?.password }}</a-typography-text>
        </a-descriptions-item>
        <a-descriptions-item :label="t('bulkUsers.usernamesLabel')">
          <ul class="username-list">
            <li v-for="u in result?.created || []" :key="u.id">
              <a-typography-text code copyable>{{ u.username }}</a-typography-text>
            </li>
          </ul>
        </a-descriptions-item>
      </a-descriptions>
    </a-modal>
  </div>
</template>

<script setup>
import { computed, h, onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { Tag, message } from 'ant-design-vue'
import {
  DeleteOutlined,
  UsergroupAddOutlined,
} from '@ant-design/icons-vue'
import CrudTable from '../../components/admin/CrudTable.vue'
import { adminDepartments, adminUsers } from '../../api/admin'

const { t } = useI18n()

// ── Bulk state ────────────────────────────────────────────────────────────

const crudRef = ref(null)
const selectedIds = ref([])
const bulkOpen = ref(false)
const resultOpen = ref(false)
const submitting = ref(false)
const error = ref('')
const result = ref(null)

const form = reactive({
  role: 'regular_employee',
  count: 5,
  department: undefined,
  password: 'Lims@2026!Init',
})

const departmentOptions = ref([])

onMounted(async () => {
  try {
    const { data } = await adminDepartments.list({ page_size: 200 })
    departmentOptions.value = (data.results || []).map((d) => ({
      value: d.id,
      label: `${d.fab_name || ''} · ${d.name}`,
    }))
  } catch {
    /* ignore — bulk create will surface a clear error if the field is empty */
  }
})

function onSelectionChange(keys) {
  selectedIds.value = keys
}

function openBulkCreate() {
  error.value = ''
  bulkOpen.value = true
}

async function submitBulk() {
  error.value = ''
  if (form.role !== 'regular_employee' && !form.department) {
    error.value = t('bulkUsers.departmentHint')
    return
  }
  submitting.value = true
  try {
    const { data } = await adminUsers.bulkCreate({
      role: form.role,
      count: form.count,
      department: form.role === 'regular_employee' ? null : form.department,
      password: form.password,
    })
    result.value = data
    bulkOpen.value = false
    resultOpen.value = true
    crudRef.value?.reload()
  } catch (e) {
    const data = e.response?.data
    if (typeof data === 'string') error.value = data
    else if (data?.detail) error.value = data.detail
    else if (data && typeof data === 'object') {
      const k = Object.keys(data)[0]
      error.value = `${k}: ${Array.isArray(data[k]) ? data[k].join(', ') : data[k]}`
    } else error.value = t('crud.addFailed')
  } finally {
    submitting.value = false
  }
}

async function onBulkDelete() {
  if (!selectedIds.value.length) {
    message.warning(t('bulkUsers.selectAtLeastOne'))
    return
  }
  try {
    const { data } = await adminUsers.bulkDelete(selectedIds.value)
    let toast = t('bulkUsers.bulkDeletedToast', { count: data.deleted })
    if ((data.skipped || []).length) {
      toast += ' ' + t('bulkUsers.bulkDeletedSkipped', { skipped: data.skipped.length })
    }
    message.success(toast)
    crudRef.value?.clearSelection()
    selectedIds.value = []
    crudRef.value?.reload()
  } catch (e) {
    message.error(e.response?.data?.detail || t('crud.deleteFailed'))
  }
}

// ── Existing single-row CRUD config (unchanged) ───────────────────────────

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
  { title: t('auth.username'), dataIndex: 'username', sorter: true, width: 180, fixed: 'left' },
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
  { title: 'FAB / ' + t('admin.nav.departments'), dataIndex: 'department_name', width: 200,
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
  { name: 'username', label: t('auth.username'), type: 'text', required: true, span: 12 },
  { name: 'email', label: t('auth.email'), type: 'text', span: 12,
    rules: [{ type: 'email', message: 'Email' }] },
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

<style scoped>
.form-hint {
  display: block;
  margin-top: 4px;
  color: var(--c-text-muted);
  font-size: 12px;
}
.username-list {
  margin: 0;
  padding-left: 18px;
  max-height: 280px;
  overflow-y: auto;
}
</style>
