<template>
  <a-config-provider :locale="zhTW">
    <!-- Guest views and the standalone /admin shell render their own layout. -->
    <router-view v-if="!showAppShell" />

    <!-- Default authenticated shell: collapsible sider + header + content. -->
    <a-layout v-else class="app-shell">
      <a-layout-sider
        v-model:collapsed="collapsed"
        collapsible
        :width="232"
        theme="light"
        class="app-sider"
      >
        <div class="brand">
          <ExperimentOutlined class="brand-icon" />
          <span v-if="!collapsed" class="brand-text">Lab Booking</span>
        </div>
        <a-menu
          v-model:selectedKeys="selectedKeys"
          mode="inline"
          theme="light"
          :items="menuItems"
          @click="onMenuClick"
        />
      </a-layout-sider>

      <a-layout>
        <a-layout-header class="app-header">
          <div class="header-left">
            <a-button type="text" @click="collapsed = !collapsed">
              <MenuFoldOutlined v-if="!collapsed" />
              <MenuUnfoldOutlined v-else />
            </a-button>
            <h2 class="page-heading">{{ pageHeading }}</h2>
          </div>

          <div class="header-right">
            <a-button v-if="auth.isSuperuser" type="primary" @click="goAdmin">
              <template #icon><ThunderboltOutlined /></template>
              管理後台
            </a-button>
            <a-dropdown>
              <a-button type="text" class="user-trigger">
                <a-avatar style="background-color: #1890ff" size="small">
                  {{ avatarLetter }}
                </a-avatar>
                <span class="username">{{ auth.user?.username || '使用者' }}</span>
                <DownOutlined />
              </a-button>
              <template #overlay>
                <a-menu @click="onUserMenuClick">
                  <a-menu-item key="profile" disabled>
                    <UserOutlined />
                    <span>{{ auth.user?.email || '—' }}</span>
                  </a-menu-item>
                  <a-menu-item key="role" disabled>
                    <SafetyOutlined />
                    <span>角色: {{ roleLabel }}</span>
                  </a-menu-item>
                  <a-menu-divider />
                  <a-menu-item key="logout" danger>
                    <LogoutOutlined />
                    <span>登出</span>
                  </a-menu-item>
                </a-menu>
              </template>
            </a-dropdown>
          </div>
        </a-layout-header>

        <a-layout-content class="app-content">
          <router-view v-slot="{ Component }">
            <transition name="fade" mode="out-in">
              <component :is="Component" />
            </transition>
          </router-view>
        </a-layout-content>

        <a-layout-footer class="app-footer">
          LIMS · Semiconductor FAB Relay Management System
        </a-layout-footer>
      </a-layout>
    </a-layout>
  </a-config-provider>
</template>

<script setup>
import { computed, h, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import zhTW from 'ant-design-vue/es/locale/zh_TW'
import {
  AppstoreOutlined,
  CheckCircleOutlined,
  DashboardOutlined,
  DownOutlined,
  ExperimentOutlined,
  FileAddOutlined,
  LogoutOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  ProfileOutlined,
  SafetyOutlined,
  ThunderboltOutlined,
  UnorderedListOutlined,
  UserOutlined,
} from '@ant-design/icons-vue'
import { useAuthStore } from './stores/auth'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()

const collapsed = ref(false)

/** Routes that render their own layout. */
const STANDALONE_PREFIXES = ['/login', '/register', '/admin']

const showAppShell = computed(() => {
  if (!auth.isLoggedIn) return false
  return !STANDALONE_PREFIXES.some((p) => route.path.startsWith(p))
})

/** Menu config: {key, label, icon, path, visible: () => boolean} */
const menuConfig = computed(() => [
  { key: 'dashboard', label: '儀表板', icon: DashboardOutlined, path: '/' },
  {
    key: 'my-orders',
    label: '我的訂單',
    icon: ProfileOutlined,
    path: '/orders',
    visible: () => auth.role === 'regular_employee' || auth.isSuperuser,
  },
  {
    key: 'create-order',
    label: '送樣申請',
    icon: FileAddOutlined,
    path: '/orders/create',
    visible: () => auth.role === 'regular_employee' || auth.isSuperuser,
  },
  {
    key: 'review',
    label: '訂單審核',
    icon: CheckCircleOutlined,
    path: '/orders/review',
    visible: () => auth.isManager,
  },
  {
    key: 'tasks',
    label: '實驗室任務',
    icon: UnorderedListOutlined,
    path: '/orders/tasks',
    visible: () => auth.isMember,
  },
  { key: 'equipment', label: '設備總覽', icon: AppstoreOutlined, path: '/equipment' },
])

const visibleMenu = computed(() =>
  menuConfig.value.filter((m) => !m.visible || m.visible()),
)

const menuItems = computed(() =>
  visibleMenu.value.map((m) => ({
    key: m.key,
    label: m.label,
    icon: () => h(m.icon),
  })),
)

const pathByKey = computed(() =>
  Object.fromEntries(visibleMenu.value.map((m) => [m.key, m.path])),
)
const labelByKey = computed(() =>
  Object.fromEntries(visibleMenu.value.map((m) => [m.key, m.label])),
)

const selectedKeys = ref([deriveKey(route.path)])

watch(
  () => route.path,
  (path) => {
    selectedKeys.value = [deriveKey(path)]
  },
)

function deriveKey(path) {
  // longest-prefix match so /orders/create wins over /orders
  const sorted = [...visibleMenu.value].sort((a, b) => b.path.length - a.path.length)
  const match = sorted.find((m) => path === m.path || path.startsWith(m.path + '/'))
  if (match) return match.key
  if (path === '/') return 'dashboard'
  return ''
}

const pageHeading = computed(() => labelByKey.value[selectedKeys.value[0]] || 'LIMS')

const avatarLetter = computed(
  () => (auth.user?.username || '?').charAt(0).toUpperCase(),
)

const ROLE_LABELS = {
  superuser: '系統管理員',
  lab_manager: '實驗室經理',
  lab_member: '實驗室成員',
  regular_employee: '一般員工',
}
const roleLabel = computed(() => ROLE_LABELS[auth.role] || auth.role || '—')

function onMenuClick({ key }) {
  const path = pathByKey.value[key]
  if (path) router.push(path)
}

function onUserMenuClick({ key }) {
  if (key === 'logout') {
    auth.logout()
    router.push('/login')
  }
}

function goAdmin() {
  router.push('/admin')
}
</script>

<style scoped>
.app-shell {
  min-height: 100vh;
}

.app-sider {
  position: sticky;
  top: 0;
  height: 100vh;
  box-shadow: 1px 0 4px rgba(0, 21, 41, 0.04);
  z-index: 10;
}

.brand {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  height: 64px;
  padding: 0 16px;
  border-bottom: 1px solid var(--c-border);
  font-weight: 700;
  font-size: 16px;
  color: var(--c-primary);
  letter-spacing: 0.4px;
}
.brand-icon {
  font-size: 22px;
}

.app-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  background: #fff;
  box-shadow: 0 1px 4px rgba(0, 21, 41, 0.06);
  height: 64px;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.page-heading {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: rgba(0, 0, 0, 0.85);
}

.header-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.user-trigger {
  display: flex;
  align-items: center;
  gap: 8px;
}
.username {
  font-weight: 500;
}

.app-content {
  padding: 24px;
  min-height: calc(100vh - 64px - 70px);
}

.app-footer {
  text-align: center;
  color: rgba(0, 0, 0, 0.45);
  background: transparent;
  padding: 16px;
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.18s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
