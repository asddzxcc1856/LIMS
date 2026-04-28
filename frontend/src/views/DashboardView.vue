<template>
  <div>
    <h1 class="page-title">Dashboard</h1>

    <div class="stats-grid">
      <div class="card stat-card">
        <div class="stat-value">{{ stats.total }}</div>
        <div class="stat-label">Total Orders</div>
      </div>
      <div class="card stat-card">
        <div class="stat-value warning">{{ stats.waiting }}</div>
        <div class="stat-label">Waiting</div>
      </div>
      <div class="card stat-card">
        <div class="stat-value info">{{ stats.in_progress }}</div>
        <div class="stat-label">In Progress</div>
      </div>
      <div class="card stat-card">
        <div class="stat-value success">{{ stats.done }}</div>
        <div class="stat-label">Done</div>
      </div>
    </div>

    <div class="card mt-4">
      <h2 style="font-size:1.1rem;margin-bottom:12px;">Welcome, {{ auth.user?.username }}</h2>
      <p class="text-muted">
        Role: <span class="badge badge-in_progress">{{ auth.user?.role }}</span>
      </p>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useAuthStore } from '../stores/auth'
import { fetchOrders } from '../api/orders'

const auth = useAuthStore()
const stats = ref({ total: 0, waiting: 0, in_progress: 0, done: 0 })

onMounted(async () => {
  try {
    const { data } = await fetchOrders()
    const orders = data.results || data
    stats.value.total = orders.length
    stats.value.waiting = orders.filter(o => o.status === 'waiting').length
    stats.value.in_progress = orders.filter(o => o.status === 'in_progress').length
    stats.value.done = orders.filter(o => o.status === 'done').length
  } catch { /* ignore */ }
})
</script>

<style scoped>
.stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 16px; }
.stat-card { text-align: center; }
.stat-value { font-size: 2rem; font-weight: 700; }
.stat-value.warning { color: var(--c-warning); }
.stat-value.info { color: var(--c-info); }
.stat-value.success { color: var(--c-success); }
.stat-label { font-size: .8rem; color: var(--c-text-muted); text-transform: uppercase; margin-top: 4px; }
</style>
