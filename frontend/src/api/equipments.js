/**
 * src/api/equipments.js
 */
import client from './client'

export const fetchExperiments = () => client.get('/equipments/experiments/')
export const fetchExperiment = (id) => client.get(`/equipments/experiments/${id}/`)
export const fetchEquipmentTypes = () => client.get('/equipments/types/')
export const fetchEquipments = (params) => client.get('/equipments/', { params })
export const fetchStatusMatrix = () => client.get('/equipments/status-matrix/')
export const fetchCapacityCheck = (experimentId) =>
  client.get('/equipments/capacity-check/', { params: { experiment_id: experimentId } })

/**
 * Recipe list — scoped to the caller's lab (managers/members see their lab's
 * equipment_type recipes; requesters get [] by design).
 * @param {Object} params - { equipment_type, is_active }
 */
export const fetchRecipes = (params = {}) =>
  client.get('/equipments/recipes/', { params })

/**
 * Manager-only status flip — fires the equipments.signals post_save handler,
 * which fans out a CRITICAL notification to lab managers (報警系統 happy path).
 */
export const patchEquipment = (id, data) =>
  client.patch(`/equipments/${id}/`, data)
