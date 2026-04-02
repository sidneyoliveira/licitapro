from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0007_contrato_pncp_documentos"),
    ]

    operations = [
        migrations.AddField(
            model_name="documentocontrato",
            name="chave_documento",
            field=models.CharField(blank=True, db_index=True, max_length=64, null=True),
        ),
    ]