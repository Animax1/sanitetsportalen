"""
Statistikk- og tjeneste-funksjoner for pasientregistreringssystemet.

All statistikk-beregning er samlet her (migrert fra Flask /api/stats og /api/full-stats).

Felles primitiver (tids-validatorer, lokal-tid-helper, RBAC) ble flyttet
til core-appen i fase 1 av sanitetsportal-migreringen. Denne filen
re-eksporterer de samme navnene slik at all eksisterende kode (i views.py,
tester m.m.) fortsetter å fungere uten endring.
"""
import statistics as smod
from datetime import datetime

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone as djtz

# Re-eksport fra core (bakoverkompatibilitet)
from core.validators import (  # noqa: F401
    TIME_FIELDS,
    TIME_FORMAT,
    TIME_FORMAT_HUMAN,
    now_local_str,
    parse_minutes,
    validate_patient_time_fields,
    validate_time_string,
)
from core.auth_decorators import (  # noqa: F401
    ROLE_HIERARKI,
    has_role_at_least,
)

from .models import Patient, AppSetting, Behandler, VaktArkiv, ArkivertPasient


# ── Hjelpefunksjoner ─────────────────────────────────────────────────────────
# (now_local_str, validate_time_string, validate_patient_time_fields,
#  parse_minutes, TIME_FORMAT, TIME_FIELDS m.m. er flyttet til core.validators
#  og re-eksporteres øverst i denne filen.)


def next_patient_nr():
    """
    Hent og inkrementer neste pasientnummer atomisk.
    Bruker select_for_update for å unngå race conditions.
    """
    with transaction.atomic():
        setting = AppSetting.objects.select_for_update().get_or_create(
            key='next_patient_nr',
            defaults={'value': '1'},
        )[0]
        nr = int(setting.value)
        setting.value = str(nr + 1)
        setting.save(update_fields=['value'])
        return nr


# ── Arkiv-tilgang (modul-spesifikk konfig) ───────────────────────────────────

# Konfigurerbar min-rolle for å SE arkiv. Endre til 'lead_view' eller 'lead' for å åpne for leads.
ARKIV_VIEW_MIN_ROLE = 'admin'

# Skriving/sletting holdes ALLTID på admin
ARKIV_WRITE_ROLE = 'admin'

# ROLE_HIERARKI og has_role_at_least er flyttet til core.auth_decorators
# og re-eksporteres øverst i denne filen.


# ── Recycle av pasientnummer ved slett ────────────────────────────────────────

def recycle_patient_nr_if_last(pasientnummer):
    """Rull tilbake next_patient_nr hvis pasientnummer == current_next - 1.

    MÅ kalles inni en eksisterende transaction.atomic-blokk (ikke inni egne).
    Bruker select_for_update() for låsing mot kappkjøring.
    Returnerer True hvis telleren ble rullet tilbake, ellers False.
    """
    setting = AppSetting.objects.select_for_update().filter(
        key='next_patient_nr'
    ).first()
    if setting is None:
        return False
    current_next = int(setting.value)
    if pasientnummer == current_next - 1:
        setting.value = str(pasientnummer)
        setting.save(update_fields=['value'])
        return True
    return False


# ── Filter for pasientliste (testbar) ────────────────────────────────────────

FILTER_CHOICES = {'alle', 'rod', 'gul', 'gronn', 'rodgul', 'aktive', 'utskrevet'}


def apply_list_filter(queryset, filter_name='alle', year=None):
    """Anvend filter på et Patient-queryset.

    Filtrene 'rod', 'gul', 'gronn' og 'rodgul' gjelder KUN aktive pasienter
    (de som ikke er utskrevet). Dette matcher referanselogikken for 'rodgul'.
    """
    qs = queryset
    if year is not None:
        qs = qs.filter(year=year)

    not_utskrevet = Q(utskrevet='') | Q(utskrevet__isnull=True)

    if filter_name == 'rod':
        qs = qs.filter(grovsortering='Rød').filter(not_utskrevet)
    elif filter_name == 'gul':
        qs = qs.filter(grovsortering='Gul').filter(not_utskrevet)
    elif filter_name == 'gronn':
        qs = qs.filter(grovsortering='Grønn').filter(not_utskrevet)
    elif filter_name == 'rodgul':
        qs = qs.filter(Q(grovsortering='Rød') | Q(grovsortering='Gul')).filter(not_utskrevet)
    elif filter_name == 'aktive':
        qs = qs.filter(not_utskrevet)
    elif filter_name == 'utskrevet':
        qs = qs.exclude(utskrevet='').exclude(utskrevet__isnull=True)
    # 'alle' returnerer alt
    return qs


# ── Aktivt år (AppSetting) ────────────────────────────────────────────────────

def get_active_year():
    """Returnerer aktivt år. Default og ved årsskifte: inneværende år."""
    current = datetime.now().year
    stored = AppSetting.get('active_year', None)
    if stored is None:
        AppSetting.set('active_year', current)
        return current
    try:
        return int(stored)
    except (ValueError, TypeError):
        AppSetting.set('active_year', current)
        return current


def set_active_year(year):
    """Behold funksjonen for potensiell fremtidig bruk via Django-admin."""
    AppSetting.set('active_year', int(year))


# ── Arrangementsnavn per år ────────────────────────────────────────────────────

def get_event_name(year):
    """Returner arrangementsnavn for et år, eller tom streng."""
    return AppSetting.get(f'event_name_{year}', '') or ''


def set_event_name(year, name):
    """Sett arrangementsnavn for et år."""
    AppSetting.set(f'event_name_{year}', (name or '').strip())


def get_event_name_or_legacy(year):
    """Prøv først event_name_<year>, fall tilbake til gammel 'event_name'."""
    per_year = get_event_name(year)
    if per_year:
        return per_year
    return AppSetting.get('event_name', '') or ''


# ── Automatisk tidsstempel for påbegynt behandling ────────────────────────────

TREATMENT_TRIGGER_FIELDS = (
    'behandler', 'helsepersonell_ref', 'helsepersonell', 'lege', 'medisiner',
    'inn_obspost', 'ut_obspost', 'utskrevet', 'utskrevet_til',
)


def stamp_pabegynt_if_needed(patient, updates):
    """Sett patient.pabegynt til nå hvis behandling starter og pabegynt er tom.

    `updates` er dicten av nye verdier som settes i denne requesten. Funksjonen
    muterer `patient` in-place, men kaller ikke save() selv – det er kallers
    ansvar. Returnerer True hvis tidsstempelet ble satt.
    """
    # Hvis allerede satt, rør ikke.
    if (patient.pabegynt or '').strip():
        return False

    # Sjekk om noen trigger-felt settes til en ikke-tom verdi i denne requesten.
    for field in TREATMENT_TRIGGER_FIELDS:
        if field in updates:
            value = updates[field]
            # FK-feltene kan komme som id eller objekt
            if field in ('behandler', 'helsepersonell_ref'):
                if value:  # id > 0 eller ikke-None objekt
                    patient.pabegynt = updates.get('_now_str') or now_local_str()
                    return True
            elif str(value).strip():
                patient.pabegynt = updates.get('_now_str') or now_local_str()
                return True
    return False




# ── Tidsstempler for obspost og utskrivelse ───────────────────────────────────

# Kjente utskrivningsutfall (kun for dokumentasjon – vi stempler ved enhver ikke-tom verdi)
DISCHARGE_OUTCOMES = {
    'hjem', 'hjem/park', 'park', 'lv', 'legevakt', 'skadepol',
    'skadepoliklinikk', 'sov', 'sov.avd', 'sovepost', 'sykehus',
    'ambulanse', 'død',
}


def _is_obs_location(plassering):
    """Returner True hvis plasseringen er en obs-plass (starter med 'obs')."""
    return (plassering or '').strip().lower().startswith('obs')


# Delte plasseringer (sone) – flere pasienter kan være her samtidig.
# Alle andre plasseringer er unike (bare én aktiv pasient om gangen).
SHARED_PLASSERINGER = {'Grønn sone', 'Gul sone'}


def is_shared_plassering(plassering):
    """True hvis plasseringen kan romme flere pasienter samtidig."""
    return (plassering or '').strip() in SHARED_PLASSERINGER


def find_plassering_conflict(plassering, year, exclude_pk=None):
    """Returner en konkurrerende aktiv pasient i samme plassering, eller None.

    Delte soner (Grønn/Gul sone) gir aldri konflikt.
    Blank plassering gir aldri konflikt.
    Utskrevne pasienter (utskrevet-felt satt) blokkerer ikke plasseringen.
    Soft-deletede pasienter (is_active=False) blokkerer heller ikke.
    Brukes for både create (exclude_pk=None) og update (exclude_pk=patient.pk).
    """
    p = (plassering or '').strip()
    if not p or is_shared_plassering(p):
        return None
    qs = Patient.objects.filter(
        is_active=True,
        year=year,
        plassering=p,
        utskrevet='',  # Kun ikke-utskrevne pasienter blokkerer plasseringen
    )
    if exclude_pk is not None:
        qs = qs.exclude(pk=exclude_pk)
    return qs.first()


def validate_plassering_unique(plassering, year, exclude_pk=None):
    """Hev ValidationError hvis plasseringen er opptatt av en annen aktiv pasient.

    Delte soner (Grønn/Gul sone) og blank plassering tillates alltid.
    Kalles før Patient.save() både ved opprettelse og oppdatering.
    """
    from django.core.exceptions import ValidationError
    conflict = find_plassering_conflict(plassering, year, exclude_pk=exclude_pk)
    if conflict is not None:
        raise ValidationError(
            f"Plasseringen '{plassering}' er allerede opptatt av pasient #"
            f"{conflict.pasientnummer}. Velg en annen plassering."
        )


def stamp_obs_times_if_needed(patient, old_plassering, updates):
    """Tidsstempel for obspost-overganger.

    - Hvis plassering settes til en obs-plassering og inn_obspost er tom:
      stempel inn_obspost = nå.
    - Hvis plassering endres FRA obs til noe annet og ut_obspost er tom:
      stempel ut_obspost = nå.

    Muterer patient in-place. Kaller ikke save() – kaller må gjøre det.
    Returnerer liste over endrede feltnavn.
    """
    now_str = updates.get('_now_str') or now_local_str()
    new_plassering = patient.plassering or ''

    was_obs = _is_obs_location(old_plassering)
    is_obs = _is_obs_location(new_plassering)

    changed = []

    # Inn obspost: nå obs, og inn_obspost er fremdeles tom
    if is_obs and not (patient.inn_obspost or '').strip():
        patient.inn_obspost = now_str
        changed.append('inn_obspost')

    # Ut obspost: var obs, nå ikke obs, og ut_obspost er tom
    if was_obs and not is_obs and not (patient.ut_obspost or '').strip():
        patient.ut_obspost = now_str
        changed.append('ut_obspost')

    return changed


def stamp_utskrevet_if_needed(patient, updates):
    """Tidsstempel utskrevet hvis utskrevet_til settes og utskrevet er tom.

    Dessuten: hvis pasienten fremdeles står i obs når hen utskrives,
    lukk obs-perioden (sett ut_obspost).
    Kaller ikke save().
    """
    now_str = updates.get('_now_str') or now_local_str()
    changed = []

    utskrevet_til = (patient.utskrevet_til or '').strip()
    utskrevet_tid = (patient.utskrevet or '').strip()

    if utskrevet_til and not utskrevet_tid:
        patient.utskrevet = now_str
        changed.append('utskrevet')

        # Hvis pasienten fremdeles er i obs, lukk obs-perioden
        if _is_obs_location(patient.plassering) and not (patient.ut_obspost or '').strip():
            patient.ut_obspost = now_str
            changed.append('ut_obspost')

    return changed


# ── Basis-statistikk (tilsvarer /api/stats) ──────────────────────────────────

def _compute_stats_from_dicts(pts):
    """Intern hjelpe-funksjon: beregn basis-statistikk fra en list-of-dicts.

    Brukes av både basic_stats (Patient.values()) og compute_arkiv_stats
    (ArkivertPasient.values()). Feltnavn må matche de som finnes i både
    Patient og ArkivertPasient.
    """
    total = len(pts)

    tilstede = sum(1 for p in pts if not p['utskrevet'])
    utskrevet_count = total - tilstede
    pagaende = sum(1 for p in pts if p.get('pabegynt') and not p['utskrevet'])
    ventende = sum(1 for p in pts if p.get('grovsortering') and not p.get('pabegynt') and not p['utskrevet'])
    i_obs = sum(1 for p in pts if p.get('inn_obspost') and not p.get('ut_obspost') and not p['utskrevet'])

    gronn = sum(1 for p in pts if p['grovsortering'] == 'Grønn')
    gul = sum(1 for p in pts if p['grovsortering'] == 'Gul')
    rod = sum(1 for p in pts if p['grovsortering'] == 'Rød')

    tilstede_gronn = sum(1 for p in pts if p['grovsortering'] == 'Grønn' and not p['utskrevet'])
    tilstede_gul = sum(1 for p in pts if p['grovsortering'] == 'Gul' and not p['utskrevet'])
    tilstede_rod = sum(1 for p in pts if p['grovsortering'] == 'Rød' and not p['utskrevet'])

    def group(src, field):
        d = {}
        for p in src:
            v = p.get(field) or 'Ukjent'
            d[v] = d.get(v, 0) + 1
        return d

    transport_counts = group(pts, 'transport')
    utskrevet_til_counts = group([p for p in pts if p['utskrevet']], 'utskrevet_til')

    prob_counts = group(pts, 'problemstilling')
    prob_counts.pop('', None)
    prob_counts.pop('Ukjent', None)
    top_probs = sorted(prob_counts.items(), key=lambda x: x[1], reverse=True)[:12]

    arrivals = {}
    for p in pts:
        if p.get('inntid'):
            for fmt in ('%d.%m.%Y %H:%M', '%Y-%m-%dT%H:%M'):
                try:
                    dt = datetime.strptime(p['inntid'].strip(), fmt)
                    key = dt.strftime('%d.%m %H:00')
                    arrivals[key] = arrivals.get(key, 0) + 1
                    break
                except ValueError:
                    continue
    arrivals_sorted = dict(sorted(arrivals.items()))

    def avg(lst):
        return round(sum(lst) / len(lst), 0) if lst else 0

    wait_times = [
        m for p in pts
        if p.get('inntid') and p.get('pabegynt')
        for m in [parse_minutes(p['inntid'], p['pabegynt'])]
        if m is not None
    ]
    obs_times = [
        m for p in pts
        if p.get('inn_obspost') and p.get('ut_obspost')
        for m in [parse_minutes(p['inn_obspost'], p['ut_obspost'])]
        if m is not None
    ]
    total_times = [
        m for p in pts
        if p.get('inntid') and p.get('utskrevet')
        for m in [parse_minutes(p['inntid'], p['utskrevet'])]
        if m is not None
    ]

    return {
        'total': total,
        'tilstede': tilstede,
        'utskrevet': utskrevet_count,
        'pagaende': pagaende,
        'ventende': ventende,
        'i_obs': i_obs,
        'gronn': gronn,
        'gul': gul,
        'rod': rod,
        'tilstede_gronn': tilstede_gronn,
        'tilstede_gul': tilstede_gul,
        'tilstede_rod': tilstede_rod,
        'transport_counts': transport_counts,
        'utskrevet_til_counts': utskrevet_til_counts,
        'top_problems': [{'problem': k, 'count': v} for k, v in top_probs],
        'arrivals_by_hour': arrivals_sorted,
        'avg_wait_min': avg(wait_times),
        'avg_obs_min': avg(obs_times),
        'avg_total_min': avg(total_times),
    }


def basic_stats(year=None):
    """
    Beregn basis-statistikk for header-chips.
    Tilsvarer Flask /api/stats-endepunktet.
    Filtrerer på aktivt år hvis year ikke er oppgitt.
    """
    if year is None:
        year = get_active_year()
    pts = list(Patient.objects.filter(is_active=True, year=year).values())
    return _compute_stats_from_dicts(pts)


# ── Full statistikk (tilsvarer /api/full-stats) ───────────────────────────────

def full_stats(year=None):
    """
    Beregn fullstendig statistikk-dashboard for aktivt år.
    Tilsvarer Flask /api/full-stats-endepunktet.
    Inkluderer Chi-square og Kruskal-Wallis tester via scipy.
    Filtrerer på aktivt år hvis year ikke er oppgitt.
    """
    if year is None:
        year = get_active_year()
    pts = list(Patient.objects.filter(is_active=True, year=year).values())
    return _compute_full_stats_from_dicts(pts)


def _compute_full_stats_from_dicts(pts):
    """Felles full-statistikk-logikk som virker på både Patient og ArkivertPasient.

    Tar en liste av dicts (fra .values()) og returnerer samme struktur som
    full_stats. Refaktorert ut slik at arkiverte vakter får samme analyse
    som aktive vakter.
    """
    try:
        from scipy.stats import chi2_contingency, kruskal
        HAS_SCIPY = True
    except ImportError:
        HAS_SCIPY = False

    total = len(pts)

    # ── Sammendragstall ──────────────────────────────────────────────────────
    tilstede = sum(1 for p in pts if not p['utskrevet'])
    utskrevet = total - tilstede
    i_obs = sum(1 for p in pts if p['inn_obspost'] and not p['ut_obspost'] and not p['utskrevet'])
    rod = sum(1 for p in pts if p['grovsortering'] == 'Rød')
    gul = sum(1 for p in pts if p['grovsortering'] == 'Gul')
    gronn = sum(1 for p in pts if p['grovsortering'] == 'Grønn')
    total_obs_count = sum(1 for p in pts if p['inn_obspost'])

    # ── Tidsstatistikk-hjelpefunksjon ────────────────────────────────────────
    def sd(lst):
        if not lst:
            return {'n': 0, 'mean': None, 'median': None, 'min': None, 'max': None}
        return {
            'n': len(lst),
            'mean': round(smod.mean(lst), 1),
            'median': round(smod.median(lst), 1),
            'min': round(min(lst), 1),
            'max': round(max(lst), 1),
        }

    def collect_times(f1, f2):
        res = []
        for p in pts:
            v1 = p.get(f1) or ''
            v2 = p.get(f2) or ''
            t = parse_minutes(v1, v2)
            if t is not None:
                res.append(t)
        return res

    total_times = collect_times('inntid', 'utskrevet')
    wait_times = collect_times('inntid', 'pabegynt')
    obs_times = collect_times('inn_obspost', 'ut_obspost')

    # ── Tid gruppert etter felt ──────────────────────────────────────────────
    def group_times(field, f1='inntid', f2='utskrevet'):
        d = {}
        for p in pts:
            key = p.get(field) or ''
            if not key:
                continue
            t = parse_minutes(p.get(f1, '') or '', p.get(f2, '') or '')
            if t is not None:
                d.setdefault(key, []).append(t)
        return d

    triage_times = group_times('grovsortering')
    problem_times = group_times('problemstilling')
    transport_times = group_times('transport')

    time_per_triage = {k: sd(v) for k, v in triage_times.items()}
    time_per_problem = dict(
        sorted(
            {k: sd(v) for k, v in problem_times.items()}.items(),
            key=lambda x: x[1]['mean'] or 0,
            reverse=True,
        )
    )
    time_per_transport = {k: sd(v) for k, v in transport_times.items()}

    # ── Telling ──────────────────────────────────────────────────────────────
    def count_field(field, only_discharged=False):
        d = {}
        src = [p for p in pts if p['utskrevet']] if only_discharged else pts
        for p in src:
            v = p.get(field) or ''
            if v:
                d[v] = d.get(v, 0) + 1
        return d

    transport_counts = count_field('transport')
    utfall_counts = count_field('utskrevet_til', only_discharged=True)
    prob_counts = count_field('problemstilling')

    # ── Ankomster per time ────────────────────────────────────────────────────
    arrivals = {}
    for p in pts:
        if p['inntid']:
            for fmt in ('%d.%m.%Y %H:%M', '%Y-%m-%dT%H:%M'):
                try:
                    dt = datetime.strptime(p['inntid'].strip(), fmt)
                    key = dt.strftime('%H:00')
                    arrivals[key] = arrivals.get(key, 0) + 1
                    break
                except ValueError:
                    continue
    arrivals = dict(sorted(arrivals.items()))

    # ── Krysstabeller ────────────────────────────────────────────────────────
    def crosstab(f1, f2, col_order=None):
        counts = {}
        rows_set, cols_set = set(), set()
        for p in pts:
            r = p.get(f1) or ''
            c = p.get(f2) or ''
            if r and c:
                counts.setdefault(r, {})
                counts[r][c] = counts[r].get(c, 0) + 1
                rows_set.add(r)
                cols_set.add(c)
        if col_order:
            cols = [c for c in col_order if c in cols_set] + \
                   sorted(c for c in cols_set if c not in col_order)
        else:
            cols = sorted(cols_set)
        rows = sorted(rows_set)
        return counts, rows, cols

    TRIAGE_ORDER = ['Rød', 'Gul', 'Grønn']
    ct_pt = crosstab('problemstilling', 'grovsortering', col_order=TRIAGE_ORDER)
    ct_tt = crosstab('grovsortering', 'transport', col_order=TRIAGE_ORDER)
    ct_pu = crosstab('problemstilling', 'utskrevet_til')

    # ── Chi-square tester ─────────────────────────────────────────────────────
    def chi2_test(counts, rows, cols):
        if not rows or not cols or not HAS_SCIPY:
            return None
        from scipy.stats import chi2_contingency
        raw = [[counts.get(r, {}).get(c, 0) for c in cols] for r in rows]
        col_sums = [sum(raw[i][j] for i in range(len(raw))) for j in range(len(cols))]
        valid_j = [j for j, s in enumerate(col_sums) if s > 0]
        matrix = [[row[j] for j in valid_j] for row in raw if sum(row) > 0]
        if len(matrix) < 2 or (matrix and len(matrix[0]) < 2):
            return None
        try:
            chi2_val, p, dof, _ = chi2_contingency(matrix)
            return {
                'chi2': round(float(chi2_val), 2),
                'p': round(float(p), 4),
                'dof': int(dof),
                'sig': bool(p < 0.05),
            }
        except Exception:
            return None

    # Chi2: obspost × triage
    obs_ct = {}
    for p in pts:
        g = p.get('grovsortering') or ''
        if not g:
            continue
        obs_ct.setdefault(g, {'Ja': 0, 'Nei': 0})
        if p['inn_obspost']:
            obs_ct[g]['Ja'] += 1
        else:
            obs_ct[g]['Nei'] += 1
    obs_chi2 = chi2_test(obs_ct, list(obs_ct.keys()), ['Ja', 'Nei'])

    chi2_results = {
        'prob_triage': chi2_test(*ct_pt),
        'triage_transport': chi2_test(*ct_tt),
        'prob_utfall': chi2_test(*ct_pu),
        'obs_triage': obs_chi2,
    }

    # ── Kruskal-Wallis tester ─────────────────────────────────────────────────
    def kw_test(groups):
        if not HAS_SCIPY:
            return None
        from scipy.stats import kruskal
        grps = [v for v in groups.values() if len(v) >= 2]
        if len(grps) < 2:
            return None
        try:
            stat, p = kruskal(*grps)
            return {'H': round(float(stat), 2), 'p': round(float(p), 4), 'sig': bool(p < 0.05)}
        except Exception:
            return None

    # ── Obspost-statistikk per gruppe ─────────────────────────────────────────
    def obs_per_group(field):
        d = {}
        for p in pts:
            key = p.get(field) or ''
            if not key:
                continue
            has_obs = bool(p['inn_obspost'])
            ot = parse_minutes(p.get('inn_obspost', '') or '', p.get('ut_obspost', '') or '')
            entry = d.setdefault(key, {'n': 0, 'med_obs': 0, 'times': []})
            entry['n'] += 1
            if has_obs:
                entry['med_obs'] += 1
            if ot is not None:
                entry['times'].append(ot)
        result = {}
        for k, v in d.items():
            pct = round(v['med_obs'] / v['n'] * 100, 1) if v['n'] > 0 else 0.0
            avg_t = None
            if v['times']:
                avg_t = round(smod.mean(v['times']), 1)
            result[k] = {
                'n': v['n'],
                'med_obs': v['med_obs'],
                'pct': pct,
                'avg_obs_min': avg_t,
            }
        return result

    return {
        'summary': {
            'total': total,
            'tilstede': tilstede,
            'utskrevet': utskrevet,
            'rod': rod,
            'gul': gul,
            'gronn': gronn,
            'i_obs': i_obs,
            'total_obs_count': total_obs_count,
            'total_time': sd(total_times),
            'wait_time': sd(wait_times),
            'obs_time': sd(obs_times),
        },
        'arrivals': arrivals,
        'transport_counts': transport_counts,
        'utfall_counts': utfall_counts,
        'prob_counts': prob_counts,
        'time_per_triage': time_per_triage,
        'time_per_problem': time_per_problem,
        'time_per_transport': time_per_transport,
        'crosstab_prob_triage': {
            'counts': ct_pt[0], 'rows': ct_pt[1], 'cols': ct_pt[2],
            'chi2': chi2_results['prob_triage'],
        },
        'crosstab_triage_transport': {
            'counts': ct_tt[0], 'rows': ct_tt[1], 'cols': ct_tt[2],
            'chi2': chi2_results['triage_transport'],
        },
        'crosstab_prob_utfall': {
            'counts': ct_pu[0], 'rows': ct_pu[1], 'cols': ct_pu[2],
            'chi2': chi2_results['prob_utfall'],
        },
        'obs_per_triage': obs_per_group('grovsortering'),
        'obs_per_problem': obs_per_group('problemstilling'),
        'chi2_table': [
            {'test': 'Problemstilling × Grovsortering', 'result': chi2_results['prob_triage']},
            {'test': 'Grovsortering × Transport', 'result': chi2_results['triage_transport']},
            {'test': 'Problemstilling × Utfall', 'result': chi2_results['prob_utfall']},
            {'test': 'Grovsortering × Obspost-bruk', 'result': chi2_results['obs_triage']},
        ],
        'kw_triage': kw_test(triage_times),
        'kw_problem': kw_test(problem_times),
        'kw_transport': kw_test(transport_times),
    }


# ── VaktArkiv-tjenester ───────────────────────────────────────────────────────

import hashlib
import json as _json_mod


def _compute_sha256_for_arkiv(arkiv, pasienter_dicts):
    """Beregn SHA-256 over kanonisk JSON av arkivdata."""
    payload = {
        'arkiv_id': arkiv.pk,
        'arrangement_navn': arkiv.arrangement_navn,
        'year_snapshot': arkiv.year_snapshot,
        'pasienter': sorted(pasienter_dicts, key=lambda p: p['pasientnummer']),
    }
    canonical = _json_mod.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()


def arkiver_aktiv_vakt(arrangement_navn, notat, user):
    """Lag VaktArkiv + ArkivertPasient-rader fra alle aktive pasienter i aktivt år.

    Returnerer (VaktArkiv-instance, antall_pasienter).
    Ruller tilbake hele transaksjonen ved feil.
    """
    from django.utils import timezone as djtz

    with transaction.atomic():
        active_year = get_active_year()
        pasienter = list(
            Patient.objects.filter(is_active=True, year=active_year)
            .select_related('behandler', 'helsepersonell_ref')
        )
        antall = len(pasienter)

        now_local = djtz.localtime(djtz.now())
        tittel = f"{arrangement_navn} — arkivert {now_local.strftime('%d.%m.%Y %H:%M')}"

        arkiv = VaktArkiv.objects.create(
            tittel=tittel,
            arrangement_navn=arrangement_navn,
            importert_av=user,
            antall_pasienter=antall,
            year_snapshot=active_year,
            notat=notat or '',
            sha256='',  # settes etter bulk_create
        )

        arkivert_rader = []
        for p in pasienter:
            arkivert_rader.append(ArkivertPasient(
                arkiv=arkiv,
                pasientnummer=p.pasientnummer,
                problemstilling=p.problemstilling or '',
                arsak=p.arsak or '',
                transport=p.transport or '',
                grovsortering=p.grovsortering or '',
                plassering=p.plassering or '',
                inntid=p.inntid or '',
                pabegynt=p.pabegynt or '',
                inn_obspost=p.inn_obspost or '',
                ut_obspost=p.ut_obspost or '',
                utskrevet=p.utskrevet or '',
                utskrevet_til=p.utskrevet_til or '',
                behandler_navn=p.behandler.name if p.behandler else '',
                helsepersonell_navn=p.helsepersonell_ref.name if p.helsepersonell_ref else '',
                lege=p.lege or '',
                medisiner=p.medisiner or '',
                journal=p.journal or '',
            ))

        ArkivertPasient.objects.bulk_create(arkivert_rader)

        # Beregn SHA-256 etter at radene er opprettet
        pasienter_dicts = list(
            ArkivertPasient.objects.filter(arkiv=arkiv).values(
                'pasientnummer', 'problemstilling', 'arsak', 'transport',
                'grovsortering', 'plassering', 'inntid', 'pabegynt',
                'inn_obspost', 'ut_obspost', 'utskrevet', 'utskrevet_til',
                'behandler_navn', 'helsepersonell_navn', 'lege', 'medisiner', 'journal',
            )
        )
        sha = _compute_sha256_for_arkiv(arkiv, pasienter_dicts)
        arkiv.sha256 = sha
        arkiv.save(update_fields=['sha256'])

        return arkiv, antall


def _arkiv_pasienter_dicts(arkiv):
    """Hent alle arkiverte pasienter som dicts — felles helper for stats-funksjoner."""
    return list(
        ArkivertPasient.objects.filter(arkiv=arkiv).values(
            'pasientnummer', 'problemstilling', 'arsak', 'transport',
            'grovsortering', 'plassering', 'inntid', 'pabegynt',
            'inn_obspost', 'ut_obspost', 'utskrevet', 'utskrevet_til',
            'behandler_navn', 'helsepersonell_navn', 'lege', 'medisiner', 'journal',
        )
    )


def compute_arkiv_stats(arkiv):
    """Beregn basis-statistikk fra ArkivertPasient (samme nøkler som basic_stats).

    Brukes for header-chips og enkle visninger.
    """
    return _compute_stats_from_dicts(_arkiv_pasienter_dicts(arkiv))


def compute_arkiv_full_stats(arkiv):
    """Beregn full statistikk-dashboard fra ArkivertPasient.

    Returnerer samme struktur som full_stats(): summary, krysstabeller,
    Chi-square og Kruskal-Wallis-tester, tids-statistikk pr. gruppe osv.
    Gjør at arkiverte vakter kan analyseres med samme verktøy som aktive.
    """
    return _compute_full_stats_from_dicts(_arkiv_pasienter_dicts(arkiv))
