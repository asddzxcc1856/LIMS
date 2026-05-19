/**
 * src/api/orders.js – Order-related API calls.
 */
import client from './client'

export const fetchOrders = (params) => client.get('/orders/', { params })
export const fetchOrder = (id) => client.get(`/orders/${id}/`)
export const createOrder = (data) => client.post('/orders/create/', data)

// Relay Stages
export const fetchStages = (params) => client.get('/orders/stages/', { params })
export const reviewStage = (id, data) => client.patch(`/orders/stages/${id}/review/`, data)
export const completeStage = (id) => client.patch(`/orders/stages/${id}/complete/`)
export const receiveStage = (id, data = {}) => client.post(`/orders/stages/${id}/receive/`, data)

// 上下貨 / 操作歷史 (StageEvent)
export const fetchStageEvents = (stageId) =>
  client.get(`/orders/stages/${stageId}/events/`)
export const recordStageEvent = (stageId, payload) =>
  client.post(`/orders/stages/${stageId}/events/`, payload)

// 簽核 (Approval)
export const fetchStageApprovals = (stageId) =>
  client.get(`/orders/stages/${stageId}/approvals/`)
export const signOffStage = (stageId, payload) =>
  client.post(`/orders/stages/${stageId}/approvals/`, payload)

// 分貨 (Sample / WIP split)
export const fetchOrderSamples = (orderId) =>
  client.get(`/orders/${orderId}/samples/`)
export const splitOrderSamples = (orderId, payload) =>
  client.post(`/orders/${orderId}/samples/`, payload)

