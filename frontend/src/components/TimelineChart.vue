<template>
  <div class="timeline-container card">
    <div class="timeline-header flex justify-between items-center mb-4">
      <div class="flex items-center gap-4">
        <h3 style="margin:0;">📅 Equipment Pipeline</h3>
        <div class="day-nav flex items-center gap-2">
          <button class="btn btn-outline btn-xs" @click="changeDay(-1)">&lt;</button>
          <span class="font-bold date-display">{{ formattedDate }}</span>
          <button class="btn btn-outline btn-xs" @click="changeDay(1)">&gt;</button>
        </div>
      </div>
      <div class="flex gap-4 text-sm font-medium">
        <span class="flex items-center gap-1"><i class="legend-box status-active"></i> Active Now</span>
        <span class="flex items-center gap-1"><i class="legend-box status-future"></i> Scheduled</span>
        <span class="flex items-center gap-1"><i class="legend-box status-done"></i> Completed</span>
      </div>
    </div>

    <div class="timeline-scroll">
      <div class="timeline-grid" :style="{ gridTemplateColumns: `120px repeat(24, 60px)` }">
        <!-- Time Header -->
        <div class="grid-header sticker-col" style="z-index:20;">Equipment</div>
        <div v-for="h in 24" :key="h" class="grid-header">{{ h-1 }}:00</div>

        <!-- Rows -->
        <template v-for="type in groupedEquipments" :key="type.type_id">
          <div class="type-row text-xs font-bold bg-muted" :style="{ gridColumn: `1 / span 25` }">
            {{ type.type_name }}
          </div>
          <div v-for="eq in type.equipments" :key="eq.id" class="eq-row-content" :style="{ gridColumn: `1 / span 25` }">
            <div class="eq-label sticker-col">{{ eq.code }}</div>
            <div v-for="h in 24" :key="h" class="time-cell"></div>
            
            <!-- Bookings Overlay -->
            <div v-for="b in getBookingsForDay(eq.id)" :key="b.id" 
                 class="booking-bar"
                 :class="['bar-' + b.displayStatus, { 'bar-locked': b.displayStatus === 'done' }]"
                 :style="getBarStyle(b)"
                 @click="b.displayStatus !== 'done' && $emit('booking-click', b)"
                 :title="`Order: ${b.order_no} (${b.displayStatus.toUpperCase()})\nAssignee: ${b.assignee_name || 'Unassigned'}\n📅 Start: ${b.start.toLocaleDateString()} ${b.start_time}\n📅 End: ${end_date_str(b.end)} ${b.end_time}\n⏱️ Duration: ${b.duration_str}${b.displayStatus === 'done' ? '\n(LOCKED)' : ''}`">
               <span class="bar-content">
                 <span class="bar-order">{{ b.order_no }}</span>
                 <span v-if="b.assignee_name" class="bar-assignee">👤 {{ b.assignee_name }}</span>
                 <span class="bar-time-sub">{{ b.start_time }} - {{ b.end_time }}</span>
               </span>
            </div>

            <!-- Now Indicator Line -->
            <div v-if="isCurrentDay" class="now-line" :style="{ left: nowPosition }"></div>
          </div>
        </template>

      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'

const props = defineProps({
  groupedEquipments: { type: Array, required: true },
  bookings: { type: Array, required: true }
})

const emit = defineEmits(['booking-click'])

const currentDate = ref(new Date())

const formattedDate = computed(() => {
  return currentDate.value.toLocaleDateString('zh-TW', { month: 'short', day: 'numeric', weekday: 'short' })
})

function changeDay(offset) {
  const d = new Date(currentDate.value)
  d.setDate(d.getDate() + offset)
  currentDate.value = d
}

function getBookingsForDay(eqId) {
  const dayStart = new Date(currentDate.value.getFullYear(), currentDate.value.getMonth(), currentDate.value.getDate(), 0, 0, 0)
  const dayEnd = new Date(dayStart)
  dayEnd.setDate(dayEnd.getDate() + 1)

  return props.bookings.filter(b => {
    const start = new Date(b.started_at || b.schedule_start)
    const end = new Date(b.ended_at || b.schedule_end)
    const matchesEq = (b.equipment === eqId || b.equipment_id === eqId)
    // Overlaps with the current day
    return matchesEq && (start < dayEnd && end > dayStart)
  }).map(b => {
    const start = new Date(b.started_at || b.schedule_start)
    const end = new Date(b.ended_at || b.schedule_end)
    const diffMs = end - start
    const hours = Math.floor(diffMs / (1000 * 60 * 60))
    const mins = Math.floor((diffMs % (1000 * 60 * 60)) / (1000 * 60))
    
    // Real-time status logic
    let displayStatus = 'waiting'
    const now = new Date()
    if (b.stage_status === 'done' || b.status === 'done' || b.order_status === 'done') {
      displayStatus = 'done'
    } else if (now >= start && now <= end) {
      displayStatus = 'active'
    } else if (start > now) {
      displayStatus = 'waiting'
    } else {
      displayStatus = 'past'
    }

    return {
      ...b,
      start,
      end,
      start_time: start.toLocaleTimeString([], {hour:'2-digit', minute:'2-digit', hour12: false}),
      end_time: end.toLocaleTimeString([], {hour:'2-digit', minute:'2-digit', hour12: false}),
      duration_str: `${hours}h ${mins}m`,
      displayStatus
    }
  })
}

const isCurrentDay = computed(() => {
  const today = new Date()
  return today.toDateString() === currentDate.value.toDateString()
})

const nowPosition = computed(() => {
  const now = new Date()
  const hours = now.getHours() + now.getMinutes() / 60
  return (120 + hours * 60) + 'px'
})

function end_date_str(date) {
  return date.toLocaleDateString()
}

function getBarStyle(b) {
  const dayStart = new Date(currentDate.value.getFullYear(), currentDate.value.getMonth(), currentDate.value.getDate(), 0, 0, 0)
  
  const startOffset = (b.start - dayStart) / (1000 * 60 * 60) // in hours
  const duration = (b.end - b.start) / (1000 * 60 * 60)
  
  // Calculate relative to current day (0 to 24)
  const relativeStart = Math.max(0, startOffset)
  const relativeEnd = Math.min(24, startOffset + duration)
  const displayDuration = relativeEnd - relativeStart

  if (displayDuration <= 0) return { display: 'none' }
  
  const left = 120 + relativeStart * 60
  const width = displayDuration * 60
  
  return {
    left: `${left}px`,
    width: `${width}px`
  }
}
</script>

<style scoped>
.timeline-container { padding: 16px; margin-top: 24px; overflow: hidden; }
.timeline-scroll { overflow-x: auto; position: relative; border: 1px solid var(--c-border); border-radius: 4px; background: var(--c-bg); }
.timeline-grid { display: grid; position: relative; min-width: max-content; }

.grid-header { 
  background: var(--c-bg-card); border-bottom: 2px solid var(--c-border); border-right: 1px solid var(--c-border);
  padding: 8px; text-align: center; font-size: 0.7rem; font-weight: 700; color: var(--c-text-muted);
}
.sticker-col { position: sticky; left: 0; z-index: 10; background: var(--c-bg-card); width: 120px; border-right: 2px solid var(--c-border); box-shadow: 4px 0 10px rgba(0,0,0,0.08); }
.type-row { padding: 8px 16px; border-bottom: 2px solid var(--c-border); position: sticky; left: 0; z-index: 5; background: #f1f5f9; color: #334155; font-size: 0.7rem; letter-spacing: 0.08em; text-transform: uppercase; }
.eq-row-content { display: flex; position: relative; height: 72px; border-bottom: 1px solid var(--c-border-light); background: rgba(255,255,255,0.4); }
.eq-label { display: flex; align-items: center; padding: 0 16px; font-size: 0.8rem; font-weight: 800; color: #0f172a; border-right: 1px solid var(--c-border-light); }
.time-cell { width: 60px; min-width: 60px; border-right: 1px solid var(--c-border-light); }

.booking-bar {
  position: absolute; top: 6px; bottom: 6px; border-radius: 8px; z-index: 2;
  font-size: 0.75rem; color: white; display: flex; align-items: center; justify-content: center;
  overflow: hidden; padding: 6px 12px;
  box-shadow: 0 6px 12px -2px rgba(50, 50, 93, 0.25), 0 3px 7px -3px rgba(0, 0, 0, 0.3);
  transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1); cursor: pointer;
  border: 1px solid rgba(255,255,255,0.25);
  backdrop-filter: blur(4px);
}
.bar-content { display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100%; width: 100%; overflow: hidden; line-height: 1.3; }
.bar-order { font-weight: 900; font-size: 0.85rem; text-shadow: 0 1px 2px rgba(0,0,0,0.3); }
.bar-assignee { font-size: 0.65rem; opacity: 0.9; font-weight: 600; margin-top: 2px; }
.bar-time-sub { font-size: 0.6rem; opacity: 0.8; font-weight: 500; font-family: 'Monaco', monospace; margin-top: 1px; }
.booking-bar:hover { filter: brightness(1.1); transform: translateY(-3px) scale(1.03); z-index: 100; box-shadow: 0 15px 25px -5px rgba(0,0,0,0.3); }

.bar-active { background: linear-gradient(135deg, #4f46e5, #3730a3); } /* Indigo - Executing Now */
.bar-waiting { background: linear-gradient(135deg, #f59e0b, #d97706); } /* Amber - Future */
.bar-done { background: linear-gradient(135deg, #059669, #064e3b); opacity: 0.65; cursor: default; } /* Emerald - Completed */
.bar-past { background: linear-gradient(135deg, #94a3b8, #64748b); opacity: 0.8; } /* Slate - Past uncompleted */

.bar-locked { pointer-events: none; filter: contrast(0.8) grayscale(0.2); }
.bar-locked:hover { transform: none !important; box-shadow: none !important; filter: contrast(0.8) grayscale(0.2) !important; }

.now-line {
  position: absolute; top: 0; bottom: 0; width: 2px;
  background: var(--c-danger); z-index: 100; pointer-events: none;
  box-shadow: 0 0 8px rgba(239, 68, 68, 0.4);
}
.now-line::after {
  content: ''; position: absolute; top: 0; left: -4px; width: 10px; height: 10px;
  background: var(--c-danger); border-radius: 50%;
}

.legend-box { width: 14px; height: 14px; display: inline-block; border-radius: 4px; vertical-align: middle; margin-right: 4px; }
.status-active { background: linear-gradient(135deg, #4f46e5, #3730a3); }
.status-future { background: linear-gradient(135deg, #f59e0b, #d97706); }
.status-done { background: linear-gradient(135deg, #059669, #064e3b); opacity: 0.7; }


.day-nav { background: var(--c-bg); padding: 2px 8px; border-radius: 20px; border: 1px solid var(--c-border); }
.date-display { font-size: 0.85rem; min-width: 90px; text-align: center; }
.btn-xs { padding: 2px 6px; font-size: 0.7rem; }
</style>
