// ════════════════════════════════════════════════════════
// NEW PATIENT MODAL
// ════════════════════════════════════════════════════════
function openNewModal() {
  ['n-problemstilling','n-arsak','n-transport','n-plassering','n-behandler'].forEach(id => {
    const el = document.getElementById(id);
    if (el) { el.value = ''; el.classList.remove('is-invalid'); }
  });
  document.getElementById('n-inntid').value = nowStr();
  document.getElementById('n-inntid').classList.remove('is-invalid');
  document.querySelectorAll('[name="n-triage"]').forEach(r => r.checked = false);
  const errEl = document.getElementById('new-form-error');
  if (errEl) errEl.style.display = 'none';
  const warnEl = document.getElementById('n-triage-warn');
  if (warnEl) warnEl.style.display = 'none';
  updatePlasseringDropdownState('n-plassering', null);
  bsNew.show();
}

async function saveNew() {
  return withSubmitGuard('btn-save-new', _saveNewImpl);
}

async function _saveNewImpl() {
  const triage = document.querySelector('[name="n-triage"]:checked')?.value || '';
  const REQUIRED = [
    { id: 'n-problemstilling', label: 'Problemstilling' },
    { id: 'n-arsak',           label: 'Årsak' },
    { id: 'n-transport',       label: 'Transport' },
    { id: 'n-inntid',          label: 'Inntid' },
    { id: 'n-plassering',      label: 'Plassering' },
  ];
  const missing = [];
  if (!triage) missing.push('Grovsortering');
  REQUIRED.forEach(({id, label}) => {
    const el = document.getElementById(id);
    const empty = !el || !el.value.trim();
    if (el) el.classList.toggle('is-invalid', empty);
    if (empty) missing.push(label);
  });
  const warnEl = document.getElementById('n-triage-warn');
  if (warnEl) warnEl.style.display = !triage ? 'block' : 'none';

  if (missing.length) {
    const errEl = document.getElementById('new-form-error');
    document.getElementById('new-form-error-text').textContent =
      'Obligatoriske felt mangler: ' + missing.join(', ');
    errEl.style.display = 'block';
    return;
  }
  document.getElementById('new-form-error').style.display = 'none';

  const body = {
    grovsortering:   triage,
    problemstilling: document.getElementById('n-problemstilling').value,
    arsak:           document.getElementById('n-arsak').value,
    transport:       document.getElementById('n-transport').value,
    inntid:          document.getElementById('n-inntid').value || nowStr(),
    plassering:      document.getElementById('n-plassering').value,
    behandler:       parseInt(document.getElementById('n-behandler').value) || null,
    helsepersonell_ref: parseInt(document.getElementById('n-helsepersonell').value) || null,
  };
  const res = await apiFetch('/pasienter/api/patients/', {
    method: 'POST',
    body: JSON.stringify(body)
  });
  if (res.ok) {
    bsNew.hide();
    await loadPatients();
    const activeTab = document.querySelector('[data-tab].active')?.dataset.tab;
    if (activeTab === 'tavle') renderBoard();
  } else if (res.status === 400) {
    let msg = 'Kunne ikke lagre pasient.';
    try { const d = await res.json(); if (d.error) msg = d.error; } catch (e) {}
    const errEl = document.getElementById('new-form-error');
    document.getElementById('new-form-error-text').textContent = msg;
    errEl.style.display = 'block';
    await loadPatients();
    updatePlasseringDropdownState('n-plassering', null);
  }
}

// ════════════════════════════════════════════════════════
// EDIT PATIENT
// ════════════════════════════════════════════════════════
function openEdit(data) {
  const role = (window.USER_ROLE || 'read_only').toLowerCase();
  if (role === 'read_only') return;
  currentEditId = data.id;
  document.getElementById('edit-title').textContent = `Pasient #${data.patient_nr}`;

  const set = (id, val) => {
    const el = document.getElementById(id);
    if (!el) return;
    el.value = val || '';
  };
  set('e-problemstilling', data.problemstilling);
  set('e-arsak',           data.arsak);
  set('e-transport',       data.transport);
  set('e-inntid',          data.inntid);
  set('e-pabegynt',        data.pabegynt);
  try { _ensurePlasseringOption('e-plassering', data.plassering); }
  catch (e) { console.warn('_ensurePlasseringOption feilet:', e); }
  set('e-plassering',      data.plassering);
  _populateBehandlerDropdown('e-behandler', data.behandler || null);
  _populateHelsepersonellDropdown('e-helsepersonell-ref', data.helsepersonell_ref || null);
  set('e-lege',            data.lege);
  set('e-medisiner',       data.medisiner);
  set('e-journal',         data.journal);
  set('e-inn-obspost',     data.inn_obspost);
  set('e-ut-obspost',      data.ut_obspost);
  set('e-utskrevet',       data.utskrevet);
  set('e-utskrevet-til',   data.utskrevet_til);

  document.querySelectorAll('[name="e-triage"]').forEach(r => r.checked = (r.value === data.grovsortering));

  updatePlasseringDropdownState('e-plassering', data.id);

  const errEl = document.getElementById('edit-form-error');
  if (errEl) errEl.style.display = 'none';

  updateTotal();
  bsEdit.show();
}

async function saveEdit() {
  return withSubmitGuard('btn-save-edit', _saveEditImpl);
}

async function _saveEditImpl() {
  if (!currentEditId) return;
  const body = {
    grovsortering:   document.querySelector('[name="e-triage"]:checked')?.value || '',
    problemstilling: document.getElementById('e-problemstilling').value,
    arsak:           document.getElementById('e-arsak').value,
    transport:       document.getElementById('e-transport').value,
    inntid:          document.getElementById('e-inntid').value,
    pabegynt:        document.getElementById('e-pabegynt').value,
    plassering:      document.getElementById('e-plassering').value,
    behandler:       parseInt(document.getElementById('e-behandler').value) || null,
    helsepersonell_ref: parseInt(document.getElementById('e-helsepersonell-ref').value) || null,
    lege:            document.getElementById('e-lege').value,
    medisiner:       document.getElementById('e-medisiner').value,
    journal:         document.getElementById('e-journal').value,
    inn_obspost:     document.getElementById('e-inn-obspost').value,
    ut_obspost:      document.getElementById('e-ut-obspost').value,
    utskrevet:       document.getElementById('e-utskrevet').value,
    utskrevet_til:   document.getElementById('e-utskrevet-til').value,
  };
  const res = await apiFetch(`/pasienter/api/patients/${currentEditId}/`, {
    method: 'PUT',
    body: JSON.stringify(body)
  });
  if (res.ok) {
    bsEdit.hide();
    await loadPatients();
    const activeTab = document.querySelector('[data-tab].active')?.dataset.tab;
    if (activeTab === 'tavle') renderBoard();
  } else if (res.status === 400) {
    let msg = 'Kunne ikke lagre endringene.';
    try { const d = await res.json(); if (d.error) msg = d.error; } catch (e) {}
    const errEl = document.getElementById('edit-form-error');
    const textEl = document.getElementById('edit-form-error-text');
    if (errEl && textEl) {
      textEl.textContent = msg;
      errEl.style.display = 'block';
    }
    await loadPatients();
    updatePlasseringDropdownState('e-plassering', currentEditId);
  }
}

async function delPatient() {
  if (!currentEditId) return;
  if (!confirm('Slett pasient? Dette kan ikke angres.')) return;
  await apiFetch(`/pasienter/api/patients/${currentEditId}/`, { method: 'DELETE' });
  bsEdit.hide();
  await loadPatients();
  const activeTab = document.querySelector('[data-tab].active')?.dataset.tab;
  if (activeTab === 'tavle') renderBoard();
}

// ════════════════════════════════════════════════════════
// PLASSERING DROPDOWN HELPER
// ════════════════════════════════════════════════════════

/**
 * Sikre at en plassering-dropdown inneholder en <option> som matcher `value`.
 * Hvis ingen option har denne verdien, legges en ny til øverst (etter '– Velg –')
 * merket som '(historisk)'. Forhindrer datatap når pasienten har en plassering
 * som ikke er i standardlisten.
 *
 * NB: Dropdown-en bruker <optgroup>, så vi må bruke `sel.children` (direkte barn:
 * '– Velg –'-option og optgroups) til insertBefore – IKKE `sel.options` som er
 * en flat liste over alle <option>-elementer (inkl. dem inne i optgroups).
 */
function _ensurePlasseringOption(selectId, value) {
  const sel = document.getElementById(selectId);
  if (!sel || !value) return;
  const exists = Array.from(sel.options).some(o => o.value === value);
  if (exists) return;
  const opt = document.createElement('option');
  opt.value = value;
  opt.textContent = `${value} (historisk)`;
  const firstChild = sel.children[0] || null;
  const isPlaceholder = firstChild && firstChild.tagName === 'OPTION' && !firstChild.value;
  try {
    if (isPlaceholder) {
      sel.insertBefore(opt, firstChild.nextSibling);
    } else if (firstChild) {
      sel.insertBefore(opt, firstChild);
    } else {
      sel.appendChild(opt);
    }
  } catch (e) {
    try { sel.appendChild(opt); } catch (e2) { /* gi opp stille */ }
  }
  opt.dataset.originalLabel = opt.textContent;
}

// ════════════════════════════════════════════════════════
// BEHANDLER & HELSEPERSONELL DROPDOWN HELPERS
// ════════════════════════════════════════════════════════

function _populateBehandlerDropdown(selectId, currentBehandler) {
  const sel = document.getElementById(selectId);
  if (!sel) return;
  const currentId = currentBehandler ? String(currentBehandler.id) : '';
  sel.innerHTML = '<option value="">—</option>';
  behandlere
    .filter(b => b.is_active || (currentBehandler && String(b.id) === currentId))
    .forEach(b => {
      const opt = document.createElement('option');
      opt.value = b.id;
      opt.textContent = b.is_active ? b.name : b.name + ' (inaktiv)';
      sel.appendChild(opt);
    });
  if (currentId) sel.value = currentId;
}

function _populateHelsepersonellDropdown(selectId, currentHp) {
  const sel = document.getElementById(selectId);
  if (!sel) return;
  const currentId = currentHp ? String(currentHp.id) : '';
  sel.innerHTML = '<option value="">—</option>';
  helsepersonellListe
    .filter(h => h.is_active || (currentHp && String(h.id) === currentId))
    .forEach(h => {
      const opt = document.createElement('option');
      opt.value = h.id;
      opt.textContent = h.is_active ? h.name : h.name + ' (inaktiv)';
      sel.appendChild(opt);
    });
  if (currentId) sel.value = currentId;
}
