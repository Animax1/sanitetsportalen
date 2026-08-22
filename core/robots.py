"""robots.txt — holder portalen ute av søkemotorer og AI-crawlere.

Portalen er en intern fagapplikasjon. Ingenting her skal indekseres, siteres
eller brukes som treningsdata. Den reelle beskyttelsen er innloggingskravet:
alt utenom ``/healthz/`` og selve innloggingssiden redirecter til login, så en
crawler kommer aldri til pasientdata uansett hva denne fila sier.

Denne fila og ``X-Robots-Tag``-headeren (``patients/middleware.py``) løser to
ulike problemer, og trengs begge:

- **robots.txt** ber crawleren la være å hente sidene. Rent frivillig — den
  virker på Googlebot, Bingbot og de navngitte AI-botene under, og gjør
  ingenting mot en scraper som ignorerer den.
- **``X-Robots-Tag: noindex``** ber om at siden ikke *vises* i resultatene.
  Den er sterkere, fordi en side kan havne i indeksen via en ekstern lenke
  selv om den aldri ble hentet.

Merk rekkefølgen: en side som er blokkert i robots.txt kan ikke leses, og da
ser crawleren heller ikke ``noindex``-headeren. Skal en URL som *allerede* er
indeksert ut av søkeresultatene, må den derfor midlertidig tillates i
robots.txt slik at headeren kan leses. For et nytt domene som aldri har vært
indeksert er det ikke et problem.

Lista over AI-crawlere er navngitt eksplisitt fordi ``User-agent: *`` ikke
alltid respekteres av dem — flere av dem dokumenterer at de kun følger sitt
eget agent-navn.
"""
from django.http import HttpResponse
from django.views.decorators.cache import cache_control
from django.views.decorators.http import require_safe

# Navngitte crawlere som samler treningsdata eller svarer på vegne av en
# AI-tjeneste. Blokkeres i tillegg til `*`, siden flere av dem kun leser
# regler adressert til seg selv.
AI_CRAWLERS = (
    'GPTBot',              # OpenAI, treningsdata
    'OAI-SearchBot',       # OpenAI, søk
    'ChatGPT-User',        # OpenAI, henting på brukers vegne
    'ClaudeBot',           # Anthropic
    'Claude-Web',          # Anthropic
    'anthropic-ai',        # Anthropic
    'Claude-SearchBot',    # Anthropic, søk
    'CCBot',               # Common Crawl — mange modeller trener på denne
    'Google-Extended',     # Googles AI-produkter (styrer ikke vanlig søk)
    'PerplexityBot',
    'Perplexity-User',
    'Applebot-Extended',
    'Bytespider',          # ByteDance
    'Amazonbot',
    'meta-externalagent',  # Meta
    'FacebookBot',
    'cohere-ai',
    'Diffbot',
    'Omgilibot',
    'ImagesiftBot',
    'Timpibot',
    'YouBot',
)

_LINJER = [
    '# Sanitetsportalen — intern fagapplikasjon.',
    '# Ingen del av dette nettstedet skal indekseres, siteres eller brukes',
    '# som treningsdata. Alt innhold krever uansett innlogging.',
    '',
    'User-agent: *',
    'Disallow: /',
    '',
]
for _bot in AI_CRAWLERS:
    _LINJER += [f'User-agent: {_bot}', 'Disallow: /', '']

ROBOTS_TXT = '\n'.join(_LINJER)


@require_safe
@cache_control(max_age=86400)
def robots_txt(request):
    """Serverer /robots.txt. Ingen auth — den må være lesbar for å virke."""
    return HttpResponse(ROBOTS_TXT, content_type='text/plain; charset=utf-8')
