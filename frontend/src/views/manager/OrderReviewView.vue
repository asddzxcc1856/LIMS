<template>
  <div>
    <div class="mb-6">
      <h1 class="page-title">Pending Lab Tasks (Waiting)</h1>
      <p class="text-muted" style="margin-top:-10px;">Review and schedule stages for your laboratory.</p>
    </div>

    <!-- Timeline Chart for Scheduling Awareness -->
    <TimelineChart 
      :grouped-equipments="groupedEquipments" 
      :bookings="allBookings" 
      class="mb-8" 
      @booking-click="openEditBooking"
    />

    <div class="card table-wrapper">
      <table>
        <thead>
          <tr>
            <th>Order #</th>
            <th>Step</th>
            <th>Equipment Type</th>
            <th>Requester</th>
            <th>Lot ID</th>
            <th>Wait Time</th>
            <th>Action</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="s in waitingStages" :key="s.id">
            <td>{{ s.order_no || '—' }}</td>
            <td><span class="badge badge-outline">Step {{ s.step_order }}</span></td>
            <td class="font-bold underline">{{ s.equipment_type_name }}</td>
            <td>{{ s.user_name || '—' }}</td>
            <td class="text-muted">{{ s.lot_id || "—" }}</td>
            <td class="text-muted" style="font-size: 0.8rem">
              {{ s.wait_duration }}
            </td>
            <td>
              <div class="flex gap-2">
                <button class="btn btn-success btn-sm" @click="openApprove(s)">
                  Schedule & Approve
                </button>
                <button class="btn btn-danger btn-sm" @click="openReject(s)">
                  Reject Order
                </button>
              </div>
            </td>
          </tr>
          <tr v-if="!waitingStages.length">
            <td colspan="7" class="text-muted" style="text-align: center">
              No pending tasks for your lab.
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Approve modal for the SPECIFIC STAGE -->
    <div v-if="approveTarget" class="modal-overlay" @click.self="approveTarget = null">
      <div class="card modal-card">
        <h3 style="margin-bottom: 4px">Approve Stage: {{ approveTarget.equipment_type_name }}</h3>
        <p class="text-muted" style="font-size: 0.85rem; margin-bottom: 16px">
          Order: {{ approveTarget.order_no }} | Step {{ approveTarget.step_order }}
        </p>

        <div v-if="approveError" class="alert-error mb-4">{{ approveError }}</div>
        <div v-if="scheduleWarning" class="alert-warning mb-4">{{ scheduleWarning }}</div>

        <div class="grid grid-cols-2 gap-4">
          <div class="form-group">
            <label>Schedule Start</label>
            <input type="datetime-local" v-model="scheduleStart" @change="validateSchedule" required />
          </div>
          <div class="form-group">
            <label>Schedule End</label>
            <input type="datetime-local" v-model="scheduleEnd" @change="validateSchedule" required />
          </div>
          <div class="form-group col-span-2">
            <label>Assign Member</label>
            <select v-model="assignee">
              <option :value="null">-- Unassigned (Station Group) --</option>
              <option v-for="u in members" :key="u.id" :value="u.id">
                {{ u.username }} ({{ u.role }})
              </option>
            </select>
          </div>
        </div>

        <div class="flex gap-2" style="margin-top: 24px">
          <button class="btn btn-success" @click="confirmApprove" :disabled="approveBusy || !!scheduleWarning">
            {{ approveBusy ? "Allocating…" : "Confirm Allocation" }}
          </button>
          <button class="btn btn-outline" @click="approveTarget = null">Cancel</button>
        </div>
      </div>
    </div>

    <!-- Reject modal -->
    <div v-if="rejectTarget" class="modal-overlay" @click.self="rejectTarget = null">
      <div class="card modal-card" style="max-width: 400px">
        <h3 style="margin-bottom: 12px">Reject Order {{ rejectTarget.order_no }}</h3>
        <div class="form-group">
          <label>Rejection Reason <span style="color: var(--c-danger)">*</span></label>
          <textarea v-model="rejectReason" rows="3" placeholder="Specify reason..." required></textarea>
        </div>
        <div class="flex gap-2">
          <button class="btn btn-danger" @click="confirmReject" :disabled="!rejectReason.trim()">Confirm Reject</button>
          <button class="btn btn-outline" @click="rejectTarget = null">Cancel</button>
        </div>
      </div>
    </div>

    <!-- Active Tasks for Personnel Reassignment -->
    <div class="mt-12">
      <h2 style="font-size: 1.25rem; font-weight: 700; margin-bottom: 12px; display: flex; align-items: center; gap: 8px;">
        🏃 Managed Tasks (In Progress)
      </h2>
      <div class="card table-wrapper">
        <table>
          <thead>
            <tr>
              <th>Order #</th>
              <th>Step</th>
              <th>Equipment Type</th>
              <th>Assignee</th>
              <th>Schedule</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="s in activeStages" :key="s.id">
              <td>{{ s.order_no }}</td>
              <td><span class="badge badge-outline">Step {{ s.step_order }}</span></td>
              <td>{{ s.equipment_type_name }}</td>
              <td>
                <span v-if="s.assignee_name" class="assignee-badge">👤 {{ s.assignee_name }}</span>
                <span v-else class="text-muted">Unassigned</span>
              </td>
              <td class="text-xs">
                {{ fmtDt(s.schedule_start) }} <br/> → {{ fmtDt(s.schedule_end) }}
              </td>
              <td>
                <button class="btn btn-outline btn-sm" @click="openReassign(s)">Reassign / Edit</button>
              </td>
            </tr>
            <tr v-if="!activeStages.length">
              <td colspan="6" class="text-muted" style="text-align: center">No active tasks currently.</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Reassign Modal -->
    <div v-if="reassignTarget" class="modal-overlay" @click.self="reassignTarget = null">
      <div class="card modal-card" style="max-width: 450px">
        <h3 style="margin-bottom: 12px">Reassign Task: {{ reassignTarget.order_no }}</h3>
        
        <div class="form-group">
          <label>New Assignee</label>
          <select v-model="reassignAssignee">
            <option :value="null">-- Unassigned --</option>
            <option v-for="u in members" :key="u.id" :value="u.id">{{ u.username }}</option>
          </select>
        </div>

        <div class="grid grid-cols-2 gap-4">
          <div class="form-group">
            <label>Adjust Start</label>
            <input type="datetime-local" v-model="reassignStart" />
          </div>
          <div class="form-group">
            <label>Adjust End</label>
            <input type="datetime-local" v-model="reassignEnd" />
          </div>
        </div>

        <div class="flex gap-2" style="margin-top: 16px">
          <button class="btn btn-primary" @click="confirmReassign" :disabled="reassignBusy">Save Changes</button>
          <button class="btn btn-outline" @click="reassignTarget = null">Cancel</button>
        </div>
      </div>
    </div>

    <!-- Edit Booking Modal (Timeline) -->
    <div v-if="editBookingTarget" class="modal-overlay" @click.self="editBookingTarget = null">
       <!-- ... keep existing edit logic ... -->
       <div class="card modal-card" style="max-width:400px;">
        <h3 style="margin-bottom:12px;">Modify Booking: {{ editBookingTarget.order_no }}</h3>
        <p class="text-muted mb-4">{{ editBookingTarget.equipment_code }} ({{ editBookingTarget.equipment_type_name }})</p>
        <div v-if="editBookingError" class="alert-error mb-4">{{ editBookingError }}</div>
        <div class="form-group">
          <label>Start Time</label>
          <input type="datetime-local" v-model="editBookingStart" />
        </div>
        <div class="form-group">
          <label>End Time</label>
          <input type="datetime-local" v-model="editBookingEnd" />
        </div>
        <div class="flex gap-2 font-mt-4">
          <button class="btn btn-primary" @click="saveBookingUpdate" :disabled="editBookingBusy">Save Changes</button>
          <button class="btn btn-outline" @click="editBookingTarget = null">Cancel</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from "vue";
import { fetchStages, reviewStage } from "../../api/orders";
import { fetchBookings } from "../../api/scheduling";
import TimelineChart from "../../components/TimelineChart.vue";
import client from "../../api/client";

const stages = ref([]);
const members = ref([]);
const groupedEquipments = ref([]);
const allBookings = ref([]);
const currentUser = ref(null);

// Approve state
const approveTarget = ref(null);
const scheduleStart = ref("");
const scheduleEnd = ref("");
const assignee = ref(null);
const approveBusy = ref(false);
const approveError = ref("");
const scheduleWarning = ref("");

// Reject state
const rejectTarget = ref(null);
const rejectReason = ref("");

// Edit Booking (Timeline) state
const editBookingTarget = ref(null);
const editBookingStart = ref("");
const editBookingEnd = ref("");
const editBookingBusy = ref(false);
const editBookingError = ref("");

const waitingStages = computed(() => stages.value.filter(s => s.status === 'waiting'));
const activeStages = computed(() => stages.value.filter(s => s.status === 'in_progress'));

// Reassign state
const reassignTarget = ref(null);
const reassignAssignee = ref(null);
const reassignStart = ref("");
const reassignEnd = ref("");
const reassignBusy = ref(false);

onMounted(async () => {
  await loadStages();
  await loadMembers();
  await loadTimelineData();
});

async function loadStages() {
  const { data } = await fetchStages(); // Fetch all stages for my lab
  stages.value = (data.results || data).map(s => ({
    ...s,
    wait_duration: s.status === 'waiting' ? 'Pending' : 'In Progress'
  }));
}

async function loadTimelineData() {
  const [resEq, resBk, resProf] = await Promise.all([
    client.get('/equipments/status-matrix/'),
    fetchBookings(),
    client.get('/users/profile/')
  ]);
  
  currentUser.value = resProf.data;
  const myDept = resProf.data.department_name;

  // Filter: Only show equipment types and units belonging to the manager's department
  groupedEquipments.value = resEq.data.map(type => {
    return {
      ...type,
      equipments: type.equipments.filter(eq => eq.department_name === myDept)
    };
  }).filter(type => type.equipments.length > 0);

  allBookings.value = resBk.data.results || resBk.data;
}

async function loadMembers() {
  const { data } = await client.get("/users/");
  members.value = (data.results || data).filter(u => ['lab_member', 'lab_manager'].includes(u.role));
}

function openApprove(stage) {
  approveTarget.value = stage;
  scheduleStart.value = "";
  scheduleEnd.value = "";
  assignee.value = null;
  approveError.value = "";
  scheduleWarning.value = "";
}

function validateSchedule() {
  scheduleWarning.value = "";
  if (scheduleStart.value && scheduleEnd.value) {
    const start = new Date(scheduleStart.value);
    const end = new Date(scheduleEnd.value);
    const now = new Date();
    if (end <= start) scheduleWarning.value = "⚠️ End must be after start.";
    else if (start < now) scheduleWarning.value = "⚠️ Start cannot be in the past.";
  }
}

async function confirmApprove() {
  approveBusy.value = true;
  try {
    await reviewStage(approveTarget.value.id, {
      action: "approve",
      schedule_start: scheduleStart.value,
      schedule_end: scheduleEnd.value,
      assignee: assignee.value
    });
    approveTarget.value = null;
    await Promise.all([loadStages(), loadTimelineData()]);
  } catch (e) {
    approveError.value = e.response?.data?.detail || "Approval failed";
  } finally {
    approveBusy.value = false;
  }
}

function toLocalISOString(dateStr) {
  const date = new Date(dateStr);
  const tzOffset = date.getTimezoneOffset() * 60000;
  const localISOTime = (new Date(date - tzOffset)).toISOString().slice(0,16);
  return localISOTime;
}

// ... existing code ...

async function openEditBooking(booking) {
  editBookingTarget.value = booking;
  editBookingStart.value = toLocalISOString(booking.start);
  editBookingEnd.value = toLocalISOString(booking.end);
}

async function saveBookingUpdate() {
  const start = new Date(editBookingStart.value);
  const end = new Date(editBookingEnd.value);
  const now = new Date();
  
  if (end <= start) { alert("End time must be after start time."); return; }
  if (start < now) { alert("Start time cannot be in the past."); return; }

  editBookingBusy.value = true;
  try {
    const { updateBooking } = await import("../../api/scheduling");
    await updateBooking(editBookingTarget.value.id, {
      started_at: editBookingStart.value,
      ended_at: editBookingEnd.value
    });
    editBookingTarget.value = null;
    await loadTimelineData();
  } catch (e) {
    editBookingError.value = e.response?.data?.detail || "Update failed";
  } finally {
    editBookingBusy.value = false;
  }
}

function openReassign(stage) {
  reassignTarget.value = stage;
  reassignAssignee.value = stage.assignee;
  reassignStart.value = toLocalISOString(stage.schedule_start);
  reassignEnd.value = toLocalISOString(stage.schedule_end);
}

async function confirmReassign() {
  // Client-side validation
  const start = new Date(reassignStart.value);
  const end = new Date(reassignEnd.value);
  const now = new Date();
  
  if (end <= start) { alert("End time must be after start time."); return; }
  if (start < now) { alert("Start time cannot be in the past."); return; }

  reassignBusy.value = true;
  try {
    await reviewStage(reassignTarget.value.id, {
      action: "reassign",
      assignee: reassignAssignee.value,
      schedule_start: reassignStart.value,
      schedule_end: reassignEnd.value
    });
    reassignTarget.value = null;
    await Promise.all([loadStages(), loadTimelineData()]);
  } catch (e) {
    alert("Reassignment failed: " + (e.response?.data?.detail || "Unknown error"));
  } finally {
    reassignBusy.value = false;
  }
}

function openReject(stage) {
  rejectTarget.value = stage;
  rejectReason.value = "";
}

async function confirmReject() {
    // Current backend rejects whole order even if only stage is rejected
    await reviewStage(rejectTarget.value.id, {
      action: "reject",
      rejection_reason: rejectReason.value
    });
    rejectTarget.value = null;
    await loadStages();
}

function fmtDt(s) {
  if (!s) return "—";
  return new Date(s).toLocaleString("zh-TW", { dateStyle: "short", timeStyle: "short" });
}
</script>

<style scoped>
.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.6); display: flex; align-items: center; justify-content: center; z-index: 100; }
.modal-card { width: 100%; max-width: 600px; max-height: 90vh; overflow-y: auto; background: var(--c-bg-card); position: relative; }
.alert-error { background: rgba(255,107,107,0.12); color: var(--c-danger); padding: 10px; border-radius: 4px; font-size: 0.85rem; }
.alert-warning { background: rgba(253,203,110,0.12); color: var(--c-warning); padding: 10px; border-radius: 4px; font-size: 0.85rem; }
.badge-outline { border: 1px solid var(--c-border); background: transparent; color: var(--c-text-muted); }
.mb-8 { margin-bottom: 2rem; }
.mb-6 { margin-bottom: 1.5rem; }
.grid-cols-2 { grid-template-columns: 1fr 1fr; }
.col-span-2 { grid-column: span 2; }
.gap-4 { gap: 1rem; }
.btn-sm { padding: 4px 8px; font-size: 0.75rem; }
.mt-12 { margin-top: 3rem; }
.assignee-badge { background: rgba(116,185,255,0.1); color: var(--c-info); padding: 2px 6px; border-radius: 4px; font-size: 0.75rem; border: 1px solid rgba(116,185,255,0.3); }
</style>
