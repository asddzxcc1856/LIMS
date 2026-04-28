<template>
  <div>
    <h1 class="page-title">Equipment Status Dashboard</h1>

    <div class="matrix-grid">
      <div v-for="group in matrix" :key="group.type_id" class="card eq-group">
        <h3 class="group-title">{{ group.type_name }}</h3>
        <div class="eq-items">
          <div
            v-for="eq in group.equipments"
            :key="eq.id"
            class="eq-card"
            :class="'status-' + eq.status"
            @click="eq.active_order ? showOrder(eq) : null"
            :style="{ cursor: eq.active_order ? 'pointer' : 'default' }"
          >
            <div class="eq-indicator"></div>
            <div class="eq-info">
              <div class="eq-code">{{ eq.code }}</div>
              <div class="eq-dept">{{ eq.department_name }}</div>
              <div class="eq-status-text">{{ statusLabel(eq.status) }}</div>
            </div>
            <div v-if="eq.active_order" class="eq-order-badge">
              {{ eq.active_order.order_no }}
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Legend -->
    <div class="legend mt-4">
      <span class="legend-item"><span class="dot dot-available"></span> Available</span>
      <span class="legend-item"><span class="dot dot-occupied"></span> Occupied</span>
      <span class="legend-item"><span class="dot dot-maintenance"></span> Maintenance</span>
      <span class="legend-item"><span class="dot dot-inactive"></span> Inactive</span>
    </div>

    <!-- Order detail popup -->
    <div v-if="selectedEq" class="modal-overlay" @click.self="selectedEq = null">
      <div class="card modal-card">
        <h3 style="margin-bottom:8px;">{{ selectedEq.code }} — Active Order</h3>
        <div v-if="selectedEq.active_order">
          <p><strong>Order:</strong> {{ selectedEq.active_order.order_no }}</p>
          <p><strong>Schedule:</strong> {{ fmtDt(selectedEq.active_order.started_at) }} → {{ fmtDt(selectedEq.active_order.ended_at) }}</p>
        </div>
        <button class="btn btn-outline mt-4" @click="selectedEq = null">Close</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { fetchStatusMatrix } from '../api/equipments'

const matrix = ref([])
const selectedEq = ref(null)

onMounted(async () => {
  const { data } = await fetchStatusMatrix()
  matrix.value = data
})

function statusLabel(s) {
  const map = { available: 'Available', occupied: 'Occupied', maintenance: 'Maintenance', inactive: 'Inactive' }
  return map[s] || s
}

function showOrder(eq) {
  selectedEq.value = eq
}

function fmtDt(s) {
  if (!s) return '—'
  return new Date(s).toLocaleString('zh-TW', { dateStyle: 'short', timeStyle: 'short' })
}
</script>

<style scoped>
.matrix-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 16px; }

.eq-group { }
.group-title { font-size: .95rem; font-weight: 700; margin-bottom: 12px; }

.eq-items { display: flex; flex-direction: column; gap: 8px; }

.eq-card {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  border-radius: 8px;
  background: var(--c-bg);
  border: 1px solid var(--c-border);
  transition: transform .15s, box-shadow .15s;
}
.eq-card:hover { transform: translateY(-1px); box-shadow: 0 4px 12px rgba(0,0,0,.2); }

.eq-indicator {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}
.status-available .eq-indicator { background: var(--c-success); box-shadow: 0 0 6px var(--c-success); }
.status-occupied .eq-indicator  { background: var(--c-info);    box-shadow: 0 0 6px var(--c-info); }
.status-maintenance .eq-indicator { background: var(--c-danger); box-shadow: 0 0 6px var(--c-danger); }
.status-inactive .eq-indicator { background: var(--c-text-muted); }

.eq-info { flex: 1; }
.eq-code { font-weight: 600; font-size: .9rem; }
.eq-dept { font-size: .7rem; color: var(--c-info); font-weight: 500; }
.eq-status-text { font-size: .75rem; color: var(--c-text-muted); }

.eq-order-badge {
  font-size: .7rem;
  background: rgba(116,185,255,.15);
  color: var(--c-info);
  padding: 2px 8px;
  border-radius: 999px;
  font-weight: 600;
}

/* Legend */
.legend { display: flex; gap: 20px; flex-wrap: wrap; }
.legend-item { display: flex; align-items: center; gap: 6px; font-size: .8rem; color: var(--c-text-muted); }
.dot { width: 8px; height: 8px; border-radius: 50%; }
.dot-available { background: var(--c-success); }
.dot-occupied { background: var(--c-info); }
.dot-maintenance { background: var(--c-danger); }
.dot-inactive { background: var(--c-text-muted); }

/* Modal */
.modal-overlay {
  position: fixed; inset: 0; background: rgba(0,0,0,.6); display: flex;
  align-items: center; justify-content: center; z-index: 100;
}
.modal-card { width: 100%; max-width: 400px; }
</style>
