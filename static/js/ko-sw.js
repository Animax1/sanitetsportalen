/* Service worker for /ko/ — KO-utskriften uten nett (13. okt. 2026).
 *
 * André: «KO har bare personlige brukere med mfa. Så nr 2 er aktuelt.» KO-siden
 * henter /ko/utskrift/ i bakgrunnen hvert femte minutt (`koKopiStart()` i
 * ko.js), og workeren legger svaret i nettleseren. Mister PC-en nettet, åpner
 * «Skriv ut» kopien — og en lasting av /ko/ uten nett gir kopien i stedet for
 * nettleserens feilside. Siden selv sier hvor gammel den er.
 *
 * **Ingen redigering uten nett** (André, 13. okt. 2026: «Offline logg er bare
 * ment for å kunne ta utskrift av det som er»). Workeren rører ingen POST og
 * ingen API-kall: det den holder, er papiret.
 *
 * Tre regler, og `avgjor()`, `kanLagres()` og `erForGammel()` er de tre
 * stedene de står (testes i node):
 *   - /ko/utskrift/: nettet først, kopien når nettet feiler.
 *   - /ko/ som side (navigate): nettet alltid; feiler det, kopien av utskriften.
 *   - **Bare svar merket `X-Ko-Kopi`** lagres. Serveren setter det for
 *     personlige kontoer (`ko.utskrift.kan_lagres_lokalt`); en delt konto
 *     etterlater ingenting. Aldri en omdirigering — en utgått sesjon gir
 *     innloggingssiden, og den skal ikke bli «utskriften».
 *
 * Serveres av ko.views.sw_view, ikke fra /static/ — en worker styrer bare
 * stier under sin egen. «Logg ut» sletter cachen og workeren
 * (`Clear-Site-Data`).
 */
const KO_SW_VERSJON = 'ko-sw-1';
const KO_SW_CACHE = `${KO_SW_VERSJON}-utskrift`;
const KO_SW_UTSKRIFT = '/ko/utskrift/';
// Samme grense som vaktlistas kopi: en vakt varer ikke lenger, og papiret fra
// i går er ikke reserven i dag.
const KO_SW_MAKS_ALDER_MS = 24 * 60 * 60 * 1000;


function avgjor(url, metode, modus, egenOrigin) {
  // -> 'utskrift' | 'side' | null. Ren funksjon, testes i node.
  if (metode !== 'GET') return null;
  let u;
  try { u = new URL(url); } catch (e) { return null; }
  if (u.origin !== egenOrigin) return null;
  if (u.pathname === KO_SW_UTSKRIFT) return 'utskrift';
  if (modus === 'navigate' && u.pathname === '/ko/') return 'side';
  return null;
}


function kanLagres(svar) {
  // Bare et helt svar, ikke en omdirigering, og bare med serverens lov.
  return !!svar && svar.ok && !svar.redirected && svar.status === 200
    && svar.headers.get('X-Ko-Kopi') === '1';
}


function erForGammel(lagretIso, naaMs) {
  // Mangler tida, regnes kopien som gammel.
  const t = Date.parse(lagretIso || '');
  if (Number.isNaN(t)) return true;
  return naaMs - t > KO_SW_MAKS_ALDER_MS;
}


async function lagre(svar) {
  const h = new Headers(svar.headers);
  h.set('X-Ko-Lagret', new Date().toISOString());
  const kropp = await svar.arrayBuffer();
  const cache = await caches.open(KO_SW_CACHE);
  await cache.put(KO_SW_UTSKRIFT, new Response(kropp, { status: 200, headers: h }));
}


async function kopien() {
  const cache = await caches.open(KO_SW_CACHE);
  const kopi = await cache.match(KO_SW_UTSKRIFT, { ignoreVary: true });
  if (!kopi) return null;
  if (erForGammel(kopi.headers.get('X-Ko-Lagret'), Date.now())) {
    await cache.delete(KO_SW_UTSKRIFT);
    return null;
  }
  return kopi;
}


async function utskriften(req) {
  try {
    const svar = await fetch(req);
    if (kanLagres(svar)) await lagre(svar.clone());
    return svar;
  } catch (e) {
    const kopi = await kopien();
    if (kopi) return kopi;
    throw e;
  }
}


async function siden(req) {
  try {
    return await fetch(req);
  } catch (e) {
    const kopi = await kopien();
    if (kopi) return kopi;
    throw e;
  }
}


self.addEventListener('install', (e) => { e.waitUntil(self.skipWaiting()); });


self.addEventListener('activate', (e) => {
  e.waitUntil((async () => {
    const navn = await caches.keys();
    await Promise.all(navn.filter((n) => n.startsWith('ko-sw-') && !n.startsWith(KO_SW_VERSJON))
      .map((n) => caches.delete(n)));
    await self.clients.claim();
  })());
});


self.addEventListener('fetch', (e) => {
  const valg = avgjor(e.request.url, e.request.method, e.request.mode, self.location.origin);
  if (valg === 'utskrift') e.respondWith(utskriften(e.request));
  else if (valg === 'side') e.respondWith(siden(e.request));
});
