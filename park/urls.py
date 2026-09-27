"""URL-konfigurasjon for park-modulen.

Mountet på ``/park/`` i ``myproject/urls.py``, før ``core``. Navnene har
`park_`-prefiks fordi navnerommet er globalt, som i de andre modulene.

**To slags ruter, og testen skiller dem** (`park/tests.py`):

- under ``/park/`` for innloggede, gatet med ``@modul_kreves('park', …)``
- under ``/park/r/`` uten innlogging, gatet med ``@park_lenke_kreves`` — tokenet
  fra tiltakskortet (``docs/FORSLAG_PARK.md`` §4). Selve siden er statisk og
  står i unntakslista i ``patients/tests_modul_dekorator.py``.
"""
from django.urls import path

from . import views, views_lag

urlpatterns = [
    path('', views.index_view, name='park_index'),

    # Siden lagene bruker. Uten innlogging; tokenet står i fragmentet.
    path('r/', views_lag.side_view, name='park_lag_side'),
    path('r/api/oppsett/', views_lag.oppsett_view, name='park_lag_oppsett'),
    path('r/api/sted/', views_lag.sted_view, name='park_lag_sted'),
    path('r/api/registrer/', views_lag.registrer_view, name='park_lag_registrer'),
    path('r/api/angre/', views_lag.angre_view, name='park_lag_angre'),
]
