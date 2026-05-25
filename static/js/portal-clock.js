const DAYS_NO = ['søndag', 'mandag', 'tirsdag', 'onsdag', 'torsdag', 'fredag', 'lørdag'];

function updateClock() {
  const el = document.getElementById('header-dt');
  if (!el) return;
  const now = new Date();
  const dayStr = DAYS_NO[now.getDay()];
  const dateStr =
    String(now.getDate()).padStart(2, '0') + '.' +
    String(now.getMonth() + 1).padStart(2, '0') + '.' +
    now.getFullYear();
  const timeStr = now.toLocaleTimeString('no-NO', {
    hour: '2-digit', minute: '2-digit', second: '2-digit'
  });
  el.innerHTML =
    `<div style="font-size:0.8rem;opacity:0.85;">${dayStr} ${dateStr}</div>` +
    `<div style="font-size:1.35rem;font-weight:300;letter-spacing:0.07em;">${timeStr}</div>`;
}

setInterval(updateClock, 1000);
updateClock();
