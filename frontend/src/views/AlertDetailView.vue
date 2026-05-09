<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { alertsApi } from '../services/api.js'
import { STATUS, ALERT_TYPES } from '../entities/Alert.js'

const props = defineProps({ id: { type: String, required: true } })
const router = useRouter()

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------
const alert       = ref(null)
const loading     = ref(true)
const error       = ref(null)
const noteBody    = ref('')
const savingNote  = ref(false)
const changingStatus = ref(false)

// ---------------------------------------------------------------------------
// Data fetching
// ---------------------------------------------------------------------------
async function fetchAlert() {
  loading.value = true
  error.value   = null
  try {
    alert.value = await alertsApi.get(props.id)
  } catch (e) {
    error.value = 'Could not load alert detail.'
    console.error(e)
  } finally {
    loading.value = false
  }
}

onMounted(fetchAlert)

// ---------------------------------------------------------------------------
// Status transitions
// ---------------------------------------------------------------------------
const TRANSITIONS = {
  OPEN:        [{ to: 'IN_PROGRESS', label: 'Start working' }, { to: 'DISMISSED', label: 'Dismiss' }],
  IN_PROGRESS: [{ to: 'RESOLVED',    label: 'Mark resolved' }, { to: 'DISMISSED', label: 'Dismiss' }],
  RESOLVED:    [{ to: 'OPEN',        label: 'Re-open' }],
  DISMISSED:   [{ to: 'OPEN',        label: 'Re-open' }],
}

const availableTransitions = computed(() =>
  alert.value ? (TRANSITIONS[alert.value.status] ?? []) : []
)

async function changeStatus(newStatus) {
  changingStatus.value = true
  try {
    alert.value = await alertsApi.updateStatus(props.id, newStatus)
  } catch (e) {
    console.error(e)
  } finally {
    changingStatus.value = false
  }
}

// ---------------------------------------------------------------------------
// Notes
// ---------------------------------------------------------------------------
async function submitNote() {
  if (!noteBody.value.trim()) return
  savingNote.value = true
  try {
    await alertsApi.addNote(props.id, noteBody.value.trim())
    noteBody.value = ''
    await fetchAlert()
  } catch (e) {
    console.error(e)
  } finally {
    savingNote.value = false
  }
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function formatDate(date) {
  if (!date) return '—'
  return new Intl.DateTimeFormat('es-ES', {
    day: '2-digit', month: '2-digit', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  }).format(date instanceof Date ? date : new Date(date))
}

function formatEUR(value) {
  if (value == null) return '—'
  return new Intl.NumberFormat('es-ES', { style: 'currency', currency: 'EUR', maximumFractionDigits: 0 })
    .format(value)
}

function priorityClass(p) { return `badge badge--${p?.toLowerCase()}` }
function statusClass(s)    { return `badge badge--status-${s?.toLowerCase()}` }
</script>

<template>
  <div class="detail-view">

    <!-- Back -->
    <button class="back-btn" @click="router.back()">← Back to alerts</button>

    <!-- Loading / Error -->
    <div v-if="loading" class="state-msg">Loading…</div>
    <div v-else-if="error" class="state-msg state-msg--error">{{ error }}</div>

    <template v-else-if="alert">

      <!-- ── Header ────────────────────────────────────────────────── -->
      <div class="detail-header">
        <div class="detail-header__meta">
          <span class="type-tag">{{ alert.alertType }}</span>
          <span class="type-name">{{ alert.typeInfo?.label }}</span>
          <span :class="priorityClass(alert.priority)">{{ alert.priority }}</span>
          <span :class="statusClass(alert.status)">{{ alert.statusInfo?.label }}</span>
        </div>
        <h1 class="detail-title">{{ alert.title }}</h1>
        <p v-if="alert.reason" class="detail-reason">{{ alert.reason }}</p>
      </div>

      <!-- ── Body grid ─────────────────────────────────────────────── -->
      <div class="detail-grid">

        <!-- Client card -->
        <section class="card">
          <h2 class="card__heading">Client</h2>
          <template v-if="alert.client">
            <dl class="info-list">
              <dt>ID</dt>   <dd>#{{ alert.client.client_id }}</dd>
              <dt>Province</dt> <dd>{{ alert.client.province ?? '—' }}</dd>
              <dt>Postal code</dt> <dd>{{ alert.client.postal_code ?? '—' }}</dd>
              <dt>Open alerts</dt> <dd>{{ alert.client.open_alert_count }}</dd>
              <dt>Total alerts</dt> <dd>{{ alert.client.alert_count }}</dd>
            </dl>
          </template>
          <p v-else class="muted">Client #{{ alert.clientId }}</p>
        </section>

        <!-- Alert details card -->
        <section class="card">
          <h2 class="card__heading">Alert details</h2>
          <dl class="info-list">
            <dt>Type</dt>
            <dd>{{ alert.alertType }} — {{ alert.typeInfo?.label }}</dd>

            <dt>Model</dt>
            <dd>{{ alert.modelLabel ?? '—' }}</dd>

            <dt>Affected family</dt>
            <dd>{{ alert.affectedFamily ?? '—' }}</dd>

            <dt>Recommended channel</dt>
            <dd>{{ alert.channelLabel ?? '—' }}</dd>

            <dt>Economic impact</dt>
            <dd>{{ formatEUR(alert.economicImpact) }}</dd>

            <dt>Urgency</dt>
            <dd :class="{ 'urgency-critical': alert.urgencyDays != null && alert.urgencyDays <= 3 }">
              {{ alert.urgencyDays != null ? `${alert.urgencyDays} days` : '—' }}
            </dd>

            <dt>Confidence</dt>
            <dd>{{ alert.confidencePct != null ? `${alert.confidencePct}%` : '—' }}</dd>

            <dt>Created</dt>
            <dd>{{ formatDate(alert.createdAt) }}</dd>

            <dt>Last updated</dt>
            <dd>{{ formatDate(alert.updatedAt) }}</dd>

            <dt v-if="alert.resolvedAt">Resolved</dt>
            <dd v-if="alert.resolvedAt">{{ formatDate(alert.resolvedAt) }}</dd>
          </dl>
        </section>

        <!-- Catalog description card -->
        <section class="card card--wide">
          <h2 class="card__heading">What this alert means</h2>
          <p class="catalog-desc">{{ alert.typeInfo?.description ?? '—' }}</p>
        </section>

        <!-- Status actions card -->
        <section class="card" v-if="availableTransitions.length">
          <h2 class="card__heading">Actions</h2>
          <div class="action-buttons">
            <button
              v-for="t in availableTransitions"
              :key="t.to"
              class="action-btn"
              :class="`action-btn--${t.to.toLowerCase()}`"
              :disabled="changingStatus"
              @click="changeStatus(t.to)"
            >
              {{ t.label }}
            </button>
          </div>
        </section>

      </div>

      <!-- ── Notes ─────────────────────────────────────────────────── -->
      <section class="card notes-section">
        <h2 class="card__heading">Notes</h2>

        <div v-if="alert.notes.length === 0" class="muted">No notes yet.</div>
        <ul v-else class="notes-list">
          <li v-for="note in alert.notes" :key="note.id" class="note-item">
            <div class="note-meta">
              <span class="note-author">{{ note.authorUsername ?? 'System' }}</span>
              <span class="note-date">{{ formatDate(note.createdAt) }}</span>
            </div>
            <p class="note-body">{{ note.body }}</p>
          </li>
        </ul>

        <form class="note-form" @submit.prevent="submitNote">
          <textarea
            v-model="noteBody"
            class="note-textarea"
            rows="3"
            placeholder="Add a note…"
          />
          <button type="submit" class="note-submit" :disabled="savingNote || !noteBody.trim()">
            {{ savingNote ? 'Saving…' : 'Add note' }}
          </button>
        </form>
      </section>

    </template>
  </div>
</template>

<style scoped>
.detail-view { display: flex; flex-direction: column; gap: 1.5rem; }

.back-btn {
  align-self: flex-start;
  background: none;
  border: none;
  color: #4299e1;
  font-size: .875rem;
  cursor: pointer;
  padding: 0;
}
.back-btn:hover { text-decoration: underline; }

/* Header */
.detail-header {
  background: #fff;
  border-radius: 10px;
  padding: 1.5rem;
  box-shadow: 0 1px 4px rgba(0,0,0,.07);
}
.detail-header__meta { display: flex; align-items: center; gap: .6rem; flex-wrap: wrap; margin-bottom: .75rem; }
.detail-title { font-size: 1.3rem; font-weight: 700; color: #1a202c; margin: 0 0 .5rem; }
.detail-reason { color: #4a5568; margin: 0; line-height: 1.6; }

/* Grid */
.detail-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 1rem;
}

/* Cards */
.card {
  background: #fff;
  border-radius: 10px;
  padding: 1.25rem;
  box-shadow: 0 1px 4px rgba(0,0,0,.07);
}
.card--wide { grid-column: 1 / -1; }

.card__heading {
  font-size: .75rem;
  text-transform: uppercase;
  letter-spacing: .6px;
  color: #718096;
  margin: 0 0 .9rem;
}

/* Info list */
.info-list { display: grid; grid-template-columns: auto 1fr; gap: .35rem .75rem; margin: 0; font-size: .875rem; }
.info-list dt { color: #718096; }
.info-list dd { margin: 0; color: #2d3748; font-weight: 500; }

.catalog-desc { color: #4a5568; line-height: 1.65; margin: 0; font-size: .9rem; }

/* Action buttons */
.action-buttons { display: flex; gap: .75rem; flex-wrap: wrap; }
.action-btn {
  padding: .5rem 1.2rem;
  border-radius: 6px;
  border: none;
  font-size: .875rem;
  font-weight: 600;
  cursor: pointer;
  transition: opacity .15s;
}
.action-btn:disabled { opacity: .5; cursor: not-allowed; }
.action-btn--in_progress { background: #ebf8ff; color: #2b6cb0; }
.action-btn--resolved    { background: #f0fff4; color: #276749; }
.action-btn--dismissed   { background: #f7fafc; color: #718096; }
.action-btn--open        { background: #fff5f5; color: #c53030; }

/* Notes */
.notes-section { display: flex; flex-direction: column; gap: 1rem; }

.notes-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: .75rem; }

.note-item {
  background: #f7fafc;
  border-radius: 6px;
  padding: .75rem;
  border-left: 3px solid #bee3f8;
}
.note-meta { display: flex; gap: 1rem; align-items: baseline; margin-bottom: .35rem; }
.note-author { font-weight: 600; font-size: .8rem; color: #2b6cb0; }
.note-date   { font-size: .75rem; color: #a0aec0; }
.note-body   { margin: 0; font-size: .875rem; color: #2d3748; line-height: 1.55; }

.note-form { display: flex; flex-direction: column; gap: .5rem; }
.note-textarea {
  width: 100%;
  padding: .6rem .75rem;
  border: 1px solid #cbd5e0;
  border-radius: 6px;
  font-size: .875rem;
  resize: vertical;
  box-sizing: border-box;
  font-family: inherit;
}
.note-textarea:focus { outline: none; border-color: #4299e1; box-shadow: 0 0 0 2px rgba(66,153,225,.2); }

.note-submit {
  align-self: flex-end;
  padding: .45rem 1.2rem;
  background: #3182ce;
  color: #fff;
  border: none;
  border-radius: 6px;
  font-size: .875rem;
  font-weight: 600;
  cursor: pointer;
}
.note-submit:disabled { opacity: .5; cursor: not-allowed; }
.note-submit:not(:disabled):hover { background: #2b6cb0; }

/* Badges (same as list view) */
.type-tag {
  display: inline-block;
  background: #ebf8ff;
  color: #2b6cb0;
  border-radius: 4px;
  padding: 2px 8px;
  font-size: .8rem;
  font-weight: 700;
}
.type-name { color: #4a5568; font-size: .875rem; }

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

.muted { color: #a0aec0; font-size: .875rem; }
.urgency-critical { color: #c53030; font-weight: 700; }

/* States */
.state-msg { padding: 3rem; text-align: center; color: #718096; }
.state-msg--error { color: #c53030; }
</style>
