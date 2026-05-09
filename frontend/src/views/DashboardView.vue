<script setup>
import { ref, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { alertsApi } from '../services/api.js'
import { ALERT_TYPES } from '../entities/Alert.js'

const router = useRouter()
const summary = ref(null)
const loading = ref(true)
const error = ref(null)

onMounted(async () => {
  try {
    summary.value = await alertsApi.summary()
  } catch (e) {
    error.value = 'Could not load dashboard. Is the backend running?'
  } finally {
    loading.value = false
  }
})

const statCards = computed(() => {
  if (!summary.value) return []
  const s = summary.value
  const openAlerts = s.by_status?.OPEN ?? 0
  const criticalHigh = (s.by_priority?.CRITICAL ?? 0) + (s.by_priority?.HIGH ?? 0)
  const totalImpact = null // not in summary — fetch separately if needed
  return [
    { label: 'Open Alerts', value: openAlerts, color: '#2563eb', sub: 'Require action' },
    { label: 'Critical / High', value: criticalHigh, color: '#ef4444', sub: 'Urgent attention' },
    { label: 'In Progress', value: s.by_status?.IN_PROGRESS ?? 0, color: '#d97706', sub: 'Being handled' },
    { label: 'Total Alerts', value: s.total ?? 0, color: '#374151', sub: 'All time' },
  ]
})

const typeRows = computed(() => {
  if (!summary.value?.by_type) return []
  return Object.entries(summary.value.by_type)
    .filter(([, cnt]) => cnt > 0)
    .map(([code, cnt]) => ({ code, cnt, info: ALERT_TYPES[code] }))
    .sort((a, b) => b.cnt - a.cnt)
})

const priorityRows = computed(() => {
  if (!summary.value?.by_priority) return []
  const order = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW']
  const total = Object.values(summary.value.by_priority).reduce((s, v) => s + v, 0) || 1
  return order.map(p => ({
    label: p,
    cnt: summary.value.by_priority[p] ?? 0,
    pct: Math.round(((summary.value.by_priority[p] ?? 0) / total) * 100),
  }))
})

function goToAlerts(params = {}) {
  router.push({ path: '/alerts', query: params })
}
</script>

<template>
  <div>
    <div class="page-header">
      <h1>Dashboard</h1>
      <p>Commercial alert overview — {{ new Date().toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric' }) }}</p>
    </div>

    <div v-if="loading" class="state-loading">Loading dashboard…</div>
    <div v-else-if="error" class="state-empty" style="color: var(--critical)">{{ error }}</div>

    <template v-else-if="summary">
      <!-- Stat cards -->
      <div class="stat-grid">
        <div
          v-for="card in statCards"
          :key="card.label"
          class="card stat-card"
          @click="goToAlerts()"
        >
          <div class="stat-value" :style="{ color: card.color }">{{ card.value }}</div>
          <div class="stat-label">{{ card.label }}</div>
          <div class="stat-sub">{{ card.sub }}</div>
        </div>
      </div>

      <!-- Alert types + Priority side by side -->
      <div class="two-col">
        <!-- By type -->
        <div class="card section-card">
          <h2 class="section-title">Alerts by Type</h2>
          <div v-if="typeRows.length === 0" class="state-empty" style="padding: 20px">No alerts yet</div>
          <div v-else class="type-list">
            <div
              v-for="row in typeRows"
              :key="row.code"
              class="type-row"
              @click="goToAlerts({ alert_type: row.code })"
            >
              <span :class="['badge', `badge-${row.code.toLowerCase()}`]">{{ row.code }}</span>
              <span class="type-label">{{ row.info?.label ?? row.code }}</span>
              <span class="type-count">{{ row.cnt }}</span>
            </div>
          </div>
        </div>

        <!-- By priority -->
        <div class="card section-card">
          <h2 class="section-title">Alerts by Priority</h2>
          <div class="priority-list">
            <div v-for="row in priorityRows" :key="row.label" class="priority-row">
              <span :class="['badge', `badge-${row.label.toLowerCase()}`]" style="width: 72px; justify-content: center">
                {{ row.label }}
              </span>
              <div class="priority-bar-wrap">
                <div
                  class="priority-bar"
                  :class="`bar-${row.label.toLowerCase()}`"
                  :style="{ width: row.pct + '%' }"
                />
              </div>
              <span class="priority-count">{{ row.cnt }}</span>
            </div>
          </div>

          <hr class="divider">

          <div class="status-grid">
            <div
              v-for="[status, cnt] in Object.entries(summary.by_status)"
              :key="status"
              class="status-chip"
              :class="`status-chip-${status.toLowerCase()}`"
              @click="goToAlerts({ status })"
            >
              <span class="status-cnt">{{ cnt }}</span>
              <span class="status-lbl">{{ status.replace('_', ' ') }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Quick CTA -->
      <div style="margin-top: 24px">
        <button class="btn btn-primary" @click="goToAlerts({ status: 'OPEN' })">
          View all open alerts →
        </button>
      </div>
    </template>
  </div>
</template>

<style scoped>
.stat-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin-bottom: 24px;
}

.stat-card {
  padding: 20px 22px;
  cursor: pointer;
  transition: box-shadow 0.15s, transform 0.1s;
}
.stat-card:hover { box-shadow: var(--shadow-md); transform: translateY(-1px); }

.stat-value {
  font-size: 36px;
  font-weight: 800;
  line-height: 1;
}
.stat-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  margin-top: 6px;
}
.stat-sub {
  font-size: 12px;
  color: var(--text-muted);
  margin-top: 2px;
}

.two-col {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

.section-card { padding: 20px; }
.section-title {
  font-size: 13px;
  font-weight: 700;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  margin-bottom: 14px;
}

.type-list { display: flex; flex-direction: column; gap: 8px; }
.type-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 8px;
  border-radius: 7px;
  cursor: pointer;
  transition: background 0.12s;
}
.type-row:hover { background: var(--page-bg); }
.type-label { flex: 1; font-size: 13px; color: var(--text-primary); }
.type-count { font-size: 13px; font-weight: 700; color: var(--text-secondary); }

.priority-list { display: flex; flex-direction: column; gap: 10px; }
.priority-row { display: flex; align-items: center; gap: 10px; }
.priority-bar-wrap {
  flex: 1;
  height: 8px;
  background: var(--page-bg);
  border-radius: 4px;
  overflow: hidden;
}
.priority-bar { height: 100%; border-radius: 4px; transition: width 0.3s; }
.bar-critical { background: var(--critical); }
.bar-high     { background: var(--high);     }
.bar-medium   { background: var(--medium);   }
.bar-low      { background: var(--low);      }
.priority-count { font-size: 13px; font-weight: 700; color: var(--text-secondary); width: 28px; text-align: right; }

.status-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 8px;
}
.status-chip {
  padding: 10px 12px;
  border-radius: 8px;
  cursor: pointer;
  border: 1px solid var(--border);
  transition: border-color 0.15s;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.status-chip:hover { border-color: #93c5fd; }
.status-cnt { font-size: 20px; font-weight: 700; }
.status-lbl { font-size: 11px; color: var(--text-muted); font-weight: 500; }
.status-chip-open        .status-cnt { color: var(--open-color);        }
.status-chip-in_progress .status-cnt { color: var(--in-progress-color); }
.status-chip-resolved    .status-cnt { color: var(--resolved-color);    }
.status-chip-dismissed   .status-cnt { color: var(--dismissed-color);   }
</style>
