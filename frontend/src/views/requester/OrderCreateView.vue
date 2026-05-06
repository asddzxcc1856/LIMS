<template>
  <div class="create-page">
    <a-page-header
      :title="t('createOrder.title')"
      :sub-title="t('createOrder.subtitle')"
      :back-icon="false"
    />

    <a-row :gutter="[16, 16]">
      <a-col :xs="24" :lg="14">
        <a-card :bordered="false" :title="t('createOrder.formTitle')">
          <a-result
            v-if="success"
            status="success"
            :title="t('createOrder.successTitle', { orderNo: createdOrderNo })"
            :sub-title="t('createOrder.successSub')"
          >
            <template #extra>
              <a-button type="primary" @click="resetForm">{{ t('createOrder.continueSubmit') }}</a-button>
              <a-button @click="$router.push('/orders')">{{ t('createOrder.seeOrderList') }}</a-button>
            </template>
          </a-result>

          <a-form
            v-else
            :model="form"
            layout="vertical"
            @finish="handleSubmit"
          >
            <a-form-item
              :label="t('createOrder.targetLabLabel')"
              name="target_department"
              :rules="[{ required: true, message: t('createOrder.requireTargetLab') }]"
            >
              <a-select
                v-model:value="form.target_department"
                :placeholder="t('createOrder.targetLabPlaceholder')"
                show-search
                option-filter-prop="label"
                size="large"
                :options="labOptions"
                :loading="loadingLabs"
              />
            </a-form-item>

            <a-form-item
              :label="t('createOrder.experimentLabel')"
              name="experiment"
              :rules="[{ required: true, message: t('createOrder.requireExperiment') }]"
            >
              <a-select
                v-model:value="form.experiment"
                :placeholder="t('createOrder.experimentPlaceholder')"
                show-search
                option-filter-prop="label"
                size="large"
                :options="experimentOptions"
                :loading="loadingExperiments"
              />
            </a-form-item>

            <a-form-item :label="t('createOrder.lotIdLabel')" name="lot_id">
              <a-input
                v-model:value="form.lot_id"
                :placeholder="t('createOrder.lotIdPlaceholder')"
                size="large"
              />
            </a-form-item>

            <a-form-item name="is_urgent">
              <a-checkbox v-model:checked="form.is_urgent">
                <a-tag color="red" style="margin-right: 6px">{{ t('orders.urgent') }}</a-tag>
                {{ t('createOrder.urgentCheckbox') }}
              </a-checkbox>
            </a-form-item>

            <a-form-item :label="t('orders.remark')" name="remark">
              <a-textarea
                v-model:value="form.remark"
                :rows="3"
                :placeholder="t('createOrder.remarkPlaceholder')"
              />
            </a-form-item>

            <a-alert
              type="info"
              show-icon
              :message="t('createOrder.singleLabNote')"
              style="margin-bottom: 16px"
            />

            <a-alert
              v-if="error"
              type="error"
              show-icon
              :message="error"
              style="margin-bottom: 16px"
            />

            <a-button
              type="primary"
              html-type="submit"
              :loading="loading"
              size="large"
            >
              <template #icon><SendOutlined /></template>
              {{ t('createOrder.submitButton') }}
            </a-button>
          </a-form>
        </a-card>
      </a-col>

      <a-col :xs="24" :lg="10">
        <a-card :bordered="false" :title="t('createOrder.requirementPreview')" class="side-card">
          <a-empty
            v-if="!form.experiment"
            :description="t('createOrder.requirementHint')"
          />
          <template v-else>
            <a-descriptions :column="1" size="small">
              <a-descriptions-item :label="t('createOrder.experimentLabel')">
                <span class="font-bold">{{ selectedExp?.name }}</span>
              </a-descriptions-item>
              <a-descriptions-item v-if="selectedExp?.remark" :label="t('orders.remark')">
                <span class="muted">{{ selectedExp.remark }}</span>
              </a-descriptions-item>
            </a-descriptions>

            <a-divider style="margin: 12px 0">{{ t('createOrder.requiredEquipments') }}</a-divider>

            <a-empty
              v-if="!(selectedExp?.required_equipments || []).length"
              :description="t('createOrder.noRequirement')"
            />
            <a-list
              v-else
              :data-source="selectedExp.required_equipments"
              size="small"
            >
              <template #renderItem="{ item }">
                <a-list-item>
                  <a-list-item-meta>
                    <template #title>
                      <a-space>
                        <a-tag color="blue">{{ t('review.step') }} {{ item.step_order }}</a-tag>
                        <span class="font-bold">{{ item.equipment_type_name }}</span>
                      </a-space>
                    </template>
                    <template #description>
                      <span class="muted">{{ t('createOrder.quantity') }}: {{ item.quantity }}</span>
                    </template>
                  </a-list-item-meta>
                </a-list-item>
              </template>
            </a-list>
          </template>
        </a-card>
      </a-col>
    </a-row>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import { SendOutlined } from '@ant-design/icons-vue'
import { fetchExperiments } from '../../api/equipments'
import { fetchDepartments } from '../../api/users'
import { createOrder } from '../../api/orders'

const { t } = useI18n()

const departments = ref([])
const experiments = ref([])
const loadingLabs = ref(false)
const loadingExperiments = ref(false)
const loading = ref(false)
const error = ref('')
const success = ref(false)
const createdOrderNo = ref(null)

const form = reactive({
  target_department: undefined,
  experiment: undefined,
  is_urgent: false,
  lot_id: '',
  remark: '',
})

const labOptions = computed(() =>
  departments.value.map((d) => ({
    value: d.id,
    label: d.fab_name ? `${d.fab_name} · ${d.name}` : d.name,
  })),
)

const experimentOptions = computed(() =>
  experiments.value.map((exp) => ({ value: exp.id, label: exp.name })),
)

const selectedExp = computed(() =>
  experiments.value.find((e) => e.id === form.experiment),
)

onMounted(async () => {
  loadingLabs.value = true
  loadingExperiments.value = true
  try {
    const [labsRes, expRes] = await Promise.allSettled([
      fetchDepartments(),
      fetchExperiments(),
    ])
    if (labsRes.status === 'fulfilled') {
      departments.value = labsRes.value.data.results || labsRes.value.data || []
    } else {
      message.error(t('createOrder.loadLabsFailed'))
    }
    if (expRes.status === 'fulfilled') {
      experiments.value = expRes.value.data.results || expRes.value.data || []
    } else {
      message.error(t('createOrder.loadExpFailed'))
    }
  } finally {
    loadingLabs.value = false
    loadingExperiments.value = false
  }
})

async function handleSubmit() {
  error.value = ''
  loading.value = true
  try {
    const payload = {
      target_department: form.target_department,
      experiment: form.experiment,
      is_urgent: form.is_urgent,
      lot_id: form.lot_id,
      remark: form.remark,
    }
    const { data } = await createOrder(payload)
    createdOrderNo.value = data.order_no
    success.value = true
    message.success(t('createOrder.successTitle', { orderNo: data.order_no }))
  } catch (e) {
    const data = e.response?.data
    if (typeof data === 'string') error.value = data
    else if (data?.detail) error.value = data.detail
    else if (data && typeof data === 'object') {
      const k = Object.keys(data)[0]
      error.value = `${k}: ${Array.isArray(data[k]) ? data[k].join(', ') : data[k]}`
    } else error.value = t('createOrder.submitFailed')
  } finally {
    loading.value = false
  }
}

function resetForm() {
  form.target_department = undefined
  form.experiment = undefined
  form.is_urgent = false
  form.lot_id = ''
  form.remark = ''
  success.value = false
  createdOrderNo.value = null
}
</script>

<style scoped>
.create-page {
  padding: 0;
}
.muted {
  color: var(--c-text-muted);
  font-size: 12px;
}
.font-bold {
  font-weight: 600;
}
.side-card :deep(.ant-card-body) {
  padding: 12px 16px;
}
</style>
