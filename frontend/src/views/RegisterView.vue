<template>
  <div class="login-container">
    <div class="login-card card">
      <h1 style="text-align:center;margin-bottom:24px;">📝 Register</h1>
      
      <div v-if="error" class="alert-error mb-4">{{ error }}</div>
      <div v-if="success" class="alert-success mb-4">
        Registration successful! You can now <router-link to="/login">login</router-link>.
      </div>

      <form v-if="!success" @submit.prevent="handleRegister">
        <div class="form-group">
          <label for="username">Username</label>
          <input id="username" v-model="form.username" type="text" required />
        </div>
        <div class="form-group">
          <label for="email">Email</label>
          <input id="email" v-model="form.email" type="email" required />
        </div>
        <div class="form-group">
          <label for="password">Password</label>
          <input id="password" v-model="form.password" type="password" required minlength="8" />
        </div>
        <div class="form-group">
          <label for="name">Full Name</label>
          <input id="name" v-model="form.first_name" type="text" required />
        </div>
        <div class="form-group">
          <label for="role">Role</label>
          <select id="role" v-model="form.role">
            <option value="regular_employee">Regular Employee (Requester)</option>
            <option value="lab_manager">Lab Manager</option>
            <option value="lab_member">Lab Member</option>
          </select>
        </div>

        <button class="btn btn-primary w-full" :disabled="loading">
          {{ loading ? 'Registering...' : 'Register' }}
        </button>
      </form>

      <div class="mt-4" style="text-align:center;font-size:.9rem;">
        Already have an account? <router-link to="/login">Login here</router-link>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import client from '../api/client'

const form = ref({
  username: '',
  email: '',
  password: '',
  first_name: '',
  last_name: '',
  role: 'regular_employee'
})
const loading = ref(false)
const error = ref('')
const success = ref(false)

async function handleRegister() {
  error.value = ''
  loading.value = true
  try {
    await client.post('/users/register/', form.value)
    success.value = true
  } catch (e) {
    error.value = e.response?.data?.detail || JSON.stringify(e.response?.data) || 'Registration failed'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-container {
  height: 100vh; display: flex; align-items: center; justify-content: center;
  background: var(--c-bg);
}
.login-card { width: 100%; max-width: 400px; padding: 40px; }
.w-full { width: 100%; }
.alert-error { background:rgba(255,107,107,.12); color:var(--c-danger); padding:10px 14px; border-radius:var(--radius); font-size:.9rem; }
.alert-success { background:rgba(0,206,201,.12); color:var(--c-success); padding:10px 14px; border-radius:var(--radius); font-size:.9rem; }
</style>
