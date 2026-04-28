/**
 * src/router/index.js – Vue Router with role-based guards.
 */
import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth'

import LoginView from '../views/LoginView.vue'
import RegisterView from '../views/RegisterView.vue'
import DashboardView from '../views/DashboardView.vue'
import OrderCreateView from '../views/requester/OrderCreateView.vue'
import OrderListView from '../views/requester/OrderListView.vue'
import OrderReviewView from '../views/manager/OrderReviewView.vue'
import OrderTasksView from '../views/member/OrderTasksView.vue'
import EquipmentDashboardView from '../views/EquipmentDashboardView.vue'

const routes = [
  { path: '/login', name: 'Login', component: LoginView, meta: { guest: true } },
  { path: '/register', name: 'Register', component: RegisterView, meta: { guest: true } },
  { path: '/', name: 'Dashboard', component: DashboardView },
  // Requester
  { path: '/orders', name: 'MyOrders', component: OrderListView },
  { path: '/orders/create', name: 'CreateOrder', component: OrderCreateView },
  // Lab Manager
  {
    path: '/orders/review',
    name: 'ReviewOrders',
    component: OrderReviewView,
    meta: { roles: ['lab_manager', 'superuser'] },
  },
  // Lab Member
  {
    path: '/orders/tasks',
    name: 'LabTasks',
    component: OrderTasksView,
    meta: { roles: ['lab_member', 'lab_manager', 'superuser'] },
  },
  // Equipment
  { path: '/equipment', name: 'EquipmentDashboard', component: EquipmentDashboardView },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach(async (to, from, next) => {
  const auth = useAuthStore()

  if (auth.accessToken && !auth.user) {
    await auth.loadProfile()
  }

  if (to.meta.guest) {
    return auth.isLoggedIn ? next('/') : next()
  }

  if (!auth.isLoggedIn) {
    return next('/login')
  }

  if (to.meta.roles && !to.meta.roles.includes(auth.role)) {
    return next('/')
  }

  next()
})

export default router
