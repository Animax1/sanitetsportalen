// ════════════════════════════════════════════════════════
// oppdrag-sentral-lasting.js
// ════════════════════════════════════════════════════════
//
// Lasting, oppstart og vaktarkivet.
//
// `oppstart()` tegner listene uansett hva første henting ga, og pollingen
// settes i `finally` — se funksjonen selv.
//
// Delt ut av `oppdrag-sentral.js` 14. sep. 2026 (gjeldspunkt 3.6).
// Fila var 1 991 linjer. Ingen bundler: filene lastes i rekkefølge fra
// `templates/oppdrag/sentral.html` og deler ett globalt navnerom som
// før. `JsSplittenErKompletTests` håndhever at ingen funksjon forsvant
// eller ble duplisert.
// ════════════════════════════════════════════════════════

// ── Lasting ─────────────────────────────────────────────

async function lastEnheter() {
  const res = await apiFetch('/oppdrag/api/enheter/', {
    headers: etagEnheter ? { 'If-None-Match': etagEnheter } : {},
  });
  if (res.status === 304) return false;
  if (!res.ok) return false;
  etagEnheter = res.headers.get('ETag');
  enheter = (await res.json()).data || [];
  enheterHentet = true;

  // **Bufferet tømmes bare når noe faktisk endret seg** — etter 304-sjekken,
  // ikke før. Tømte vi det på hver runde, ville et åpent panel stått på
  // «Henter…» for alltid: `undefined` betyr «ikke hentet», og ingenting
  // ville hentet det på nytt.
  //
  // Står et panel åpent, hentes det på nytt her. Et tall om hvem som er i
  // bilen skal ikke bli stående fra forrige time.
  besetninger = {};
  if (apenBesetning !== null) hentBesetning(apenBesetning);
  return true;
}


async function lastOppdrag() {
  const res = await apiFetch('/oppdrag/api/oppdrag/', {
    headers: etagOppdrag ? { 'If-None-Match': etagOppdrag } : {},
  });
  if (res.status === 304) return false;
  if (!res.ok) return false;
  etagOppdrag = res.headers.get('ETag');
  oppdragsliste = (await res.json()).data || [];
  oppdragHentet = true;
  return true;
}


function fyllNedtrekk() {
  // Kalles fra pollingen hver gang enhetslista har endret seg — og en
  // statusendring på en bil er en endring. Mens operatøren fyller ut «Nytt
  // oppdrag» bygges avkryssingen altså om under henne; det som sto krysset
  // av og valgt må derfor settes tilbake (André, 12. sep. 2026: «krysset
  // forsvinner når jeg går nedover i listen»).
  const enhetsvalg = document.getElementById('nytt-enheter');
  if (enhetsvalg) {
    const krysset = _valgteEnheter();
    enhetsvalg.innerHTML = mkEnhetsvalg()
      || '<div class="tom-melding">Ingen enheter på vakt.</div>';
    enhetsvalg.querySelectorAll('input[name="nytt-enhet"]').forEach((i) => {
      if (krysset.includes(Number(i.value))) i.checked = true;
    });
  }
  const lokvalg = document.getElementById('nytt-lokasjon');
  if (lokvalg) {
    const valgt = lokvalg.value;
    const aktive = lokasjoner.filter((l) => l.er_aktiv);
    lokvalg.innerHTML = (aktive.map(
      (l) => `<option value="${escHtmlValue(l.id)}">${escapeHtml(l.navn)}</option>`).join(''));
    if (valgt && aktive.some((l) => String(l.id) === String(valgt))) lokvalg.value = valgt;
  }
}


function visManglendeOppsett() {
  // Et skjema som lar deg trykke «Opprett» og så feiler med «Ukjent enhet» er
  // verre enn et som sier fra på forhånd hva som mangler.
  const boks = document.getElementById('mangler-oppsett');
  if (!boks) return;
  const mangler = [];
  if (!enheter.filter((e) => e.pa_vakt).length) mangler.push('ingen enheter på vakt');
  if (!lokasjoner.filter((l) => l.er_aktiv).length) mangler.push('ingen aktive lokasjoner');

  const knapp = document.querySelector('[data-bs-target="#nyttOppdragModal"]');
  if (mangler.length) {
    document.getElementById('mangler-hva').textContent = ' Portalen har ' + mangler.join(' og ') + '.';
    boks.classList.remove('d-none');
    if (knapp) knapp.disabled = true;
  } else {
    boks.classList.add('d-none');
    if (knapp) knapp.disabled = false;
  }
}


//: Plassholderen mens første henting mangler. Sida poller hvert 30. sekund,
//: så meldingen sier hva som skjer videre i stedet for å stå på «Laster…».
const LASTEFEIL = 'Kunne ikke hente lista — prøver igjen om 30 sekunder.';


async function _trygt(laster) {
  // Et kall som kaster (ingen nett, avbrutt) skal ikke ta med seg resten av
  // runden — og heller ikke oppstarten, som setter pollingen etterpå.
  try {
    return await laster();
  } catch (e) {
    return false;
  }
}


async function lastAlt() {
  const [nyeEnheter, nyeOppdrag] = await Promise.all([_trygt(lastEnheter), _trygt(lastOppdrag)]);
  if (nyeEnheter) renderEnheter();
  if (nyeOppdrag) renderOppdrag();
  if (nyeEnheter) fyllNedtrekk();
  visManglendeOppsett();
}


function _visLastefeil(id) {
  const el = document.getElementById(id);
  if (el) el.innerHTML = '<div class="tom-melding">' + LASTEFEIL + '</div>';
}


async function oppstart() {
  // Første besøk (André, 13. sep. 2026): «Laster…» sto tomt. Oppstarten var
  // fire kall på rad uten feilhåndtering — feilet ett, tegnet ingen noe, og
  // pollingen ble aldri satt. Nå får listene innhold uansett hva hentingen
  // ga: det de har, eller LASTEFEIL til første henting lykkes. Tom og ikke
  // hentet er to ulike ting — «Ingen enheter på vakt» før svaret er kommet
  // hadde vært en løgn. Tegnefunksjonene selv kjenner ikke skillet: de
  // tegner det som ligger i `enheter`/`oppdragsliste`.
  await _trygt(lastLokasjoner);
  await lastAlt();
  if (enheterHentet) renderEnheter(); else _visLastefeil('enhetsliste');
  if (oppdragHentet) renderOppdrag(); else _visLastefeil('oppdragsliste');
  fyllNedtrekk();
  visManglendeOppsett();
}


// ── Vaktarkiv (fase 7) ───────────────────────────────────────────────────
//
// Kun global admin ser knappen, og serveren gater alle fire endepunktene på
// nytt. Arkivering fryser vakten med signatur; historikken over rydder tavla
// og er reversibel. To handlinger, to knapper.

let arkivliste = [];

function _arkivTittel(a) {
  // Eldre arkiv har «Vaktnavn — arkivert …» som tittel; navnet står alt på
  // raden under, så det klippes her. Nye arkiv lages uten det.
  const prefiks = `${a.vakt_navn} — `;
  const t = String(a.tittel || '');
  if (a.vakt_navn && t.startsWith(prefiks)) {
    const rest = t.slice(prefiks.length);
    return rest.charAt(0).toUpperCase() + rest.slice(1);
  }
  return t;
}


function renderArkiv() {
  const el = document.getElementById('arkivliste');
  if (!el) return;
  if (!arkivliste.length) {
    el.innerHTML = '<div class="tom-melding">Ingen arkiverte vakter ennå.</div>';
    return;
  }
  el.innerHTML = arkivliste.map((a) => {
    const kollaps = a.kollapset
      ? '<span class="oppdrag-meta">· radene er slettet, kun tall igjen</span>'
      : '';
    // Hoistet ut av mal-strengen, som `oppdragslinje` i `_enhetskort`: en
    // nøstet mal-streng inne i en `${...}` er usynlig for XSS-skanneren —
    // regexen dens stopper på den første `}`, så den ser et avkuttet uttrykk
    // og ikke escapingen inni. Notatet escapes fortsatt her.
    const notat = a.notat
      ? `<div class="oppdrag-fritekst">${escapeHtml(a.notat)}</div>` : '';
    return `
    <div class="oppdrag-rad">
      <div class="d-flex align-items-center gap-2 flex-wrap">
        <span class="oppdrag-problem">${escapeHtml(_arkivTittel(a))}</span>
        <span class="oppdrag-nr">${escHtmlValue(a.antall_oppdrag)} oppdrag</span>
      </div>
      <div class="oppdrag-meta mt-1">
        ${escapeHtml(a.vakt_navn)} · arkivert av ${escapeHtml(a.importert_av)}
        ${kollaps}
      </div>
      ${notat}
      <div class="mt-2 d-flex gap-2">
        <button class="btn btn-sm btn-outline-primary" type="button"
                data-action="visArkivStatistikk" data-id="${escHtmlValue(a.id)}">Vis statistikk</button>
        <button class="btn btn-sm btn-outline-secondary" type="button"
                data-action="visArkiv" data-id="${escHtmlValue(a.id)}">Signatur</button>
        <button class="btn btn-sm btn-outline-danger" type="button"
                data-action="slettArkiv" data-id="${escHtmlValue(a.id)}">Slett</button>
      </div>
      <div id="arkiv-detalj-${escHtmlValue(a.id)}" class="mt-2"></div>
    </div>`;
  }).join('');
}


async function lastArkiv() {
  const res = await apiFetch('/oppdrag/api/arkiv/');
  if (!res.ok) return;
  arkivliste = (await res.json()).data || [];
  renderArkiv();
}


async function arkiverVakt() {
  const feil = document.getElementById('arkiv-feil');
  feil?.classList.add('d-none');
  await withSubmitGuard('arkiv-knapp', async () => {
    const notat = (document.getElementById('arkiv-notat')?.value || '').trim();
    const res = await apiFetch('/oppdrag/api/arkiv/', {
      method: 'POST',
      body: JSON.stringify({ notat }),
    });
    const d = await res.json().catch(() => ({}));
    if (!res.ok || d.status !== 'ok') {
      // Inline, ikke alert(): meldingen hører hjemme ved knappen som
      // feilet, og en alert forsvinner før man rekker å lese den.
      if (feil) {
        feil.textContent = d.message || 'Arkivering feilet.';
        feil.classList.remove('d-none');
      }
      return;
    }
    const notatfelt = document.getElementById('arkiv-notat');
    if (notatfelt) notatfelt.value = '';
    // Vakta er lukket: tavla og historikken er tomme, og nummeret starter
    // på nytt. Alt som viser oppdrag må tegnes på nytt.
    await lastArkiv();
    await lastAlt();
  });
}


function visArkivStatistikk(id) {
  // Som pasientarkivet: tallene tegnes på /statistikk/, ikke som en linje
  // her (André, 12. sep. 2026: «viser i ren tekst»). Arkiv-id-en i URL-en,
  // så sida kan lastes på nytt og deles.
  window.location.href = `/statistikk/?kilde=oppdrag&arkiv=${encodeURIComponent(id)}`;
}


async function visArkiv(id) {
  const boks = document.getElementById(`arkiv-detalj-${id}`);
  if (!boks) return;
  if (boks.innerHTML) { boks.innerHTML = ''; return; }   // klikk igjen = lukk

  const res = await apiFetch(`/oppdrag/api/arkiv/${id}/`);
  if (!res.ok) return;
  const a = (await res.json()).data || {};
  const s = a.stats && a.stats.summary ? a.stats.summary : null;
  if (!s) { boks.innerHTML = '<div class="tom-melding">Ingen tall.</div>'; return; }

  // Signaturen er hele poenget med et arkiv: stemmer den ikke, skal det stå
  // først og tydelig, ikke som en detalj under tallene.
  const tukling = a.tamper_detected
    ? '<div class="text-danger fw-bold mb-1">Signaturen stemmer ikke — arkivet kan være endret.</div>'
    : '';
  boks.innerHTML = `
    ${tukling}
    <div class="oppdrag-meta">
      ${escHtmlValue(s.total)} oppdrag · ${escHtmlValue(s.fullforte)} fullført ·
      median responstid ${escHtmlValue(fmtMin(s.responstid.median))} ·
      median oppdragstid ${escHtmlValue(fmtMin(s.oppdragstid.median))}
    </div>
    <div class="oppdrag-meta">SHA-256: ${escapeHtml((a.sha256 || '').slice(0, 16))}…</div>`;
}


async function slettArkiv(id) {
  if (!confirm('Slette arkivet? Det kan ikke angres, og arkivet er det '
             + 'eneste som står igjen etter at vakten er avsluttet.')) return;
  const res = await apiFetch(`/oppdrag/api/arkiv/${id}/`, {
    method: 'DELETE',
    body: JSON.stringify({ confirm: true }),
  });
  if (!res.ok) return;
  await lastArkiv();
}


document.addEventListener('DOMContentLoaded', async () => {
  try {
    await oppstart();
  } finally {
    // Pollingen settes uansett hvordan oppstarten gikk — det er den som
    // henter lista når nettet er tilbake.
    // Samme kadens som pasientlista. ETag gjør at et poll uten endring koster
    // en 304 uten kropp.
    setInterval(lastAlt, 30000);
    // «12 min siden» eldes uten at serveren sier noe — lista svarer 304 når
    // ingenting er endret. Én tegning i minuttet holder tallene ærlige.
    // — men ikke over LASTEFEIL: en liste som ikke er hentet har ingen tall.
    setInterval(() => {
      if (oppdragHentet) renderOppdrag();
      if (enheterHentet) renderEnheter();
    }, 60000);
  }
});


// «Nytt oppdrag» begynner tomt hver gang det åpnes — se `nullstillNyttOppdrag`.
document.getElementById('nyttOppdragModal')
  ?.addEventListener('show.bs.modal', nullstillNyttOppdrag);
// Vaktarkivet og historikken åpnes med data-bs-toggle: notatet fra et avvist
// forsøk og søketeksten skal ikke stå igjen (André, 19. sep. 2026).
nullstillModalVedLukking('arkivModal', ['arkiv-notat'], 'arkiv-feil');
nullstillModalVedLukking('historikkModal', ['historikk-sok'], 'historikk-feil');
