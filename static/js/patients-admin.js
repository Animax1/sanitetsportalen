// ════════════════════════════════════════════════════════
// PASIENTMODULEN — ADMIN-HANDLINGER
//
// Het patients-stats.js til statistikk ble egen modul. Statistikkrenderingen
// er flyttet til statistikk.js; det som ble igjen er registeradministrasjon,
// sesjonstimeout, nullstilling og vaktarkivet.
//
// **Alt her er admin-only server-side** — views_registre.py og
// views_patients.py krever role='admin', arkivet krever ARKIV_*_ROLE (også
// admin). Fila lastes derfor kun for admin, ikke for lead/lead_view som før.
// De to rollene fikk aldri brukt noe av dette; API-et avviste dem.
//
// Legger du til noe her som en lavere rolle skal kunne bruke, hører det
// hjemme i patients-app.js i stedet. `JsModulLastingTests` i patients/tests.py
// håndhever dette.
// ════════════════════════════════════════════════════════

let forstehjelpere = [];
let helsepersonellListe = [];


// ════════════════════════════════════════════════════════
// SETTINGS  (GET /api/settings/ , PUT /api/settings/)
// ════════════════════════════════════════════════════════


// ════════════════════════════════════════════════════════
// SESJONSTIMEOUT
// ════════════════════════════════════════════════════════

async function saveSessionTimeout() {
  const el = document.getElementById('session-timeout-input');
  if (!el) return;
  const hours = parseInt(el.value, 10);
  if (isNaN(hours) || hours < 1 || hours > 24) {
    alert('Oppgi et tall mellom 1 og 24');
    return;
  }
  try {
    await apiFetch('/pasienter/api/session-timeout/', {method:'PUT', body: JSON.stringify({hours})});
    alert('Sesjonstimeout oppdatert.');
  } catch (e) {
    alert('Kunne ikke lagre: ' + e.message);
  }
}

// ════════════════════════════════════════════════════════
// FORSTEHJELPERE
// ════════════════════════════════════════════════════════

// ETag for forstehjelpere – unngår unyttig dataoverføring når listen er uendret


async function addForstehjelper() {
  const nameEl = document.getElementById('new-forstehjelper-name');
  const name = (nameEl?.value || '').trim();
  if (!name) { alert('Skriv inn et navn.'); return; }
  const res = await apiFetch('/pasienter/api/forstehjelpere/', {
    method: 'POST',
    body: JSON.stringify({ name })
  });
  if (res.ok) {
    nameEl.value = '';
    await loadForstehjelpere();
  } else {
    const d = await res.json();
    alert(d.error || 'Feil ved oppretting av førstehjelper.');
  }
}

async function toggleForstehjelper(id) {
  const b = forstehjelpere.find(x => x.id === id);
  if (!b) return;
  const res = await apiFetch(`/pasienter/api/forstehjelpere/${id}/`, {
    method: 'PUT',
    body: JSON.stringify({ is_active: !b.is_active })
  });
  if (res.ok) await loadForstehjelpere();
}

async function deleteForstehjelper(id) {
  if (!confirm('Slett førstehjelper? Hvis førstehjelperen er knyttet til pasienter, vil slettingen blokkeres.')) return;
  const res = await apiFetch(`/pasienter/api/forstehjelpere/${id}/`, { method: 'DELETE' });
  if (res.ok) {
    await loadForstehjelpere();
  } else {
    const d = await res.json();
    alert(d.error || 'Feil ved sletting.');
  }
}

// ════════════════════════════════════════════════════════
// HELSEPERSONELL (samme mønster som forstehjelpere)
// ════════════════════════════════════════════════════════


async function addHelsepersonell() {
  const nameEl = document.getElementById('new-helsepersonell-name');
  const name = (nameEl?.value || '').trim();
  if (!name) { alert('Skriv inn et navn.'); return; }
  const res = await apiFetch('/pasienter/api/helsepersonell/', {
    method: 'POST',
    body: JSON.stringify({ name })
  });
  if (res.ok) {
    nameEl.value = '';
    await loadHelsepersonell();
  } else {
    const d = await res.json();
    alert(d.error || 'Feil ved oppretting av helsepersonell.');
  }
}

async function toggleHelsepersonell(id) {
  const h = helsepersonellListe.find(x => x.id === id);
  if (!h) return;
  const res = await apiFetch(`/pasienter/api/helsepersonell/${id}/`, {
    method: 'PUT',
    body: JSON.stringify({ is_active: !h.is_active })
  });
  if (res.ok) await loadHelsepersonell();
}

async function deleteHelsepersonell(id) {
  if (!confirm('Slett helsepersonell? Hvis helsepersonellet er knyttet til pasienter, vil slettingen blokkeres.')) return;
  const res = await apiFetch(`/pasienter/api/helsepersonell/${id}/`, { method: 'DELETE' });
  if (res.ok) {
    await loadHelsepersonell();
  } else {
    const d = await res.json();
    alert(d.error || 'Feil ved sletting.');
  }
}

// ════════════════════════════════════════════════════════
// NULLSTILL AKTIV VAKT
// ════════════════════════════════════════════════════════

async function doResetActiveYear() {
  const res = await apiFetch('/pasienter/api/reset-active-year/', {
    method: 'POST',
    body: JSON.stringify({ confirm: true })
  });
  const d = await res.json();
  bootstrap.Modal.getInstance(document.getElementById('resetModal'))?.hide();
  if (res.ok) {
    const melding = `${d.antall_slettet} pasienter slettet. Aktiv vakt er nullstilt.`;
    alert(melding);
    await loadPatients();
  } else {
    alert(d.error || 'Feil ved nullstilling.');
  }
}

// ════════════════════════════════════════════════════════

// ════════════════════════════════════════════════════════
// AUTO-REFRESH + INIT
// Polling pauses automatisk når fanen er skjult (document.hidden === true).
// Dette sparer batteri og nettverkstrafikk når brukeren ikke ser på siden.
// ════════════════════════════════════════════════════════


// ════════════════════════════════════════════════════════
// VAKTARKIV
// ════════════════════════════════════════════════════════

let _aktivtArkivId = null;

async function lagreVaktSomArkiv() {
  const navn = (document.getElementById('arkiv-arrangement-navn')?.value || '').trim();
  const notat = (document.getElementById('arkiv-notat')?.value || '').trim();
  const feilEl = document.getElementById('arkiv-lagre-feil');

  if (!navn) {
    if (feilEl) { feilEl.textContent = 'Arrangementsnavn er påkrevd.'; feilEl.classList.remove('d-none'); }
    return;
  }
  if (feilEl) feilEl.classList.add('d-none');

  const res = await apiFetch('/pasienter/api/innstillinger/arkiv/lagre/', {
    method: 'POST',
    body: JSON.stringify({ arrangement_navn: navn, notat })
  });
  const d = await res.json();
  bootstrap.Modal.getInstance(document.getElementById('arkivLagreModal'))?.hide();
  if (res.ok) {
    alert(`Arkiv lagret: "${d.tittel}" (${d.antall_pasienter} pasienter).`);
  } else {
    alert(d.error || 'Feil ved arkivering.');
  }
}

async function loadArkivListe() {
  const container = document.getElementById('arkiv-liste-innhold');
  if (!container) return;
  container.innerHTML = '<span class="text-muted small">Laster...</span>';

  const res = await apiFetch('/pasienter/api/innstillinger/arkiv/');
  if (!res.ok) {
    container.innerHTML = '<span class="text-danger small">Kunne ikke hente arkivliste.</span>';
    return;
  }
  const data = await res.json();
  if (!data.length) {
    container.innerHTML = '<span class="text-muted small">Ingen arkiverte vakter funnet.</span>';
    return;
  }

  const rows = data.map(a => `
    <tr>
      <td class="small">${_escHtml(a.tittel)}</td>
      <td class="small text-nowrap">${_escHtml(a.importert_at ? a.importert_at.slice(0,16).replace('T',' ') : '')}</td>
      <td class="small text-center">${a.antall_pasienter}</td>
      <td class="small">
        <button class="btn btn-outline-primary btn-sm py-0 px-1" data-action="visArkivDetalj" data-id="${a.id}">
          <i class="bi bi-bar-chart me-1"></i>Statistikk
        </button>
        <button class="btn btn-outline-danger btn-sm py-0 px-1 ms-1" data-action="slettArkiv" data-id="${a.id}">
          <i class="bi bi-trash"></i>
        </button>
      </td>
    </tr>
  `).join('');

  container.innerHTML = `
    <table class="table table-sm table-hover mb-0">
      <thead class="table-light"><tr>
        <th>Tittel</th><th>Dato</th><th class="text-center">Antall</th><th>Handlinger</th>
      </tr></thead>
      <tbody>${rows}</tbody>
    </table>
  `;
}

async function visArkivDetalj(id) {
  _aktivtArkivId = id;
  const modal = new bootstrap.Modal(document.getElementById('arkivDetaljModal'));
  modal.show();

  document.getElementById('arkiv-detalj-tittel').innerHTML =
    '<i class="bi bi-archive me-2"></i>Laster arkiv...';
  document.getElementById('arkiv-detalj-meta').textContent = '';
  document.getElementById('arkiv-detalj-stats').innerHTML =
    '<span class="text-muted small">Henter statistikk...</span>';
  document.getElementById('arkiv-detalj-tamper')?.classList.add('d-none');
  document.getElementById('arkiv-detalj-slett')?.classList.add('d-none');
  document.getElementById('arkiv-detalj-fullstats-btn')?.classList.add('d-none');

  const res = await apiFetch(`/pasienter/api/innstillinger/arkiv/${id}/`);
  if (!res.ok) {
    document.getElementById('arkiv-detalj-stats').innerHTML =
      '<span class="text-danger">Kunne ikke hente arkivdata.</span>';
    return;
  }
  const d = await res.json();

  document.getElementById('arkiv-detalj-tittel').innerHTML =
    `<i class="bi bi-archive me-2"></i>${_escHtml(d.tittel)}`;

  const datoStr = d.importert_at ? d.importert_at.slice(0,16).replace('T',' ') : '';
  document.getElementById('arkiv-detalj-meta').innerHTML =
    `Arrangement: <strong>${_escHtml(d.arrangement_navn)}</strong> &nbsp;|&nbsp; ` +
    `Arkivert: ${datoStr} av ${_escHtml(d.importert_av)} &nbsp;|&nbsp; ` +
    `Pasienter: ${d.antall_pasienter} &nbsp;|&nbsp; År: ${d.year_snapshot}` +
    (d.notat ? ` &nbsp;|&nbsp; <em>${_escHtml(d.notat)}</em>` : '');

  if (d.tamper_detected) {
    document.getElementById('arkiv-detalj-tamper')?.classList.remove('d-none');
  }

  const s = d.stats || {};
  document.getElementById('arkiv-detalj-stats').innerHTML = `
    <div class="row g-2 mb-3">
      <div class="col-6 col-md-3"><div class="border rounded p-2 text-center small">
        <div class="fw-bold fs-5">${s.total ?? 0}</div><div class="text-muted">Totalt</div>
      </div></div>
      <div class="col-6 col-md-3"><div class="border rounded p-2 text-center small" style="border-color:#16a34a!important">
        <div class="fw-bold fs-5 text-success">${s.gronn ?? 0}</div><div class="text-muted">Grønn</div>
      </div></div>
      <div class="col-6 col-md-3"><div class="border rounded p-2 text-center small" style="border-color:#ca8a04!important">
        <div class="fw-bold fs-5" style="color:#ca8a04">${s.gul ?? 0}</div><div class="text-muted">Gul</div>
      </div></div>
      <div class="col-6 col-md-3"><div class="border rounded p-2 text-center small" style="border-color:#dc2626!important">
        <div class="fw-bold fs-5 text-danger">${s.rod ?? 0}</div><div class="text-muted">Rød</div>
      </div></div>
    </div>
    <div class="row g-2 mb-3">
      <div class="col-4"><div class="border rounded p-2 text-center small">
        <div class="fw-bold">${s.tilstede ?? 0}</div><div class="text-muted">Tilstede</div>
      </div></div>
      <div class="col-4"><div class="border rounded p-2 text-center small">
        <div class="fw-bold">${s.utskrevet ?? 0}</div><div class="text-muted">Utskrevet</div>
      </div></div>
      <div class="col-4"><div class="border rounded p-2 text-center small">
        <div class="fw-bold">${s.i_obs ?? 0}</div><div class="text-muted">I obs</div>
      </div></div>
    </div>
    <div class="row g-2">
      <div class="col-4"><div class="border rounded p-2 text-center small">
        <div class="fw-bold">${s.avg_wait_min ?? 0} min</div><div class="text-muted">Snitt ventetid</div>
      </div></div>
      <div class="col-4"><div class="border rounded p-2 text-center small">
        <div class="fw-bold">${s.avg_obs_min ?? 0} min</div><div class="text-muted">Snitt obs-tid</div>
      </div></div>
      <div class="col-4"><div class="border rounded p-2 text-center small">
        <div class="fw-bold">${s.avg_total_min ?? 0} min</div><div class="text-muted">Snitt total tid</div>
      </div></div>
    </div>
  `;

  window._sisteArkivArrangement = d.arrangement_navn || '';
  window._sisteArkivImportertAt = d.importert_at || '';
  window._sisteArkivAntall = d.antall_pasienter ?? 0;

  const fullBtn = document.getElementById('arkiv-detalj-fullstats-btn');
  if (fullBtn) fullBtn.classList.remove('d-none');

  const slettDiv = document.getElementById('arkiv-detalj-slett');
  if (slettDiv) slettDiv.classList.remove('d-none');
}

async function slettArkivFraDetalj() {
  if (!_aktivtArkivId) return;
  await slettArkiv(_aktivtArkivId);
  bootstrap.Modal.getInstance(document.getElementById('arkivDetaljModal'))?.hide();
}

async function slettArkiv(id) {
  if (!confirm('Er du sikker på at du vil slette dette arkivet? Handlingen kan ikke angres.')) return;
  const res = await apiFetch(`/pasienter/api/innstillinger/arkiv/${id}/`, {
    method: 'DELETE',
    body: JSON.stringify({ confirm: true })
  });
  const d = await res.json();
  if (res.ok) {
    alert('Arkivet er slettet.');
    await loadArkivListe();
  } else {
    alert(d.error || 'Feil ved sletting av arkiv.');
  }
}


// Admin-listene i innstillinger. De bygger knapper med onclick mot
// toggle/delete-funksjonene under, som bare finnes i denne fila — derfor bor
// renderingen her og ikke i patients-app.js. Lasterne kaller dem via _kall().
function renderForstehjelperAdmin() {
  const container = document.getElementById('forstehjelpere-list');
  if (!container) return;
  if (!forstehjelpere.length) {
    container.innerHTML = '<span class="text-muted small">Ingen forstehjelpere registrert.</span>';
    return;
  }
  const rows = forstehjelpere.map(b => `
    <div class="d-flex align-items-center gap-2 mb-1" style="font-size:0.85rem;">
      <span class="flex-grow-1 ${b.is_active ? '' : 'text-muted'}">${escHtmlValue(b.name)}${b.is_active ? '' : ' <em>(inaktiv)</em>'}</span>
      <button class="btn btn-outline-secondary btn-sm py-0 px-1" data-action="toggleForstehjelper" data-id="${b.id}" title="${b.is_active ? 'Deaktiver' : 'Aktiver'}">
        <i class="bi bi-${b.is_active ? 'toggle-on' : 'toggle-off'}"></i>
      </button>
      <button class="btn btn-outline-danger btn-sm py-0 px-1" data-action="deleteForstehjelper" data-id="${b.id}" title="Slett">
        <i class="bi bi-trash"></i>
      </button>
    </div>`).join('');
  container.innerHTML = rows;
}

function renderHelsepersonellAdmin() {
  const container = document.getElementById('helsepersonell-list');
  if (!container) return;
  if (!helsepersonellListe.length) {
    container.innerHTML = '<span class="text-muted small">Ingen helsepersonell registrert.</span>';
    return;
  }
  const rows = helsepersonellListe.map(h => `
    <div class="d-flex align-items-center gap-2 mb-1" style="font-size:0.85rem;">
      <span class="flex-grow-1 ${h.is_active ? '' : 'text-muted'}">${escHtmlValue(h.name)}${h.is_active ? '' : ' <em>(inaktiv)</em>'}</span>
      <button class="btn btn-outline-secondary btn-sm py-0 px-1" data-action="toggleHelsepersonell" data-id="${h.id}" title="${h.is_active ? 'Deaktiver' : 'Aktiver'}">
        <i class="bi bi-${h.is_active ? 'toggle-on' : 'toggle-off'}"></i>
      </button>
      <button class="btn btn-outline-danger btn-sm py-0 px-1" data-action="deleteHelsepersonell" data-id="${h.id}" title="Slett">
        <i class="bi bi-trash"></i>
      </button>
    </div>`).join('');
  container.innerHTML = rows;
}

// ════════════════════════════════════════════════════════
// ARKIVSTATISTIKK
// ════════════════════════════════════════════════════════

// Renderingen bor på /statistikk/ nå, så knappen navigerer i stedet for å
// hente og tegne. Arkiv-id-en går i URL-en fordi statistikksiden må kunne
// lastes på nytt, bokmerkes og deles uten å miste hvilket arkiv den viser —
// tilstand i en variabel her ville ikke overlevd navigeringen.
function visArkivFullStatistikk() {
  if (!_aktivtArkivId) return;
  window.location.href = `/statistikk/?arkiv=${encodeURIComponent(_aktivtArkivId)}`;
}

