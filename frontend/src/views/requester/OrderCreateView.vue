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
                :options="experimentOptions"
                :loading="loadingExperiments"
              />
            </a-form-item>

            <a-form-item
              :label="t('createOrder.lotIdLabel')"
              name="lot_id"
              :rules="[{ required: true, message: t('createOrder.requireLotId') }]"
            >
              <a-select
                v-model:value="form.lot_id"
                :placeholder="t('createOrder.lotIdPlaceholder')"
                size="large"
                show-search
                option-filter-prop="label"
                :options="lotOptions"
                :loading="loadingLots"
                :not-found-content="lots.length ? undefined : t('createOrder.noLotsAvailable')"
              />
              <!-- Lock notice — surfaced when the chosen lot is currently
                   being processed by another order, so the requester knows
                   why submission is blocked. -->
              <a-alert
                v-if="selectedLotIsLocked"
                type="warning"
                show-icon
                style="margin-top: 8px"
                :message="t('createOrder.lotLockedTitle')"
                :description="t('createOrder.lotLockedDesc', { orderNo: selectedLotInfo.active_order_no })"
              />
              <!-- Historical experiments already run on this lot. Helps the
                   requester avoid accidentally re-submitting the same
                   experiment (backend will reject too, but pre-warning UX). -->
              <a-card
                v-if="selectedLotInfo && selectedLotInfo.experiments_done.length"
                size="small"
                style="margin-top: 8px"
                :body-style="{ padding: '8px 12px' }"
              >
                <div class="lot-history-title">
                  <HistoryOutlined />&nbsp;{{ t('createOrder.lotHistoryTitle') }}
                </div>
                <div class="lot-history-list">
                  <a-tag
                    v-for="row in selectedLotInfo.experiments_done"
                    :key="row.order_no"
                    :color="row.experiment_id === form.experiment ? 'red' : 'success'"
                  >
                    <CheckCircleOutlined />&nbsp;
                    {{ row.experiment_name }}
                    <span class="lot-history-meta">· {{ row.order_no }}</span>
                  </a-tag>
                </div>
                <a-alert
                  v-if="selectedExperimentAlreadyDone"
                  type="error"
                  show-icon
                  style="margin-top: 8px"
                  :message="t('createOrder.dupExpTitle')"
                  :description="t('createOrder.dupExpDesc')"
                />
              </a-card>
            </a-form-item>

            <a-form-item name="is_urgent">
              <a-checkbox v-model:checked="form.is_urgent">
                <a-tag color="red" style="margin-right: 6px">{{ t('orders.urgent') }}</a-tag>
                {{ t('createOrder.urgentCheckbox') }}
              </a-checkbox>
            </a-form-item>

            <a-form-item
              :label="t('orders.requirements')"
              name="requirements"
              :rules="[{ required: true, message: t('createOrder.requireRequirements') }]"
            >
              <a-textarea
                v-model:value="form.requirements"
                :rows="4"
                :placeholder="t('createOrder.requirementsPlaceholder')"
              />
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
              :disabled="!canSubmit"
              size="large"
            >
              <template #icon><SendOutlined /></template>
              {{ t('createOrder.submitButton') }}
            </a-button>
          </a-form>
        </a-card>
      </a-col>

      <a-col :xs="24" :lg="10">
        <a-card :bordered="false" :title="t('createOrder.experimentInfo')" class="side-card">
          <a-empty
            v-if="!form.experiment"
            :description="t('createOrder.pickExperimentHint')"
          />
          <a-descriptions v-else :column="1" size="small">
            <a-descriptions-item :label="t('createOrder.experimentLabel')">
              <span class="font-bold">{{ selectedExp?.name }}</span>
            </a-descriptions-item>
            <a-descriptions-item :label="t('createOrder.targetLabLabel')">
              <a-tag color="blue">{{ selectedExp?.department_name || '—' }}</a-tag>
            </a-descriptions-item>
            <a-descriptions-item v-if="selectedExp?.remark" :label="t('orders.remark')">
              <span class="muted">{{ selectedExp.remark }}</span>
            </a-descriptions-item>
          </a-descriptions>
        </a-card>
      </a-col>
    </a-row>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import {
  CheckCircleOutlined,
  HistoryOutlined,
  SendOutlined,
} from '@ant-design/icons-vue'
import { fetchExperiments } from '../../api/equipments'
import { fetchWaferLots } from '../../api/users'
import { createOrder } from '../../api/orders'
import { useLocalizedLabel } from '../../composables/useLocalizedLabel'

const { localized } = useLocalizedLabel()

const { t } = useI18n()

const experiments = ref([])
const lots = ref([])
const loadingExperiments = ref(false)
const loadingLots = ref(false)
const loading = ref(false)
const error = ref('')
const success = ref(false)
const createdOrderNo = ref(null)

const form = reactive({
  experiment: undefined,
  is_urgent: false,
  lot_id: undefined,
  requirements: '',
  remark: '',
})

const lotOptions = computed(() =>
  lots.value.map((l) => {
    // Compose the label so the dropdown lists the lock state + completed
    // experiment count inline; the requester can see at a glance which
    // lots are available.
    const parts = [l.code]
    if (l.notes) parts.push(`— ${l.notes}`)
    if (l.is_locked) {
      parts.push(`· ${t('createOrder.lotOptLocked', { orderNo: l.active_order_no || '' })}`)
    } else if (l.experiments_done && l.experiments_done.length) {
      parts.push(`· ${t('createOrder.lotOptDone', { n: l.experiments_done.length })}`)
    }
    return {
      value: l.code,
      label: parts.join(' '),
      // Disabled options stay visible in the dropdown so the requester
      // sees that lot exists and is reserved — they just can't pick it.
      disabled: l.is_locked,
    }
  }),
)

const selectedLotInfo = computed(() =>
  lots.value.find((l) => l.code === form.lot_id) || null,
)

const selectedLotIsLocked = computed(() => !!selectedLotInfo.value?.is_locked)

const selectedExperimentAlreadyDone = computed(() => {
  if (!selectedLotInfo.value || !form.experiment) return false
  return selectedLotInfo.value.experiments_done.some(
    (row) => row.experiment_id === form.experiment,
  )
})

const canSubmit = computed(() => {
  // Submit is allowed iff: experiment + lot picked, lot not locked, and
  // (lot, experiment) pair not already completed. The backend re-checks
  // these on the server side; this is just UX pre-warning.
  if (!form.experiment || !form.lot_id) return false
  if (selectedLotIsLocked.value) return false
  if (selectedExperimentAlreadyDone.value) return false
  return true
})

const experimentOptions = computed(() =>
  experiments.value.map((exp) => {
    const displayName = localized(exp)
    return {
      value: exp.id,
      label: exp.department_name ? `${displayName} (${exp.department_name})` : displayName,
    }
  }),
)

const selectedExp = computed(() =>
  experiments.value.find((e) => e.id === form.experiment),
)

async function refreshLots() {
  loadingLots.value = true
  try {
    const { data } = await fetchWaferLots()
    lots.value = data.results || data || []
  } catch {
    message.error(t('createOrder.loadLotsFailed'))
  } finally {
    loadingLots.value = false
  }
}

onMounted(async () => {
  loadingExperiments.value = true
  const [expRes] = await Promise.allSettled([fetchExperiments()])
  if (expRes.status === 'fulfilled') {
    experiments.value = expRes.value.data.results || expRes.value.data || []
  } else {
    message.error(t('createOrder.loadExpFailed'))
  }
  loadingExperiments.value = false
  await refreshLots()
})

async function handleSubmit() {
  error.value = ''
  loading.value = true
  try {
    const payload = {
      experiment: form.experiment,
      is_urgent: form.is_urgent,
      lot_id: form.lot_id,
      requirements: form.requirements,
      remark: form.remark,
    }
    const { data } = await createOrder(payload)
    createdOrderNo.value = data.order_no
    success.value = true
    // Reload the lot list so the lot we just claimed flips to "locked"
    // in the dropdown — otherwise "Submit another" would let the user
    // re-pick a lot the backend will now reject.
    refreshLots()
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
  form.lot_id = undefined
  form.requirements = ''
  form.remark = ''
  success.value = false
  createdOrderNo.value = null
  // Re-pull lots so the dropdown immediately reflects the newly-locked lot.
  refreshLots()
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
.lot-history-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--c-text-muted);
  margin-bottom: 6px;
}
.lot-history-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.lot-history-meta {
  opacity: 0.7;
  font-size: 11px;
}
</style>
