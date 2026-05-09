<script setup>
import { ref, reactive, onMounted, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { alertsApi } from '../services/api.js'

const router = useRouter()
const route  = useRoute()

const alerts  = ref([])
const count   = ref(0)
const loading = ref(true)
const error   = ref(null)
const page    = ref(1)
const PAGE_SIZE = 50

const filters = reactive({
  status:     route.query.status     ?? '',
  priority:   route.query.priority   ?? '',
  alert_type: route.query.alert_type ?? '',
  search:     route.query.search     ?? '',
  ordering:   '-created_at',
})

async function fetchAlerts() {
  loading.value = true
  error.value   = null
  try {
    const params = { page: page.value }
    if (filters.status)     params.status     = filters.status
    if (filters.priority)   params.priority   = filters.priority
    if (filters.alert_type) params.alert_type = filters.alert_type
    if (filters.search)     params.search     = filters.search
    if (filters.ordering)   params.ordering   = filters.ordering
    const res = await alertsApi.list(params)
    alerts.value = res.results ?? res
    count.value  = res.count   ?? alerts.value.length
  } catch (e) {
    error.value = 'Could not load alerts. Is the backend running?'
  } finally {
    loading.value = false
  }
}

onMounted(fetchAlerts)

let debounceTimer = null
watch(filters, () => {
  page.value = 1
  clearTimeout(debounceTimer)
  debounceTimer = setTimeout(fetchAlerts, 250)
}, { deep: true })

watch(page, fetchAlerts)

function resetFilters() {
  filters.status = ''
  filters.priority = ''
  filters.alert_type = ''
  filters.search = ''
  page.value = 1
}

function openAlert(id) {
  router.push(`/alerts/${id}`)
}

function priorityClass(p) {
  return `badge-${p.toLowerCase()}`
}

function statusClass(s) {
  return `badge-${s.toLowerCase()}`
}

function typeClass(t) {
  return `badge-${t.toLowerCase()}`
}

function fmtImpact(v) {
  if (v == null) return '—'
  return new Intl.NumberFormat('es-ES', { style: 'currency', currency: 'EUR', maximumFractionDigits: 0 }).format(v)
}

function fmtDate(d) {
  if (!d) return '—'
  return new Date(d).toLocaleDateString('en-GB', { day: '2-digit', month: 'short' })
}

const totalPages = () => Math.ceil(count.value / PAGE_SIZE)
</script>

<template>
  <div>
    <div class="page-header">
      <h1>Alerts</h1>
      <p v-if="!loading">{{ count.toLocaleString() }} alert{{ count !== 1 ? 's' : '' }}</p>
    </div>

    <!-- Filters -->
    <div class="card filters-bar">
      <input
        v-model="filters.search"
        class="form-control search-input"
        placeholder="Search client, family, title…"
      />

      <select v-model="filters.status" class="form-control">
        <option value="">All statuses</option>
        <option value="OPEN">Open</option>
        <option value="IN_PROGRESS">In Progress</option>
        <option value="RESOLVED">Resolved</option>
        <option value="DISMISSED">Dismissed</option>
      </select>

      <select v-model="filters.priority" class="form-control">
        <option value="">All priorities</option>
        <option value="CRITICAL">Critical</option>
        <option value="HIGH">High</option>
        <option value="MEDIUM">Medium</option>
        <option value="LOW">Low</option>
      </select>

      <select v-model="filters.alert_type" class="form-control">
        <option value="">All types</option>
        <option value="A2">A2 — Capture Window</option>
        <option value="A3">A3 — Commodity Churn</option>
        <option value="A4">A4 — Technical Churn</option>
        <option value="A5">A5 — Recoverable</option>
        <option value="A6">A6 — Abrupt Drop</option>
        <option value="A1">A1 — Replenishment</option>
        <option value="A7">A7 — No 2nd Purchase</option>
        <option value="A8">A8 — Hidden Friction</option>
        <option value="A9">A9 — Pre-Churn</option>
      </select>

      <select v-model="filters.ordering" class="form-control">
        <option value="-created_at">Newest first</option>
        <option value="-economic_impact">Highest impact</option>
        <option value="urgency_days">Most urgent</option>
        <option value="-priority">Priority</option>
      </select>

      <button class="btn btn-secondary" @click="resetFilters">Reset</button>
    </div>

    <!-- Table -->
    <div class="card table-card">
      <div v-if="loading" class="state-loading">Loading alerts…</div>
      <div v-else-if="error" class="state-empty" style="color: var(--critical)">{{ error }}</div>
      <div v-else-if="alerts.length === 0" class="state-empty">No alerts match the current filters.</div>

      <table v-else class="alerts-table">
        <thead>
          <tr>
            <th>Type</th>
            <th>Priority</th>
            <th>Status</th>
            <th>Client</th>
            <th>Family</th>
            <th>Title</th>
            <th style="text-align:right">Impact</th>
            <th>Date</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="a in alerts"
            :key="a.id"
            class="alert-row"
            @click="openAlert(a.id)"
          >
            <td>
              <span :class="['badge', typeClass(a.alertType)]">{{ a.alertType }}</span>
            </td>
            <td>
              <span :class="['badge', priorityClass(a.priority)]">{{ a.priority }}</span>
            </td>
            <td>
              <span :class="['badge', statusClass(a.status)]">{{ a.status.replace('_', ' ') }}</span>
            </td>
            <td class="cell-mono">{{ a.clientExternalId ?? a.clientId }}</td>
            <td>{{ a.affectedFamily ?? '—' }}</td>
            <td class="cell-title">{{ a.title }}</td>
            <td class="cell-impact">{{ fmtImpact(a.economicImpact) }}</td>
            <td class="cell-date">{{ fmtDate(a.createdAt) }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Pagination -->
    <div v-if="totalPages() > 1" class="pagination">
      <button class="btn btn-secondary" :disabled="page <= 1" @click="page--">← Prev</button>
      <span class="page-info">Page {{ page }} of {{ totalPages() }}</span>
      <button class="btn btn-secondary" :disabled="page >= totalPages()" @click="page++">Next →</button>
    </div>
  </div>
</template>

<style scoped>
.filters-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  padding: 14px 16px;
  margin-bottom: 16px;
  align-items: center;
}

.search-input { flex: 1; min-width: 200px; }

.table-card { overflow: hidden; }

.alerts-table {
  width: 100%;
  border-collapse: collapse;
}

.alerts-table th {
  padding: 10px 14px;
  text-align: left;
  font-size: 11px;
  font-weight: 600;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  border-bottom: 1px solid var(--border);
  background: var(--page-bg);
}

.alerts-table td {
  padding: 11px 14px;
  border-bottom: 1px solid var(--border);
  vertical-align: middle;
}

.alert-row {
  cursor: pointer;
  transition: background 0.1s;
}
.alert-row:hover td { background: #f9fafb; }
.alert-row:last-child td { border-bottom: none; }

.cell-mono  { font-family: monospace; font-size: 12px; color: var(--text-secondary); }
.cell-title { max-width: 300px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 13px; }
.cell-impact { text-align: right; font-weight: 600; font-size: 13px; }
.cell-date  { color: var(--text-muted); font-size: 12px; white-space: nowrap; }

.pagination {
  display: flex;
  align-items: center;
  gap: 12px;
  justify-content: center;
  margin-top: 20px;
}
.page-info { font-size: 13px; color: var(--text-secondary); }
</style>
