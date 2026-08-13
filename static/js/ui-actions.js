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

document.addEventListener('submit', (e) => {
  const skjema = e.target;
  if (!(skjema instanceof HTMLFormElement)) return;

  const melding = skjema.dataset.confirm;
  if (!melding) return;

  if (!window.confirm(melding)) {
    e.preventDefault();
  }
}, true);
