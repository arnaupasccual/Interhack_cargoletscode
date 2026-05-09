// ---------------------------------------------------------------------------
// Alert entity — mirrors the backend Alert model and the alert catalog (A1–A9)
// ---------------------------------------------------------------------------

/** All nine alert types as defined in the alert catalog. */
export const ALERT_TYPES = {
  A1: {
    code: 'A1',
    label: 'Replenish Soon',
    description: 'A loyal customer is approaching their usual reorder window for a commodity family.',
    modelSource: 'M1',
    defaultChannel: 'TELEMARKETER',
    defaultPriority: 'MEDIUM',
    urgencyClass: 'low',       // low / medium / high / critical
  },
  A2: {
    code: 'A2',
    label: 'Capture Window',
    description: 'A promiscuous customer is in their expected buying window but has not ordered — opportunity to capture demand from the competition.',
    modelSource: 'M2',
    defaultChannel: 'SALES_REP',
    defaultPriority: 'MEDIUM',
    urgencyClass: 'medium',
  },
  A3: {
    code: 'A3',
    label: 'Commodity Churn',
    description: 'A loyal customer shows a sustained and statistically significant drop in commodity consumption over 3+ consecutive weeks.',
    modelSource: 'M2',
    defaultChannel: 'SALES_REP',
    defaultPriority: 'HIGH',
    urgencyClass: 'high',
  },
  A4: {
    code: 'A4',
    label: 'Technical Product Churn',
    description: 'A customer buying a technical product shows an anomalous pattern relative to their own individual history (silence, volume drop, family abandonment).',
    modelSource: 'M3',
    defaultChannel: 'SALES_REP',
    defaultPriority: 'HIGH',
    urgencyClass: 'high',
  },
  A5: {
    code: 'A5',
    label: 'Recoverable Customer',
    description: 'A previously inactive customer emits a weak reactivation signal — optimal moment to re-engage before they solidify as lost.',
    modelSource: 'M3',
    defaultChannel: 'MARKETING_AUTO',
    defaultPriority: 'MEDIUM',
    urgencyClass: 'medium',
  },
  A6: {
    code: 'A6',
    label: 'Abrupt Volume Anomaly',
    description: 'An apparently stable customer suffers a sharp, sudden volume drop with no prior gradual trend to explain it.',
    modelSource: 'M2',
    defaultChannel: 'SALES_REP',
    defaultPriority: 'CRITICAL',
    urgencyClass: 'critical',
  },
  A7: {
    code: 'A7',
    label: 'New Customer — No Second Purchase',
    description: 'A new customer has not reordered within the window M1 estimated they should have — early non-conversion risk.',
    modelSource: 'M1',
    defaultChannel: 'TELEMARKETER',
    defaultPriority: 'MEDIUM',
    urgencyClass: 'medium',
  },
  A8: {
    code: 'A8',
    label: 'Hidden Friction (Returns)',
    description: 'A customer shows a growing return/cancellation pattern that has not yet hit volume — statistically precedes churn and is the earliest signal in the system.',
    modelSource: 'M4',
    defaultChannel: 'SALES_REP',
    defaultPriority: 'HIGH',
    urgencyClass: 'high',
  },
  A9: {
    code: 'A9',
    label: 'Pre-Churn Signal',
    description: 'No single signal crosses its threshold, but the weighted combination of multiple simultaneous weak signals indicates an incipient churn process.',
    modelSource: 'M5',
    defaultChannel: 'SALES_REP',
    defaultPriority: 'HIGH',
    urgencyClass: 'high',
  },
}

/** Priority levels — ordered from most to least severe. */
export const PRIORITY = {
  CRITICAL: { value: 'CRITICAL', label: 'Critical', order: 0 },
  HIGH:     { value: 'HIGH',     label: 'High',     order: 1 },
  MEDIUM:   { value: 'MEDIUM',   label: 'Medium',   order: 2 },
  LOW:      { value: 'LOW',      label: 'Low',      order: 3 },
}

/** Workflow statuses for an alert. */
export const STATUS = {
  OPEN:        { value: 'OPEN',        label: 'Open'        },
  IN_PROGRESS: { value: 'IN_PROGRESS', label: 'In Progress' },
  RESOLVED:    { value: 'RESOLVED',    label: 'Resolved'    },
  DISMISSED:   { value: 'DISMISSED',   label: 'Dismissed'   },
}

/** Commercial channels recommended per alert. */
export const CHANNEL = {
  SALES_REP:      { value: 'SALES_REP',      label: 'Sales Representative' },
  TELEMARKETER:   { value: 'TELEMARKETER',   label: 'Telesales'            },
  MARKETING_AUTO: { value: 'MARKETING_AUTO', label: 'Marketing Automation' },
}

/** ML models that can generate alerts. */
export const MODEL_SOURCE = {
  M0: { value: 'M0', label: 'M0 — Customer Segmentation'   },
  M1: { value: 'M1', label: 'M1 — Replenishment Prediction' },
  M2: { value: 'M2', label: 'M2 — Commodity Churn'          },
  M3: { value: 'M3', label: 'M3 — Technical Product Churn'  },
  M4: { value: 'M4', label: 'M4 — Return Risk'              },
  M5: { value: 'M5', label: 'M5 — Pre-Churn Signal'         },
}

// ---------------------------------------------------------------------------
// Alert class
// ---------------------------------------------------------------------------

export class Alert {
  /**
   * @param {Object} data  Raw JSON object returned by the backend API.
   */
  constructor(data) {
    this.id              = data.id
    this.alertType       = data.alert_type          // 'A1' … 'A9'
    this.priority        = data.priority            // CRITICAL / HIGH / MEDIUM / LOW
    this.status          = data.status              // OPEN / IN_PROGRESS / RESOLVED / DISMISSED
    this.modelSource     = data.model_source        // M0 … M5

    // Content
    this.title           = data.title
    this.reason          = data.reason ?? ''        // Natural-language explanation from the model
    this.affectedFamily  = data.affected_family ?? null

    // Client (may be a nested object on detail view, or just an id on list view)
    this.clientId        = data.client                           // FK integer
    this.client          = data.client_info ?? null              // Nested object (detail only)
    this.clientExternalId = data.client_external_id ?? null      // The supplier's own client_id
    this.clientProvince  = data.client_province ?? null

    // Actionability
    this.recommendedChannel = data.recommended_channel ?? null
    this.economicImpact  = data.economic_impact != null ? parseFloat(data.economic_impact) : null
    this.urgencyDays     = data.urgency_days ?? null
    this.confidenceScore = data.confidence_score ?? null         // 0–1 float

    // Timestamps
    this.createdAt       = data.created_at  ? new Date(data.created_at)  : null
    this.updatedAt       = data.updated_at  ? new Date(data.updated_at)  : null
    this.resolvedAt      = data.resolved_at ? new Date(data.resolved_at) : null

    // Notes (only present in detail responses)
    this.notes           = (data.notes ?? []).map(n => new AlertNote(n))
  }

  // ---------------------------------------------------------------------------
  // Computed / derived properties
  // ---------------------------------------------------------------------------

  /** Full metadata object from ALERT_TYPES for this alert's code. */
  get typeInfo() {
    return ALERT_TYPES[this.alertType] ?? null
  }

  /** Human-readable label, e.g. "A3 — Commodity Churn". */
  get typeLabel() {
    return this.typeInfo
      ? `${this.alertType} — ${this.typeInfo.label}`
      : this.alertType
  }

  get priorityInfo() {
    return PRIORITY[this.priority] ?? null
  }

  get statusInfo() {
    return STATUS[this.status] ?? null
  }

  get channelLabel() {
    return CHANNEL[this.recommendedChannel]?.label ?? this.recommendedChannel
  }

  get modelLabel() {
    return MODEL_SOURCE[this.modelSource]?.label ?? this.modelSource
  }

  /** True while the alert has not been acted upon yet. */
  get isOpen()        { return this.status === 'OPEN' }
  get isInProgress()  { return this.status === 'IN_PROGRESS' }
  get isResolved()    { return this.status === 'RESOLVED' }
  get isDismissed()   { return this.status === 'DISMISSED' }
  get isClosed()      { return this.isResolved || this.isDismissed }

  get isCritical()    { return this.priority === 'CRITICAL' }
  get isHigh()        { return this.priority === 'HIGH' }

  /** Urgency class string from the catalog — useful for CSS colour coding. */
  get urgencyClass()  { return this.typeInfo?.urgencyClass ?? 'medium' }

  /** Economic impact formatted as a locale string, or null. */
  get economicImpactFormatted() {
    if (this.economicImpact == null) return null
    return new Intl.NumberFormat('es-ES', { style: 'currency', currency: 'EUR' })
      .format(this.economicImpact)
  }

  /** Confidence as a 0–100 integer percentage, or null. */
  get confidencePct() {
    if (this.confidenceScore == null) return null
    return Math.round(this.confidenceScore * 100)
  }

  // ---------------------------------------------------------------------------
  // Serialisation helpers
  // ---------------------------------------------------------------------------

  /**
   * Minimal payload for a status PATCH to /api/v1/alerts/{id}/status/
   * @param {string} newStatus
   */
  static statusPayload(newStatus) {
    return { status: newStatus }
  }

  /**
   * Reconstruct an Alert from a raw API response.
   * Convenience wrapper so callers don't need to import the class.
   */
  static fromAPI(data) {
    return new Alert(data)
  }

  /**
   * Map a list of raw API objects to Alert instances.
   */
  static listFromAPI(dataArray) {
    return dataArray.map(d => new Alert(d))
  }
}

// ---------------------------------------------------------------------------
// AlertNote class
// ---------------------------------------------------------------------------

export class AlertNote {
  constructor(data) {
    this.id             = data.id
    this.alertId        = data.alert
    this.authorId       = data.author ?? null
    this.authorUsername = data.author_username ?? null
    this.body           = data.body
    this.createdAt      = data.created_at ? new Date(data.created_at) : null
  }
}
