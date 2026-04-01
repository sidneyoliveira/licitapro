from django.db import migrations, models
import django.db.models.deletion


def seed_linhas(apps, schema_editor):
    DocumentoPNCP = apps.get_model("api", "DocumentoPNCP")
    ProcessoDocumentoLinha = apps.get_model("api", "ProcessoDocumentoLinha")

    docs = DocumentoPNCP.objects.all().order_by("processo_id", "criado_em", "id")
    ultima_ordem = {}

    for doc in docs:
        pid = doc.processo_id
        ordem = ultima_ordem.get(pid, 0) + 1
        ultima_ordem[pid] = ordem

        nome = (doc.titulo or "Documento").strip() or f"Documento {ordem}"

        linha = ProcessoDocumentoLinha.objects.create(
            processo_id=pid,
            nome=nome,
            tipo_documento_id=doc.tipo_documento_id,
            ordem=ordem,
            custom=True,
            ativo=True,
        )

        doc.linha_documento_id = linha.id
        doc.save(update_fields=["linha_documento"])


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0004_item_valor_homologado"),
    ]

    operations = [
        migrations.CreateModel(
            name="ProcessoDocumentoLinha",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("nome", models.CharField(max_length=255)),
                ("tipo_documento_id", models.PositiveIntegerField()),
                ("ordem", models.PositiveIntegerField(default=1)),
                ("custom", models.BooleanField(default=False)),
                ("ativo", models.BooleanField(default=True)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
                (
                    "processo",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="linhas_documentos",
                        to="api.processolicitatorio",
                    ),
                ),
            ],
            options={
                "ordering": ["ordem", "id"],
            },
        ),
        migrations.AddField(
            model_name="documentopncp",
            name="linha_documento",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="documentos_pncp", to="api.processodocumentolinha"),
        ),
        migrations.RunPython(seed_linhas, migrations.RunPython.noop),
        migrations.RemoveConstraint(
            model_name="documentopncp",
            name="uniq_docpncp_processo_tipo_ativo",
        ),
        migrations.AddConstraint(
            model_name="documentopncp",
            constraint=models.UniqueConstraint(
                condition=models.Q(ativo=True) & ~models.Q(status="removido"),
                fields=("linha_documento",),
                name="uniq_docpncp_linha_ativo",
            ),
        ),
        migrations.AddConstraint(
            model_name="processodocumentolinha",
            constraint=models.UniqueConstraint(
                condition=models.Q(ativo=True),
                fields=("processo", "ordem"),
                name="uniq_doclinha_processo_ordem_ativo",
            ),
        ),
    ]
