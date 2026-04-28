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
