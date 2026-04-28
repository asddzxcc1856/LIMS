<template>
  <div>
    <h1 class="page-title">My Orders</h1>

    <div class="card table-wrapper">
      <table>
        <thead>
          <tr>
            <th>#</th>
            <th>Experiment</th>
            <th>Lot ID</th>
            <th>Relay Progress</th>
            <th>Overall Status</th>
            <th>Action</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="o in orders" :key="o.id">
            <td>{{ o.order_no }}</td>
            <td class="font-bold">{{ o.experiment_name }}</td>
            <td class="text-muted">{{ o.lot_id }}</td>
            <td>
              <!-- Inline Relay Progress -->
              <div class="relay-mini-track">
                <div v-for="s in o.stages" :key="s.id" 
                     class="relay-dot" 
                     :class="'status-' + s.status"
                     :title="`${s.department_name}: ${s.equipment_type_name} (${s.status})`">
                </div>
              </div>
            </td>
            <td><span :class="'badge badge-' + o.status">{{ o.status }}</span></td>
            <td>
              <button class="btn btn-outline btn-sm" @click="viewDetail(o)">View Details</button>
            </td>
          </tr>
          <tr v-if="!orders.length">
            <td colspan="6" class="text-muted" style="text-align:center;">No orders yet.</td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Order Detail Modal -->
    <div v-if="selectedOrder" class="modal-overlay" @click.self="selectedOrder = null">
      <div class="card modal-card">
        <div class="modal-header">
          <h3>Order Detail: {{ selectedOrder.order_no }}</h3>
          <button class="close-btn" @click="selectedOrder = null">&times;</button>
        </div>

        <!-- Advanced Relay Tracker -->
        <div class="relay-tracker-container mb-8">
          <h4 class="text-sm font-bold mb-4 uppercase tracking-wider text-muted">Experiment Relay Pipeline</h4>
          <div class="relay-tracker">
            <div v-for="(stage, idx) in selectedOrder.stages" :key="stage.id" 
                 class="relay-step" 
                 :class="{ 
                    'active': stage.status === 'in_progress', 
                    'waiting': stage.status === 'waiting',
                    'completed': stage.status === 'done',
                    'pending': stage.status === 'pending'
                 }">
              <div class="relay-circle">
                <i v-if="stage.status === 'done'">✓</i>
                <span v-else>{{ idx + 1 }}</span>
              </div>
              <div class="relay-info text-center">
                <div class="relay-lab">{{ stage.department_name }}</div>
                <div class="relay-eq">{{ stage.equipment_type_name }}</div>
                <div class="relay-status-text">{{ stage.status }}</div>
              </div>
              <div v-if="idx < selectedOrder.stages.length - 1" class="relay-line"></div>
            </div>
          </div>
        </div>

        <div class="modal-content grid grid-cols-2 gap-4">
          <section>
            <h4>General Information</h4>
            <p><strong>Experiment:</strong> {{ selectedOrder.experiment_name }}</p>
            <p><strong>Lot ID:</strong> {{ selectedOrder.lot_id || '—' }}</p>
            <p><strong>Total Status:</strong> <span :class="'badge badge-' + selectedOrder.status">{{ selectedOrder.status }}</span></p>
            <p><strong>Urgent:</strong> {{ selectedOrder.is_urgent ? '🔴 Yes' : 'No' }}</p>
          </section>
          
          <section>
            <h4>Current / Last Active Station</h4>
            <div v-if="currentStage" class="active-stage-box">
              <p><strong>Lab:</strong> {{ currentStage.department_name }}</p>
              <p><strong>Member:</strong> {{ currentStage.assignee_name || 'Not assigned' }}</p>
              <p><strong>Equipment:</strong> {{ currentStage.equipment_code || 'TBD' }}</p>
              <p v-if="currentStage.schedule_start">
                <strong>Schedule:</strong> {{ fmtDt(currentStage.schedule_start) }}
              </p>
            </div>
            <p v-else class="text-muted">No active station.</p>
          </section>

          <section class="col-span-2" v-if="selectedOrder.rejection_reason">
            <h4 style="color:var(--c-danger);">Rejection Reason</h4>
            <div class="rejection-box">{{ selectedOrder.rejection_reason }}</div>
          </section>

          <section class="col-section col-span-2">
            <h4>Remarks</h4>
            <p class="text-muted">{{ selectedOrder.remark || 'No remark provided.' }}</p>
          </section>
        </div>

        <div class="modal-footer">
          <button class="btn btn-outline" @click="selectedOrder = null">Close</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { fetchOrders, fetchOrder } from '../../api/orders'

const orders = ref([])
const selectedOrder = ref(null)

const currentStage = computed(() => {
  if (!selectedOrder.value || !selectedOrder.value.stages) return null
  // Return the first stage that isn't DONE, or the last stage if all are done
  const active = selectedOrder.value.stages.find(s => s.status !== 'done')
  return active || selectedOrder.value.stages[selectedOrder.value.stages.length - 1]
})

onMounted(async () => {
  const { data } = await fetchOrders()
  orders.value = data.results || data
})

async function viewDetail(order) {
  try {
    const { data } = await fetchOrder(order.id)
    selectedOrder.value = data
  } catch (e) {
    alert('Failed to load order detail.')
  }
}

function fmtDt(s) {
  if (!s) return '—'
  return new Date(s).toLocaleString('zh-TW', { dateStyle: 'short', timeStyle: 'short' })
}
</script>

<style scoped>
.modal-overlay {
  position: fixed; inset: 0; background: rgba(0,0,0,.6); display: flex;
  align-items: center; justify-content: center; z-index: 100; padding: 20px;
}
.modal-card { width: 100%; max-width: 800px; max-height: 90vh; overflow-y: auto; background: var(--c-bg-card); position: relative; }
.modal-header { display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--c-border); padding-bottom: 12px; margin-bottom: 20px; }
.close-btn { background: none; border: none; font-size: 1.5rem; cursor: pointer; color: var(--c-text-muted); }
.modal-content h4 { margin-top: 0; margin-bottom: 8px; font-size: .85rem; color: var(--c-primary); border-bottom: 1px solid var(--c-border); padding-bottom: 4px; uppercase: true; }
.modal-footer { margin-top: 24px; border-top: 1px solid var(--c-border); padding-top: 16px; text-align: right; }

.grid { display: grid; }
.grid-cols-2 { grid-template-columns: 1fr 1fr; }
.col-span-2 { grid-column: span 2; }
.gap-4 { gap: 1rem; }
.mb-8 { margin-bottom: 2rem; }

.relay-mini-track { display: flex; gap: 4px; }
.relay-dot { width: 10px; height: 10px; border-radius: 50%; background: var(--c-border); }
.relay-dot.status-done { background: var(--c-success); }
.relay-dot.status-in_progress { background: var(--c-info); animation: pulse 2s infinite; }
.relay-dot.status-waiting { background: var(--c-warning); }

@keyframes pulse {
  0% { transform: scale(1); opacity: 1; }
  50% { transform: scale(1.3); opacity: 0.7; }
  100% { transform: scale(1); opacity: 1; }
}

/* Advanced Relay Tracker */
.relay-tracker { display: flex; align-items: flex-start; justify-content: space-around; position: relative; }
.relay-step { position: relative; flex: 1; display: flex; flex-direction: column; align-items: center; }
.relay-circle { 
  width: 36px; height: 36px; border-radius: 50%; background: var(--c-bg); border: 3px solid var(--c-border);
  display: flex; align-items: center; justify-content: center; font-weight: bold; z-index: 2; margin-bottom: 12px;
  transition: all 0.3s;
}
.relay-line { position: absolute; top: 18px; left: calc(50% + 18px); right: calc(-50% + 18px); height: 3px; background: var(--c-border); z-index: 1; }

.relay-step.completed .relay-circle { background: var(--c-success); border-color: var(--c-success); color: white; }
.relay-step.completed .relay-line { background: var(--c-success); }
.relay-step.active .relay-circle { background: var(--c-info); border-color: var(--c-info); color: white; box-shadow: 0 0 15px var(--c-info); }
.relay-step.waiting .relay-circle { border-color: var(--c-warning); color: var(--c-warning); }

.relay-lab { font-size: 0.7rem; font-weight: bold; color: var(--c-text-muted); text-transform: uppercase; }
.relay-eq { font-size: 0.85rem; font-weight: 700; margin: 2px 0; }
.relay-status-text { font-size: 0.65rem; padding: 2px 6px; border-radius: 10px; background: var(--c-bg); border: 1px solid var(--c-border); display: inline-block; }

.active-stage-box { background: rgba(0,0,0,0.03); border: 1px dashed var(--c-border); padding: 12px; border-radius: 8px; font-size: 0.85rem; }
.rejection-box { background: rgba(255,107,107,.1); border-left: 4px solid var(--c-danger); padding: 12px; font-size: .9rem; color: var(--c-danger); }
</style>
