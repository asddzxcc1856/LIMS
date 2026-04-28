<template>
  <!-- Guest: no shell -->
  <router-view v-if="!auth.isLoggedIn" />

  <!-- Authenticated: sidebar + content -->
  <div v-else class="app-shell">
    <aside class="sidebar">
      <div class="logo">⚗️ Lab Booking</div>

      <router-link to="/">Dashboard</router-link>
      <router-link v-if="auth.role === 'regular_employee'" to="/orders">My Orders</router-link>
      <router-link v-if="auth.role === 'regular_employee'" to="/orders/create">New Order</router-link>

      <router-link v-if="auth.isManager" to="/orders/review">Review Orders</router-link>
      <router-link v-if="auth.isMember || auth.isManager" to="/orders/tasks">Lab Tasks</router-link>
      <router-link to="/equipment">Equipment Status</router-link>

      <a href="#" @click.prevent="handleLogout" style="margin-top:auto;">Logout</a>
    </aside>

    <main class="main-content">
      <router-view />
    </main>
  </div>
</template>

<script setup>
import { useAuthStore } from './stores/auth'
import { useRouter } from 'vue-router'

const auth = useAuthStore()
const router = useRouter()

function handleLogout() {
  auth.logout()
  router.push('/login')
}
</script>
