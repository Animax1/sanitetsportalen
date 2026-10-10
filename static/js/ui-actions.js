// ════════════════════════════════════════════════════════
// DELTE UI-HANDLERE FOR PORTALSIDENE
//
// Erstatter inline `onsubmit="return confirm(...)"` på destruktive skjemaer.
// Inline handlere krever `unsafe-inline` i CSP-ens script-src (F5); blir det
// direktivet strammet uten at handlerne er flyttet, forsvinner bekreftelsen
// stille — og sletting av bruker, frysing av konto og MFA-nullstilling skjer
// uten at noen blir spurt.
//
// Bruk: <form ... data-confirm="Slette Kari permanent?">
// ════════════════════════════════════════════════════════

// ── «Logg ut» med usendte stemplinger (10. okt. 2026) ─────────────────────
// Utloggingen sender `Clear-Site-Data: "storage"` (H4), og det tømmer
// offline-køene i bilen og vaktlista. Køen skal *ikke* overleve utloggingen —
// da ligger den igjen på en delt PC — men den som trykker skal vite hva hun
// sletter. Gjelder skjemaer med `data-utlogging`.
//
// Prefiksene er de samme som `koNokkel()` i `oppdrag-enhet.js` og
// `vaktliste-offline.js` gir til `brukerNokkel()`; `core/tests_utlogging.py`
// krever det. Fila laster ikke `portal-utils.js`, så nøkkelen bygges her.
const OFFLINE_KOER = ['oppdrag_ko_v1', 'vl_stemplinger_v1'];

/** Antall usendte stemplinger for brukeren på denne enheten. Kaster aldri:
 *  et lager som ikke kan leses skal ikke hindre utloggingen. */
function usendteStemplinger(lager, brukerId) {
  if (brukerId === undefined || brukerId === null || brukerId === '') return 0;
  let antall = 0;
  for (const prefiks of OFFLINE_KOER) {
    try {
      const ko = JSON.parse(lager.getItem(`${prefiks}:u${brukerId}`) || '[]');
      if (Array.isArray(ko)) antall += ko.length;
    } catch (_) { /* ødelagt eller sperret lager: ingenting å miste */ }
  }
  return antall;
}

/** Spørsmålet før utlogging, eller `null` når ingenting går tapt. */
function utloggingsAdvarsel(antall) {
  if (!(antall > 0)) return null;
  const hva = antall === 1 ? '1 stempling som ikke er sendt' : `${antall} stemplinger som ikke er sendt`;
  return `Du har ${hva} ennå. Logger du ut nå, slettes ${antall === 1 ? 'den' : 'de'} `
    + 'fra denne enheten og kommer aldri fram.\n\n'
    + 'Avbryt for å vente til du har dekning, eller OK for å logge ut likevel.';
}

function _utloggingSkalStoppes(skjema) {
  if (!('utlogging' in skjema.dataset)) return false;
  let lager = null;
  try { lager = window.localStorage; } catch (_) { return false; }
  if (!lager) return false;
  const melding = utloggingsAdvarsel(usendteStemplinger(lager, window.PORTAL_BRUKER_ID));
  return melding !== null && !window.confirm(melding);
}

document.addEventListener('submit', (e) => {
  const skjema = e.target;
  if (!(skjema instanceof HTMLFormElement)) return;

  if (_utloggingSkalStoppes(skjema)) {
    e.preventDefault();
    return;
  }

  const melding = skjema.dataset.confirm;
  if (!melding) return;

  if (!window.confirm(melding)) {
    e.preventDefault();
  }
}, true);
