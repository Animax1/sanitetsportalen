# Sanitetsportal — Fase 5

**Leveranse:** Bruker‑Behandler‑kobling, «Mine pasienter»‑filter, generisk varsel‑bjelle.

Fase 5 lar innloggede brukere kobles til en oppføring i Behandler‑ eller Helsepersonell‑listen. Når en pasient tildeles, eller flyttes mellom slike oppføringer, mottar de berørte brukerne et varsel som vises i en bjelle øverst til høyre i portalen. Varsel‑modulen er bygget generisk slik at Vakter, Utstyr og fremtidige moduler kan ta den i bruk uten endringer i `core`.

## Innholdsfortegnelse

- [Hva er nytt](#hva-er-nytt)
- [Arkitektur](#arkitektur)
- [Databasemodeller](#databasemodeller)
- [Migrasjoner](#migrasjoner)
- [API for varsler](#api-for-varsler)
- [Endepunkter](#endepunkter)
- [Frontend](#frontend)
- [Administrasjon](#administrasjon)
- [Tester](#tester)
- [Drift og rutiner](#drift-og-rutiner)
- [Fremtidige utvidelser](#fremtidige-utvidelser)

## Hva er nytt

| Område | Endring |
|---|---|
| Modeller | `Behandler.user` og `Helsepersonell.user` (`OneToOneField` mot `CustomUser`, `SET_NULL`) |
| Modeller | `core.Notification` — generisk varsel‑modell med `level`-felt (info / warning / critical) |
| API | `core.notifications.notify(user, *, module_slug, kind, title='', message='', url='', level='info')` med 24‑timers dedupliseringsvindu |
| Pasientliste | `?mine=1` filtrerer på pasienter der innlogget bruker er Behandler eller Helsepersonell. Default AV. |
| UI | «Mine pasienter»‑bryter i pasientregistreringen (toolbar). Tilstand lagres i `localStorage`. |
| UI | Varsel‑bjelle med ulest‑badge i `base_portal.html`. Polling hvert 30. sekund når fanen er synlig. |
| UI | Varsel‑side `/varsler/` med liste, paginering, mark‑as‑read og mark‑all‑read. |
| Admin | Bruker‑detalj viser ny seksjon «Pasientregistrering: rollekobling» der admin kan koble en bruker til Behandler **eller** Helsepersonell (XOR‑validert). |
| Signaler | `patients.signals` sender varsel ved tildeling og overføring av pasient. Feiler aldri lagringen. |

## Arkitektur

### Datamodell‑oversikt

```
CustomUser ─┬─< Behandler.user        (OneToOne, SET_NULL)
            ├─< Helsepersonell.user   (OneToOne, SET_NULL)
            └─< Notification.user     (FK, CASCADE)
```

### Hendelsesflyt — tildeling av pasient

1. Bruker lagrer pasient med `behandler=<Behandler>` eller `helsepersonell_ref=<Helsepersonell>`.
2. `patients.signals.patient_pre_save` lagrer originalverdiene (`_orig_behandler_id`, `_orig_helsepersonell_ref_id`) på instansen.
3. `patients.signals.patient_post_save` sammenligner mot originalen og kaller `_notify_assignment` for nye eiere og `_notify_transfer` for forrige eier.
4. `core.notifications.notify()` oppretter `Notification` hvis ikke et duplikat (samme `user`, `kind`, `message`) finnes siste 24 timer.
5. Frontend henter ulest‑antall hvert 30. sekund fra `GET /api/varsler/ulest-antall/` og oppdaterer bjelle‑badgen.

## Databasemodeller

### `patients.models.Behandler` (Fase 5‑tillegg)

```python
user = models.OneToOneField(
    'accounts.CustomUser',
    on_delete=models.SET_NULL,
    null=True, blank=True,
    related_name='behandler_profil',
    verbose_name='Bruker',
    help_text='Hvis koblet, kan brukeren filtrere på sine pasienter og motta varsler.',
)
```

### `patients.models.Helsepersonell` (Fase 5‑tillegg)

```python
user = models.OneToOneField(
    'accounts.CustomUser',
    on_delete=models.SET_NULL,
    null=True, blank=True,
    related_name='helsepersonell_profil',
    verbose_name='Bruker',
)
```

### `core.models.Notification`

```python
class Notification(models.Model):
    LEVEL_INFO     = 'info'
    LEVEL_WARNING  = 'warning'
    LEVEL_CRITICAL = 'critical'

    user         = models.ForeignKey('accounts.CustomUser', on_delete=CASCADE)
    module_slug  = models.CharField(max_length=64)   # 'patients', 'vakter', ...
    kind         = models.CharField(max_length=64)   # 'patient_assigned', 'patient_transferred_away'
    level        = models.CharField(max_length=16, choices=LEVEL_CHOICES, default='info')
    title        = models.CharField(max_length=200)
    message      = models.TextField(blank=True)
    url          = models.CharField(max_length=500, blank=True)
    is_read      = models.BooleanField(default=False, db_index=True)
    read_at      = models.DateTimeField(null=True, blank=True)
    created_at   = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=['user', 'is_read', '-created_at'],
                         name='core_notif_user_read_idx'),
            models.Index(fields=['user', 'module_slug', '-created_at'],
                         name='core_notif_user_module_idx'),
        ]
        ordering = ['-created_at']
```

`level`-feltet brukes ikke aktivt i UI per Fase 5, men er reservert for fremtidig differensiering av badge‑farge, lyd og push.

## Migrasjoner

| Migrasjon | Beskrivelse |
|---|---|
| `patients/0008_behandler_user_helsepersonell_user.py` | Legger til `user`-feltet på `Behandler` og `Helsepersonell`. |
| `patients/0009_link_behandlere_to_users.py` | Datamigrering: kobler automatisk Behandler/Helsepersonell hvis `name` matcher et `CustomUser.username` (case‑insensitiv). Logger antall koblinger og navn uten match. |
| `core/0003_notification.py` | Oppretter `Notification`-tabellen med indekser. |
| `core/0004_notification_read_at.py` | Legger til `read_at`-feltet. |

Migrasjonen `0009` er idempotent og trygg å kjøre flere ganger.

## API for varsler

```python
from core.notifications import notify

notify(
    user=mottaker,                  # CustomUser
    module_slug='patients',         # hvilken modul som lager varselet
    kind='patient_assigned',        # type — brukes til dedup og filter
    title='Ny pasient tildelt',
    message='Du er satt som førstehjelper for pasient #1234.',
    url='/pasienter/?focus=1234',
    level='info',                   # eller 'warning' / 'critical'
)
```

Returnerer `Notification`-instansen, eller `None` hvis dedup blokkerte opprettelsen. Anonyme brukere får aldri varsler.

**Dedupliseringsregel:** samme `(user, kind, message)` siste 24 timer → blokkeres. `title` og `url` ekskluderes fra dedup‑sammenligningen.

## Endepunkter

| Metode | URL | Beskrivelse |
|---|---|---|
| `GET`  | `/api/varsler/ulest-antall/` | Returnerer `{"unread": <int>}`. Pollet av bjellen. |
| `GET`  | `/varsler/` | Paginert liste over brukerens varsler. |
| `GET`/`POST` | `/varsler/<id>/lest/` | Markerer varsel som lest og redirecter til `notification.url`. |
| `POST` | `/varsler/marker-alle-lest/` | Markerer alle uleste varsler for brukeren som lest. |

Alle endepunkter krever innlogging. Bruker kan kun lese og endre **egne** varsler — forsøk på å åpne andres varsel returnerer `404`.

## Frontend

### «Mine pasienter»‑bryter

I `templates/patients/index.html` (toolbar):

```html
<div class="form-check form-switch ms-2">
  <input class="form-check-input" type="checkbox" id="toggle-mine"
         onchange="toggleMine(this.checked)">
  <label class="form-check-label small" for="toggle-mine">Mine pasienter</label>
</div>
```

`static/js/script.js` lagrer tilstanden i `localStorage.mineOnly` og sender `?mine=1` på begge fetcher (`loadPatients()` og `renderBoard()`). Server‑side filter — ikke klient‑side — slik at search‑indeksen ikke blir misvisende.

### Varsel‑bjelle

I `core/templates/core/base_portal.html` rett etter brukernavnet:

```html
<a id="notification-bell" href="{% url 'core:notification_list' %}">
  <i class="bi bi-bell-fill"></i>
  <span id="notification-badge" class="badge bg-danger"
        data-count="{{ notification_unread_count|default:0 }}">...</span>
</a>
```

Polling‑skriptet (samme fil) henter `/api/varsler/ulest-antall/` hvert 30. sekund. Polling pauser når fanen er skjult (`document.visibilityState`) for å spare ressurser.

## Administrasjon

I bruker‑detaljvisningen (`/accounts/brukere/<id>/`) finnes nå seksjonen **Pasientregistrering: rollekobling**. Admin kan koble brukeren til en oppføring i Behandler‑ eller Helsepersonell‑listen.

Begrensninger:
- En bruker kan kun kobles til **én** rolle (XOR — forsøk på begge gir valideringsfeil).
- Dropdowns viser kun ledige oppføringer (ingen `user`) **pluss** den allerede tilkoblede.
- Endring av kobling frigjør den gamle automatisk i samme transaksjon.

## Tester

Nye testfiler:

- `core/tests_notifications.py` — 22 tester for `notify()`, endepunkter, context processor, ulest‑telling, mark‑read/mark‑all‑read, sikkerhet (kan ikke åpne andres varsel).
- `patients/tests_fase5.py` — 14 tester for `?mine=1`-filter, tildelings‑signal, transfer‑signal (begge parter varsles), `UserPatientLinkForm` (XOR‑validering, bytte, frigjøring).

Total testsuite: **497 tester, alle grønne** (vekst fra 461 i Fase 4).

Kjøring:

```powershell
python manage.py test
```

## Drift og rutiner

### Etter deploy

1. Kjør migrasjoner: `python manage.py migrate`.
2. Datamigrasjonen `0009` logger til stdout hvilke navn som ikke fikk match. Sjekk loggen og koble manuelt fra admin‑UI om nødvendig.
3. Verifiser at bjellen vises og at polling‑skriptet ikke logger feil i nettleser‑konsollen.

### Rydding av gamle varsler

Det finnes ingen automatisk opprydning per Fase 5. Hvis tabellen vokser stor (> 100k rader), kan en management‑command eller en periodisk SQL‑jobb slette varsler eldre enn N dager:

```python
from datetime import timedelta
from django.utils import timezone
from core.models import Notification

cutoff = timezone.now() - timedelta(days=90)
Notification.objects.filter(created_at__lt=cutoff, is_read=True).delete()
```

## Fremtidige utvidelser

| Bruksområde | Beskrivelse |
|---|---|
| Vakter | Varsle deltakere når en vakt opprettes, endres eller avlyses. |
| Utstyr | Varsle ansvarlige når et utstyrselement må kontrolleres eller er utløpt. |
| Beredskap | Kritiske varsler (`level='critical'`) med fremhevet badge‑farge og lydsignal. |
| Push / e‑post | Utvid `notify()` med kanal‑valg (in‑app + push + e‑post). |
| Filter i UI | Modul‑dropdown på `/varsler/` (indeksen `core_notif_user_module_idx` er allerede på plass). |
