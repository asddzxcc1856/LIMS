<template>
  <div class="create-page">
    <a-page-header title="送樣申請" sub-title="選擇實驗類型,Lab Manager 將安排設備與時間" :back-icon="false" />

    <a-row :gutter="[16, 16]">
      <a-col :xs="24" :lg="14">
        <a-card :bordered="false" title="申請表單">
          <a-result
            v-if="success"
            status="success"
            :title="`訂單 ${createdOrderNo} 已成功送出!`"
            sub-title="狀態為「等待中」,Lab Manager 將進行排程審核"
          >
            <template #extra>
              <a-button type="primary" @click="resetForm">繼續送樣</a-button>
              <a-button @click="$router.push('/orders')">查看訂單清單</a-button>
            </template>
          </a-result>

          <a-form
            v-else
            :model="form"
            layout="vertical"
            @finish="handleSubmit"
          >
            <a-form-item
              label="實驗類型"
              name="experiment"
              :rules="[{ required: true, message: '請選擇實驗類型' }]"
            >
              <a-select
                v-model:value="form.experiment"
                placeholder="請選擇要進行的實驗"
                show-search
                option-filter-prop="label"
                size="large"
                @change="onExperimentChange"
                :options="experimentOptions"
              />
            </a-form-item>

            <a-form-item label="Lot ID" name="lot_id">
              <a-input
                v-model:value="form.lot_id"
                placeholder="例如: LOT-2026-A001"
                size="large"
              />
            </a-form-item>

            <a-form-item name="is_urgent">
              <a-checkbox v-model:checked="form.is_urgent">
                <a-tag color="red" style="margin-right: 6px">緊急</a-tag>
                標記為緊急訂單(優先排程)
              </a-checkbox>
            </a-form-item>

            <a-form-item label="備註" name="remark">
              <a-textarea
                v-model:value="form.remark"
                :rows="3"
                placeholder="任何需要 Lab Manager 知道的細節..."
              />
            </a-form-item>

            <a-alert
              type="info"
              show-icon
              message="排程時間將由 Lab Manager 在審核階段決定"
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
              送出申請
            </a-button>
          </a-form>
        </a-card>
      </a-col>

      <a-col :xs="24" :lg="10">
        <a-card
          v-if="!form.experiment"
          :bordered="false"
          title="設備需求預覽"
        >
          <a-empty description="請先選擇實驗類型,系統將顯示所需設備與容量" />
        </a-card>

        <template v-else>
          <a-card :bordered="false" title="所需設備清單" class="side-card">
            <a-list
              :data-source="selectedExp?.required_equipments || []"
              size="small"
            >
              <template #renderItem="{ item }">
                <a-list-item>
                  <a-list-item-meta>
                    <template #title>
                      <a-space>
                        <a-tag color="blue">Step {{ item.step_order }}</a-tag>
                        <span class="font-bold">{{ item.equipment_type_name }}</span>
                      </a-space>
                    </template>
                    <template #description>
                      <span class="muted">{{ item.department_name }} · 數量 {{ item.quantity }}</span>
                    </template>
                  </a-list-item-meta>
                </a-list-item>
              </template>
              <template #loadMore>
                <a-empty
                  v-if="!(selectedExp?.required_equipments || []).length"
                  description="此實驗未定義設備需求"
                />
              </template>
            </a-list>
          </a-card>

          <a-card
            v-if="capacity"
            :bordered="false"
            title="設備容量檢查"
            class="side-card"
            style="margin-top: 16px"
          >
            <a-alert
              v-if="capacity.has_shortage"
              type="warning"
              show-icon
              message="設備資源不足"
              description="預計排程可能延後,請考慮非緊急訂單"
              style="margin-bottom: 12px"
            />
            <a-alert
              v-else
              type="success"
              show-icon
              message="設備資源充足,可立即排程"
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
import { message } from 'ant-design-vue'
import { SendOutlined } from '@ant-design/icons-vue'
import { fetchCapacityCheck, fetchExperiments } from '../../api/equipments'
import { createOrder } from '../../api/orders'

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
    message.error('載入實驗清單失敗')
  }
})

async function onExperimentChange() {
  capacity.value = null
  if (!form.experiment) return
  try {
    const { data } = await fetchCapacityCheck(form.experiment)
    capacity.value = data
  } catch {
    /* capacity check 是輔助資訊,失敗不阻止建單 */
  }
}

async function handleSubmit() {
  error.value = ''
  loading.value = true
  try {
    const { data } = await createOrder(form)
    createdOrderNo.value = data.order_no
    success.value = true
    message.success(`訂單 ${data.order_no} 建立成功`)
  } catch (e) {
    const data = e.response?.data
    if (typeof data === 'string') error.value = data
    else if (data?.detail) error.value = data.detail
    else if (data && typeof data === 'object') {
      const k = Object.keys(data)[0]
      error.value = `${k}: ${Array.isArray(data[k]) ? data[k].join(', ') : data[k]}`
    } else error.value = '送出失敗'
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
  color: rgba(0, 0, 0, 0.45);
  font-size: 12px;
}
.font-bold {
  font-weight: 600;
}
.side-card :deep(.ant-card-body) {
  padding: 12px 16px;
}
</style>
