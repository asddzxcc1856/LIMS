<template>
  <a-layout class="admin-shell">
    <a-layout-sider
      v-model:collapsed="collapsed"
      collapsible
      :width="240"
      theme="dark"
      class="admin-sider"
    >
      <div class="admin-brand">
        <ThunderboltOutlined class="brand-icon" />
        <span v-if="!collapsed" class="brand-text">LIMS Admin</span>
      </div>
      <a-menu
        v-model:selectedKeys="selectedKeys"
        mode="inline"
        theme="dark"
        :items="menuItems"
        @click="onMenuClick"
      />
    </a-layout-sider>

    <a-layout>
      <a-layout-header class="admin-header">
        <div class="admin-header-left">
          <a-breadcrumb>
            <a-breadcrumb-item>
              <HomeOutlined />
              <span>&nbsp;LIMS</span>
            </a-breadcrumb-item>
            <a-breadcrumb-item>{{ currentLabel }}</a-breadcrumb-item>
          </a-breadcrumb>
        </div>
        <div class="admin-header-right">
          <a-tag color="processing" v-if="auth.user">
            <UserOutlined />&nbsp;{{ auth.user.username }} ({{ auth.role }})
          </a-tag>
          <a-button type="link" @click="goHome">
            <template #icon><RollbackOutlined /></template>
            返回主系統
          </a-button>
          <a-button type="link" danger @click="onLogout">
            <template #icon><LogoutOutlined /></template>
            登出
          </a-button>
        </div>
      </a-layout-header>

      <a-layout-content class="admin-content">
        <router-view v-slot="{ Component }">
          <transition name="fade" mode="out-in">
            <component :is="Component" />
          </transition>
        </router-view>
      </a-layout-content>

      <a-layout-footer class="admin-footer">
        LIMS Admin Console &nbsp;·&nbsp; Semiconductor FAB Relay Management
      </a-layout-footer>
    </a-layout>
  </a-layout>
</template>

<script setup>
import { computed, h, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  ApartmentOutlined,
  AppstoreOutlined,
  BankOutlined,
  CalendarOutlined,
  ClusterOutlined,
  ContainerOutlined,
  DashboardOutlined,
  ExperimentOutlined,
  FileSearchOutlined,
  HomeOutlined,
  LogoutOutlined,
  NodeIndexOutlined,
  ProfileOutlined,
  RollbackOutlined,
  TeamOutlined,
  ThunderboltOutlined,
  ToolOutlined,
  UserOutlined,
} from '@ant-design/icons-vue'
import { useAuthStore } from '../../stores/auth'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()

const collapsed = ref(false)

const menuConfig = [
  { key: 'dashboard', label: '系統儀表板', icon: DashboardOutlined, path: '/admin/dashboard' },
  { key: 'logs', label: '活動日誌', icon: FileSearchOutlined, path: '/admin/logs' },
  { type: 'divider' },
  { key: 'fabs', label: 'FAB 工廠', icon: BankOutlined, path: '/admin/fabs' },
  { key: 'departments', label: '部門', icon: ApartmentOutlined, path: '/admin/departments' },
  { key: 'users', label: '使用者', icon: TeamOutlined, path: '/admin/users' },
  { type: 'divider' },
  { key: 'experiments', label: '實驗類型', icon: ExperimentOutlined, path: '/admin/experiments' },
  { key: 'equipment-types', label: '設備類型', icon: AppstoreOutlined, path: '/admin/equipment-types' },
  { key: 'equipment', label: '設備', icon: ToolOutlined, path: '/admin/equipment' },
  {
    key: 'experiment-requirements',
    label: '實驗設備需求',
    icon: ClusterOutlined,
    path: '/admin/experiment-requirements',
  },
  { type: 'divider' },
  { key: 'orders', label: '訂單', icon: ProfileOutlined, path: '/admin/orders' },
  { key: 'order-stages', label: '訂單階段', icon: NodeIndexOutlined, path: '/admin/order-stages' },
  { key: 'bookings', label: '設備預約', icon: CalendarOutlined, path: '/admin/bookings' },
]

const menuItems = computed(() =>
  menuConfig.map((item, idx) =>
    item.type === 'divider'
      ? { type: 'divider', key: `d-${idx}` }
      : { key: item.key, label: item.label, icon: () => h(item.icon) },
  ),
)

const pathByKey = Object.fromEntries(
  menuConfig.filter((m) => m.key).map((m) => [m.key, m.path]),
)
const labelByKey = Object.fromEntries(
  menuConfig.filter((m) => m.key).map((m) => [m.key, m.label]),
)

const selectedKeys = ref([deriveKey(route.path)])

watch(
  () => route.path,
  (path) => {
    selectedKeys.value = [deriveKey(path)]
  },
)

function deriveKey(path) {
  const segment = path.split('/')[2] || 'dashboard'
  return segment in pathByKey ? segment : 'dashboard'
}

const currentLabel = computed(() => labelByKey[selectedKeys.value[0]] || '管理後台')

function onMenuClick({ key }) {
  router.push(pathByKey[key])
}

function goHome() {
  router.push('/')
}

function onLogout() {
  auth.logout()
  router.push('/login')
}
</script>

<style scoped>
.admin-shell {
  min-height: 100vh;
}

.admin-sider {
  position: sticky;
  top: 0;
  height: 100vh;
}

.admin-brand {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  height: 64px;
  color: #fff;
  font-size: 18px;
  font-weight: 600;
  letter-spacing: 0.6px;
  background: linear-gradient(135deg, rgba(24, 144, 255, 0.18), transparent);
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
}

.brand-icon {
  font-size: 22px;
  color: #1890ff;
}

.admin-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  background: #fff;
  box-shadow: 0 1px 4px rgba(0, 21, 41, 0.08);
}

.admin-header-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.admin-content {
  margin: 24px;
  padding: 24px;
  background: #fff;
  min-height: calc(100vh - 64px - 70px - 48px);
  border-radius: 8px;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
}

.admin-footer {
  text-align: center;
  color: rgba(0, 0, 0, 0.45);
  background: transparent;
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
