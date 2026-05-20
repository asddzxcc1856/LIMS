<template>
  <div class="reports-page">
    <a-page-header
      :title="t('reports.title')"
      :sub-title="t('reports.subtitle')"
      :back-icon="false"
    >
      <template #extra>
        <a-radio-group v-model:value="days" button-style="solid" @change="reload">
          <a-radio-button :value="7">{{ t('reports.last7') }}</a-radio-button>
          <a-radio-button :value="14">{{ t('reports.last14') }}</a-radio-button>
          <a-radio-button :value="30">{{ t('reports.last30') }}</a-radio-button>
        </a-radio-group>
        <a-button @click="reload" :loading="loading">
          <template #icon><ReloadOutlined /></template>
          {{ t('common.refresh') }}
        </a-button>
      </template>
    </a-page-header>

    <a-row :gutter="[16, 16]">
      <a-col :xs="24" :md="12">
        <a-card
          :title="t('reports.utilizationTitle')"
          :bordered="false"
          :body-style="{ padding: '16px 16px 8px' }"
        >
          <a-spin :spinning="loading">
            <LineChart
              v-if="utilizationSeries.length"
              :data="utilizationSeries"
              :series="[{ name: t('reports.utilizationPct'), key: 'utilization', color: '#1890ff' }]"
              :y-max="100"
              :y-format="(v) => `${v}%`"
              :aria-label="t('reports.utilizationTitle')"
            />
            <a-empty v-else :description="t('reports.noData')" />
          </a-spin>
          <div class="card-foot">
            {{ t('reports.utilizationHint') }}
          </div>
        </a-card>
      </a-col>

      <a-col :xs="24" :md="12">
        <a-card
          :title="t('reports.orderTrendTitle')"
          :bordered="false"
          :body-style="{ padding: '16px 16px 8px' }"
        >
          <a-spin :spinning="loading">
            <LineChart
              v-if="orderTrendSeries.length"
              :data="orderTrendSeries"
              :series="[
                { name: t('reports.orderCreated'), key: 'created', color: '#1890ff' },
                { name: t('reports.orderDone'), key: 'done', color: '#52c41a' },
                { name: t('reports.orderRejected'), key: 'rejected', color: '#f5222d' },
              ]"
              :aria-label="t('reports.orderTrendTitle')"
            />
            <a-empty v-else :description="t('reports.noData')" />
          </a-spin>
          <div class="card-foot">
            {{ t('reports.orderTrendHint') }}
          </div>
        </a-card>
      </a-col>
    </a-row>

    <a-card
      :title="t('reports.operatorTitle')"
      :bordered="false"
      style="margin-top: 16px"
      :body-style="{ padding: '16px' }"
    >
      <a-spin :spinning="loading">
        <BarChart
          v-if="operatorRows.length"
          :data="operatorRows"
          :aria-label="t('reports.operatorTitle')"
        />
        <a-empty v-else :description="t('reports.noData')" />
      </a-spin>
      <div class="card-foot">
        {{ t('reports.operatorHint') }}
      </div>

      <!-- Detailed table — every operator with breakdown of events +
           approvals so the manager can review individual work -->
      <a-divider />
      <a-table
        :columns="operatorTableColumns"
        :data-source="operatorTableRows"
        :pagination="{ pageSize: 10, showTotal: paginationTotal }"
        size="small"
        row-key="user_id"
        :scroll="{ x: 'max-content' }"
      />
    </a-card>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ReloadOutlined } from '@ant-design/icons-vue'
import {
  fetchChartEquipmentUtilization,
  fetchChartOperatorActivity,
  fetchChartOrderTrend,
} from '../../api/admin'
import LineChart from '../../components/charts/LineChart.vue'
import BarChart from '../../components/charts/BarChart.vue'

const { t } = useI18n()

const loading = ref(false)
const days = ref(14)
const utilizationSeries = ref([])
const orderTrendSeries = ref([])
const operatorRows = ref([])

const paginationTotal = (n) => t('crud.paginationTotal', { total: n })

const operatorTableColumns = computed(() => [
  { title: t('reports.operatorName'), dataIndex: 'username' },
  { title: t('reports.operatorEvents'), dataIndex: 'events', width: 120, sorter: true },
  { title: t('reports.operatorApprovals'), dataIndex: 'approvals', width: 120, sorter: true },
  { title: t('reports.operatorTotal'), dataIndex: 'total', width: 120, sorter: true },
])

const operatorTableRows = computed(() =>
  operatorRows.value.map((row) => ({
    ...row,
    user_id: row.user_id || row.username,
    total: (row.events || 0) + (row.approvals || 0),
  })),
)

onMounted(reload)

async function reload() {
  loading.value = true
  try {
    const [{ data: util }, { data: trend }, { data: ops }] = await Promise.all([
      fetchChartEquipmentUtilization(days.value),
      fetchChartOrderTrend(days.value),
      fetchChartOperatorActivity({ days: 30, limit: 12 }),
    ])
    utilizationSeries.value = util.series || []
    orderTrendSeries.value = trend.series || []
    operatorRows.value = (ops.series || []).map((row) => ({
      ...row,
      label: row.username,
      value: (row.events || 0) + (row.approvals || 0),
    }))
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.reports-page { padding: 0; }
.card-foot {
  margin-top: 8px;
  color: var(--c-text-muted);
  font-size: 12px;
}
</style>
