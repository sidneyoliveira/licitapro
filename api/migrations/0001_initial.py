from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('api', 'ULTIMA_MIGRACAO_APLICADA'),
    ]

    operations = [
        migrations.AddField(
            model_name='fornecedor',
            name='nome_fantasia',
            field=models.CharField(max_length=255, blank=True, null=True),
        ),
        migrations.AddField(
            model_name='fornecedor',
            name='porte',
            field=models.CharField(max_length=100, blank=True, null=True),
        ),
        migrations.AddField(
            model_name='fornecedor',
            name='cep',
            field=models.CharField(max_length=20, blank=True, null=True),
        ),
        migrations.AddField(
            model_name='fornecedor',
            name='logradouro',
            field=models.CharField(max_length=255, blank=True, null=True),
        ),
        migrations.AddField(
            model_name='fornecedor',
            name='numero',
            field=models.CharField(max_length=50, blank=True, null=True),
        ),
        migrations.AddField(
            model_name='fornecedor',
            name='bairro',
            field=models.CharField(max_length=100, blank=True, null=True),
        ),
        migrations.AddField(
            model_name='fornecedor',
            name='complemento',
            field=models.CharField(max_length=255, blank=True, null=True),
        ),
        migrations.AddField(
            model_name='fornecedor',
            name='uf',
            field=models.CharField(max_length=2, blank=True, null=True),
        ),
        migrations.AddField(
            model_name='fornecedor',
            name='municipio',
            field=models.CharField(max_length=100, blank=True, null=True),
        ),
    ]
