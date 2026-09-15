// ════════════════════════════════════════════════════════
// vaktliste-handlinger.js
// ════════════════════════════════════════════════════════
//
// Handlinger og ressursroller: alt som skriver.
//
// Delt ut av `vaktliste.js` 14. sep. 2026 (gjeldspunkt 3.6). Fila var
// 3 801 linjer. Ingen bundler: filene lastes i rekkefølge fra
// `templates/vaktliste/index.html`, og funksjonene deler ett globalt
// navnerom som før. `VaktlisteFileneDekkerAltTests` håndhever at
// ingen funksjon forsvant eller ble duplisert i delingen.
// ════════════════════════════════════════════════════════

// ── Handlinger ───────────────────────────────────────────────────────────

function _visFeil(id, melding) {
  const el = document.getElementById(id);
  if (!el) return;
  el.textContent = melding;
  el.classList.remove('d-none');
}


function _skjulFeil(id) {
  document.getElementById(id)?.classList.add('d-none');
}


function _lukkModal(id) {
  bootstrap.Modal.getInstance(document.getElementById(id))?.hide();
}


// datetime-local gir «2026-10-03T08:00» uten sone. Serveren gjør den aware
// i lokal sone — det er den tiden brukeren faktisk mente.
function _tidFraFelt(id) {
  const el = document.getElementById(id);
  return el && el.value ? el.value : null;
}


async function opprettVaktliste() {
  _skjulFeil('ny-vakt-feil');
  await withSubmitGuard('ny-vakt-knapp', async () => {
    const navn = (document.getElementById('ny-vakt-navn')?.value || '').trim();
    if (!navn) { _visFeil('ny-vakt-feil', 'Vakten må ha et navn.'); return; }

    const res = await apiFetch('/vaktliste/api/vaktlister/', {
      method: 'POST',
      body: JSON.stringify({
        navn,
        startet: _tidFraFelt('ny-vakt-start'),
        planlagt_slutt: _tidFraFelt('ny-vakt-slutt'),
        kopier_fra: document.getElementById('ny-vakt-kopier')?.value || null,
      }),
    });
    const d = await res.json().catch(() => ({}));
    if (!res.ok || d.status !== 'ok') {
      _visFeil('ny-vakt-feil', d.message || 'Kunne ikke opprette vaktlista.');
      return;
    }
    _lukkModal('nyVaktlisteModal');
    document.getElementById('ny-vakt-navn').value = '';
    await lastVaktlister();
    await lastListe(d.data.id);
  });
}


function apneNyRessurs(gruppeId) {
  // Gruppa kommer enten fra knappen inne i fanen (`data-arg`), eller fra
  // fanen man står i. Nedtrekket er fortsatt et nedtrekk, så den første
  // enheten i en ny gruppe også har en vei inn.
  _skjulFeil('ny-ressurs-feil');
  const felt = document.getElementById('ny-ressurs-gruppe');
  const maal = gruppeId != null && gruppeId !== '' ? gruppeId : aktivFane;
  const valgbare = (aktivListe?.grupper || [])
    .filter((g) => g.er_aktiv && gruppaHarPlass(g));
  _fyll('ny-ressurs-gruppe', valgbare, null);
  const gruppe = valgbare.find((g) => String(g.id) === String(maal));
  if (felt && gruppe) {
    felt.value = String(gruppe.id);
    const tittel = document.getElementById('ny-ressurs-tittel');
    if (tittel) tittel.textContent = `Ny ${gruppe.navn}`;
  }
  bootstrap.Modal.getOrCreateInstance(document.getElementById('nyRessursModal')).show();
}


async function opprettRessurs() {
  if (!aktivListe) return;
  _skjulFeil('ny-ressurs-feil');
  await withSubmitGuard('ny-ressurs-knapp', async () => {
    const navn = (document.getElementById('ny-ressurs-navn')?.value || '').trim();
    if (!navn) { _visFeil('ny-ressurs-feil', 'Ressursen må ha et navn.'); return; }

    const res = await apiFetch(
      `/vaktliste/api/vaktlister/${aktivListe.vaktliste.id}/ressurser/`, {
        method: 'POST',
        // Bare navn og gruppe. Reservasjon og enhetskobling settes i
        // «Rediger» — de hører til enheten, ikke til opprettelsen.
        body: JSON.stringify({
          navn,
          gruppe_id: document.getElementById('ny-ressurs-gruppe')?.value,
        }),
      });
    const d = await res.json().catch(() => ({}));
    if (!res.ok || d.status !== 'ok') {
      _visFeil('ny-ressurs-feil', d.message || 'Kunne ikke legge til ressursen.');
      return;
    }
    _lukkModal('nyRessursModal');
    document.getElementById('ny-ressurs-navn').value = '';
    // Fanen er gruppa, så det er dit den nye ressursen dukker opp.
    aktivFane = String(d.data.gruppe_id);
    await lastListe(aktivListe.vaktliste.id);
  });
}


function apneRessurs(id) {
  // **Rediger-vinduet, og det eneste stedet en ressurs kan fjernes.**
  // «Fjern ressurs» sto tidligere naken ved siden av «Sett på vakt», og
  // CASCADE tar alle skiftene: ett feilklikk kostet hele bemanningen på
  // bilen. Nå må man inn hit først, og bekrefte etterpå.
  const r = aktivListe?.ressurser.find((x) => x.id === id);
  if (!r) return;
  _skjulFeil('ressurs-feil');
  const modal = document.getElementById('ressursModal');
  modal.dataset.ressurs = String(id);

  document.getElementById('ressurs-navn').value = r.navn;
  _settValg('ressurs-gruppe', (aktivListe.grupper || []).filter(
    (g) => g.er_aktiv || g.id === r.gruppe_id), r.gruppe_id);
  _settValg('ressurs-korps', aktivListe.korps || [], r.korps_id, 'Ureservert');
  _settValg('ressurs-enhet', aktivListe.enheter || [], r.enhet_id, 'Ingen');

  const antall = _posterFor(id).length;
  const tekst = document.getElementById('ressurs-slett-tekst');
  if (tekst) {
    tekst.textContent = antall
      ? `${antall} oppsatt(e) skift fjernes sammen med ressursen.`
      : 'Ressursen har ingen skift på seg.';
  }
  bootstrap.Modal.getOrCreateInstance(modal).show();
}


function _settValg(id, rader, valgt, tomEtikett) {
  // Fylles fra data hver gang vinduet åpnes. Serveren sender listene i
  // hovedsvaret, og å bygge dem i malen ville krevd en ny sidelasting for
  // hver nye gruppe.
  const el = document.getElementById(id);
  if (!el) return;
  const valg = tomEtikett != null
    ? [`<option value="">— ${escapeHtml(tomEtikett)} —</option>`] : [];
  el.innerHTML = valg.concat(rader.map((r) => {
    const merke = r.id === valgt ? ' selected' : '';
    return `<option value="${escHtmlValue(r.id)}"${merke}>${escapeHtml(r.navn)}</option>`;
  })).join('');
}


async function lagreRessurs() {
  const id = document.getElementById('ressursModal')?.dataset.ressurs;
  if (!id) return;
  _skjulFeil('ressurs-feil');
  await withSubmitGuard('ressurs-knapp', async () => {
    const navn = (document.getElementById('ressurs-navn')?.value || '').trim();
    if (!navn) { _visFeil('ressurs-feil', 'Ressursen må ha et navn.'); return; }

    const res = await apiFetch(`/vaktliste/api/ressurser/${id}/`, {
      method: 'PUT',
      body: JSON.stringify({
        navn,
        gruppe_id: document.getElementById('ressurs-gruppe')?.value || null,
        korps_id: document.getElementById('ressurs-korps')?.value || null,
        enhet_id: document.getElementById('ressurs-enhet')?.value || null,
      }),
    });
    const d = await res.json().catch(() => ({}));
    if (!res.ok || d.status !== 'ok') {
      _visFeil('ressurs-feil', d.message || 'Kunne ikke lagre ressursen.');
      return;
    }
    _lukkModal('ressursModal');
    await lastListe(aktivListe.vaktliste.id);
  });
}


async function slettRessurs() {
  const id = Number(document.getElementById('ressursModal')?.dataset.ressurs);
  if (!id) return;
  const ressurs = aktivListe?.ressurser.find((r) => r.id === id);
  const antall = _posterFor(id).length;
  const advarsel = antall
    ? `\n\n${antall} oppsatt(e) skift fjernes sammen med den. Dette kan ikke angres.`
    : '\n\nDette kan ikke angres.';
  if (!confirm(`Fjerne «${ressurs ? ressurs.navn : 'ressursen'}»?${advarsel}`)) return;

  // Serveren krever `confirm` i tillegg til dialogen her. De to er ikke
  // samme sperre: dialogen stopper feilklikket, kroppen stopper et kall som
  // treffer URL-en uten å mene det.
  const res = await apiFetch(`/vaktliste/api/ressurser/${id}/`, {
    method: 'DELETE', body: JSON.stringify({ confirm: true }),
  });
  const d = await res.json().catch(() => ({}));
  if (!res.ok) {
    _visFeil('ressurs-feil', d.message || 'Kunne ikke fjerne ressursen.');
    return;
  }
  _lukkModal('ressursModal');
  // Bli stående i gruppa hvis den har flere ressurser igjen; var det den
  // siste, forsvinner fanen og «Oversikt» er det eneste rimelige stedet.
  const gruppeId = ressurs ? ressurs.gruppe_id : null;
  await lastListe(aktivListe.vaktliste.id);
  if (!gruppeId || !_ressurserIGruppe(gruppeId).length) {
    aktivFane = OVERSIKT;
    tegn();
  }
}




function veksleRessurs(id) {
  // Sammenslå eller vis igjen. Tilstanden ligger i `ressursApen` og ikke i
  // DOM-en, fordi panelet tegnes på nytt ved hvert faneskift.
  const ressurs = aktivListe?.ressurser.find((r) => r.id === id);
  if (!ressurs) return;
  ressursApen.set(id, !ressursErApen(ressurs));
  tegnPanel();
}


function apneVaktpost(ressursId) {
  const ressurs = aktivListe?.ressurser.find((r) => r.id === ressursId);
  if (!ressurs) return;
  // **Kortet åpnes når man skal legge noe i det.** Ellers lagrer man et skift
  // og ser ingenting skje — knappen står jo i hodet på et sammenslått kort.
  ressursApen.set(ressursId, true);
  _skjulFeil('ny-vaktpost-feil');
  document.getElementById('ny-vaktpost-tittel').textContent =
    `Opprett vakt — ${ressurs.navn}`;
  document.getElementById('nyVaktpostModal').dataset.ressurs = String(ressursId);
  // Rollene som tilbys er gruppas — samme regel som i raden.
  _fyll('ny-vaktpost-rolle',
        rollerForGruppe(ressurs.gruppe_id, null), 'Uten rolle');
  document.getElementById('ny-vaktpost-mannskap').value = '';
  document.getElementById('ny-vaktpost-antall').value = '1';
  const nyProbono = document.getElementById('ny-vaktpost-probono');
  if (nyProbono) nyProbono.checked = false;

  // **Datoen står der på forhånd, hentet fra vaktas start.** Feltet er
  // uendret — samme native velger, samme visning — men det er aldri tomt,
  // og da taster man fire siffer for klokkeslettet i stedet for tolv for
  // hele datoen. Vaktas start og ikke klokka nå: en oktobervakt planlegges i
  // august, og «i dag» er da et årstall på avveie.
  //
  // Sto feltene urørt, bar de dessuten tidene fra forrige gang vinduet var
  // åpent — på en annen ressurs, i en annen gruppe.
  const start = aktivListe?.vaktliste?.startet || null;
  _settTid('ny-vaktpost-fra', start);
  // Til-tiden står åtte timer etter fra (André, 12. sep. 2026) — et
  // vanlig skift, og aldri før fra.
  _settTid('ny-vaktpost-til', _plussTimer(start, 8));

  _vaktpostModusSkifte();
  bootstrap.Modal.getOrCreateInstance(document.getElementById('nyVaktpostModal')).show();
}


function _vaktpostModusSkifte() {
  // Antall plasser gir bare mening for ledige: to identiske rader med samme
  // person ville uansett brutt unik-skranken.
  const valgt = document.getElementById('ny-vaktpost-mannskap')?.value;
  document.getElementById('ny-vaktpost-antall-rad')
    ?.classList.toggle('d-none', !!valgt);
}


// ── Ressursroller ────────────────────────────────────────────────────────
//
// Administreres herfra, ikke fra mannskapsregisteret: rollene brukes i
// ressurstabellen, og å måtte bytte side for å lage «Sjåfør» mens man bemanner
// en bil er akkurat den knotet dette skal fjerne.

function apneRoller(ressursId) {
  // **Manageren åpnes fra ressursen og gjelder ressursens gruppe.** Lager du
  // «Sjåfør» inne i Ambulanse 1, finnes den på hver ambulanse — men ikke på
  // samleplassen. Gruppa er riktig nivå: har du tre ambulanser, vil du lage
  // rollen én gang, ikke tre.
  const r = aktivListe?.ressurser.find((x) => x.id === ressursId);
  if (!r) return;
  _skjulFeil('rolle-feil');
  const modal = document.getElementById('rollerModal');
  modal.dataset.gruppe = String(r.gruppe_id);
  document.getElementById('ny-rolle-navn').value = '';

  const tittel = document.getElementById('roller-tittel');
  if (tittel) tittel.textContent = `Roller for ${r.gruppe_navn}`;
  const hjelp = document.getElementById('roller-hjelp');
  if (hjelp) {
    hjelp.textContent = `Rollene gjelder alle ressurser i gruppa `
                      + `«${r.gruppe_navn}», ikke bare ${r.navn}.`;
  }

  tegnRoller();
  bootstrap.Modal.getOrCreateInstance(modal).show();
}


function tegnRoller() {
  const el = document.getElementById('rolle-liste');
  if (!el) return;
  const gruppeId = Number(document.getElementById('rollerModal')?.dataset.gruppe);
  const roller = ((aktivListe && aktivListe.roller) || [])
    .filter((r) => r.gruppe_id === gruppeId);
  el.innerHTML = roller.length ? roller.map(mkRolleRad).join('')
    : '<div class="vl-tom">Ingen roller i denne gruppa ennå.</div>';
}


function mkRolleRad(r) {
  // «I bruk» står i lista: en rolle man kan slette uten å vite hvor mange
  // skift som peker på den, sletter man for lett.
  const bruk = r.i_bruk
    ? `<span class="vl-meta">${escHtmlValue(r.i_bruk)} i bruk</span>`
    : '<span class="vl-meta">ubrukt</span>';
  return `
    <div class="vl-rad">
      <span class="vl-navn">${escapeHtml(r.navn)}</span>
      <div class="d-flex align-items-center gap-2">
        ${bruk}
        <button class="btn btn-sm btn-outline-danger" type="button"
                title="Slett rollen" aria-label="Slett rollen"
                data-action="slettRolle" data-id="${escHtmlValue(r.id)}"><i class="bi bi-trash"></i></button>
      </div>
    </div>`;
}


async function opprettRolle() {
  _skjulFeil('rolle-feil');
  await withSubmitGuard('ny-rolle-knapp', async () => {
    const navn = (document.getElementById('ny-rolle-navn')?.value || '').trim();
    if (!navn) { _visFeil('rolle-feil', 'Rollen må ha et navn.'); return; }
    const gruppeId = document.getElementById('rollerModal')?.dataset.gruppe;

    const res = await apiFetch('/vaktliste/api/roller/', {
      method: 'POST', body: JSON.stringify({ navn, gruppe_id: gruppeId }),
    });
    const d = await res.json().catch(() => ({}));
    if (!res.ok || d.status !== 'ok') {
      _visFeil('rolle-feil', d.message || 'Kunne ikke legge til rollen.');
      return;
    }
    document.getElementById('ny-rolle-navn').value = '';
    await lastListe(aktivListe.vaktliste.id);
    tegnRoller();
  });
}


async function slettRolle(id) {
  const rolle = (aktivListe.roller || []).find((r) => r.id === id);
  if (!rolle) return;
  if (!confirm(`Slette rollen «${rolle.navn}»?`)) return;

  const res = await apiFetch(`/vaktliste/api/roller/${id}/`, { method: 'DELETE' });
  const d = await res.json().catch(() => ({}));
  if (!res.ok) { _visFeil('rolle-feil', d.message || 'Kunne ikke slette.'); return; }
  _skjulFeil('rolle-feil');
  await lastListe(aktivListe.vaktliste.id);
  tegnRoller();
}


function apneGrupper() {
  // **Gruppene hadde endepunkt, men ingen flate.** Det er nøyaktig feilen
  // Django-admin ga oss én gang før: et register som bare finnes i API-et,
  // finnes ikke for brukeren. Uten dette kunne man ikke lage «Førstehjelpstelt»
  // i det hele tatt — bare velge blant de seks migrasjonen seedet.
  _skjulFeil('gruppe-feil');
  document.getElementById('ny-gruppe-navn').value = '';
  document.getElementById('ny-gruppe-ikon').value = '';
  const flere = document.getElementById('ny-gruppe-flere');
  if (flere) flere.checked = true;
  tegnGrupper();
  bootstrap.Modal.getOrCreateInstance(document.getElementById('grupperModal')).show();
}


function tegnGrupper() {
  const el = document.getElementById('gruppe-liste');
  if (!el) return;
  const grupper = (aktivListe && aktivListe.grupper) || [];
  el.innerHTML = grupper.length ? grupper.map(mkGruppeRad).join('')
    : '<div class="vl-tom">Ingen grupper ennå.</div>';
}


function mkGruppeRad(g) {
  // «I bruk» er antall ressurser på gruppa. En gruppe man kan slette uten å
  // vite hvor mange biler som står i den, sletter man for lett — og
  // `PROTECT` ville uansett stoppet det, men da som en feilmelding framfor
  // som noe man kunne sett på forhånd.
  const bruk = g.i_bruk
    ? `<span class="vl-meta">${escHtmlValue(g.i_bruk)} i bruk</span>`
    : '<span class="vl-meta">ubrukt</span>';
  const ett = g.flere_enheter === false
    ? '<span class="vl-merkelapp">ett eksemplar</span>' : '';
  const slett = g.i_bruk ? '' : `
        <button class="btn btn-sm btn-outline-danger" type="button"
                title="Slett gruppa" aria-label="Slett gruppa"
                data-action="slettGruppe" data-id="${escHtmlValue(g.id)}"><i class="bi bi-trash"></i></button>`;
  return `
    <div class="vl-rad">
      <span class="vl-navn">
        <i class="bi bi-${escHtmlValue(g.ikon)} me-2"></i>${escapeHtml(g.navn)}
      </span>
      <div class="d-flex align-items-center gap-2">
        ${ett}
        ${bruk}
        ${slett}
      </div>
    </div>`;
}


async function opprettGruppe() {
  _skjulFeil('gruppe-feil');
  await withSubmitGuard('ny-gruppe-knapp', async () => {
    const navn = (document.getElementById('ny-gruppe-navn')?.value || '').trim();
    if (!navn) { _visFeil('gruppe-feil', 'Gruppa må ha et navn.'); return; }

    const res = await apiFetch('/vaktliste/api/grupper/', {
      method: 'POST',
      body: JSON.stringify({
        navn,
        ikon: (document.getElementById('ny-gruppe-ikon')?.value || '').trim(),
        flere_enheter: !!document.getElementById('ny-gruppe-flere')?.checked,
      }),
    });
    const d = await res.json().catch(() => ({}));
    if (!res.ok || d.status !== 'ok') {
      _visFeil('gruppe-feil', d.message || 'Kunne ikke legge til gruppa.');
      return;
    }
    document.getElementById('ny-gruppe-navn').value = '';
    document.getElementById('ny-gruppe-ikon').value = '';
    await lastListe(aktivListe.vaktliste.id);
    tegnGrupper();
  });
}


async function slettGruppe(id) {
  const gruppe = (aktivListe.grupper || []).find((g) => g.id === id);
  if (!gruppe) return;
  if (!confirm(`Slette gruppa «${gruppe.navn}»?`)) return;

  const res = await apiFetch(`/vaktliste/api/grupper/${id}/`, { method: 'DELETE' });
  const d = await res.json().catch(() => ({}));
  if (!res.ok) { _visFeil('gruppe-feil', d.message || 'Kunne ikke slette.'); return; }
  _skjulFeil('gruppe-feil');
  await lastListe(aktivListe.vaktliste.id);
  tegnGrupper();
}


function apneVakt() {
  // **Ett vindu for vakten.** Lengden og utskriften er begge ting man gjør
  // med *vakten*, ikke med en ressurs — og som to knapper i toppen konkurrerte
  // de med «Ny ressurs» og «Ny vaktliste» om plassen uten å høre til samme
  // spørsmål. Utskriften ligger her fordi den er hele vaktlista på ett ark.
  //
  // **Vinduet åpnes også uten vaktliste.** Korps og kompetanser bor her, og
  // de er nettopp det man legger inn før den første lista finnes — sto
  // vinduet stengt til da, var registrene uten vei inn. Bolkene som gjelder
  // én liste skjules i stedet.
  _skjulFeil('vakt-lengde-feil');
  const harListe = !!aktivListe;
  document.getElementById('vakt-for-lista')
    ?.classList.toggle('d-none', !harListe);
  const lengde = document.getElementById('vakt-lengde-bolk');
  if (lengde && !harListe) lengde.classList.add('d-none');

  if (!harListe) {
    const t = document.getElementById('vakt-tittel');
    if (t) t.textContent = 'Innstillinger';
    _apneModal('vaktModal');
    return;
  }

  const vl = aktivListe.vaktliste;
  _settTid('vakt-start', vl.startet);
  _settTid('vakt-slutt', vl.planlagt_slutt);

  const tittel = document.getElementById('vakt-tittel');
  if (tittel) tittel.textContent = vl.vakt_navn;
  const spenn = document.getElementById('vakt-spenn');
  if (spenn) spenn.textContent = _vaktspenn();
  const antall = document.getElementById('vakt-antall');
  if (antall) {
    const poster = aktivListe.vaktposter || [];
    const ledige = poster.filter((v) => v.ledig).length;
    const tall = _telling(poster, _tidsblokker(poster).length);
    antall.textContent = ledige
      ? `${tall} · ${ledige} ${ledige === 1 ? 'ledig plass' : 'ledige plasser'}`
      : tall;
  }

  if (lengde) lengde.classList.toggle('d-none', !kanLede());
  const arkivBolk = document.getElementById('vakt-arkiv-bolk');
  if (arkivBolk) arkivBolk.classList.toggle('d-none', !_erAdmin());
  tegnDriftknapp();
  _apneModal('vaktModal');
}


async function visArkiverteVaktlister() {
  // «Arkiv» ved siden av «Arkiver vaktlisten», i sitt eget vindu (André,
  // 12. sep. 2026). Lista lå først inne i innstillingene bak en veksleknapp,
  // og leste som rot.
  const el = document.getElementById('vakt-arkiverte');
  if (!el) return;
  _skjulFeil('vakt-arkiv-feil');
  el.innerHTML = '<div class="vl-meta">Henter…</div>';
  _byttModal('vaktModal', 'vaktArkivModal');
  await lastArkiverteVaktlister();
}


function _byttModal(fra, til) {
  // Ett vindu om gangen. Er det første åpent, ventes det på at Bootstrap
  // har lukket det før det neste åpnes — to åpne modaler stabler bakgrunner,
  // og det var den feilen som frøs oppdragsvinduet 12. sep. 2026.
  const fraEl = document.getElementById(fra);
  if (fraEl && fraEl.classList.contains('show')) {
    fraEl.addEventListener('hidden.bs.modal', () => _apneModal(til), { once: true });
    _lukkModal(fra);
    return;
  }
  _apneModal(til);
}


async function slettVaktliste() {
  // Sletting for godt — global admin, to bekreftelser (dialogen og
  // `confirm: true` i kroppen), som på ressursen. Arkivering er det
  // reversible alternativet ved siden av.
  if (!aktivListe) return;
  const navn = aktivListe.vaktliste.vakt_navn;
  if (!confirm(`Slette vaktlisten for «${navn}» for godt? Alle ressurser og skift forsvinner. Arkiver i stedet hvis du kan trenge den igjen.`)) return;
  if (!confirm(`Er du sikker? «${navn}» kan ikke hentes tilbake.`)) return;
  const res = await apiFetch(`/vaktliste/api/vaktlister/${aktivListe.vaktliste.id}/`, {
    method: 'DELETE', body: JSON.stringify({ confirm: true }),
  });
  const d = await res.json().catch(() => ({}));
  if (!res.ok || d.status !== 'ok') {
    _visFeil('vakt-lengde-feil', d.message || 'Kunne ikke slette.');
    return;
  }
  _lukkModal('vaktModal');
  await lastVaktlister();
}


async function arkiverVaktliste() {
  // Arkivert, ikke slettet: lista går ut av velgeren, alt står, og den
  // kan hentes tilbake her (André, 12. sep. 2026).
  if (!aktivListe) return;
  if (!confirm(`Arkivere vaktlisten for «${aktivListe.vaktliste.vakt_navn}»? Den kan hentes tilbake her.`)) return;
  const res = await apiFetch(`/vaktliste/api/vaktlister/${aktivListe.vaktliste.id}/arkiver/`, { method: 'POST' });
  const d = await res.json().catch(() => ({}));
  if (!res.ok || d.status !== 'ok') {
    _visFeil('vakt-lengde-feil', d.message || 'Kunne ikke arkivere.');
    return;
  }
  _lukkModal('vaktModal');
  await lastVaktlister();
}


async function gjenopprettVaktliste(id) {
  const res = await apiFetch(`/vaktliste/api/vaktlister/${id}/gjenopprett/`, { method: 'POST' });
  const d = await res.json().catch(() => ({}));
  if (!res.ok || d.status !== 'ok') {
    _visFeil('vakt-arkiv-feil', d.message || 'Kunne ikke hente tilbake.');
    return;
  }
  _lukkModal('vaktArkivModal');
  await lastVaktlister();
  await lastListe(id);
}


async function lastArkiverteVaktlister() {
  const el = document.getElementById('vakt-arkiverte');
  if (!el) return;
  const res = await apiFetch('/vaktliste/api/vaktlister/?arkiverte=1');
  if (!res.ok) return;
  const lister = (await res.json()).data || [];
  el.innerHTML = mkArkiverteVaktlister(lister);
}


function mkArkiverteVaktlister(lister) {
  if (!lister.length) return '<div class="vl-meta">Ingen arkiverte vaktlister.</div>';
  return lister.map((vl) => `
    <div class="d-flex align-items-center gap-2 py-1">
      <span class="flex-grow-1">${escapeHtml(vl.vakt_navn)}
        <span class="vl-meta">· arkivert ${escapeHtml(_dag(vl.arkivert_at))} ${escapeHtml(_kl(vl.arkivert_at))}</span></span>
      <button type="button" class="btn btn-outline-secondary btn-sm"
              data-action="gjenopprettVaktliste" data-id="${escHtmlValue(vl.id)}">Hent tilbake</button>
    </div>`).join('');
}


function skrivUtVakta() {
  // Vinduet må lukkes først: en åpen modal ligger over arket, og
  // `window.print()` tar med det som står på skjermen.
  _lukkModal('vaktModal');
  visFane(OVERSIKT);
  setTimeout(skrivUt, 250);
}


function _plussTimer(iso, timer) {
  const d = _d(iso);
  if (!d) return null;
  d.setTime(d.getTime() + timer * 3600000);
  return d.toISOString();
}


function foreslaaTil(fraId, tilId) {
  // Når fra endres og til er tom eller ligger før fra, settes til = fra + 8 t.
  // Et til som alt står etter fra røres ikke — det er noen som har satt det.
  const fra = document.getElementById(fraId);
  const til = document.getElementById(tilId);
  if (!fra || !til || !fra.value) return;
  if (til.value && til.value > fra.value) return;
  til.value = _iso16(_plussTimer(fra.value, 8));
}


function _settTid(id, iso) {
  const el = document.getElementById(id);
  if (el) el.value = iso ? _iso16(iso) : '';
}


async function lagreVaktlengde() {
  _skjulFeil('vakt-lengde-feil');
  await withSubmitGuard('vakt-lengde-knapp', async () => {
    const res = await apiFetch(`/vaktliste/api/vaktlister/${aktivListe.vaktliste.id}/`, {
      method: 'PUT',
      body: JSON.stringify({
        startet: _tidFraFelt('vakt-start'),
        planlagt_slutt: _tidFraFelt('vakt-slutt'),
      }),
    });
    const d = await res.json().catch(() => ({}));
    if (!res.ok || d.status !== 'ok') {
      _visFeil('vakt-lengde-feil', d.message || 'Kunne ikke lagre.');
      return;
    }
    _lukkModal('vaktModal');
    await lastVaktlister();
    await lastListe(aktivListe.vaktliste.id);
  });
}


async function opprettVaktpost() {
  const modal = document.getElementById('nyVaktpostModal');
  const ressursId = modal?.dataset.ressurs;
  if (!ressursId) return;

  _skjulFeil('ny-vaktpost-feil');
  await withSubmitGuard('ny-vaktpost-knapp', async () => {
    const fra = _tidFraFelt('ny-vaktpost-fra');
    const til = _tidFraFelt('ny-vaktpost-til');
    if (!fra || !til) {
      _visFeil('ny-vaktpost-feil', 'Skiftet må ha både fra- og til-tidspunkt.');
      return;
    }

    const res = await apiFetch(`/vaktliste/api/ressurser/${ressursId}/vaktposter/`, {
      method: 'POST',
      body: JSON.stringify({
        mannskap_id: document.getElementById('ny-vaktpost-mannskap')?.value || null,
        ..._korpsKropp('korps_id', document.getElementById('ny-vaktpost-korps')?.value || ''),
        rolle_id: document.getElementById('ny-vaktpost-rolle')?.value || null,
        probono: !!document.getElementById('ny-vaktpost-probono')?.checked,
        antall: Number(document.getElementById('ny-vaktpost-antall')?.value) || 1,
        fra_tid: fra,
        til_tid: til,
      }),
    });
    const d = await res.json().catch(() => ({}));
    if (!res.ok || d.status !== 'ok') {
      _visFeil('ny-vaktpost-feil', d.message || 'Kunne ikke sette personen på vakt.');
      return;
    }
    _lukkModal('nyVaktpostModal');
    await lastListe(aktivListe.vaktliste.id);
  });
}


function apneGrenser() {
  if (!belastning) return;
  _skjulFeil('grenser-feil');
  _settVerdi('grense-skift', belastning.grenser.maks_skift_timer);
  _settVerdi('grense-hvile', belastning.grenser.min_hvile_timer);
  _apneModal('grenserModal');
}


async function lagreGrenser() {
  _skjulFeil('grenser-feil');
  await withSubmitGuard('grenser-knapp', async () => {
    const res = await apiFetch('/vaktliste/api/grenser/', {
      method: 'PUT',
      body: JSON.stringify({
        maks_skift_timer: _lesFelt('grense-skift'),
        min_hvile_timer: _lesFelt('grense-hvile'),
      }),
    });
    const d = await res.json().catch(() => ({}));
    if (!res.ok || d.status !== 'ok') {
      _visFeil('grenser-feil', d.message || 'Kunne ikke lagre grensene.');
      return;
    }
    _lukkModal('grenserModal');
    // Varslene regnes på serveren mot grensene, så tallene må hentes på nytt
    // — ikke bare tekstene som nevner dem.
    belastning = null;
    await lastBelastning();
  });
}


async function settDrift(tilstand) {
  if (!aktivListe) return;
  skjulPanelfeil();
  const res = await apiFetch(
    `/vaktliste/api/vaktlister/${aktivListe.vaktliste.id}/drift/${tilstand}/`,
    { method: 'POST' });
  const d = await res.json().catch(() => ({}));
  if (!res.ok || d.status !== 'ok') {
    visPanelfeil(d.message || 'Kunne ikke endre driftstatus.');
    return;
  }
  // Stenges innsjekken mens man står i «Tilstede nå», forsvinner fanen —
  // og en fane som forsvinner under føttene skal ikke etterlate et tomt
  // panel.
  if (tilstand === 'stopp' && aktivFane === TILSTEDE) aktivFane = OVERSIKT;
  await lastListe(aktivListe.vaktliste.id);
  // Reserven sendes ved sett i drift når admin har slått det på. Drift ble
  // satt uansett; feilet sendingen, skal vaktleder få vite det nå — ikke
  // oppdage det når portalen er nede.
  const u = d.data && d.data.utsending;
  if (u && u.feil) visPanelfeil(`Lista er i drift, men fila ble ikke sendt: ${u.feil}`);
}


//: Klienthandling → serverens overgang. Ett sted, slik at de fire knappene
//: og de fire endepunktene ikke kan gli fra hverandre.
const STEMPLINGER = {
  stemplMott: 'mott',
  stemplAvVakt: 'av_vakt',
  angreMott: 'angre_mott',
  angreAvVakt: 'angre_av_vakt',
};


function stemplMott(id) { return _stemple(id, STEMPLINGER.stemplMott); }
function stemplAvVakt(id) { return _stemple(id, STEMPLINGER.stemplAvVakt); }
function angreMott(id) { return _stemple(id, STEMPLINGER.angreMott); }
function angreAvVakt(id) { return _stemple(id, STEMPLINGER.angreAvVakt); }


async function _stemple(id, handling) {
  // **Kroppen bærer bare tidspunktet.** Knappen vet hvilken overgang den
  // utfører, og serveren utleder ingenting av gjeldende tilstand — samme grep
  // som oppdragsmodulens stemplinger. `POST .../neste/` ville gitt et kappløp
  // når to trykk kommer tett.
  //
  // **Offline drift (13. sep. 2026):** svarer ikke serveren, legges
  // stemplingen i kø med tida trykket skjedde, vises som utført, og sendes
  // når serveren svarer igjen (`synkKo`). Er innloggingen gått ut, står den
  // også i kø — banneret sier det, og den sendes etter ny innlogging.
  if (!aktivListe) return;
  skjulPanelfeil();
  const tidspunkt = new Date().toISOString();
  // Står noe i kø, går alt i kø: rekkefølgen er regelen («av vakt» krever
  // «møtt»), og et trykk som sniker forbi køen bryter den.
  if (koLes().length) {
    _leggIKo(id, handling, tidspunkt);
    synkKo();
    return;
  }
  let res;
  try {
    res = await apiFetch(`/vaktliste/api/vaktposter/${id}/stempling/${handling}/`,
                         { method: 'POST', body: JSON.stringify({ tidspunkt }) });
  } catch (e) {
    _leggIKo(id, handling, tidspunkt);
    return;
  }
  if (_sesjonUtgaatt(res)) {
    _leggIKo(id, handling, tidspunkt);
    return;
  }
  const d = await res.json().catch(() => ({}));
  if (!res.ok || d.status !== 'ok') {
    visPanelfeil(d.message || 'Kunne ikke registrere stemplingen.');
    return;
  }
  await lastListe(aktivListe.vaktliste.id);
}
