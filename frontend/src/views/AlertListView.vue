<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { alertsApi } from '../services/api.js'
import { ALERT_TYPES, PRIORITY, STATUS } from '../entities/Alert.js'

const router = useRouter()

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------
const alerts      = ref([])
const summary     = ref(null)
const loading     = ref(true)
const error       = ref(null)

const filters = ref({
  status:     '',
  priority:   '',
  alert_type: '',
  search:     '',
})

// ---------------------------------------------------------------------------
// Data fetching
// ---------------------------------------------------------------------------
async function fetchAll() {
  loading.value = true
  error.value   = null
  try {
    const params = Object.fromEntries(
      Object.entries(filters.value).filter(([, v]) => v !== '')
    )
    const [listResult, summaryResult] = await Promise.all([
      alertsApi.list(params),
      alertsApi.summary(),
    ])
    alerts.value  = listResult.results ?? listResult
    summary.value = summaryResult
  } catch (e) {
    error.value = 'Could not load alerts. Is the backend running?'
    console.error(e)
  } finally {
    loading.value = false
  }
}

onMounted(fetchAll)

// Re-fetch when any filter changes (debounced for search field)
let searchTimer = null
watch(
  () => ({ ...filters.value }),
  (newVal, oldVal) => {
    if (newVal.search !== oldVal.search) {
      clearTimeout(searchTimer)
      searchTimer = setTimeout(fetchAll, 350)
    } else {
      fetchAll()
    }
  },
  { deep: true }
)

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
const PRIORITY_ORDER = { CRITICAL: 0, HIGH: 1, MEDIUM: 2, LOW: 3 }

function priorityClass(priority) {
  return `badge badge--${priority.toLowerCase()}`
}

function statusClass(status) {
  return `badge badge--status-${status.toLowerCase()}`
}

function urgencyLabel(days) {
  if (days == null) return '—'
  if (days <= 3)  return `${days}d ⚠`
  if (days <= 7)  return `${days}d`
  return `${days}d`
}

function formatDate(date) {
  if (!date) return '—'
  return new Intl.DateTimeFormat('es-ES', { day: '2-digit', month: '2-digit', year: '2-digit' })
    .format(date instanceof Date ? date : new Date(date))
}

function formatEUR(value) {
  if (value == null) return '—'
  return new Intl.NumberFormat('es-ES', { style: 'currency', currency: 'EUR', maximumFractionDigits: 0 })
    .format(value)
}

function goToDetail(alert) {
  router.push({ name: 'alert-detail', params: { id: alert.id } })
}

// ---------------------------------------------------------------------------
// Summary card helpers
// ---------------------------------------------------------------------------
const summaryCards = computed(() => {
  if (!summary.value) return []
  const s = summary.value
  return [
    { label: 'Total',       value: s.total,                       accent: 'neutral' },
    { label: 'Open',        value: s.by_status.OPEN ?? 0,        accent: 'info'    },
    { label: 'Critical',    value: s.by_priority.CRITICAL ?? 0,  accent: 'critical'},
    { label: 'High',        value: s.by_priority.HIGH ?? 0,      accent: 'high'    },
    { label: 'In Progress', value: s.by_status.IN_PROGRESS ?? 0, accent: 'warning' },
    { label: 'Resolved',    value: s.by_status.RESOLVED ?? 0,    accent: 'success' },
  ]
})
</script>

<template>
  <div class="alert-list-view">

    <!-- Summary cards -->
    <section v-if="summary" class="summary-row">
      <div
        v-for="card in summaryCards"
        :key="card.label"
        class="summary-card"
        :class="`summary-card--${card.accent}`"
      >
        <span class="summary-card__value">{{ card.value }}</span>
        <span class="summary-card__label">{{ card.label }}</span>
      </div>
    </section>

    <!-- Filters -->
    <section class="filters-bar">
      <input
        v-model="filters.search"
        class="filter-input filter-input--search"
        placeholder="Search title, client, family…"
      />

      <select v-model="filters.status" class="filter-select">
        <option value="">All statuses</option>
        <option v-for="(s, key) in STATUS" :key="key" :value="s.value">{{ s.label }}</option>
      </select>

      <select v-model="filters.priority" class="filter-select">
        <option value="">All priorities</option>
        <option v-for="(p, key) in PRIORITY" :key="key" :value="p.value">{{ p.label }}</option>
      </select>

      <select v-model="filters.alert_type" class="filter-select">
        <option value="">All types</option>
        <option v-for="(t, key) in ALERT_TYPES" :key="key" :value="t.code">
          {{ t.code }} — {{ t.label }}
        </option>
      </select>

      <button class="btn-reset" @click="filters = { status: '', priority: '', alert_type: '', search: '' }">
        Reset
      </button>
    </section>

    <!-- Error state -->
    <div v-if="error" class="state-msg state-msg--error">{{ error }}</div>

    <!-- Loading state -->
    <div v-else-if="loading" class="state-msg">Loading alerts…</div>

    <!-- Empty state -->
    <div v-else-if="alerts.length === 0" class="state-msg">
      No alerts match the current filters.
    </div>

    <!-- Table -->
    <div v-else class="table-wrapper">
      <table class="alert-table">
        <thead>
          <tr>
            <th>Type</th>
            <th>Priority</th>
            <th>Status</th>
            <th>Client</th>
            <th>Family</th>
            <th>Channel</th>
            <th>Impact</th>
            <th>Urgency</th>
            <th>Created</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="alert in alerts"
            :key="alert.id"
            class="alert-row"
            @click="goToDetail(alert)"
          >
            <td>
              <span class="type-tag" :title="alert.typeInfo?.description">
                {{ alert.alertType }}
              </span>
              <span class="type-label">{{ alert.typeInfo?.label }}</span>
            </td>
            <td>
              <span :class="priorityClass(alert.priority)">{{ alert.priority }}</span>
            </td>
            <td>
              <span :class="statusClass(alert.status)">{{ alert.statusInfo?.label ?? alert.status }}</span>
            </td>
            <td class="client-cell">
              <span v-if="alert.clientExternalId">#{{ alert.clientExternalId }}</span>
              <span v-if="alert.clientProvince" class="province">{{ alert.clientProvince }}</span>
            </td>
            <td>{{ alert.affectedFamily ?? '—' }}</td>
            <td>{{ alert.channelLabel ?? '—' }}</td>
            <td class="numeric">{{ formatEUR(alert.economicImpact) }}</td>
            <td class="numeric" :class="{ 'urgency--low': alert.urgencyDays != null && alert.urgencyDays <= 3 }">
              {{ urgencyLabel(alert.urgencyDays) }}
            </td>
            <td>{{ formatDate(alert.createdAt) }}</td>
          </tr>
        </tbody>
      </table>
    </div>

  </div>
</template>

<style scoped>
.alert-list-view { display: flex; flex-direction: column; gap: 1.5rem; }

/* Summary cards */
.summary-row { display: flex; gap: 1rem; flex-wrap: wrap; }

.summary-card {
  background: #fff;
  border-radius: 10px;
  padding: .9rem 1.4rem;
  min-width: 110px;
  display: flex;
  flex-direction: column;
  gap: .2rem;
  box-shadow: 0 1px 4px rgba(0,0,0,.07);
  border-left: 4px solid #cbd5e0;
}
.summary-card--critical { border-color: #e53e3e; }
.summary-card--high     { border-color: #dd6b20; }
.summary-card--warning  { border-color: #d69e2e; }
.summary-card--info     { border-color: #3182ce; }
.summary-card--success  { border-color: #38a169; }
.summary-card--neutral  { border-color: #718096; }

.summary-card__value { font-size: 1.8rem; font-weight: 700; line-height: 1; color: #1a202c; }
.summary-card__label { font-size: .75rem; color: #718096; text-transform: uppercase; letter-spacing: .5px; }

/* Filters */
.filters-bar { display: flex; gap: .75rem; flex-wrap: wrap; align-items: center; }

.filter-input,
.filter-select {
  padding: .45rem .75rem;
  border: 1px solid #cbd5e0;
  border-radius: 6px;
  font-size: .875rem;
  background: #fff;
  color: #2d3748;
  outline: none;
}
.filter-input:focus,
.filter-select:focus { border-color: #4299e1; box-shadow: 0 0 0 2px rgba(66,153,225,.25); }
.filter-input--search { flex: 1; min-width: 220px; }

.btn-reset {
  padding: .45rem 1rem;
  border: 1px solid #cbd5e0;
  border-radius: 6px;
  background: #edf2f7;
  color: #4a5568;
  font-size: .875rem;
  cursor: pointer;
}
.btn-reset:hover { background: #e2e8f0; }

/* States */
.state-msg {
  padding: 3rem;
  text-align: center;
  color: #718096;
  background: #fff;
  border-radius: 10px;
}
.state-msg--error { color: #c53030; background: #fff5f5; border: 1px solid #feb2b2; }

/* Table */
.table-wrapper { background: #fff; border-radius: 10px; overflow: hidden; box-shadow: 0 1px 4px rgba(0,0,0,.07); }

.alert-table { width: 100%; border-collapse: collapse; font-size: .875rem; }

.alert-table thead { background: #f7fafc; }
.alert-table th {
  padding: .75rem 1rem;
  text-align: left;
  font-size: .75rem;
  text-transform: uppercase;
  letter-spacing: .5px;
  color: #718096;
  border-bottom: 1px solid #e2e8f0;
}

.alert-row {
  cursor: pointer;
  transition: background .1s;
  border-bottom: 1px solid #edf2f7;
}
.alert-row:last-child { border-bottom: none; }
.alert-row:hover { background: #ebf8ff; }

.alert-table td { padding: .7rem 1rem; vertical-align: middle; }

.type-tag {
  display: inline-block;
  background: #ebf8ff;
  color: #2b6cb0;
  border-radius: 4px;
  padding: 1px 6px;
  font-size: .75rem;
  font-weight: 700;
  margin-right: .4rem;
}
.type-label { color: #4a5568; }

/* Badges */
.badge {
  display: inline-block;
  border-radius: 999px;
  padding: 2px 10px;
  font-size: .72rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: .4px;
}
.badge--critical { background: #fff5f5; color: #c53030; }
.badge--high     { background: #fffaf0; color: #c05621; }
.badge--medium   { background: #fefcbf; color: #744210; }
.badge--low      { background: #f0fff4; color: #276749; }

.badge--status-open        { background: #ebf8ff; color: #2b6cb0; }
.badge--status-in_progress { background: #fef3c7; color: #92400e; }
.badge--status-resolved    { background: #f0fff4; color: #276749; }
.badge--status-dismissed   { background: #f7fafc; color: #718096; }

.client-cell { display: flex; flex-direction: column; gap: .1rem; }
.province    { font-size: .75rem; color: #718096; }

.numeric { text-align: right; font-variant-numeric: tabular-nums; }
.urgency--low { color: #c53030; font-weight: 700; }
</style>
