from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0008_documentocontrato_chave_documento"),
    ]

    operations = [
        migrations.AddField(
            model_name="contratoempenho",
            name="fruto_adesao",
            field=models.BooleanField(default=False, help_text="Indica se o contrato é fruto de adesão a Ata de Registro de Preços."),
        ),
        migrations.AddField(
            model_name="contratoempenho",
            name="numero_parcelas",
            field=models.PositiveIntegerField(blank=True, null=True, help_text="Número de parcelas do pagamento."),
        ),
        migrations.AddField(
            model_name="contratoempenho",
            name="valor_parcela",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=18, null=True, help_text="Valor de cada parcela."),
        ),
    ]
