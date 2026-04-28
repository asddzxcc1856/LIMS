<template>
  <div class="login-wrapper">
    <div class="login-card card">
      <h1 class="login-title">⚗️ Lab Booking</h1>
      <p class="text-muted" style="margin-bottom:24px;">Sign in to your account</p>

      <div v-if="error" class="alert-error">{{ error }}</div>

      <form @submit.prevent="handleLogin">
        <div class="form-group">
          <label for="username">Username</label>
          <input id="username" v-model="username" required autocomplete="username" />
        </div>
        <div class="form-group">
          <label for="password">Password</label>
          <input id="password" v-model="password" type="password" required autocomplete="current-password" />
        </div>
        <button class="btn btn-primary w-full" :disabled="loading">
          {{ loading ? 'Logging in...' : 'Login' }}
        </button>
      </form>

      <div class="mt-4" style="text-align:center;font-size:.9rem;">
        Don't have an account? <router-link to="/register">Register here</router-link>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const router = useRouter()
const username = ref('')
const password = ref('')
const error = ref('')
const loading = ref(false)

async function handleLogin() {
  error.value = ''
  loading.value = true
  try {
    await auth.login(username.value, password.value)
    router.push('/')
  } catch (e) {
    error.value = e.response?.data?.detail || 'Login failed'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-wrapper {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  background: var(--c-bg);
}
.login-card {
  width: 100%;
  max-width: 400px;
  text-align: center;
}
.login-title {
  font-size: 1.6rem;
  font-weight: 700;
  color: var(--c-primary);
}
.alert-error {
  background: rgba(255,107,107,.12);
  color: var(--c-danger);
  padding: 10px 14px;
  border-radius: var(--radius);
  margin-bottom: 16px;
  font-size: .85rem;
}
.w-full { width: 100%; }
</style>
