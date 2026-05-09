<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { alertsApi } from '../services/api.js'

const props   = defineProps({ id: { type: String, required: true } })
const router  = useRouter()
const alert   = ref(null)
const loading = ref(true)
const error   = ref(null)
const noteBody = ref('')
const savingNote = ref(false)
const updatingStatus = ref(false)

onMounted(async () => {
  try {
    alert.value = await alertsApi.get(props.id)
  } catch (e) {
    error.value = 'Alert not found.'
  } finally {
    loading.value = false
  }
})

async function updateStatus(newStatus) {
  updatingStatus.value = true
  try {
    alert.value = await alertsApi.updateStatus(props.id, newStatus)
  } finally {
    updatingStatus.value = false
  }
}

async function addNote() {
  if (!noteBody.value.trim()) return
  savingNote.value = true
  try {
    const note = await alertsApi.addNote(props.id, noteBody.value.trim())
    alert.value.notes.push(note)
    noteBody.value = ''
  } finally {
    savingNote.value = false
  }
}

function fmtImpact(v) {
  if (v == null) return '—'
  return new Intl.NumberFormat('es-ES', { style: 'currency', currency: 'EUR' }).format(v)
}

function fmtDate(d) {
  if (!d) return '—'
  return new Date(d).toLocaleString('en-GB', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' })
}

const STATUS_TRANSITIONS = {
  OPEN:        ['IN_PROGRESS', 'DISMISSED'],
  IN_PROGRESS: ['RESOLVED',    'DISMISSED'],
  RESOLVED:    [],
  DISMISSED:   ['OPEN'],
}

function availableTransitions(current) {
  return STATUS_TRANSITIONS[current] ?? []
}

function statusBtnClass(s) {
  if (s === 'RESOLVED')  return 'btn-success'
  if (s === 'DISMISSED') return 'btn-danger'
  return 'btn-secondary'
}
</script>

<template>
  <div>
    <!-- Back -->
    <button class="btn btn-secondary back-btn" @click="router.back()">← Back</button>

    <div v-if="loading" class="state-loading">Loading alert…</div>
    <div v-else-if="error" class="state-empty" style="color: var(--critical)">{{ error }}</div>

    <template v-else-if="alert">
      <!-- Header card -->
      <div class="card header-card">
        <div class="header-top">
          <div class="header-badges">
            <span :class="['badge', `badge-${alert.alertType.toLowerCase()}`]" style="font-size: 13px; padding: 4px 10px">
              {{ alert.alertType }}
            </span>
            <span :class="['badge', `badge-${alert.priority.toLowerCase()}`]">{{ alert.priority }}</span>
            <span :class="['badge', `badge-${alert.status.toLowerCase()}`]">{{ alert.status.replace('_', ' ') }}</span>
          </div>

          <!-- Status actions -->
          <div class="status-actions" v-if="availableTransitions(alert.status).length">
            <span class="actions-label">Mark as:</span>
            <button
              v-for="next in availableTransitions(alert.status)"
              :key="next"
              :class="['btn', statusBtnClass(next)]"
              :disabled="updatingStatus"
              @click="updateStatus(next)"
            >
              {{ next.replace('_', ' ') }}
            </button>
          </div>
        </div>

        <h1 class="alert-title">{{ alert.title }}</h1>

        <div class="meta-grid">
          <div class="meta-item">
            <span class="meta-label">Client ID</span>
            <span class="meta-value">{{ alert.clientExternalId ?? alert.clientId }}</span>
          </div>
          <div class="meta-item">
            <span class="meta-label">Province</span>
            <span class="meta-value">{{ alert.clientProvince ?? '—' }}</span>
          </div>
          <div class="meta-item">
            <span class="meta-label">Family</span>
            <span class="meta-value">{{ alert.affectedFamily ?? '—' }}</span>
          </div>
          <div class="meta-item">
            <span class="meta-label">Channel</span>
            <span class="meta-value">{{ alert.channelLabel ?? '—' }}</span>
          </div>
          <div class="meta-item">
            <span class="meta-label">Economic Impact</span>
            <span class="meta-value impact">{{ fmtImpact(alert.economicImpact) }}</span>
          </div>
          <div class="meta-item">
            <span class="meta-label">Urgency (days)</span>
            <span class="meta-value">{{ alert.urgencyDays ?? '—' }}</span>
          </div>
          <div class="meta-item">
            <span class="meta-label">Model</span>
            <span class="meta-value">{{ alert.modelLabel }}</span>
          </div>
          <div class="meta-item">
            <span class="meta-label">Created</span>
            <span class="meta-value">{{ fmtDate(alert.createdAt) }}</span>
          </div>
        </div>
      </div>

      <!-- Reason -->
      <div v-if="alert.reason" class="card reason-card">
        <h2 class="section-title">Signal Explanation</h2>
        <p class="reason-text">{{ alert.reason }}</p>
      </div>

      <!-- Notes -->
      <div class="card notes-card">
        <h2 class="section-title">Notes</h2>

        <div v-if="alert.notes.length === 0" class="no-notes">No notes yet.</div>
        <div v-else class="notes-list">
          <div v-for="note in alert.notes" :key="note.id" class="note-item">
            <div class="note-meta">
              <span class="note-author">{{ note.authorUsername ?? 'Anonymous' }}</span>
              <span class="note-date">{{ fmtDate(note.createdAt) }}</span>
            </div>
            <p class="note-body">{{ note.body }}</p>
          </div>
        </div>

        <div class="add-note">
          <textarea
            v-model="noteBody"
            class="form-control note-input"
            placeholder="Add a note or action log entry…"
            rows="3"
          />
          <button
            class="btn btn-primary"
            :disabled="!noteBody.trim() || savingNote"
            @click="addNote"
          >
            {{ savingNote ? 'Saving…' : 'Add Note' }}
          </button>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.back-btn { margin-bottom: 20px; }

.header-card { padding: 24px; margin-bottom: 16px; }
.header-top  { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; flex-wrap: wrap; margin-bottom: 14px; }
.header-badges { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }

.status-actions { display: flex; align-items: center; gap: 8px; }
.actions-label  { font-size: 12px; color: var(--text-muted); }

.alert-title {
  font-size: 20px;
  font-weight: 700;
  color: var(--text-primary);
  line-height: 1.3;
  margin-bottom: 20px;
}

.meta-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
}

.meta-item { display: flex; flex-direction: column; gap: 3px; }
.meta-label { font-size: 11px; color: var(--text-muted); font-weight: 600; text-transform: uppercase; letter-spacing: 0.04em; }
.meta-value { font-size: 14px; font-weight: 500; }
.meta-value.impact { font-size: 16px; font-weight: 700; color: #16a34a; }

.reason-card { padding: 20px; margin-bottom: 16px; }
.reason-text {
  font-size: 14px;
  line-height: 1.6;
  color: var(--text-primary);
  white-space: pre-wrap;
}

.section-title {
  font-size: 11px;
  font-weight: 700;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  margin-bottom: 14px;
}

.notes-card { padding: 20px; }
.no-notes { font-size: 13px; color: var(--text-muted); margin-bottom: 16px; }

.notes-list { display: flex; flex-direction: column; gap: 12px; margin-bottom: 20px; }
.note-item {
  background: var(--page-bg);
  border-radius: 8px;
  padding: 12px 14px;
  border: 1px solid var(--border);
}
.note-meta { display: flex; align-items: center; gap: 10px; margin-bottom: 6px; }
.note-author { font-size: 12px; font-weight: 600; color: var(--text-primary); }
.note-date   { font-size: 11px; color: var(--text-muted); }
.note-body   { font-size: 13px; line-height: 1.5; color: var(--text-primary); }

.add-note {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid var(--border);
}

.note-input { width: 100%; resize: vertical; font-family: inherit; }
</style>
