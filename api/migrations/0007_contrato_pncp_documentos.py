# Generated manually to support Contrato PNCP integration and contract documents.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0006_ataregistroprecos_possibilidade_adesao_link_pncp"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="contratoempenho",
            options={
                "ordering": ["-criado_em"],
                "verbose_name": "Contrato/Empenho",
                "verbose_name_plural": "Contratos/Empenhos",
            },
        ),
        migrations.RemoveField(
            model_name="contratoempenho",
            name="sequencial_publicacao",
        ),
        migrations.AddField(
            model_name="contratoempenho",
            name="ativo",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="contratoempenho",
            name="data_assinatura",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="contratoempenho",
            name="data_vigencia_fim",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="contratoempenho",
            name="data_vigencia_inicio",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="contratoempenho",
            name="link_pncp",
            field=models.URLField(
                blank=True,
                help_text="URL retornada pelo PNCP (header Location) na inserção do contrato.",
                null=True,
                verbose_name="Link no PNCP",
            ),
        ),
        migrations.AddField(
            model_name="contratoempenho",
            name="numero_controle_pncp",
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
        migrations.AddField(
            model_name="contratoempenho",
            name="objeto",
            field=models.TextField(blank=True, help_text="Objeto do contrato/empenho.", null=True),
        ),
        migrations.AddField(
            model_name="contratoempenho",
            name="pncp_publicado_em",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="contratoempenho",
            name="pncp_sequencial_contrato",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="contratoempenho",
            name="status",
            field=models.CharField(
                choices=[
                    ("rascunho", "Rascunho (local)"),
                    ("publicado", "Publicado no PNCP"),
                    ("cancelado", "Cancelado"),
                ],
                default="rascunho",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="contratoempenho",
            name="valor_global",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=18, null=True),
        ),
        migrations.AddField(
            model_name="contratoempenho",
            name="valor_inicial",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=18, null=True),
        ),
        migrations.CreateModel(
            name="DocumentoContrato",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("tipo_documento_id", models.PositiveIntegerField()),
                ("titulo", models.CharField(default="Documento do Contrato", max_length=255)),
                ("observacao", models.TextField(blank=True, null=True)),
                ("arquivo", models.FileField(upload_to="contratos_pncp/")),
                ("arquivo_nome", models.CharField(blank=True, max_length=255, null=True)),
                ("arquivo_hash", models.CharField(blank=True, max_length=80, null=True)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("rascunho", "Rascunho (local)"),
                            ("enviado", "Enviado ao PNCP"),
                            ("erro", "Erro no envio"),
                            ("removido", "Removido"),
                        ],
                        default="rascunho",
                        max_length=20,
                    ),
                ),
                ("pncp_sequencial_documento", models.PositiveIntegerField(blank=True, null=True)),
                ("pncp_publicado_em", models.DateTimeField(blank=True, null=True)),
                ("ativo", models.BooleanField(default=True)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                (
                    "contrato",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="documentos",
                        to="api.contratoempenho",
                    ),
                ),
            ],
            options={
                "verbose_name": "Documento de Contrato",
                "verbose_name_plural": "Documentos de Contratos",
                "ordering": ["-criado_em"],
            },
        ),
    ]
