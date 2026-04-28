/**
 * src/api/scheduling.js
 */
import client from './client'

export const fetchBookings = (params) => client.get('/scheduling/bookings/', { params })
export const updateBooking = (id, data) => client.patch(`/scheduling/bookings/${id}/`, data)
export const checkAvailability = (params) => client.get('/scheduling/availability/', { params })
