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

