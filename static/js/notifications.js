/* notifications.js — portal-wide varsel-bjelle
 *
 * Lastes av base_portal.html, base.html og patients/index.html.
 * Håndterer: badge-polling, dropdown-innlasting, klikk-navigasjon.
 *
 * Klikk-logikk:
 *   - Samme modul som brukeren er i → marker lest inline, bli på siden
 *   - Annen modul (eller portal) → naviger til varselets URL
 */
(function () {
  'use strict';

  /* ── Endepunkter ──────────────────────────────────────────────────────── */
  const API_COUNT = '/api/varsler/ulest-antall/';
  const API_LIST  = '/api/varsler/';
  const API_READ  = (pk) => `/api/varsler/${pk}/lest/`;
  const API_ALL   = '/api/varsler/marker-alle-lest/';
  const PAGE_ALL  = '/varsler/';
  const NAV_READ  = (pk) => `/varsler/${pk}/lest/`;   // HTML-redirect-variant

  /* ── DOM ─────────────────────────────────────────────────────────────── */
  const badgeEl    = document.getElementById('notification-badge');
  const listEl     = document.getElementById('notif-list');
  const markAllBtn = document.getElementById('notif-mark-all-btn');
  const bellBtn    = document.getElementById('notif-bell-btn');

  if (!badgeEl) return;   // side uten bjelle — avslutt stille

  /* ── CSRF (leses fra <meta name="csrf-token">) ───────────────────────── */
  function getCsrf() {
    return document.querySelector('meta[name="csrf-token"]')?.content ?? '';
  }

  /* ── Hvilken modul er brukeren i nå? ────────────────────────────────── */
  function currentModule() {
    const p = window.location.pathname;
    if (p.startsWith('/pasienter/')) return 'patients';
    // Fremtidige moduler: if (p.startsWith('/vakter/')) return 'vakter';
    return null;
  }

  /* ── Badge-hjelper ───────────────────────────────────────────────────── */
  function setBadge(n) {
    n = parseInt(n, 10) || 0;
    badgeEl.textContent = n > 99 ? '99+' : String(n);
    badgeEl.style.display = n > 0 ? 'inline-flex' : 'none';
  }

  /* ── Generisk fetch ──────────────────────────────────────────────────── */
  async function apiFetch(url, method) {
    const opts = { credentials: 'same-origin' };
    if (method === 'POST') {
      opts.method  = 'POST';
      opts.headers = { 'X-CSRFToken': getCsrf() };
    }
    const res = await fetch(url, opts);
    if (!res.ok) throw new Error(`${method ?? 'GET'} ${url} → ${res.status}`);
    return res.json();
  }

  /* ── Badge-polling (hvert 30 sek, kun når fanen er aktiv) ───────────── */
  async function pollCount() {
    if (document.visibilityState !== 'visible') return;
    try {
      const data = await apiFetch(API_COUNT);
      setBadge(data.unread);
    } catch (_) {}
  }
  setInterval(pollCount, 30_000);
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') pollCount();
  });

  /* ── HTML-escaping ───────────────────────────────────────────────────── */
  function esc(str) {
    return String(str ?? '')
      .replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  /* ── Relativ tidslabel ───────────────────────────────────────────────── */
  function timeLabel(iso) {
    const diffMin = Math.floor((Date.now() - new Date(iso)) / 60_000);
    if (diffMin < 1)   return 'Akkurat nå';
    if (diffMin < 60)  return `${diffMin} min siden`;
    const h = Math.floor(diffMin / 60);
    if (h < 24)        return `${h} t siden`;
    return new Date(iso).toLocaleDateString('nb-NO', { day: 'numeric', month: 'short' });
  }

  /* ── Render liste ────────────────────────────────────────────────────── */
  function renderList(notifications) {
    if (!listEl) return;
    if (!notifications.length) {
      listEl.innerHTML =
        '<div class="notif-empty"><i class="bi bi-bell-slash"></i><div>Ingen varsler</div></div>';
      return;
    }
    listEl.innerHTML = notifications.map(n => `
      <div class="notif-item${n.is_read ? '' : ' unread'}"
           data-id="${n.id}"
           data-url="${esc(n.url)}"
           data-module="${esc(n.module_slug)}"
           role="button" tabindex="0">
        <div class="notif-item-body">
          <div class="notif-item-title">${esc(n.title)}</div>
          ${n.message ? `<div class="notif-item-msg">${esc(n.message)}</div>` : ''}
          <div class="notif-item-time">${timeLabel(n.created_at)}</div>
        </div>
        ${!n.is_read ? '<div class="notif-dot" aria-hidden="true"></div>' : ''}
      </div>`).join('');

    listEl.querySelectorAll('.notif-item').forEach(el => {
      el.addEventListener('click', () => handleClick(el));
      el.addEventListener('keydown', e => { if (e.key === 'Enter') handleClick(el); });
    });
  }

  /* ── Klikk-logikk (kontekst-bevisst) ────────────────────────────────── */
  async function handleClick(el) {
    const pk      = el.dataset.id;
    const url     = el.dataset.url;
    const mod     = el.dataset.module;
    const sameApp = mod && mod === currentModule();

    if (sameApp || !url) {
      // Marker lest inline — brukeren blir på siden
      try {
        const data = await apiFetch(API_READ(pk), 'POST');
        el.classList.remove('unread');
        el.querySelector('.notif-dot')?.remove();
        setBadge(data.unread_count);
      } catch (_) {}
    } else {
      // Naviger — eksisterende HTML-view markerer som lest og redirecter
      window.location.href = NAV_READ(pk);
    }
  }

  /* ── Last varsler når dropdown åpnes ────────────────────────────────── */
  async function loadNotifications() {
    if (!listEl) return;
    listEl.innerHTML = '<div class="notif-empty">Laster…</div>';
    try {
      const data = await apiFetch(API_LIST);
      renderList(data.notifications);
      setBadge(data.unread_count);
    } catch (_) {
      listEl.innerHTML = '<div class="notif-empty">Kunne ikke laste varsler.</div>';
    }
  }

  /* ── Marker alle lest ────────────────────────────────────────────────── */
  if (markAllBtn) {
    markAllBtn.addEventListener('click', async () => {
      try {
        await apiFetch(API_ALL, 'POST');
        setBadge(0);
        listEl?.querySelectorAll('.notif-item').forEach(el => {
          el.classList.remove('unread');
          el.querySelector('.notif-dot')?.remove();
        });
      } catch (_) {}
    });
  }

  /* ── Bootstrap dropdown-event ────────────────────────────────────────── */
  if (bellBtn) {
    bellBtn.addEventListener('show.bs.dropdown', loadNotifications);
  }
})();
