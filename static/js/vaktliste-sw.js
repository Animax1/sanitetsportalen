/* Service worker for /vaktliste/ — offline drift (13. sep. 2026).
 *
 * Holder siden, stilene, skriptene og siste svar fra vaktliste-API-et lokalt,
 * så drifts-PC-en kan vise lista og stemple møtt/av vakt når serveren ikke
 * svarer. Stemplingene selv legges i kø av vaktliste.js — workeren rører
 * ingen POST.
 *
 * Tre regler, og `avgjor()` er det ene stedet de står:
 *   - API-GET under /vaktliste/api/: nettet først, kopien når nettet feiler.
 *     Kopien får headeren X-Vl-Kopi med tida den ble lagret, så siden kan si
 *     «viser lista slik den var kl 12:04».
 *   - Siden selv (/vaktliste/): nettet først, kopien når nettet feiler. Bare
 *     et svar som ikke er en omdirigering lagres — en utgått sesjon gir
 *     innloggingssiden, og den skal ikke bli «vaktlista».
 *   - Statiske filer og CDN (Bootstrap, ikoner): kopien først, nettet i
 *     bakgrunnen. Filnavnene er hashet av WhiteNoise, så en gammel kopi er
 *     aldri feil versjon.
 *
 * Serveres av vaktliste.views.sw_view, ikke fra /static/ — en worker styrer
 * bare stier under sin egen.
 */
// Bumpes når en gammel kopi skal kastes, ikke ved hver endring: `activate`
// sletter alle `vl-sw-`-cacher som ikke bærer denne strengen. Til `vl-sw-5`
// 14. sep. 2026, fordi `vaktliste.js` ble delt i fem filer — den gamle
// samlefila lå igjen i skallcachen som død vekt på hver drifts-PC som hadde
// vært innom. **Prisen er datakopien**: den slettes med, så en PC som mister
// nettet rett etter en bump står uten offline-liste til den har lastet én
// gang online. Derfor ikke ved hver endring — filnavnene er hashet av
// WhiteNoise, så en ny fil hentes uansett uten at versjonen røres.
const VERSJON = 'vl-sw-5';
const SKALL = `${VERSJON}-skall`;
const DATA = `${VERSJON}-data`;
// Bibliotekene ligger under /static/ (13. sep. 2026, H3) — ingen CDN å hente.
const CDN = [];
// Datakopien serveres ikke etter dette (13. sep. 2026, H4): en vakt varer
// ikke lenger, og en kopi av mannskapsregisteret skal ikke ligge klar til
// den som åpner sida uten nett uker senere. Logg ut rydder alt uansett.
const MAKS_ALDER_MS = 24 * 60 * 60 * 1000;


function erForGammel(lagretIso, naaMs) {
  // Ren funksjon, testes i node. Mangler tida, regnes kopien som gammel.
  const t = Date.parse(lagretIso || '');
  if (Number.isNaN(t)) return true;
  return naaMs - t > MAKS_ALDER_MS;
}


function avgjor(url, metode, modus, egenOrigin) {
  // -> 'api' | 'side' | 'statisk' | null. Ren funksjon, testes i node.
  if (metode !== 'GET') return null;
  let u;
  try { u = new URL(url); } catch (e) { return null; }
  if (u.origin === egenOrigin) {
    if (u.pathname === '/vaktliste/sw.js') return null;
    if (u.pathname.startsWith('/vaktliste/api/')) {
      // Fila og utsendingen er ikke noe å vise offline.
      if (/\/fil\/$/.test(u.pathname)) return null;
      return 'api';
    }
    if (modus === 'navigate') {
      return u.pathname === '/vaktliste/' ? 'side' : null;
    }
    if (u.pathname.startsWith('/static/')) return 'statisk';
    return null;
  }
  return CDN.includes(u.origin) ? 'statisk' : null;
}


function kanLagres(svar) {
  // Ikke omdirigeringer (innlogging), ikke feil, ikke delvise svar.
  return !!svar && svar.ok && !svar.redirected && svar.status === 200;
}


function medLagretTid(svar, naaIso) {
  // Klon med tida lagt på, så kopien vet hvor gammel den er når den serveres.
  const h = new Headers(svar.headers);
  h.set('X-Vl-Lagret', naaIso);
  return svar.arrayBuffer().then((kropp) =>
    new Response(kropp, { status: svar.status, statusText: svar.statusText, headers: h }));
}


function somKopi(svar) {
  const h = new Headers(svar.headers);
  h.set('X-Vl-Kopi', h.get('X-Vl-Lagret') || '');
  return svar.arrayBuffer().then((kropp) =>
    new Response(kropp, { status: svar.status, statusText: svar.statusText, headers: h }));
}


async function nettForst(req, cacheNavn) {
  const cache = await caches.open(cacheNavn);
  try {
    const svar = await fetch(req);
    if (kanLagres(svar)) {
      const lagret = await medLagretTid(svar.clone(), new Date().toISOString());
      await cache.put(req, lagret);
    }
    return svar;
  } catch (e) {
    const kopi = await cache.match(req);
    if (kopi && !erForGammel(kopi.headers.get('X-Vl-Lagret'), Date.now())) return somKopi(kopi);
    if (kopi) await cache.delete(req);
    throw e;
  }
}


function filnokkel(url) {
  // Ren funksjon, testes i node. Adressen uten WhiteNoise-hashen:
  // `/static/js/a.1a2b3c4d5e6f.js` → `/static/js/a.js`. Hashen er Djangos
  // `md5(...)[:12]` (`HashedFilesMixin.file_hash`).
  let u;
  try { u = new URL(url); } catch (e) { return url; }
  return u.origin + u.pathname.replace(/\.[0-9a-f]{12}(\.[^./]+)$/, '$1');
}


async function ryddEldreUtgaver(cache, url) {
  // **Skallcachen vokste for hver deploy** (26. sep. 2026, G5). Hver endret
  // fil får et nytt hashet navn, den nye ble lagt til og den gamle lå igjen
  // til neste `VERSJON`-bump. Når en fil hentes under et navn vi ikke har,
  // er alle andre utgaver av den utdatert.
  const nokkel = filnokkel(url);
  const alle = await cache.keys();
  await Promise.all(alle
    .filter((r) => r.url !== url && filnokkel(r.url) === nokkel)
    .map((r) => cache.delete(r)));
}


async function kopiForst(req, cacheNavn) {
  const cache = await caches.open(cacheNavn);
  const kopi = await cache.match(req);
  const henting = fetch(req).then(async (svar) => {
    if (svar && (svar.ok || svar.type === 'opaque')) {
      await cache.put(req, svar.clone());
      if (!kopi) await ryddEldreUtgaver(cache, req.url);
    }
    return svar;
  }).catch(() => null);
  if (kopi) return kopi;
  const svar = await henting;
  if (svar) return svar;
  throw new Error('Ingen kopi og ikke nett');
}


self.addEventListener('install', (e) => {
  e.waitUntil(self.skipWaiting());
});


function skalKastes(navn) {
  // Ren funksjon, testes i node — som `avgjor()` og `erForGammel()`.
  //
  // Prefiks og ikke likhet, fordi hver versjon har to cacher (`-skall` og
  // `-data`). Og bare våre egne: workeren deler origin med resten av
  // portalen, så `caches.keys()` kan inneholde noe vi ikke eier.
  return navn.startsWith('vl-sw-') && !navn.startsWith(VERSJON);
}


async function ryddGamleCacher() {
  const navn = await caches.keys();
  await Promise.all(navn.filter(skalKastes).map((n) => caches.delete(n)));
}


self.addEventListener('activate', (e) => {
  e.waitUntil((async () => {
    await ryddGamleCacher();
    await self.clients.claim();
  })());
});


self.addEventListener('fetch', (e) => {
  const valg = avgjor(e.request.url, e.request.method, e.request.mode, self.location.origin);
  if (valg === 'api') e.respondWith(nettForst(e.request, DATA));
  else if (valg === 'side') e.respondWith(nettForst(e.request, SKALL));
  else if (valg === 'statisk') e.respondWith(kopiForst(e.request, SKALL));
});
