const UI_VERSION = '2.7.9';
const state = { hives: [], batches: [], alerts: [], summary: {}, verifications: {}, backendVersion: null, preferredDemoHiveId: null };
const $ = (id) => document.getElementById(id);

async function jsonFetch(url, options = {}) {
  const res = await fetch(url, options);
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.error || `HTTP ${res.status}`);
  return body;
}

function escapeHtml(v) {
  const d = document.createElement('div');
  d.textContent = v ?? '';
  return d.innerHTML;
}

let loadInProgress = false;
const actionLocks = new Set();
let registrationToastTimer = null;

function setRefreshUi(mode, detail = '') {
  const button = $('refresh');
  const status = $('refresh-status');
  if (mode === 'loading') {
    if (button) {
      button.disabled = true;
      button.textContent = 'Refreshing…';
    }
    if (status) {
      status.textContent = 'Updating dashboard…';
      status.className = 'refresh-status is-loading';
    }
    return;
  }
  if (mode === 'success') {
    if (button) {
      button.disabled = false;
      button.textContent = 'Refresh';
    }
    if (status) {
      status.textContent = detail || 'Updated just now';
      status.className = 'refresh-status is-success';
    }
    return;
  }
  if (button) {
    button.disabled = false;
    button.textContent = 'Refresh';
  }
  if (status) {
    status.textContent = detail || 'Refresh failed';
    status.className = 'refresh-status is-error';
  }
}

async function checkBackendVersion() {
  try {
    const info = await jsonFetch(`/api/version?_=${Date.now()}`);
    state.backendVersion = info.version || null;
    if (state.backendVersion && state.backendVersion !== UI_VERSION) {
      logEvent('review', 'Version mismatch', `UI ${UI_VERSION} is running against backend ${state.backendVersion}. Stop the old server and restart this release.`);
      return false;
    }
    return true;
  } catch (e) {
    console.warn('Nectar Chain backend version check unavailable', e);
    return true;
  }
}

function clearRegistrationState() {
  const preview = $('registration-preview');
  if (preview) { preview.hidden = true; preview.innerHTML = ''; }
  if (registrationToastTimer) { clearTimeout(registrationToastTimer); registrationToastTimer = null; }
}

function showRegistrationToast(kind, title, detail, duration = 4500) {
  const el = $('registration-preview');
  if (!el) return;
  if (registrationToastTimer) clearTimeout(registrationToastTimer);
  el.hidden = false;
  el.className = `registration-toast ${kind === 'error' ? 'error' : 'success'}`;
  el.innerHTML = `<strong>${escapeHtml(title)}</strong><span>${escapeHtml(detail)}</span>`;
  registrationToastTimer = setTimeout(() => {
    el.hidden = true;
    el.className = 'registration-preview';
    el.innerHTML = '';
    registrationToastTimer = null;
  }, duration);
}

function clearEventLog() {
  const el = $('event-log');
  if (el) el.innerHTML = '';
}

function setActionLocked(id, locked, label = 'Working…') {
  if (locked) actionLocks.add(id); else actionLocks.delete(id);
  document.querySelectorAll(`[data-action-id="${CSS.escape(id)}"]`).forEach(btn => {
    btn.disabled = locked;
    if (locked) {
      if (!btn.dataset.originalText) btn.dataset.originalText = btn.textContent;
      btn.textContent = label;
    } else if (btn.dataset.originalText) {
      btn.textContent = btn.dataset.originalText;
      delete btn.dataset.originalText;
    }
  });
}

function actionIsLocked(id) { return actionLocks.has(id); }

async function loadAll(options = {}) {
  const manual = !!options.manual;
  if (loadInProgress) {
    if (manual) {
      logEvent('review', 'Refresh skipped', 'A dashboard refresh is already in progress.');
    }
    return false;
  }

  loadInProgress = true;
  const refreshStartedAt = performance.now();
  if (manual) setRefreshUi('loading');

  const tasks = [
    ['hives', '/api/hives', state.hives, renderHives],
    ['batches', '/api/batches', state.batches, renderLedger],
    ['alerts', '/api/health-alerts', state.alerts, renderAlerts],
    ['summary', '/api/summary', state.summary, null]
  ];
  const failures = [];

  try {
    await Promise.all(tasks.map(async ([key, url, fallback, renderer]) => {
      try {
        const value = await jsonFetch(url);
        state[key] = value;
        if (renderer) renderer();
      } catch (e) {
        failures.push(`${key}: ${e.message}`);
        console.error(`Nectar Chain ${key} refresh failed`, e);
        state[key] = fallback;
        if (renderer) renderer();
      }
    }));

    renderStats();

    if (failures.length) {
      const detail = failures.join(' · ');
      logEvent('review', 'Dashboard refresh warning', detail);
      if (manual) setRefreshUi('error', 'Updated with warnings');
      return false;
    }

    if (manual) {
      const elapsed = Math.max(0, Math.round(performance.now() - refreshStartedAt));
      const summary = state.summary || {};
      const hiveCount = summary.hives ?? state.hives.length;
      const batchCount = summary.committed ?? state.batches.filter(b => b.record_hash).length;
      const timestamp = new Date().toLocaleTimeString();
      logEvent('approved', 'Dashboard refreshed', `${hiveCount} hives · ${batchCount} committed batches · data loaded successfully in ${elapsed} ms.`);
      setRefreshUi('success', `Updated ${timestamp}`);
    }
    return true;
  } catch (e) {
    console.error('Nectar Chain dashboard refresh failed', e);
    if (manual) {
      logEvent('review', 'Dashboard refresh failed', e.message);
      setRefreshUi('error', 'Refresh failed');
    }
    return false;
  } finally {
    loadInProgress = false;
    if (manual && $('refresh')?.disabled) setRefreshUi('success', `Updated ${new Date().toLocaleTimeString()}`);
  }
}

function renderStats() {
  const s = state.summary || {};
  if ($('stat-hives')) $('stat-hives').textContent = s.hives ?? state.hives.length;
  if ($('stat-batches')) $('stat-batches').textContent = s.committed ?? state.batches.filter(b => b.record_hash).length;
  if ($('stat-readings')) $('stat-readings').textContent = s.readings ?? 0;
  if ($('stat-review')) $('stat-review').textContent = s.pending_review ?? state.batches.filter(b => b.validation_status === 'PENDING_REVIEW').length;
  if ($('stat-alerts')) $('stat-alerts').textContent = s.active_alerts ?? state.alerts.filter(a => !a.acknowledged).length;
  if ($('stat-chain')) $('stat-chain').textContent = s.committed ? (s.chain_verified ? 'INTACT' : 'BROKEN') : '—';
}

function riskChip(risk) {
  if (!risk || risk === 'unknown') return '<span class="chip">unknown</span>';
  return `<span class="chip risk-chip risk-${risk}">${escapeHtml(risk.toUpperCase())} RISK</span>`;
}

function renderHives() {
  const el = $('hive-list');
  if (!el) return;
  if (!state.hives.length) {
    el.innerHTML = '<div class="empty">No hives registered yet. Load demo data or register one above.</div>';
    return;
  }
  el.innerHTML = state.hives.map(h => `
    <div class="hive-item enhanced">
      <div class="hive-icon">🐝</div>
      <div class="hive-main">
        <strong>${escapeHtml(h.hive_id)} · ${escapeHtml(h.apiary_name)}</strong>
        <small>${escapeHtml(h.beekeeper_name)} · ${escapeHtml(h.region)} · ${escapeHtml(h.floral_source)}</small>
        <div class="hive-health-line"><span>${escapeHtml(h.health?.message || 'No health context yet.')}</span></div>
      </div>
      <div class="hive-side">
        <div class="chip info">${h.last_weight ? `${h.last_weight} kg` : 'awaiting sensor'}</div>
        ${riskChip(h.health?.risk)}
      </div>
    </div>`).join('');
  renderDemoHiveOptions();
}

function renderDemoHiveOptions() {
  const select = $('demo-harvest-hive');
  if (!select) return;
  const previous = select.value;
  if (!state.hives.length) {
    select.innerHTML = '<option value="">No registered hives</option>';
    select.disabled = true;
    return;
  }
  select.disabled = false;
  select.innerHTML = state.hives.map(h => `<option value="${escapeHtml(h.hive_id)}">${escapeHtml(h.hive_id)} · ${escapeHtml(h.apiary_name)}</option>`).join('');

  // Prefer the hive that was just registered. Otherwise preserve the operator's
  // existing selection, and finally fall back to the first available hive.
  const preferred = state.preferredDemoHiveId;
  if (preferred && state.hives.some(h => h.hive_id === preferred)) {
    select.value = preferred;
  } else if (state.hives.some(h => h.hive_id === previous)) {
    select.value = previous;
  } else {
    select.value = state.hives[0].hive_id;
  }
}

function statusChip(b) {
  if (b.record_hash) return '<span class="chip ok">COMMITTED</span>';
  if (b.validation_status === 'REJECTED') return '<span class="chip" style="color:#9b1c1c;background:#fff0f1;border-color:#f0c9cd">REJECTED</span>';
  return '<span class="chip review">MANUAL REVIEW</span>';
}

function verificationBox(id) {
  const v = state.verifications[id];
  if (!v) return '';
  if (v.verified) {
    return `<div class="verification-result verified">
      <div class="verification-title">✓ HASH VERIFIED</div>
      <div class="verification-grid"><span>Record hash</span><b>VALID</b><span>Evidence bundle</span><b>VALID</b><span>Batch chain</span><b>VALID</b><span>Custody trail</span><b>VALID</b></div>
      <small>${escapeHtml(v.reason)}</small>
    </div>`;
  }
  return `<div class="verification-result tampered">
      <div class="verification-title">⚠ TAMPERING DETECTED</div>
      <div class="verification-grid"><span>Record hash</span><b>FAILED</b><span>Evidence bundle</span><b>${v.evidence_verified ? 'VALID' : 'FAILED'}</b><span>Batch chain</span><b>${v.chain_verified ? 'VALID' : 'FAILED'}</b><span>Custody trail</span><b>${v.custody_verified ? 'VALID' : 'FAILED'}</b></div>
      <small>${escapeHtml(v.reason)}</small>
    </div>`;
}

function evidencePreview(b) {
  if (!b.evidence_items?.length) return '<div class="empty compact">No camera evidence attached.</div>';
  const items = b.evidence_items.slice(0, 3).map(x => `
    <div class="evidence-thumb">
      <img src="${x.url}" alt="${escapeHtml(x.evidence_type)} evidence">
      <div><b>${escapeHtml(x.evidence_type.replaceAll('_', ' '))}</b><small>${escapeHtml(x.source)}</small></div>
    </div>`).join('');
  return `<div class="evidence-preview">${items}</div>`;
}

function nextStageButton(b) {
  const stages = ['Harvested', 'Processing', 'Distribution', 'Retail'];
  const i = stages.indexOf(b.stage);
  const n = stages[i + 1];
  return n ? `<button class="btn secondary" data-action-id="stage:${b.batch_id}:${n}" onclick="advanceStage('${b.batch_id}','${n}')">Move to ${n}</button>` : '';
}

function renderLedger() {
  const el = $('ledger-list');
  if (!el) return;
  if (!state.batches.length) {
    el.innerHTML = '<div class="empty">No batches yet. Run the simulator or load demo data.</div>';
    return;
  }
  el.innerHTML = state.batches.map(b => {
    const committed = !!b.record_hash;
    const ai = b.ai_disease_risk ? `${b.ai_disease_risk} risk` : 'AI pending';
    const evidence = b.evidence_status || 'SENSOR_ONLY';
    return `
      <article class="ledger-card">
        <div class="ledger-top">
          <div class="batch-id">${escapeHtml(b.batch_id)}</div>
          <div><h3>${escapeHtml(b.apiary_name)} · ${escapeHtml(b.floral_source)}</h3><div class="muted">${escapeHtml(b.beekeeper_name)} · ${escapeHtml(b.region)} · ${b.quantity_kg} kg</div></div>
          <div class="chips">${statusChip(b)}<span class="chip">${escapeHtml(ai)}</span><span class="chip info">Evidence: ${escapeHtml(evidence.replace('_',' '))}</span></div>
        </div>
        <div class="ledger-detail">
          <div>
            <div class="muted">Evidence + AI validation</div>
            <div>Weight: ${b.sensor_weight_before} → ${b.sensor_weight_after} kg · Δ ${b.harvest_delta_kg} kg</div>
            <div>Environment: ${b.avg_temperature ?? '—'} °C · ${b.avg_humidity ?? '—'}% RH</div>
            <div>Predicted yield: ${b.ai_predicted_yield_kg ?? '—'} kg · confidence: ${b.ai_confidence ? Math.round(b.ai_confidence * 100) + '%' : '—'}</div>
            <div>Harvest confidence: ${b.harvest_confidence ? Math.round(b.harvest_confidence * 100) + '%' : '—'}</div>
            <div>Hive-health risk: ${riskChip(b.ai_disease_risk)}</div>
            <div class="muted">${escapeHtml(b.health_warning || b.validation_reason)}</div>
            ${b.image_risk ? `<div class="visual-screen-line">📷 Visual screen: <b>${escapeHtml(b.image_risk.toUpperCase())} RISK</b> <small>${escapeHtml(b.image_method || '')}</small></div>` : ''}
            <div class="inline-buttons">
              ${committed ? `<a class="btn secondary" href="${b.scan_url}" target="_blank">Open consumer page</a><button class="btn secondary" data-action-id="verify:${b.batch_id}" onclick="verifyBatch('${b.batch_id}')">Verify integrity</button><button class="btn danger" data-action-id="tamper:${b.batch_id}" onclick="tamper('${b.batch_id}')">Simulate tampering</button>${nextStageButton(b)}` : (b.validation_status === 'REJECTED' ? `<span class="muted">Rejected — no QR or ledger record.</span>` : `<button class="btn primary" data-action-id="validate:${b.batch_id}" onclick="validateBatch('${b.batch_id}')">Validate & commit</button><button class="btn secondary" data-action-id="approve:${b.batch_id}" onclick="approve('${b.batch_id}')">Manual approve</button><button class="btn danger" data-action-id="reject:${b.batch_id}" onclick="reject('${b.batch_id}')">Reject</button><button class="btn secondary" data-action-id="health:${b.batch_id}" onclick="demoHealth('${b.batch_id}')">Run demo health screen</button>`)}
              ${!committed && b.validation_status !== 'REJECTED' ? `<button class="btn secondary" onclick="document.getElementById('evidence-${b.batch_id}').showModal()">Add camera evidence</button>` : ''}
              ${b.evidence_items?.length ? `<button class="btn secondary" onclick="toggleEvidence('${b.batch_id}')">View evidence</button>` : ''}
            </div>
            ${verificationBox(b.batch_id)}
            <div id="evidence-view-${b.batch_id}" class="evidence-expanded hidden">${evidencePreview(b)}</div>
          </div>
          <div>
            ${committed ? `<div class="muted">Committed hash</div><div class="hashbox">${b.record_hash}</div><div class="muted" style="margin-top:8px">Previous hash: ${b.prev_hash ? b.prev_hash.slice(0,24)+'…' : 'GENESIS'}</div><div class="muted" style="margin-top:8px">Evidence bundle: <code>${(b.evidence_hash || '').slice(0,24)}…</code></div>` : '<div class="empty compact">No hash / QR yet. The batch is held until review.</div>'}
            ${evidencePreview(b)}
          </div>
        </div>
      </article>
      ${!committed ? `<dialog id="evidence-${b.batch_id}" class="evidence-dialog"><form method="dialog" onsubmit="return false"><div class="dialog-head"><h3>Camera evidence · ${escapeHtml(b.batch_id)}</h3><button type="button" class="icon-btn" onclick="document.getElementById('evidence-${b.batch_id}').close()">×</button></div><p class="sub">Upload both pre/post harvest images and an optional health-screen image. Complete pre/post evidence is required before trusted commitment.</p><label>Pre-harvest image<input type="file" id="pre-${b.batch_id}" accept="image/*"></label><label>Post-harvest image<input type="file" id="post-${b.batch_id}" accept="image/*"></label><label>Health-screen image<input type="file" id="health-${b.batch_id}" accept="image/*"></label><div class="dialog-actions"><button type="button" class="btn secondary" onclick="document.getElementById('evidence-${b.batch_id}').close()">Cancel</button><button type="button" class="btn primary" onclick="uploadEvidence('${b.batch_id}')">Upload & analyze</button></div></form></dialog>` : ''}`;
  }).join('');
}

function renderAlerts() {
  const el = $('health-alert-list');
  if (!el) return;
  if (!state.alerts.length) {
    el.innerHTML = '<div class="empty">No elevated health warnings recorded.</div>';
    return;
  }
  el.innerHTML = state.alerts.map(a => `
    <div class="alert-card ${a.risk === 'high' ? 'high' : 'medium'}">
      <div class="alert-icon">${a.risk === 'high' ? '!' : 'i'}</div>
      <div><strong>${escapeHtml(a.hive_id)} · ${escapeHtml(a.apiary_name)}</strong><span>${escapeHtml(a.message)}</span><small>${escapeHtml(a.source)} · ${escapeHtml(a.timestamp.replace('T',' ').slice(0,16))}</small></div>
      ${a.acknowledged ? '<span class="chip ok">ACK</span>' : ''}
    </div>`).join('');
}

function logEvent(cls, title, detail) {
  const el = $('event-log');
  if (!el) return;
  el.insertAdjacentHTML('afterbegin', `<div class="event ${cls}"><b>${escapeHtml(title)}</b><small>${escapeHtml(detail || '')}</small></div>`);
}

function normalizeRegistrationText(value) {
  return String(value ?? '').trim().replace(/\s+/g, ' ');
}

function showRegistrationPreview(kind, title, detail) {
  if (kind === 'ok' && title === 'Registering exact values') return;
  showRegistrationToast(kind, title, detail);
}


const registrationForm = $('register-hive-form');
if (registrationForm) registrationForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const data = {
    hive_id: normalizeRegistrationText(form.elements.namedItem('hive_id')?.value).toUpperCase(),
    beekeeper_name: normalizeRegistrationText(form.elements.namedItem('beekeeper_name')?.value),
    apiary_name: normalizeRegistrationText(form.elements.namedItem('apiary_name')?.value),
    region: normalizeRegistrationText(form.elements.namedItem('region')?.value),
    floral_source: normalizeRegistrationText(form.elements.namedItem('floral_source')?.value)
  };

  if (Object.values(data).some(v => !v)) {
    showRegistrationPreview('error', 'Registration failed', 'Fill all five hive registration fields.');
    logEvent('review', 'Registration failed', 'Fill all five hive registration fields.');
    return;
  }
  if (!/^[A-Za-z0-9][A-Za-z0-9_-]{2,63}$/.test(data.hive_id)) {
    showRegistrationPreview('error', 'Registration failed', 'Invalid Hive ID. Use 3–64 letters, numbers, hyphens, or underscores.');
    logEvent('review', 'Registration failed', 'Invalid Hive ID. Use 3–64 letters, numbers, hyphens, or underscores.');
    return;
  }
  const textFields = ['beekeeper_name','apiary_name','region','floral_source'];
  const alphaNumeric = /[\p{L}\p{N}]/u;
  const invalidTextField = textFields.find(k => !alphaNumeric.test(data[k]));
  if (invalidTextField) {
    const msg = `${invalidTextField.replaceAll('_', ' ')} must contain letters or numbers.`;
    showRegistrationPreview('error', 'Registration failed', msg);
    logEvent('review', 'Registration failed', msg);
    return;
  }

  // Show the exact payload that is about to be persisted. This prevents a
  // judge/demo operator from mistaking a stale browser field for saved data.
  showRegistrationPreview('ok', 'Registering exact values', `${data.hive_id} · ${data.apiary_name} · ${data.beekeeper_name} · ${data.region} · ${data.floral_source}`);

  const button = $('register-hive');
  button.disabled = true;
  button.textContent = 'Registering…';
  try {
    const created = await jsonFetch('/api/hives',{method:'POST',headers:{'Content-Type':'application/json','Cache-Control':'no-store'},body:JSON.stringify(data)});
    const fields = ['hive_id','beekeeper_name','apiary_name','region','floral_source'];

    // Verify what is actually persisted by reading the hive back from the
    // authoritative GET endpoint. Do not rely on optional response metadata
    // because an older running backend can otherwise create the hive correctly
    // while a newer UI falsely reports an integrity failure.
    const persistedHives = await jsonFetch(`/api/hives?_=${Date.now()}`);
    const persisted = persistedHives.find(h => String(h.hive_id).toUpperCase() === data.hive_id);
    const persistedMismatch = !persisted ? 'Hive was not found after the registration request.' : fields.find(k => String(persisted[k] ?? '') !== String(data[k] ?? ''));
    if (persistedMismatch) {
      const message = typeof persistedMismatch === 'string'
        ? persistedMismatch
        : `Saved ${persistedMismatch.replaceAll('_',' ')} does not match the value submitted.`;
      showRegistrationPreview('error', 'Registration not verified', message);
      logEvent('review', 'Registration not verified', message);
      await loadAll({ manual: true });
      return;
    }

    state.hives = [...state.hives.filter(h => h.hive_id !== persisted.hive_id), persisted];
    state.hives.sort((a,b) => a.hive_id.localeCompare(b.hive_id));
    // Automatically target the newly registered hive for the next demo harvest.
    // Registration itself does NOT create a harvest batch; the explicit demo
    // harvest action below creates the batch/ledger record.
    state.preferredDemoHiveId = persisted.hive_id;
    renderHives();
    form.reset();
    showRegistrationToast('success', 'Registration verified', `${persisted.hive_id} is stored exactly as entered. The Demo hive selector in Harvest events is now set to ${persisted.hive_id}.`);
    logEvent('approved','Hive registered',`${persisted.hive_id} · ${persisted.apiary_name} · ${persisted.beekeeper_name} · ${persisted.region} · ${persisted.floral_source}`);
    await loadAll();
    renderDemoHiveOptions();
    const demoSelector = $('demo-harvest-hive');
    if (demoSelector) demoSelector.value = persisted.hive_id;
  } catch(e){
    showRegistrationPreview('error', 'Registration failed', e.message);
    logEvent('review','Registration failed',e.message);
  } finally {
    button.disabled = false;
    button.textContent = 'Register hive';
  }
});

const hiveIdInput = $('hive_id');
if (hiveIdInput) hiveIdInput.addEventListener('input', () => {
  const start = hiveIdInput.selectionStart;
  hiveIdInput.value = hiveIdInput.value.toUpperCase();
  if (typeof start === 'number') hiveIdInput.setSelectionRange(start, start);
});

if ($('refresh')) $('refresh').addEventListener('click', () => loadAll({ manual: true }));
if ($('refresh-alerts')) $('refresh-alerts').addEventListener('click', async () => {
  if (actionIsLocked('alerts-refresh')) return;
  setActionLocked('alerts-refresh', true, 'Refreshing…');
  try {
    state.alerts = await jsonFetch(`/api/health-alerts?_=${Date.now()}`);
    renderAlerts(); renderStats();
    logEvent('approved', 'Alerts refreshed', `${state.alerts.length} health alert${state.alerts.length === 1 ? '' : 's'} loaded.`);
  } catch (e) { logEvent('review','Alert refresh failed',e.message); }
  finally { setActionLocked('alerts-refresh', false); }
});

if ($('seed-demo')) $('seed-demo').addEventListener('click', async () => {
  const lockId = 'demo-seed';
  if (actionIsLocked(lockId)) return;
  setActionLocked(lockId, true, 'Reloading…');
  clearEventLog();
  clearRegistrationState();
  $('register-hive-form')?.reset();
  state.hives = [];
  state.batches = [];
  state.alerts = [];
  state.summary = {};
  state.verifications = {};
  state.preferredDemoHiveId = null;
  renderHives();
  renderLedger();
  renderAlerts();
  renderStats();
  try {
    const r = await jsonFetch('/api/demo/seed', { method: 'POST', headers: { 'Cache-Control': 'no-store' } });
    logEvent('approved', 'Demo data reloaded', 'Fresh deterministic synthetic data restored; old event history and verification state cleared.');
    await loadAll({ manual: true });
    renderDemoHiveOptions();
  } catch (e) {
    logEvent('review', 'Demo reset failed', e.message);
    await loadAll({ manual: true });
  } finally {
    setActionLocked(lockId, false);
  }
});

if ($('verify-chain')) $('verify-chain').addEventListener('click', async()=>{
  if (actionIsLocked('verify-chain')) return;
  setActionLocked('verify-chain', true, 'Verifying…');
  try {
    const r=await jsonFetch('/api/batches');
    const committed=r.filter(b=>b.record_hash);
    if(!committed.length) return logEvent('review','No committed batches','Load demo data first.');
    const checks=await Promise.all(committed.map(b=>jsonFetch(`/api/verify/${b.batch_id}`)));
    checks.forEach(c => state.verifications[c.batch_id] = c);
    const bad=checks.find(x=>!x.verified);
    logEvent(bad?'review':'approved',bad?'CHAIN BROKEN':'CHAIN INTACT',bad?`${bad.batch_id}: ${bad.reason}`:`All ${checks.length} committed batches verified successfully.`);
    await loadAll();
  } catch(e){ logEvent('review','Verification failed',e.message); }
  finally { setActionLocked('verify-chain', false); }
});


async function runDemoHarvestForSelectedHive() {
  const button = $('demo-harvest');
  const selector = $('demo-harvest-hive');
  const hiveId = selector?.value;
  const lockId = `demo-harvest:${hiveId}`;
  if (actionIsLocked(lockId)) return;
  if (!hiveId) {
    logEvent('review','Demo harvest failed','Register or load a hive first.');
    return;
  }
  if (button) button.dataset.actionId = lockId;
  setActionLocked(lockId, true, 'Running…');
  try {
    const r = await jsonFetch('/api/demo/harvest',{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({hive_id:hiveId})
    });
    const ev = r.harvest_event;
    if (!ev) {
      logEvent('review','No harvest batch created',r.message || 'The simulator did not produce a weight-triggered harvest event.');
      return;
    }
    const kind = ev.committed ? 'approved' : 'review';
    const suffix = ev.idempotent ? ' Duplicate click ignored; existing batch reused.' : '';
    logEvent(kind, `Harvest ${ev.batch_id}: ${ev.validation_status}`, `${hiveId} · ${ev.reason || 'Harvest candidate created.'}${suffix}`);
    state.preferredDemoHiveId = hiveId;
    await loadAll();
    location.hash = 'ledger';
    requestAnimationFrame(() => {
      document.getElementById('ledger')?.scrollIntoView({behavior:'smooth', block:'start'});
    });
  } catch(e) {
    logEvent('review','Demo harvest failed',e.message);
  } finally {
    setActionLocked(lockId, false);
  }
}

if ($('demo-harvest')) $('demo-harvest').addEventListener('click', runDemoHarvestForSelectedHive);
window.verifyBatch = async (id) => {
  const lockId = `verify:${id}`;
  if (actionIsLocked(lockId)) return;
  setActionLocked(lockId, true, 'Verifying…');
  try {
    const r = await jsonFetch(`/api/verify/${id}`);
    state.verifications[id] = r;
    logEvent(r.verified ? 'approved' : 'review', r.verified ? `${id} VERIFIED ✓` : `${id} TAMPERING DETECTED`, r.reason);
    await loadAll();
  } catch(e) {
    state.verifications[id] = { verified:false, reason:e.message, chain_verified:false, custody_verified:false, evidence_verified:false };
    logEvent('review', `${id} Verification failed`, e.message);
    renderLedger();
  } finally {
    setActionLocked(lockId, false);
  }
};

window.tamper = async (id) => {
  const lockId = `tamper:${id}`;
  if (actionIsLocked(lockId)) return;
  setActionLocked(lockId, true, 'Applying…');
  try {
    await jsonFetch(`/api/batch/${id}/tamper`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({field:'quantity_kg',value:999.9})});
    delete state.verifications[id];
    logEvent('review','Demo tampering applied',`${id} quantity changed without changing its committed hash.`);
    await loadAll();
  } catch(e){ logEvent('review','Tamper demo failed',e.message); }
  finally { setActionLocked(lockId, false); }
};

window.advanceStage = async (id, stage) => {
  const lockId = `stage:${id}:${stage}`;
  if (actionIsLocked(lockId)) return;
  setActionLocked(lockId, true, 'Updating…');
  try { await jsonFetch(`/api/batch/${id}/stage`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({stage})}); logEvent('approved',`${id} moved to ${stage}`,'Custody trail updated and re-verifiable.'); await loadAll(); }
  catch(e){ logEvent('review','Stage update failed',e.message); }
  finally { setActionLocked(lockId, false); }
};

window.validateBatch = async (id) => {
  const lockId = `validate:${id}`;
  if (actionIsLocked(lockId)) return;
  setActionLocked(lockId, true, 'Checking…');
  try {
    const r = await jsonFetch(`/api/batch/${id}/validate`, {method:'POST'});
    const committed = !!r.record_hash;
    logEvent(committed ? 'approved' : 'review', committed ? `${id} validated and committed` : `${id} still requires review`, r.validation_reason || 'Validation completed.');
    await loadAll();
  } catch(e) { logEvent('review','Validation failed',e.message); }
  finally { setActionLocked(lockId, false); }
};

window.reject = async (id) => {
  const lockId = `reject:${id}`;
  if (actionIsLocked(lockId)) return;
  const note = prompt('Reason for rejection (optional):') || 'Reviewer rejected the harvest candidate after inspection.';
  setActionLocked(lockId, true, 'Rejecting…');
  try {
    await jsonFetch(`/api/batch/${id}/manual-reject`, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({note})});
    logEvent('review', `${id} rejected`, 'No ledger record or QR was generated.');
    await loadAll();
  } catch(e) { logEvent('review','Rejection failed',e.message); }
  finally { setActionLocked(lockId, false); }
};

window.approve = async (id) => {
  const lockId = `approve:${id}`;
  if (actionIsLocked(lockId)) return;
  setActionLocked(lockId, true, 'Approving…');
  try { await jsonFetch(`/api/batch/${id}/manual-approve`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({note:'Reviewer inspected the evidence and approved the harvest.'})}); logEvent('approved',`${id} manually approved`,'Hash committed and QR generated.'); await loadAll(); }
  catch(e){ logEvent('review','Manual approval failed',e.message); }
  finally { setActionLocked(lockId, false); }
};

window.toggleEvidence = (id) => {
  const el = document.getElementById(`evidence-view-${id}`);
  if (el) el.classList.toggle('hidden');
};

window.uploadEvidence = async (id) => {
  const fd = new FormData();
  const pre = document.getElementById(`pre-${id}`)?.files?.[0];
  const post = document.getElementById(`post-${id}`)?.files?.[0];
  const health = document.getElementById(`health-${id}`)?.files?.[0];
  if (pre) fd.append('pre_image', pre);
  if (post) fd.append('post_image', post);
  if (health) fd.append('health_image', health);
  try {
    const r = await fetch(`/api/batch/${id}/evidence`, { method:'POST', body:fd });
    const body = await r.json();
    if (!r.ok) throw new Error(body.error || `HTTP ${r.status}`);
    document.getElementById(`evidence-${id}`)?.close();
    logEvent('approved','Camera evidence stored',`${id}: ${r.evidence_status || 'evidence updated'}; hashes linked to the bundle.`);
    await loadAll();
  } catch(e) { logEvent('review','Evidence upload failed',e.message); }
};

window.demoHealth = async (id) => {
  const lockId = `health:${id}`;
  if (actionIsLocked(lockId)) return;
  setActionLocked(lockId, true, 'Screening…');
  try {
    const r = await jsonFetch(`/api/batch/${id}/demo-health-screen`, {method:'POST'});
    logEvent(r.image_analysis?.risk === 'low' ? 'approved' : 'review', `${id} visual health screen: ${(r.image_analysis?.risk || 'unknown').toUpperCase()} risk`, 'Supplementary Varroa-associated visual screening signal; not a diagnosis.');
    await loadAll();
  } catch(e) { logEvent('review','Health screen failed',e.message); }
  finally { setActionLocked(lockId, false); }
};

checkBackendVersion().finally(() => loadAll());
