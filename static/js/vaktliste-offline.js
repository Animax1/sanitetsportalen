// ════════════════════════════════════════════════════════
// vaktliste-offline.js
// ════════════════════════════════════════════════════════
//
// Offline drift: køen for møtt/av vakt, og synkingen når nettet er tilbake.
//
// **Står noe i kø, går alt i kø** — rekkefølgen er regelen.
//
// Delt ut av `vaktliste.js` 14. sep. 2026 (gjeldspunkt 3.6). Fila var
// 3 801 linjer. Ingen bundler: filene lastes i rekkefølge fra
// `templates/vaktliste/index.html`, og funksjonene deler ett globalt
// navnerom som før. `VaktlisteFileneDekkerAltTests` håndhever at
// ingen funksjon forsvant eller ble duplisert i delingen.
// ════════════════════════════════════════════════════════

// ── Offline drift (13. sep. 2026) ─────────────────────────────────────────────
//
// Service workeren (`/vaktliste/sw.js`) holder siden og siste liste lokalt.
// Det som står her er køen for stemplinger, projeksjonen av den på lista, og
// banneret som sier hva som skjer. Samme mønster som bilens offline-kø i
// oppdrag-enhet.js: localStorage, ett tidspunkt per trykk, sendes i
// rekkefølge, og et avvist trykk fjernes med beskjed.

let offlineTilstand = { frakoblet: false, kopiFra: null, sesjonUtgaatt: false, sistFeil: '' };
let synkPaagaar = false;


function koNokkel() {
  return 'vl_stemplinger_v1';
}


function koLes() {
  try {
    const raa = globalThis.localStorage.getItem(koNokkel());
    const verdi = raa ? JSON.parse(raa) : [];
    return Array.isArray(verdi) ? verdi : [];
  } catch (e) {
    return [];
  }
}


function koSkriv(ko) {
  try {
    globalThis.localStorage.setItem(koNokkel(), JSON.stringify(ko));
    return true;
  } catch (e) {
    return false;
  }
}


function _leggIKo(vaktpostId, handling, tidspunkt) {
  const ko = koLes();
  ko.push({ id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
            vaktpostId, handling, tidspunkt,
            vaktlisteId: aktivListe ? aktivListe.vaktliste.id : null });
  koSkriv(ko);
  _projiserKo();
  tegn();
  tegnOffline();
}


function _brukLokalt(vp, handling, tidspunkt) {
  // Speiler `services.STEMPLINGER` på én rad, uten forutsetningene: køen
  // sendes i rekkefølge, og serveren håndhever dem når den får trykket.
  if (handling === 'mott') vp.mott_at = vp.mott_at || tidspunkt;
  else if (handling === 'av_vakt') vp.av_vakt_at = vp.av_vakt_at || tidspunkt;
  else if (handling === 'angre_mott') vp.mott_at = null;
  else if (handling === 'angre_av_vakt') vp.av_vakt_at = null;
  vp.er_tilstede = !!vp.mott_at && !vp.av_vakt_at;
  vp.i_ko = true;
  return vp;
}


function _projiserKo() {
  // Legg køens trykk oppå lista fra serveren — også når lista er lastet på
  // nytt (fra nett eller kopi), så det som er trykket ikke forsvinner før
  // serveren har det.
  if (!aktivListe) return;
  const alle = aktivListe.alle_vaktposter || aktivListe.vaktposter || [];
  alle.forEach((vp) => { vp.i_ko = false; });
  koLes().forEach((k) => {
    const vp = alle.find((v) => v.id === k.vaktpostId);
    if (vp) _brukLokalt(vp, k.handling, k.tidspunkt);
  });
}


function _sesjonUtgaatt(res) {
  // `login_required` svarer med en omdirigering til innloggingssiden, og
  // fetch følger den: et 200 med HTML fra /accounts/login/. Et 403 fra
  // API-et betyr det samme når knappen vistes — den vises bare med stemplerett.
  if (!res) return false;
  if (res.redirected && /\/accounts\/login/.test(res.url || '')) return true;
  return res.status === 403 || res.status === 401;
}


async function synkKo() {
  // Send køen i rekkefølge. Stopper ved første nettverksfeil eller utgått
  // innlogging — resten venter. Et trykk serveren avviser (400/409: regelen
  // holdt ikke) fjernes, og beskjeden vises; det er ikke noe å prøve igjen.
  if (synkPaagaar) return;
  let ko = koLes();
  if (!ko.length) return;
  synkPaagaar = true;
  let sendt = 0;
  try {
    while (ko.length) {
      const k = ko[0];
      let res;
      try {
        res = await apiFetch(`/vaktliste/api/vaktposter/${k.vaktpostId}/stempling/${k.handling}/`,
                             { method: 'POST', body: JSON.stringify({ tidspunkt: k.tidspunkt }) });
      } catch (e) {
        offlineTilstand.frakoblet = true;
        break;
      }
      if (_sesjonUtgaatt(res)) {
        offlineTilstand.sesjonUtgaatt = true;
        break;
      }
      offlineTilstand.frakoblet = false;
      offlineTilstand.sesjonUtgaatt = false;
      const d = await res.json().catch(() => ({}));
      if (!res.ok || d.status !== 'ok') {
        offlineTilstand.sistFeil = d.message || `Stemplingen ble avvist (${res.status}).`;
      }
      ko = ko.slice(1);
      koSkriv(ko);
      sendt += 1;
    }
  } finally {
    synkPaagaar = false;
  }
  if (sendt && aktivListe) await lastListe(aktivListe.vaktliste.id);
  else tegnOffline();
}


function tegnOffline() {
  // Ett banner, én setning om gangen — den som gjelder. Kølengden står
  // alltid når den er over null.
  const el = document.getElementById('vl-offline');
  if (!el) return;
  const antall = koLes().length;
  const venter = antall
    ? ` ${antall} ${antall === 1 ? 'stempling' : 'stemplinger'} venter på å bli sendt.` : '';
  let tekst = '';
  let klasse = 'alert-warning';
  if (offlineTilstand.sesjonUtgaatt) {
    tekst = 'Innloggingen har gått ut. Logg inn på nytt i en annen fane, så sendes det som venter.' + venter;
  } else if (offlineTilstand.frakoblet || offlineTilstand.kopiFra) {
    const fra = offlineTilstand.kopiFra ? ` Viser lista slik den var ${_dag(offlineTilstand.kopiFra)} ${_kl(offlineTilstand.kopiFra)}.` : '';
    tekst = 'Serveren svarer ikke.' + fra + ' Møtt og av vakt kan fortsatt stemples; de sendes når serveren svarer.' + venter;
  } else if (antall) {
    tekst = 'Sender…' + venter;
    klasse = 'alert-secondary';
  } else if (offlineTilstand.sistFeil) {
    tekst = `En stempling fra køen ble avvist: ${offlineTilstand.sistFeil}`;
    klasse = 'alert-danger';
  }
  el.className = `alert py-2 ${klasse}${tekst ? '' : ' d-none'}`;
  el.textContent = tekst;
  if (!antall && !offlineTilstand.frakoblet) offlineTilstand.sistFeil = '';
  _tegnOfflineKlar();
}


async function _tegnOfflineKlar() {
  // «Klar for offline» i vaktlinja når workeren styrer siden og lista ligger
  // i kopi. Sjekkes, ikke antas: en registrert worker uten kopi dekker
  // ingenting.
  const el = document.getElementById('vl-offline-klar');
  if (!el || !aktivListe) return;
  let klar = false;
  try {
    if (globalThis.navigator?.serviceWorker?.controller && globalThis.caches) {
      const kopi = await caches.match(`/vaktliste/api/vaktlister/${aktivListe.vaktliste.id}/`);
      klar = !!kopi;
    }
  } catch (e) { klar = false; }
  el.classList.toggle('d-none', !klar);
}


function registrerOffline() {
  if (!globalThis.navigator?.serviceWorker) return;
  navigator.serviceWorker.register('/vaktliste/sw.js').catch(() => { /* uten worker: som før */ });
  globalThis.addEventListener('online', () => { offlineTilstand.frakoblet = false; synkKo(); });
  globalThis.addEventListener('offline', () => { offlineTilstand.frakoblet = true; tegnOffline(); });
  setInterval(synkKo, 15000);
}


function _korpsKropp(felt, verdi) {
  // Reservasjonsfeltet bærer tre tilstander i ett nedtrekk; serveren har to
  // felt. «alle» blir `alle_korps: true`, et korps blir `korps_id` og slår
  // `alle_korps` av, tomt er planlagt. Andre felt går rett gjennom.
  if (felt !== 'korps_id') {
    const kropp = {};
    kropp[felt] = verdi === '' ? null : verdi;
    return kropp;
  }
  if (verdi === 'alle') return { alle_korps: true, korps_id: null };
  return { alle_korps: false, korps_id: verdi === '' || verdi == null ? null : verdi };
}


async function endreVaktpost(id, felt, verdi) {
  // Redigering i raden: skriv, gå videre, ferdig. Serveren avviser fortsatt
  // et skift som slutter før det begynner — da rulles raden tilbake til det
  // som faktisk står lagret, og meldingen vises over tabellen.
  const kropp = _korpsKropp(felt, verdi);

  const res = await apiFetch(`/vaktliste/api/vaktposter/${id}/`, {
    method: 'PUT', body: JSON.stringify(kropp),
  });
  const d = await res.json().catch(() => ({}));
  if (!res.ok || d.status !== 'ok') {
    visPanelfeil(d.message || 'Kunne ikke lagre endringen.');
    await lastListe(aktivListe.vaktliste.id);   // rull tilbake til lagret verdi
    return;
  }
  skjulPanelfeil();
  await lastListe(aktivListe.vaktliste.id);
}


function visPanelfeil(melding) {
  const el = document.getElementById('vl-feil');
  if (!el) return;
  el.textContent = melding;
  el.classList.remove('d-none');
}


function skjulPanelfeil() {
  document.getElementById('vl-feil')?.classList.add('d-none');
}


function apneRedigerVaktpost(id) {
  // **Bytte person skal ikke koste skiftet.** Før måtte man fjerne raden og
  // sette den opp på nytt, og da mistet man tidene og rollen som allerede
  // sto der. Her endres alt sammen i ett kall, og serveren sjekker den doble
  // regelen på nytt mot den som skal inn.
  const vp = (aktivListe?.vaktposter || []).find((v) => v.id === id);
  if (!vp) return;
  const ressurs = aktivListe.ressurser.find((r) => r.id === vp.ressurs_id);
  if (!ressurs) return;

  _skjulFeil('vaktpost-feil');
  const modal = document.getElementById('vaktpostModal');
  modal.dataset.vaktpost = String(id);

  const tittel = document.getElementById('vaktpost-tittel');
  if (tittel) tittel.textContent = `Rediger skift — ${ressurs.navn}`;

  _fyll('vaktpost-mannskap', (aktivListe.mannskap || []).map((m) => ({
    id: m.id, navn: `${m.navn} — ${m.korps_navn}`,
  })), '— ledig plass —');
  _fyll('vaktpost-rolle', rollerForGruppe(ressurs.gruppe_id, vp.rolle_id),
        'Uten rolle');
  _fyll('vaktpost-korps', [{ id: 'alle', navn: 'Åpen for alle' }].concat(
    (aktivListe.korps || []).map((k) => ({
      id: k.id, navn: k.kortnavn || k.navn,
    }))), '— som ressursen —');
  _settVerdi('vaktpost-korps', vp.alle_korps ? 'alle' : vp.plass_korps_id);

  _settVerdi('vaktpost-mannskap', vp.mannskap_id);
  _settVerdi('vaktpost-rolle', vp.rolle_id);
  _settTid('vaktpost-fra', vp.fra_tid);
  _settTid('vaktpost-til', vp.til_tid);
  _settVerdi('vaktpost-merknad', vp.merknad || '');
  const probono = document.getElementById('vaktpost-probono');
  if (probono) probono.checked = !!vp.probono;

  bootstrap.Modal.getOrCreateInstance(modal).show();
}


async function dupliserVaktpost() {
  // En ledig plass til med samme spenn, rolle og reservasjon (André,
  // 12. sep. 2026: «om jeg glemte å sette flere plasser»). Personen kopieres
  // ikke — det er plassen som mangler, ikke henne.
  const modal = document.getElementById('vaktpostModal');
  const id = modal?.dataset.vaktpost;
  const vp = (aktivListe?.vaktposter || []).find((v) => v.id === Number(id));
  if (!vp) return;
  _skjulFeil('vaktpost-feil');
  const fra = _tidFraFelt('vaktpost-fra');
  const til = _tidFraFelt('vaktpost-til');
  const res = await apiFetch(`/vaktliste/api/ressurser/${vp.ressurs_id}/vaktposter/`, {
    method: 'POST',
    body: JSON.stringify({
      fra_tid: fra, til_tid: til,
      rolle_id: document.getElementById('vaktpost-rolle')?.value || null,
      ..._korpsKropp('korps_id', document.getElementById('vaktpost-korps')?.value || ''),
      probono: !!document.getElementById('vaktpost-probono')?.checked,
    }),
  });
  const d = await res.json().catch(() => ({}));
  if (!res.ok || d.status !== 'ok') {
    _visFeil('vaktpost-feil', d.message || 'Kunne ikke duplisere skiftet.');
    return;
  }
  _lukkModal('vaktpostModal');
  await lastListe(aktivListe.vaktliste.id);
}


function _settVerdi(id, verdi) {
  const el = document.getElementById(id);
  if (el) el.value = verdi == null ? '' : String(verdi);
}


async function lagreVaktpost() {
  const id = document.getElementById('vaktpostModal')?.dataset.vaktpost;
  if (!id) return;
  _skjulFeil('vaktpost-feil');
  await withSubmitGuard('vaktpost-knapp', async () => {
    const fra = _tidFraFelt('vaktpost-fra');
    const til = _tidFraFelt('vaktpost-til');
    if (!fra || !til) {
      _visFeil('vaktpost-feil', 'Skiftet må ha både fra- og til-tidspunkt.');
      return;
    }

    const res = await apiFetch(`/vaktliste/api/vaktposter/${id}/`, {
      method: 'PUT',
      body: JSON.stringify({
        mannskap_id: document.getElementById('vaktpost-mannskap')?.value || null,
        ..._korpsKropp('korps_id', document.getElementById('vaktpost-korps')?.value || ''),
        rolle_id: document.getElementById('vaktpost-rolle')?.value || null,
        merknad: document.getElementById('vaktpost-merknad')?.value || '',
        probono: !!document.getElementById('vaktpost-probono')?.checked,
        fra_tid: fra,
        til_tid: til,
      }),
    });
    const d = await res.json().catch(() => ({}));
    if (!res.ok || d.status !== 'ok') {
      _visFeil('vaktpost-feil', d.message || 'Kunne ikke lagre skiftet.');
      return;
    }
    _lukkModal('vaktpostModal');
    await lastListe(aktivListe.vaktliste.id);
  });
}


async function slettVaktpost() {
  const id = Number(document.getElementById('vaktpostModal')?.dataset.vaktpost);
  if (!id) return;
  const vp = (aktivListe?.vaktposter || []).find((v) => v.id === id);
  const hvem = vp && !vp.ledig ? `«${vp.navn}»` : 'den ledige plassen';
  if (!confirm(`Fjerne skiftet for ${hvem}?\n\nDette kan ikke angres.`)) return;

  const res = await apiFetch(`/vaktliste/api/vaktposter/${id}/`, { method: 'DELETE' });
  const d = await res.json().catch(() => ({}));
  if (!res.ok) {
    _visFeil('vaktpost-feil', d.message || 'Kunne ikke fjerne skiftet.');
    return;
  }
  _lukkModal('vaktpostModal');
  await lastListe(aktivListe.vaktliste.id);
}
