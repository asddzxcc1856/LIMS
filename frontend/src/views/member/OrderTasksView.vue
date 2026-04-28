<template>
  <div>
    <h1 class="page-title">Lab Execution Tasks</h1>

    <p class="text-muted mb-4" style="margin-top:-10px;">
      Perform and complete assigned experiment stages.
    </p>

    <div class="card table-wrapper">
      <table>
        <thead>
          <tr>
            <th>Order #</th>
            <th>Stage</th>
            <th>Equipment</th>
            <th>Lot ID</th>
            <th>Schedule</th>
            <th>Assigned To</th>
            <th>Action</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="s in tasks" :key="s.id" :class="{ 'my-task': isAssignedToMe(s) }">
            <td>{{ s.order_no || '—' }}</td>
            <td>
               <div class="flex flex-col">
                 <span class="font-bold">{{ s.equipment_type_name }}</span>
                 <span class="text-xs text-muted">Step {{ s.step_order }}</span>
               </div>
            </td>
            <td class="font-bold color-info">
              {{ s.equipment_code || '—' }}
            </td>
            <td class="text-muted">{{ s.lot_id }}</td>
            <td class="text-muted" style="font-size:.8rem;">
              {{ fmtDt(s.schedule_start) }} → {{ fmtDt(s.schedule_end) }}
            </td>
            <td>
              <span v-if="isAssignedToMe(s)" class="badge-me">Me</span>
              <span v-else-if="s.assignee_name" class="text-muted">{{ s.assignee_name }}</span>
              <span v-else class="text-muted"><i>Unassigned</i></span>
            </td>
            <td>
              <div v-if="isAssignedToMe(s)">
                <button 
                  class="btn btn-success btn-sm" 
                  :disabled="!canComplete(s)"
                  @click="handleComplete(s)"
                  :title="!canComplete(s) ? 'Task scheduled for future. Cannot complete yet.' : ''"
                >
                  Mark Stage Done
                </button>
                <div v-if="!canComplete(s)" class="text-xs text-danger mt-1">Not started yet</div>
              </div>
              <span v-else class="text-muted" style="font-size:.75rem;">Viewing Only</span>
            </td>
          </tr>
          <tr v-if="!tasks.length">
            <td colspan="7" class="text-muted" style="text-align:center;">No active stages in progress.</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { fetchStages, completeStage } from '../../api/orders'
import { useAuthStore } from '../../stores/auth'

const auth = useAuthStore()
const tasks = ref([])

onMounted(async () => {
  await loadTasks()
})

async function loadTasks() {
  // Query all IN_PROGRESS order stages
  // Managers see all in dept, Members see all in dept or assigned to them handled by backend
  const { data } = await fetchStages({ status: 'in_progress' })
  tasks.value = data.results || data
}

function isAssignedToMe(stage) {
  return stage.assignee === auth.user?.id
}

function canComplete(stage) {
  if (!stage.schedule_start) return true;
  return new Date() >= new Date(stage.schedule_start);
}

async function handleComplete(stage) {
  if (!confirm(`Mark Step ${stage.step_order} (${stage.equipment_type_name}) as completed?`)) return
  
  try {
    await completeStage(stage.id)
    await loadTasks()
  } catch (e) {
    alert(e.response?.data?.detail || 'Failed to complete stage.')
  }
}

function fmtDt(s) {
  if (!s) return '—'
  return new Date(s).toLocaleString('zh-TW', { dateStyle: 'short', timeStyle: 'short' })
}
</script>

<style scoped>
.my-task { background: rgba(0,206,201,.05); border-left: 3px solid var(--c-primary); }
.badge-me { background: var(--c-primary); color: white; padding: 2px 8px; border-radius: 999px; font-size: .7rem; font-weight: 700; }
.btn-sm { padding: 4px 10px; font-size: .8rem; }
.color-info { color: var(--c-info); }
.flex-col { display: flex; flex-direction: column; }
</style>
