/**
 * src/stores/auth.js – Pinia auth store.
 * Manages JWT tokens, user profile, and role-based helpers.
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { login as apiLogin, fetchProfile } from '../api/users'

export const useAuthStore = defineStore('auth', () => {
  const user = ref(null)
  const accessToken = ref(localStorage.getItem('access_token') || '')
  const refreshToken = ref(localStorage.getItem('refresh_token') || '')

  const isLoggedIn = computed(() => !!accessToken.value)
  const role = computed(() => user.value?.role || '')
  const isManager = computed(() => ['lab_manager', 'superuser'].includes(role.value))
  const isMember = computed(() => ['lab_member', 'lab_manager', 'superuser'].includes(role.value))

  async function login(username, password) {
    const { data } = await apiLogin(username, password)
    accessToken.value = data.access
    refreshToken.value = data.refresh
    localStorage.setItem('access_token', data.access)
    localStorage.setItem('refresh_token', data.refresh)
    await loadProfile()
  }

  async function loadProfile() {
    try {
      const { data } = await fetchProfile()
      user.value = data
    } catch {
      logout()
    }
  }

  function logout() {
    user.value = null
    accessToken.value = ''
    refreshToken.value = ''
    localStorage.removeItem('access_token')
    localStorage.removeItem('refresh_token')
  }

  return { user, accessToken, refreshToken, isLoggedIn, role, isManager, isMember, login, loadProfile, logout }
})
