from django.db import migrations, models


class Migration(migrations.Migration):
    """`Mannskap.epost` — kontaktinfo og nøkkelen for automatisk kontokobling
    (André, 12. sep. 2026). Ren skjemaendring, ingen data flyttes."""

    dependencies = [
        ("vaktliste", "0013_vaktliste_arkivert"),
    ]

    operations = [
        migrations.AddField(
            model_name="mannskap",
            name="epost",
            field=models.EmailField(
                blank=True, default="", max_length=120, verbose_name="E-post",
                help_text="Valgfritt. Finnes en portalbruker med samme e-post, "
                          "kobles kontoen automatisk."),
        ),
    ]
