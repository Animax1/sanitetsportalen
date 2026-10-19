// ════════════════════════════════════════════════════════════════════════════
// ko-hode.js — hodet i hendelsen: talegruppa (TG), beskrivelsen og de eksterne
// aktørene som er varslet (19. okt. 2026). Skilt ut av ko-hendelser.js samme
// dag, da den sto på 1 798 av 1 800 linjer (`core/tests_js_splitt.py`).
//
// Tredje av KOs seks filer. Ingenting kjører på toppnivå; `koTegnDetalj()` i
// ko-hendelser.js kaller byggerne her. Reglene står i `ko/services.py`
// (`sett_talegruppe`, `sett_beskrivelse`, `varsle`) og i `ko/CLAUDE.md`.
// ════════════════════════════════════════════════════════════════════════════

// ── Talegruppa i Nødnett (19. okt. 2026) ─────────────────────────────────────
// «TG er talegruppe som vi bruker i nødnett … Når den settes bør de kunne
// velge å om å dele til bil enheter» (André). **To knapper, ikke en
// avkrysning for deling**: hodet tegnes om ved hver poll, og en avkrysning
// ville blitt nullstilt mens hun valgte. Nedtrekket bevares (`koBevarFelter`).

// Valgene i nedtrekket: lista fra KO-innstillinger, og TG-en hendelsen står på
// selv om den er tatt ut av lista siden.
function koTalegruppeValg(h) {
  const liste = (window.KO_TALEGRUPPER || []).slice();
  if (h.talegruppe && !liste.includes(h.talegruppe)) liste.push(h.talegruppe);
  return liste;
}

function koTalegruppeHtml(h, kan) {
  const tg = String(h.talegruppe || '');
  const merke = tg
    ? '<b>' + escapeHtml(tg) + '</b> <span class="badge ' + (h.talegruppe_delt ? 'delt">Delt med bilene' : 'bg-secondary">Intern')
      + '</span>'
    : '<span class="text-muted">ingen</span>';
  const valg = koTalegruppeValg(h);
  if (!kan || h.status !== 'apen' || !valg.length) {
    return tg ? '<div class="d-flex align-items-center gap-2 flex-wrap mt-2"><span class="h-felt">'
      + '<i class="bi bi-headset"></i> TG:</span>' + merke + '</div>' : '';
  }
  const id = escapeHtml(h.id);
  return '<div class="d-flex align-items-center gap-2 flex-wrap mt-2"><span class="h-felt"><i class="bi bi-headset"></i> TG:</span>'
    + merke
    + '<select id="ko-tg-valg" class="form-select form-select-sm w-auto" aria-label="Talegruppe">'
    + '<option value="">— ingen TG —</option>'
    + valg.map((n) => '<option value="' + escapeHtml(n) + '"' + (n === tg ? ' selected' : '') + '>' + escapeHtml(n) + '</option>').join('')
    + '</select>'
    + '<button type="button" class="btn btn-sm btn-outline-secondary" data-action="koSettTalegruppe" data-id="' + id + ':intern">Sett</button>'
    + '<button type="button" class="btn btn-sm btn-outline-success" data-action="koSettTalegruppe" data-id="' + id + ':del"'
    + ' title="Bilene på hendelsens oppdrag ser TG-en og linja i loggen"><i class="bi bi-send me-1"></i>Sett og del med bilene</button>'
    + '</div>';
}

async function koSettTalegruppe(arg) {
  const [id, hvordan] = String(arg).split(':');
  const valgt = (document.getElementById('ko-tg-valg') || {}).value || '';
  const { res, data } = await _koHendelsehandling('/ko/api/hendelser/' + id + '/talegruppe/',
    { talegruppe: valgt, del: hvordan === 'del' });
  if (!res.ok) { window.alert(data.message || 'Talegruppen ble ikke satt.'); return; }
  await koHentLogg();
  koHentOppdragPaaNytt();
}

// ── Beskrivelsen og de eksterne aktørene i hodet (19. okt. 2026) ───────────
// Beskrivelsen er en logglinje; hodet viser gjeldende versjon av kjeden
// `beskrivelse_rot` peker på, og «Oppdater» er en retting (`ko/CLAUDE.md`).

let koBeskrivelseRedigeres = null;   // hendelsen der beskrivelsen står åpen

// Den gjeldende beskrivelsen, eller null. `koLinjer` er nøklet på rot og
// holder alltid nyeste ledd, så dette er et oppslag og ikke et søk.
function koBeskrivelse(h) {
  if (!h || !h.beskrivelse_rot) return null;
  const linje = koLinjer.get(h.beskrivelse_rot);
  return linje && !linje.fjernet ? linje : null;
}

function koBeskrivelseHtml(h, kan) {
  const besk = koBeskrivelse(h);
  if (koBeskrivelseRedigeres === h.id && kan) {
    return '<div class="h-beskrivelse h-beskrivelse-rediger mt-2">'
      + '<textarea id="ko-beskrivelse-tekst" class="form-control form-control-sm" rows="3"'
      + ' data-linje="' + escapeHtml(besk ? besk.id : '') + '"'
      + ' placeholder="Hva har skjedd, hvor, hvem — det alle må vite">' + escapeHtml(besk ? besk.tekst : '') + '</textarea>'
      + '<div class="d-flex gap-2 mt-1">'
      + '<button type="button" class="btn btn-sm btn-primary" id="ko-beskrivelse-lagre" data-action="koBeskrivelseLagre"'
      + ' data-id="' + escapeHtml(h.id) + '"><i class="bi bi-check2 me-1"></i>Lagre</button>'
      + '<button type="button" class="btn btn-sm btn-outline-secondary" data-action="koBeskrivelseAvbryt"'
      + ' data-id="' + escapeHtml(h.id) + '">Avbryt</button>'
      + '<span class="text-muted small align-self-center">Lagres som en retting — loggen viser hva som sto før.</span>'
      + '</div><div class="text-danger small mt-1 d-none" id="ko-beskrivelse-feil" role="alert"></div></div>';
  }
  const knapp = kan
    ? '<button type="button" class="btn btn-link btn-sm p-0 ms-auto" data-action="koBeskrivelseRediger"'
      + ' data-id="' + escapeHtml(h.id) + '"><i class="bi bi-pencil me-1"></i>' + (besk ? 'Oppdater' : 'Legg til beskrivelse') + '</button>'
    : '';
  if (!besk) {
    return knapp ? '<div class="h-beskrivelse h-beskrivelse-tom mt-2 d-flex">' + knapp + '</div>' : '';
  }
  const hvem = escapeHtml(besk.forfatter || '') + ' ' + escapeHtml(koKlokke(besk.registrert_at || besk.tidspunkt))
    + (besk.korrigerer ? ' · oppdatert' : '');
  return '<div class="h-beskrivelse mt-2">'
    + '<div class="d-flex align-items-center gap-2"><span class="h-felt"><i class="bi bi-card-text"></i> Beskrivelse</span>'
    + '<span class="text-muted small">' + hvem + '</span>' + koDeltMerke(besk) + knapp + '</div>'
    + '<div class="h-beskrivelse-tekst">' + escapeHtml(besk.tekst) + '</div></div>';
}

// Lista fra KO-innstillinger, pluss varslede som er tatt ut av den siden.
function koEksterneValg(h) {
  const varslet = new Map((h.varslinger || []).map((v) => [v.ressurs_id, v]));
  const ut = (window.KO_EKSTERNE || []).map((r) => ({ id: r.id, navn: r.navn, varslet: varslet.get(r.id) || null }));
  const kjente = new Set(ut.map((r) => r.id));
  (h.varslinger || []).forEach((v) => {
    if (!kjente.has(v.ressurs_id)) ut.push({ id: v.ressurs_id, navn: v.navn, varslet: v });
  });
  return ut;
}

// **`value` er tilstanden et trykk gir**: delegeringen sender `el.value`, ikke
// `checked` (`hendelseArgumenter`) — uavkrysset bærer «1», avkrysset «0».
function koEksterneHtml(h, kan) {
  const valg = koEksterneValg(h);
  if (!valg.length) return '';
  const aktiv = kan && h.status === 'apen';
  const bokser = valg.map((r) => {
    const v = r.varslet;
    // En varsling uten ressurs (raden er slettet) kan ikke angres herfra.
    const laast = !aktiv || r.id === null || r.id === undefined;
    return '<label class="h-ekstern' + (v ? ' varslet' : '') + '"' + (v && v.av ? ' title="Krysset av av ' + escapeHtml(v.av) + '"' : '') + '>'
      + '<input type="checkbox" class="form-check-input me-1" data-action="koVarsle" data-hendelse="change"'
      + ' data-felt="varslet" data-id="' + escapeHtml(r.id) + '" value="' + (v ? '0' : '1') + '"'
      + (v ? ' checked' : '') + (laast ? ' disabled' : '') + '>'
      + escapeHtml(r.navn) + (v ? ' <span class="tid">' + escapeHtml(koKlokke(v.tid)) + '</span>' : '')
      + '</label>';
  }).join('');
  const tid = aktiv
    ? '<input type="time" id="ko-varsling-tid" class="form-control form-control-sm h-ekstern-tid"'
      + ' title="Når de ble varslet — blank er nå" aria-label="Varslet klokka">'
    : '';
  return '<div class="d-flex align-items-center gap-2 flex-wrap mt-2">'
    + '<span class="h-felt"><i class="bi bi-broadcast"></i> Varslet:</span>' + bokser + tid + '</div>';
}

function koBeskrivelseRediger(id) {
  koBeskrivelseRedigeres = Number(id);
  koTegnDetalj();
  const felt = document.getElementById('ko-beskrivelse-tekst');
  if (felt) felt.focus();
}

function koBeskrivelseAvbryt() {
  koBeskrivelseRedigeres = null;
  koTegnDetalj();
}

async function koBeskrivelseLagre(id) {
  const felt = document.getElementById('ko-beskrivelse-tekst');
  const feil = document.getElementById('ko-beskrivelse-feil');
  if (!felt) return;
  await withSubmitGuard('ko-beskrivelse-lagre', async () => {
    const { res, data } = await _koHendelsehandling('/ko/api/hendelser/' + id + '/beskrivelse/',
      { tekst: felt.value, linje: (felt.dataset || {}).linje || null });
    if (!res.ok) {
      if (feil) { feil.textContent = data.message || 'Beskrivelsen ble ikke lagret.'; feil.classList.remove('d-none'); }
      // 409: noen andre oppdaterte den. Hent den nye; teksten hun skrev står i feltet.
      if (res.status === 409) koHentLogg();
      return;
    }
    if (data.linje) koLinjer.set(data.linje.rot, data.linje);
    if (data.data) koHendelser.set(data.data.id, data.data);
    koBeskrivelseRedigeres = null;
    koTegnDetalj();
    // En delt beskrivelse står i bilen; rettingen skal fram dit også.
    koHentOppdragPaaNytt();
  });
}

async function koVarsle(ressursId, felt, verdi) {
  const id = koApenHendelseId;
  if (id === null) return;
  const tid = (document.getElementById('ko-varsling-tid') || {}).value || '';
  const kropp = { ressurs_id: ressursId, varslet: verdi === '1' };
  if (kropp.varslet && tid) kropp.tidspunkt = koTidspunktISO(tid);
  const { res, data } = await _koHendelsehandling('/ko/api/hendelser/' + id + '/varsling/', kropp);
  if (!res.ok) window.alert(data.message || 'Varslingen ble ikke lagret.');
  await koHentLogg();
  koHentOppdragPaaNytt();
}
