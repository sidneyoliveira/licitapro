from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0003_notificacao"),
    ]

    operations = [
        migrations.AddField(
            model_name="item",
            name="valor_homologado",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Valor unitário homologado após definição do fornecedor vencedor.",
                max_digits=14,
                null=True,
            ),
        ),
    ]
