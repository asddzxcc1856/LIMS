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
                @change="onExperimentChange"
                :options="experimentOptions"
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
              :message="t('createOrder.scheduleNote')"
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
        <a-card
          v-if="!form.experiment"
          :bordered="false"
          :title="t('createOrder.requirementPreview')"
        >
          <a-empty :description="t('createOrder.requirementHint')" />
        </a-card>

        <template v-else>
          <a-card :bordered="false" :title="t('createOrder.requiredEquipments')" class="side-card">
            <a-list
              :data-source="selectedExp?.required_equipments || []"
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
                      <span class="muted">{{ item.department_name }} · {{ t('createOrder.quantity') }} {{ item.quantity }}</span>
                    </template>
                  </a-list-item-meta>
                </a-list-item>
              </template>
              <template #loadMore>
                <a-empty
                  v-if="!(selectedExp?.required_equipments || []).length"
                  :description="t('createOrder.noRequirement')"
                />
              </template>
            </a-list>
          </a-card>

          <a-card
            v-if="capacity"
            :bordered="false"
            :title="t('createOrder.capacityCheckTitle')"
            class="side-card"
            style="margin-top: 16px"
          >
            <a-alert
              v-if="capacity.has_shortage"
              type="warning"
              show-icon
              :message="t('createOrder.shortageTitle')"
              :description="t('createOrder.shortageDesc')"
              style="margin-bottom: 12px"
            />
            <a-alert
              v-else
              type="success"
              show-icon
              :message="t('createOrder.sufficient')"
              style="margin-bottom: 12px"
            />
            <a-list
              :data-source="capacity.details"
              size="small"
            >
              <template #renderItem="{ item }">
                <a-list-item>
                  <span>{{ item.equipment_type }}</span>
                  <a-tag :color="item.shortage ? 'error' : 'success'">
                    {{ item.available }} / {{ item.required }}
                  </a-tag>
                </a-list-item>
              </template>
            </a-list>
          </a-card>
        </template>
      </a-col>
    </a-row>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import { SendOutlined } from '@ant-design/icons-vue'
import { fetchCapacityCheck, fetchExperiments } from '../../api/equipments'
import { createOrder } from '../../api/orders'

const { t } = useI18n()

const experiments = ref([])
const capacity = ref(null)
const loading = ref(false)
const error = ref('')
const success = ref(false)
const createdOrderNo = ref(null)

const form = reactive({
  experiment: undefined,
  is_urgent: false,
  lot_id: '',
  remark: '',
})

const experimentOptions = computed(() =>
  experiments.value.map((exp) => ({ label: exp.name, value: exp.id })),
)

const selectedExp = computed(() =>
  experiments.value.find((e) => e.id === form.experiment),
)

onMounted(async () => {
  try {
    const { data } = await fetchExperiments()
    experiments.value = data.results || data
  } catch {
    message.error(t('createOrder.loadExpFailed'))
  }
})

async function onExperimentChange() {
  capacity.value = null
  if (!form.experiment) return
  try {
    const { data } = await fetchCapacityCheck(form.experiment)
    capacity.value = data
  } catch {
    /* capacity check is informational; failure should not block submission */
  }
}

async function handleSubmit() {
  error.value = ''
  loading.value = true
  try {
    const { data } = await createOrder(form)
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
  form.experiment = undefined
  form.is_urgent = false
  form.lot_id = ''
  form.remark = ''
  capacity.value = null
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
