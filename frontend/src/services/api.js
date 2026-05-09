import axios from 'axios'
import { Alert } from '../entities/Alert.js'

const http = axios.create({
  baseURL: 'http://localhost:8000/api/v1/',
  timeout: 8000,
  headers: { 'Content-Type': 'application/json' },
})

// ---------------------------------------------------------------------------
// Alerts
// ---------------------------------------------------------------------------

export const alertsApi = {
  /** Paginated list with optional filters: status, priority, alert_type, client, search. */
  list(params = {}) {
    return http.get('alerts/', { params }).then(r => ({
      ...r.data,
      results: Alert.listFromAPI(r.data.results ?? r.data),
    }))
  },

  /** Full detail including nested client info and notes. */
  get(id) {
    return http.get(`alerts/${id}/`).then(r => Alert.fromAPI(r.data))
  },

  /** Dashboard counts grouped by status, priority and type. */
  summary() {
    return http.get('alerts/summary/').then(r => r.data)
  },

  /** Change status: OPEN → IN_PROGRESS → RESOLVED / DISMISSED. */
  updateStatus(id, newStatus) {
    return http.patch(`alerts/${id}/status/`, { status: newStatus }).then(r => Alert.fromAPI(r.data))
  },

  /** List notes attached to an alert. */
  getNotes(id) {
    return http.get(`alerts/${id}/notes/`).then(r => r.data)
  },

  /** Add a note to an alert. */
  addNote(id, body) {
    return http.post(`alerts/${id}/notes/`, { body }).then(r => r.data)
  },
}

// ---------------------------------------------------------------------------
// Clients
// ---------------------------------------------------------------------------

export const clientsApi = {
  list(params = {}) {
    return http.get('clients/', { params }).then(r => r.data)
  },

  get(id) {
    return http.get(`clients/${id}/`).then(r => r.data)
  },

  getAlerts(id, params = {}) {
    return http.get(`clients/${id}/alerts/`, { params })
      .then(r => Alert.listFromAPI(r.data))
  },

  getSales(id) {
    return http.get(`clients/${id}/sales/`).then(r => r.data)
  },

  getPotentials(id) {
    return http.get(`clients/${id}/potentials/`).then(r => r.data)
  },
}

// ---------------------------------------------------------------------------
// CSV uploads
// ---------------------------------------------------------------------------

export const csvApi = {
  list() {
    return http.get('csv-uploads/').then(r => r.data)
  },

  upload(file, uploadType) {
    const form = new FormData()
    form.append('file', file)
    form.append('upload_type', uploadType)
    return http.post('csv-uploads/', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }).then(r => r.data)
  },
}

export default http
