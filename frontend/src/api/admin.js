/**
 * src/api/admin.js — Superuser-only admin endpoints.
 *
 * Each domain table is wrapped in a uniform CRUD resource so the generic
 * CrudTable component can drive any table without bespoke API plumbing.
 */
import client from './client'

const resource = (path) => ({
  /** List with optional query params (search, ordering, page, page_size). */
  list: (params = {}) => client.get(`/admin/${path}/`, { params }),
  /** Retrieve a single record by id. */
  retrieve: (id) => client.get(`/admin/${path}/${id}/`),
  /** Create a new record. */
  create: (data) => client.post(`/admin/${path}/`, data),
  /** Partial update (PATCH semantics). */
  update: (id, data) => client.patch(`/admin/${path}/${id}/`, data),
  /** Delete a record. */
  remove: (id) => client.delete(`/admin/${path}/${id}/`),
})

export const adminFabs = resource('fabs')
export const adminDepartments = resource('departments')
export const adminWaferLots = resource('wafer-lots')
export const adminUsers = {
  ...resource('users'),
  /** Provision N requesters / lab members / lab managers in one shot. */
  bulkCreate: (payload) => client.post('/admin/users/bulk-create/', payload),
  /** Delete N user accounts; safety rails on backend skip self/last superuser. */
  bulkDelete: (ids) => client.post('/admin/users/bulk-delete/', { ids }),
}
export const adminExperiments = resource('experiments')
export const adminEquipmentTypes = resource('equipment-types')
export const adminEquipment = resource('equipment')
export const adminRecipes = resource('recipes')
export const adminExperimentRequirements = resource('experiment-requirements')
export const adminOrders = resource('orders')
export const adminOrderStages = resource('order-stages')
export const adminBookings = resource('bookings')
export const adminStageEvents = resource('stage-events')
export const adminApprovals = resource('approvals')
export const adminSamples = resource('samples')

/** Aggregated dashboard statistics. */
export const fetchAdminDashboard = () => client.get('/monitoring/dashboard/')

/** Paginated, filterable activity log feed. */
export const fetchActivityLogs = (params = {}) =>
  client.get('/monitoring/logs/', { params })

/** Daily equipment utilization% for the last N days. */
export const fetchChartEquipmentUtilization = (days = 7) =>
  client.get('/monitoring/charts/equipment-utilization/', { params: { days } })

/** Daily order trend (created / done / rejected). */
export const fetchChartOrderTrend = (days = 30) =>
  client.get('/monitoring/charts/order-trend/', { params: { days } })

/** Top-N operators by event + approval volume. */
export const fetchChartOperatorActivity = (params = {}) =>
  client.get('/monitoring/charts/operator-activity/', { params })

// ──────── Notifications (bell icon) ────────
export const fetchNotifications = (params = {}) =>
  client.get('/monitoring/notifications/', { params })

export const fetchNotificationSummary = () =>
  client.get('/monitoring/notifications/summary/')

export const markNotificationRead = (id) =>
  client.post(`/monitoring/notifications/${id}/mark-read/`)

export const markAllNotificationsRead = () =>
  client.post('/monitoring/notifications/mark-all-read/')
