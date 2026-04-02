from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0005_processo_documento_linha_e_vinculo_docpncp"),
    ]

    operations = [
        migrations.AddField(
            model_name="ataregistroprecos",
            name="possibilidade_adesao",
            field=models.BooleanField(
                default=False,
                help_text="Indicador se a Ata permite adesão de não participantes (PNCP).",
                verbose_name="Permite adesão de não participantes",
            ),
        ),
        migrations.AddField(
            model_name="ataregistroprecos",
            name="link_pncp",
            field=models.URLField(
                blank=True,
                null=True,
                help_text="URL retornada pelo PNCP (header Location) na inserção da ata.",
                verbose_name="Link no PNCP",
            ),
        ),
    ]
