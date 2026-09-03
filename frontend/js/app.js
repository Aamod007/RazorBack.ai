// ==========================================================================
// DisputeGuard Frontend Controller — Track 02 AI Risk Manager
// ==========================================================================

let allDisputes = [];
let activeFilter = 'all';
let currentActiveDisputeId = null;
let currentActiveDisputeDetail = null;

document.addEventListener('DOMContentLoaded', () => {
  fetchSystemStatus();
  fetchDisputes();
  fetchEvaluationMetrics();
  
  // Polling queue every 6 seconds
  setInterval(fetchDisputes, 6000);
});

// 1. System Status
async function fetchSystemStatus() {
  try {
    const res = await fetch('/api/system/status');
    const data = await res.json();
    const badge = document.getElementById('modeBadge');
    if (data.mode === 'live_test_api') {
      badge.textContent = `Mode: Live Test API (${data.key_id_preview})`;
      badge.style.borderColor = 'var(--emerald)';
      badge.style.color = '#34d399';
    } else {
      badge.textContent = `Mode: Sandbox Mode (Zero-Credential Ready)`;
    }
  } catch (err) {
    console.error('Failed to fetch system status', err);
  }
}

// 2. Fetch & Render Disputes Queue
async function fetchDisputes() {
  try {
    const res = await fetch('/api/disputes');
    allDisputes = await res.json();
    renderDisputeTable();
    updateKPIs();
  } catch (err) {
    console.error('Failed to fetch disputes', err);
  }
}

function updateKPIs() {
  const activeCount = allDisputes.filter(d => d.status !== 'closed').length;
  document.getElementById('kpiActiveCount').textContent = activeCount;

  // Capital defended
  const contestedDisputes = allDisputes.filter(d => 
    d.decision_status === 'auto_contested' || d.decision_status === 'manually_contested'
  );
  const totalProtected = contestedDisputes.reduce((sum, d) => sum + (d.amount || 0), 0);
  document.getElementById('kpiCapitalProtected').textContent = `₹${totalProtected.toLocaleString('en-IN')}`;

  // Update filter counters
  document.getElementById('countFilterAll').textContent = allDisputes.length;
  document.getElementById('countFilterReview').textContent = allDisputes.filter(d => 
    d.decision_status === 'draft_pending_review' || d.decision_status === 'upload_failed_review'
  ).length;
  document.getElementById('countFilterContested').textContent = contestedDisputes.length;
  document.getElementById('countFilterAccepted').textContent = allDisputes.filter(d => 
    d.decision_status === 'auto_accepted' || d.decision_status === 'manually_accepted'
  ).length;
  document.getElementById('countFilterFailed').textContent = allDisputes.filter(d => 
    d.decision_status === 'upload_failed_review'
  ).length;
}

function setFilter(filter) {
  activeFilter = filter;
  document.querySelectorAll('.filter-tab').forEach(t => t.classList.remove('active'));
  event.target.classList.add('active');
  renderDisputeTable();
}

function renderDisputeTable() {
  const tbody = document.getElementById('disputeTableBody');
  if (!allDisputes || allDisputes.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="7" style="text-align: center; padding: 2.5rem; color: var(--text-muted);">
          No disputes currently in ledger. Click Step 1 in the Evaluator Controller above to seed a dispute!
        </td>
      </tr>
    `;
    return;
  }

  let filtered = allDisputes;
  if (activeFilter === 'review') {
    filtered = allDisputes.filter(d => d.decision_status === 'draft_pending_review' || d.decision_status === 'upload_failed_review');
  } else if (activeFilter === 'contested') {
    filtered = allDisputes.filter(d => d.decision_status === 'auto_contested' || d.decision_status === 'manually_contested');
  } else if (activeFilter === 'accepted') {
    filtered = allDisputes.filter(d => d.decision_status === 'auto_accepted' || d.decision_status === 'manually_accepted');
  } else if (activeFilter === 'failed') {
    filtered = allDisputes.filter(d => d.decision_status === 'upload_failed_review');
  }

  const now = Math.floor(Date.now() / 1000);

  tbody.innerHTML = filtered.map(d => {
    // Hours remaining
    const hoursRem = d.respond_by > now ? ((d.respond_by - now) / 3600).toFixed(1) : 0;
    const isUrgent = hoursRem > 0 && hoursRem <= 24;

    // Status badge class
    let badgeClass = 'badge-draft-pending';
    let statusLabel = d.decision_status.replace(/_/g, ' ');
    if (d.decision_status === 'auto_contested') {
      badgeClass = 'badge-auto-contested';
      statusLabel = 'AUTO CONTESTED';
    } else if (d.decision_status === 'manually_contested') {
      badgeClass = 'badge-manually-contested';
      statusLabel = 'MANUAL CONTEST';
    } else if (d.decision_status === 'auto_accepted' || d.decision_status === 'manually_accepted') {
      badgeClass = 'badge-auto-accepted';
      statusLabel = d.decision_status === 'auto_accepted' ? 'AUTO ACCEPTED' : 'MANUAL ACCEPT';
    } else if (d.decision_status === 'upload_failed_review') {
      badgeClass = 'badge-upload-failed';
      statusLabel = 'UPLOAD FAILED (REVIEW)';
    }

    return `
      <tr class="dispute-row" onclick="openDisputeModal('${d.id}')">
        <td class="disp-id-cell">
          <span>${d.id}</span>
          <span class="disp-source-badge">${d.source}</span>
        </td>
        <td>
          <span class="badge-reason">${d.reason_code.replace(/_/g, ' ')}</span>
          <div style="font-size: 0.72rem; color: var(--text-muted); margin-top: 0.2rem;">Phase: ${d.phase}</div>
        </td>
        <td style="font-family: var(--font-mono); font-weight: 700;">
          ₹${d.amount.toLocaleString('en-IN')}
        </td>
        <td>
          <span class="sla-badge ${isUrgent ? 'sla-urgent' : ''}">
            ⏱ ${hoursRem}h remaining
          </span>
        </td>
        <td>
          <div class="win-prob-cell">
            <span style="font-size: 0.75rem; color: var(--text-muted);">AI Win Probability</span>
            <span class="win-prob-val" id="rowProb_${d.id}">Evaluating...</span>
          </div>
        </td>
        <td>
          <span class="status-pill-badge ${badgeClass}">${statusLabel}</span>
        </td>
        <td>
          <button class="btn-action-view" onclick="event.stopPropagation(); openDisputeModal('${d.id}')">
            Inspect & Review
          </button>
        </td>
      </tr>
    `;
  }).join('');

  // Fetch individual probabilities for rows
  filtered.forEach(d => loadRowProb(d.id));
}

async function loadRowProb(disputeId) {
  try {
    const res = await fetch(`/api/disputes/${disputeId}`);
    const data = await res.json();
    const elem = document.getElementById(`rowProb_${disputeId}`);
    if (!elem) return;

    if (data.decision && typeof data.decision.win_probability === 'number') {
      const p = Math.round(data.decision.win_probability * 100);
      let color = 'var(--emerald)';
      if (p < 40) color = 'var(--rose)';
      else if (p < 65) color = 'var(--amber)';
      elem.innerHTML = `
        <span style="color: ${color}; font-weight: 700;">${p}%</span>
        <div class="prob-bar-track" style="margin-top: 2px;">
          <div class="prob-bar-fill ${p >= 65 ? 'prob-high' : (p >= 40 ? 'prob-mid' : 'prob-low')}" style="width: ${p}%;"></div>
        </div>
      `;
    } else {
      elem.textContent = 'Pending';
    }
  } catch (e) {
    // Ignore silent row refresh errors
  }
}

// 3. Dispute Detail Modal
async function openDisputeModal(disputeId) {
  currentActiveDisputeId = disputeId;
  const modal = document.getElementById('disputeModal');
  modal.classList.add('open');

  try {
    const res = await fetch(`/api/disputes/${disputeId}`);
    const data = await res.json();
    currentActiveDisputeDetail = data;

    // Header Info
    document.getElementById('modalDisputeId').textContent = data.dispute.id;
    document.getElementById('modalSubhead').textContent = 
      `Amount: ₹${data.dispute.amount.toLocaleString('en-IN')} • Reason: ${data.dispute.reason_code} • Phase: ${data.dispute.phase} • SLA: ${data.time_remaining_hours}h left`;

    // 1. Evidence Packet Tab
    renderEvidenceTab(data);

    // 2. ML Features Tab
    renderMLTab(data);

    // 3. Decision Gate Trace Tab
    renderDecisionTab(data);

    // 4. Audit Log Replay Tab
    renderAuditTab(data);

    // Modal Action Footer Buttons Configuration
    const btnRetry = document.getElementById('modalBtnRetryUpload');
    const btnApprove = document.getElementById('modalBtnApprove');
    const btnAccept = document.getElementById('modalBtnAccept');
    const alertFail = document.getElementById('modalUploadFailureAlert');

    const status = data.dispute.decision_status;
    if (status === 'upload_failed_review') {
      alertFail.style.display = 'flex';
      btnRetry.style.display = 'inline-block';
      btnApprove.disabled = true;
      btnApprove.style.opacity = '0.5';
    } else {
      alertFail.style.display = 'none';
      btnRetry.style.display = 'none';
      btnApprove.disabled = false;
      btnApprove.style.opacity = '1';
    }

    if (status === 'auto_contested' || status === 'manually_contested' || status === 'auto_accepted' || status === 'manually_accepted') {
      btnApprove.style.display = 'none';
      btnAccept.style.display = 'none';
    } else {
      btnApprove.style.display = 'inline-block';
      btnAccept.style.display = 'inline-block';
    }

  } catch (err) {
    console.error('Failed to load dispute detail', err);
    showToast('Failed to load dispute details', 'error');
  }
}

function renderEvidenceTab(data) {
  const ev = data.evidence;
  if (!ev) return;

  const scorePct = Math.round((ev.completeness_score || 0) * 100);
  const badge = document.getElementById('modalCompletenessBadge');
  badge.textContent = `Completeness: ${scorePct}%`;
  badge.style.color = scorePct >= 70 ? '#34d399' : (scorePct >= 40 ? '#fbbf24' : '#f87171');

  const grid = document.getElementById('modalEvidenceSlotsGrid');
  const slots = ev.slots || {};
  const missingSlots = ev.missing_slots || [];

  const slotKeys = [
    'shipping_proof', 'billing_proof', 'customer_communication', 
    'proof_of_service', 'access_activity_log', 'term_and_conditions'
  ];

  grid.innerHTML = slotKeys.map(slotName => {
    const isMissing = missingSlots.includes(slotName);
    const contentList = slots[slotName] || [];
    const isPresent = !isMissing && (contentList.length > 0 || (typeof slots[slotName] === 'string' && slots[slotName].length > 0));

    let contentDesc = 'No merchant record available for this slot.';
    if (isPresent) {
      if (Array.isArray(contentList) && contentList.length > 0) {
        contentDesc = JSON.stringify(contentList[0]).slice(0, 140) + '...';
      } else {
        contentDesc = String(slots[slotName]).slice(0, 140) + '...';
      }
    }

    return `
      <div class="evidence-slot-card ${isPresent ? 'filled' : (isMissing ? 'missing' : '')}">
        <div class="slot-header">
          <span>${slotName.replace(/_/g, ' ').toUpperCase()}</span>
          <span class="slot-pill ${isPresent ? 'present' : 'empty'}">
            ${isPresent ? 'VERIFIED' : (isMissing ? 'MISSING (UNVERIFIED)' : 'EMPTY')}
          </span>
        </div>
        <div class="slot-content-text">${contentDesc}</div>
      </div>
    `;
  }).join('');

  // Explanation Letter (<= 1000 chars)
  const letterText = (ev.slots && ev.slots.explanation_letter) ? ev.slots.explanation_letter : '';
  const textarea = document.getElementById('modalExplanationLetter');
  textarea.value = letterText;
  updateCharCount();
}

function updateCharCount() {
  const textarea = document.getElementById('modalExplanationLetter');
  const counter = document.getElementById('letterCharCounter');
  const len = textarea.value.length;
  counter.textContent = `${len} / 1000`;
  if (len > 950) {
    counter.classList.add('warning');
  } else {
    counter.classList.remove('warning');
  }
}

function renderMLTab(data) {
  const dec = data.decision;
  const p = dec ? Math.round(dec.win_probability * 100) : 0;
  document.getElementById('modalMLScore').textContent = `${p}%`;

  const features = data.features || {};
  const grid = document.getElementById('modalFeaturesGrid');
  grid.innerHTML = Object.entries(features).map(([k, v]) => `
    <div style="background: var(--bg-card); padding: 0.65rem; border-radius: 6px; border: 1px solid var(--border-subtle);">
      <div style="font-size: 0.7rem; color: var(--text-muted); text-transform: uppercase;">${k.replace(/_/g, ' ')}</div>
      <div style="font-weight: 700; color: #fff; margin-top: 2px;">${v}</div>
    </div>
  `).join('');
}

function renderDecisionTab(data) {
  const dec = data.decision;
  if (!dec) return;

  const actionBadge = document.getElementById('modalDecisionActionBadge');
  actionBadge.textContent = dec.action.toUpperCase().replace(/_/g, ' ');
  document.getElementById('modalRuleFired').textContent = dec.rule_fired;
  document.getElementById('modalDecisionExplanation').textContent = dec.explanation;
  document.getElementById('modalDecisionActor').textContent = `Deciding Actor: ${dec.actor}`;
  document.getElementById('modalDecisionTime').textContent = `Evaluated: ${new Date(dec.timestamp).toLocaleTimeString()}`;
}

function renderAuditTab(data) {
  const events = data.audit_events || [];
  const timeline = document.getElementById('modalAuditTimeline');

  if (events.length === 0) {
    timeline.innerHTML = '<div style="color: var(--text-muted);">No audit events recorded.</div>';
    return;
  }

  timeline.innerHTML = events.map(evt => `
    <div class="timeline-item">
      <div class="timeline-header">
        <span class="timeline-type">${evt.event_type.replace(/_/g, ' ').toUpperCase()}</span>
        <span class="timeline-ts">${new Date(evt.timestamp).toLocaleTimeString()}</span>
      </div>
      <div class="timeline-actor">Actor: ${evt.actor}</div>
      <pre class="timeline-snapshot">${JSON.stringify(evt.payload_snapshot, null, 2)}</pre>
    </div>
  `).join('');
}

function switchModalTab(tabName) {
  document.querySelectorAll('.modal-tab-btn').forEach(btn => btn.classList.remove('active'));
  document.querySelectorAll('.tab-pane').forEach(pane => pane.classList.remove('active'));
  
  event.target.classList.add('active');
  if (tabName === 'evidence') document.getElementById('tabEvidence').classList.add('active');
  if (tabName === 'ml') document.getElementById('tabML').classList.add('active');
  if (tabName === 'decision') document.getElementById('tabDecision').classList.add('active');
  if (tabName === 'audit') document.getElementById('tabAudit').classList.add('active');
}

function closeModal() {
  document.getElementById('disputeModal').classList.remove('open');
  currentActiveDisputeId = null;
}

// 4. Modal Actions (Approve, Accept, Retry, Binder)
function openEvidenceBinderFromModal() {
  if (!currentActiveDisputeId) return;
  window.open(`/api/disputes/${currentActiveDisputeId}/binder`, '_blank');
}

async function approveContestFromModal() {
  if (!currentActiveDisputeId) return;
  const customSummary = document.getElementById('modalExplanationLetter').value;

  try {
    const res = await fetch(`/api/disputes/${currentActiveDisputeId}/approve`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        analyst_id: 'analyst_aamod',
        custom_summary: customSummary
      })
    });
    const result = await res.json();
    showToast('Contest approved and submitted to Razorpay!', 'success');
    closeModal();
    fetchDisputes();
  } catch (err) {
    showToast('Error approving contest', 'error');
  }
}

async function acceptDisputeFromModal() {
  if (!currentActiveDisputeId) return;
  if (!confirm('Are you sure you want to accept this dispute? This will concede the chargeback.')) return;

  try {
    const res = await fetch(`/api/disputes/${currentActiveDisputeId}/accept`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        analyst_id: 'analyst_aamod',
        reason: 'Analyst conceded dispute after evidence review'
      })
    });
    showToast('Dispute conceded and closed', 'success');
    closeModal();
    fetchDisputes();
  } catch (err) {
    showToast('Error accepting dispute', 'error');
  }
}

async function retryUploadForModal() {
  if (!currentActiveDisputeId) return;
  try {
    showToast('Retrying document upload with exponential backoff...', 'success');
    const res = await fetch(`/api/disputes/${currentActiveDisputeId}/retry_upload`, {
      method: 'POST'
    });
    const result = await res.json();
    if (result.status === 'success') {
      showToast('Document upload succeeded! Dispute re-evaluated.', 'success');
      openDisputeModal(currentActiveDisputeId);
      fetchDisputes();
    } else {
      showToast('Upload failed again. Retaining in escalation queue.', 'error');
    }
  } catch (err) {
    showToast('Error retrying upload', 'error');
  }
}

// 5. Evaluator Demo Runner (§4.4)
async function triggerDemoStep(archetype) {
  try {
    const isFail = archetype === 'induced_upload_failure';
    showToast(`Executing Step: ${archetype}...`, 'success');
    
    const res = await fetch('/api/simulator/seed', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        archetype: archetype,
        induce_failure: isFail
      })
    });
    const data = await res.json();
    showToast(`Seeded dispute ${data.seeded.dispute_id}`, 'success');
    await fetchDisputes();

    // Automatically open modal for evaluator to inspect
    if (data.seeded && data.seeded.dispute_id) {
      setTimeout(() => openDisputeModal(data.seeded.dispute_id), 400);
    }
  } catch (err) {
    showToast('Failed to trigger demo step', 'error');
  }
}

// 6. Held-Out Evaluation & Financial Impact Hub
async function fetchEvaluationMetrics() {
  try {
    const res = await fetch('/api/evaluation/metrics');
    const data = await res.json();
    renderEvaluationHub(data);
  } catch (err) {
    console.error('Failed to fetch evaluation metrics', err);
  }
}

function renderEvaluationHub(data) {
  if (!data || !data.metrics) return;

  document.getElementById('evalSampleCount').textContent = `Held-Out Set: ${data.held_out_samples} cases`;

  // Core Metrics
  document.getElementById('metricPrecision').textContent = `${(data.metrics.precision * 100).toFixed(1)}%`;
  document.getElementById('metricRecall').textContent = `${(data.metrics.recall * 100).toFixed(1)}%`;
  document.getElementById('metricF1').textContent = `${(data.metrics.f1_score * 100).toFixed(1)}%`;
  document.getElementById('metricAUC').textContent = `${(data.metrics.roc_auc * 100).toFixed(1)}%`;

  // Confusion Matrix
  const cm = data.confusion_matrix;
  document.getElementById('cmTP').textContent = cm.true_positives;
  document.getElementById('cmFP').textContent = cm.false_positives;
  document.getElementById('cmFN').textContent = cm.false_negatives;
  document.getElementById('cmTN').textContent = cm.true_negatives;

  // Financial Costs
  const fin = data.financial_impact_inr;
  document.getElementById('costFP').textContent = `₹${fin.false_positive_cost_inr.toLocaleString('en-IN')}`;
  document.getElementById('costFN').textContent = `₹${fin.false_negative_cost_inr.toLocaleString('en-IN')}`;

  // Win-Rate Lift
  const win = data.win_rate_comparison;
  const dgWin = (win.disputeguard_win_rate * 100).toFixed(1);
  const contestAllWin = (win.baseline_contest_all_rate * 100).toFixed(1);
  document.getElementById('winRateDG').textContent = `${dgWin}%`;
  document.getElementById('winRateComparisonText').textContent = 
    `RazorBack.ai (${dgWin}%) vs Contest-All (${contestAllWin}%) vs Accept-All (0%) [Lift: +${win.win_rate_lift_pct}%]`;
  
  // KPI Header Lift
  document.getElementById('kpiWinRateLift').textContent = `+${win.win_rate_lift_pct}%`;
  document.getElementById('kpiSlaSafety').textContent = `${data.sla_safety_rate_pct}%`;
}

async function retrainModel() {
  try {
    showToast('Retraining XGBoost on synthetic 70/30 stratified split...', 'success');
    const res = await fetch('/api/evaluation/retrain', { method: 'POST' });
    const data = await res.json();
    renderEvaluationHub(data.metrics);
    showToast('Model retrained and held-out evaluation updated!', 'success');
  } catch (err) {
    showToast('Error retraining model', 'error');
  }
}

// 7. Toast Notification Utility
function showToast(message, type = 'info') {
  const container = document.getElementById('toastContainer');
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.textContent = message;
  container.appendChild(toast);
  setTimeout(() => {
    toast.remove();
  }, 3500);
}
