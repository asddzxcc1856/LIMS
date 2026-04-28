<template>
  <div>
    <h1 class="page-title">Create Order</h1>

    <div v-if="success" class="alert-success mb-4">
      ✅ Order {{ createdOrderNo }} submitted! Status: Waiting for review.
    </div>
    <div v-if="error" class="alert-error mb-4">{{ error }}</div>

    <div class="create-layout">
      <!-- Main form -->
      <form class="card" @submit.prevent="handleSubmit">
        <div class="form-group">
          <label for="experiment">Experiment</label>
          <select id="experiment" v-model="form.experiment" required @change="onExperimentChange">
            <option value="" disabled>Select experiment…</option>
            <option v-for="exp in experiments" :key="exp.id" :value="exp.id">
              {{ exp.name }}
            </option>
          </select>
        </div>

        <div class="form-group">
          <label for="lot_id">Lot ID</label>
          <input id="lot_id" v-model="form.lot_id" placeholder="e.g. LOT-2026-A001" />
        </div>

        <div class="form-group">
          <label style="display:flex;align-items:center;gap:8px;cursor:pointer;">
            <input type="checkbox" v-model="form.is_urgent" style="width:auto;" />
            Urgent Request
          </label>
        </div>

        <div class="form-group">
          <label for="remark">Remark</label>
          <textarea id="remark" v-model="form.remark" rows="3"></textarea>
        </div>

        <p class="text-muted" style="font-size:.8rem;margin-bottom:16px;">
          ℹ️ Schedule time will be determined by the Lab Manager during review.
        </p>

        <button class="btn btn-primary" :disabled="loading">
          {{ loading ? 'Submitting…' : 'Submit Order' }}
        </button>
      </form>

      <!-- Side panel: equipment requirements + capacity alert -->
      <div v-if="selectedExp" class="side-panel card">
        <h3 style="font-size:1rem;margin-bottom:12px;">📋 Required Equipment</h3>
        <ul class="req-list">
          <li v-for="req in selectedExp.required_equipments" :key="req.id" class="req-item">
            <span class="req-step">Step {{ req.step_order }}:</span>
            <span class="req-type">{{ req.equipment_type_name }}</span>
            <span class="req-lab">({{ req.department_name }})</span>
          </li>
        </ul>

        <!-- Capacity Alert -->
        <div v-if="capacity" style="margin-top:16px;">
          <div v-if="capacity.has_shortage" class="capacity-alert">
            ⚠️ 設備資源不足，預計排程需延後
          </div>
          <div v-else class="capacity-ok">
            ✅ 設備資源充足
          </div>
          <div v-for="d in capacity.details" :key="d.equipment_type" class="capacity-row">
            <span>{{ d.equipment_type }}</span>
            <span :class="d.shortage ? 'shortage' : 'sufficient'">
              {{ d.available }} / {{ d.required }} available
            </span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { fetchExperiments, fetchCapacityCheck } from '../../api/equipments'
import { createOrder } from '../../api/orders'

const experiments = ref([])
const form = ref({ experiment: '', is_urgent: false, lot_id: '', remark: '' })
const loading = ref(false)
const success = ref(false)
const createdOrderNo = ref(null)
const error = ref('')
const capacity = ref(null)

const selectedExp = computed(() => experiments.value.find(e => e.id === form.value.experiment))

onMounted(async () => {
  const { data } = await fetchExperiments()
  experiments.value = data.results || data
})

async function onExperimentChange() {
  capacity.value = null
  if (form.value.experiment) {
    try {
      const { data } = await fetchCapacityCheck(form.value.experiment)
      capacity.value = data
    } catch { /* ignore */ }
  }
}

async function handleSubmit() {
  error.value = ''
  success.value = false
  loading.value = true
  try {
    const { data } = await createOrder(form.value)
    createdOrderNo.value = data.order_no
    success.value = true
    form.value = { experiment: '', is_urgent: false, lot_id: '', remark: '' }
    capacity.value = null
  } catch (e) {
    error.value = e.response?.data?.detail || JSON.stringify(e.response?.data) || 'Submission failed'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.create-layout { display: grid; grid-template-columns: 1fr 320px; gap: 24px; align-items: start; }
@media (max-width: 800px) { .create-layout { grid-template-columns: 1fr; } }

.side-panel { position: sticky; top: 32px; }

.alert-success { background:rgba(0,206,201,.12); color:var(--c-success); padding:10px 14px; border-radius:var(--radius); font-size:.9rem; }
.alert-error { background:rgba(255,107,107,.12); color:var(--c-danger); padding:10px 14px; border-radius:var(--radius); font-size:.9rem; }
.req-list { list-style:none; padding:0; display: flex; flex-direction: column; gap: 8px; }
.req-item { font-size:.85rem; display: flex; flex-direction: column; }
.req-step { font-weight: 700; color: var(--c-text-muted); font-size: 0.7rem; text-transform: uppercase; }
.req-type { color: var(--c-info); font-weight: 600; }
.req-lab { color: var(--c-text-muted); font-size: 0.75rem; font-style: italic; }

.capacity-alert { background:rgba(255,107,107,.12); color:var(--c-danger); padding:10px 14px; border-radius:var(--radius); font-size:.85rem; font-weight:600; margin-bottom:8px; }
.capacity-ok { background:rgba(0,206,201,.12); color:var(--c-success); padding:10px 14px; border-radius:var(--radius); font-size:.85rem; font-weight:600; margin-bottom:8px; }
.capacity-row { display:flex; justify-content:space-between; padding:4px 0; font-size:.85rem; }
.shortage { color:var(--c-danger); font-weight:600; }
.sufficient { color:var(--c-success); }
</style>
