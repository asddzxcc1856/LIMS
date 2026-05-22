<template>
  <a-layout class="admin-shell">
    <a-layout-sider
      v-model:collapsed="collapsed"
      collapsible
      :width="240"
      :collapsed-width="isMobile ? 0 : 64"
      theme="dark"
      class="admin-sider"
      :class="{ 'admin-sider-mobile': isMobile, 'admin-sider-collapsed': collapsed }"
    >
      <div class="admin-brand">
        <ThunderboltOutlined class="brand-icon" />
        <span v-if="!collapsed" class="brand-text">{{ t('admin.consoleBrand') }}</span>
      </div>
      <a-menu
        v-model:selectedKeys="selectedKeys"
        mode="inline"
        theme="dark"
        :items="menuItems"
        @click="onMenuClick"
      />
    </a-layout-sider>

    <!-- Mobile backdrop closes the sider when tapped outside. -->
    <div
      v-if="isMobile && !collapsed"
      class="sider-backdrop"
      @click="collapsed = true"
    ></div>

    <a-layout>
      <a-layout-header class="admin-header">
        <div class="admin-header-left">
          <a-breadcrumb>
            <a-breadcrumb-item>
              <HomeOutlined />
              <span>&nbsp;{{ t('admin.breadcrumbHome') }}</span>
            </a-breadcrumb-item>
            <a-breadcrumb-item>{{ currentLabel }}</a-breadcrumb-item>
          </a-breadcrumb>
        </div>
        <div class="admin-header-right">
          <NotificationBell />
          <a-tag v-if="auth.user" color="processing" class="who-tag">
            <UserOutlined />&nbsp;{{ auth.user.username }} ({{ auth.role }})
          </a-tag>
          <a-button type="link" @click="goHome" class="back-btn">
            <template #icon><RollbackOutlined /></template>
            <span class="btn-text">{{ t('admin.backToMain') }}</span>
          </a-button>
          <a-button type="link" danger @click="onLogout" class="logout-btn">
            <template #icon><LogoutOutlined /></template>
            <span class="btn-text">{{ t('auth.logout') }}</span>
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
        {{ t('admin.consoleBrand') }} &nbsp;·&nbsp; {{ t('common.appFullName') }}
      </a-layout-footer>
    </a-layout>
  </a-layout>
</template>

<script setup>
import { computed, h, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import {
  ApartmentOutlined,
  AppstoreOutlined,
  BankOutlined,
  CalendarOutlined,
  ClusterOutlined,
  ContainerOutlined,
  DashboardOutlined,
  DeploymentUnitOutlined,
  ExperimentOutlined,
  HistoryOutlined,
  PartitionOutlined,
  SafetyCertificateOutlined,
  FileSearchOutlined,
  HomeOutlined,
  LogoutOutlined,
  NodeIndexOutlined,
  ProfileOutlined,
  RollbackOutlined,
  TagsOutlined,
  TeamOutlined,
  ThunderboltOutlined,
  ToolOutlined,
  UserOutlined,
} from '@ant-design/icons-vue'
import { useAuthStore } from '../../stores/auth'
import { useBreakpoint } from '../../composables/useBreakpoint'
import NotificationBell from '../../components/NotificationBell.vue'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()
const { t } = useI18n()

const { isMobile, isTablet } = useBreakpoint()
const collapsed = ref(false)

watch(
  isTablet,
  (small) => { if (small) collapsed.value = true },
  { immediate: true },
)
watch(
  isMobile,
  (small) => { if (small) collapsed.value = true },
  { immediate: true },
)

const menuConfig = computed(() => [
  { key: 'dashboard', label: t('admin.nav.dashboard'), icon: DashboardOutlined, path: '/admin/dashboard' },
  { key: 'logs', label: t('admin.nav.logs'), icon: FileSearchOutlined, path: '/admin/logs' },
  { type: 'divider' },
  { key: 'fabs', label: t('admin.nav.fabs'), icon: BankOutlined, path: '/admin/fabs' },
  { key: 'departments', label: t('admin.nav.departments'), icon: ApartmentOutlined, path: '/admin/departments' },
  { key: 'wafer-lots', label: t('admin.nav.waferLots'), icon: TagsOutlined, path: '/admin/wafer-lots' },
  { key: 'users', label: t('admin.nav.users'), icon: TeamOutlined, path: '/admin/users' },
  { type: 'divider' },
  { key: 'experiments', label: t('admin.nav.experiments'), icon: ExperimentOutlined, path: '/admin/experiments' },
  { key: 'equipment-types', label: t('admin.nav.equipmentTypes'), icon: AppstoreOutlined, path: '/admin/equipment-types' },
  { key: 'equipment', label: t('admin.nav.equipment'), icon: ToolOutlined, path: '/admin/equipment' },
  { key: 'recipes', label: t('admin.nav.recipes'), icon: DeploymentUnitOutlined, path: '/admin/recipes' },
  {
    key: 'experiment-requirements',
    label: t('admin.nav.experimentRequirements'),
    icon: ClusterOutlined,
    path: '/admin/experiment-requirements',
  },
  { type: 'divider' },
  { key: 'orders', label: t('admin.nav.orders'), icon: ProfileOutlined, path: '/admin/orders' },
  { key: 'order-stages', label: t('admin.nav.orderStages'), icon: NodeIndexOutlined, path: '/admin/order-stages' },
  { key: 'bookings', label: t('admin.nav.bookings'), icon: CalendarOutlined, path: '/admin/bookings' },
  { key: 'stage-events', label: t('admin.nav.stageEvents'), icon: HistoryOutlined, path: '/admin/stage-events' },
  { key: 'approvals', label: t('admin.nav.approvals'), icon: SafetyCertificateOutlined, path: '/admin/approvals' },
  { key: 'samples', label: t('admin.nav.samples'), icon: PartitionOutlined, path: '/admin/samples' },
])

const menuItems = computed(() =>
  menuConfig.value.map((item, idx) =>
    item.type === 'divider'
      ? { type: 'divider', key: `d-${idx}` }
      : { key: item.key, label: item.label, icon: () => h(item.icon) },
  ),
)

const pathByKey = computed(() =>
  Object.fromEntries(menuConfig.value.filter((m) => m.key).map((m) => [m.key, m.path])),
)
const labelByKey = computed(() =>
  Object.fromEntries(menuConfig.value.filter((m) => m.key).map((m) => [m.key, m.label])),
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
  return segment in pathByKey.value ? segment : 'dashboard'
}

const currentLabel = computed(
  () => labelByKey.value[selectedKeys.value[0]] || t('admin.consoleSubtitle'),
)

function onMenuClick({ key }) {
  router.push(pathByKey.value[key])
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
  z-index: 50;
}

.admin-sider-mobile {
  position: fixed;
  top: 0;
  left: 0;
  height: 100vh;
  transition: transform 0.2s ease;
}
.admin-sider-mobile.admin-sider-collapsed {
  transform: translateX(-100%);
}
.sider-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.4);
  z-index: 40;
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
  background: var(--c-bg-card);
  border-bottom: 1px solid var(--c-border);
  box-shadow: 0 1px 4px rgba(0, 21, 41, 0.08);
  position: sticky;
  top: 0;
  z-index: 30;
}

.admin-header-left {
  min-width: 0;
  overflow: hidden;
}

.admin-header-right {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-shrink: 0;
}

.admin-content {
  margin: 24px;
  padding: 24px;
  background: var(--c-bg-card);
  color: var(--c-text);
  min-height: calc(100vh - 64px - 70px - 48px);
  border-radius: 8px;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
}

.admin-footer {
  text-align: center;
  color: var(--c-text-muted);
  background: transparent;
}

@media (max-width: 1199px) {
  .admin-header {
    padding: 0 16px;
  }
  .admin-header-right {
    gap: 6px;
  }
  .admin-content {
    margin: 16px;
    padding: 16px;
  }
  .who-tag {
    max-width: 220px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
}

@media (max-width: 767px) {
  .admin-header {
    padding: 0 8px;
  }
  .admin-content {
    margin: 8px;
    padding: 12px;
  }
  .who-tag {
    display: none;
  }
  .btn-text {
    display: none;
  }
  .admin-footer {
    font-size: 12px;
    padding: 8px;
  }
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
