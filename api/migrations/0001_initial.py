import django.contrib.auth.models
import django.contrib.auth.validators
import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        # ------------------------------------------------------------------ #
        # CustomUser
        # ------------------------------------------------------------------ #
        migrations.CreateModel(
            name="CustomUser",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("password", models.CharField(max_length=128, verbose_name="password")),
                ("last_login", models.DateTimeField(blank=True, null=True, verbose_name="last login")),
                ("is_superuser", models.BooleanField(default=False, verbose_name="superuser status")),
                ("username", models.CharField(error_messages={"unique": "A user with that username already exists."}, max_length=150, unique=True, validators=[django.contrib.auth.validators.UnicodeUsernameValidator()], verbose_name="username")),
                ("first_name", models.CharField(blank=True, max_length=150, verbose_name="first name")),
                ("last_name", models.CharField(blank=True, max_length=150, verbose_name="last name")),
                ("email", models.EmailField(blank=True, max_length=254, verbose_name="email address")),
                ("is_staff", models.BooleanField(default=False, verbose_name="staff status")),
                ("is_active", models.BooleanField(default=True, verbose_name="active")),
                ("date_joined", models.DateTimeField(default=django.utils.timezone.now, verbose_name="date joined")),
                ("cpf", models.CharField(blank=True, max_length=14, null=True, unique=True)),
                ("data_nascimento", models.DateField(blank=True, null=True)),
                ("phone", models.CharField(blank=True, max_length=20, null=True)),
                ("profile_image", models.ImageField(blank=True, null=True, upload_to="profile_pics/")),
                ("receber_anotacoes_compartilhadas", models.BooleanField(default=True, help_text="Permite que outros usuários compartilhem anotações com este usuário.", verbose_name="Receber anotações compartilhadas")),
                ("groups", models.ManyToManyField(blank=True, related_name="customuser_groups", to="auth.group")),
                ("user_permissions", models.ManyToManyField(blank=True, related_name="customuser_permissions", to="auth.permission")),
            ],
            options={
                "verbose_name": "user",
                "verbose_name_plural": "users",
                "abstract": False,
            },
            managers=[
                ("objects", django.contrib.auth.models.UserManager()),
            ],
        ),
        # ------------------------------------------------------------------ #
        # Entidade
        # ------------------------------------------------------------------ #
        migrations.CreateModel(
            name="Entidade",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("nome", models.CharField(max_length=200, unique=True)),
                ("cnpj", models.CharField(blank=True, max_length=18, null=True, unique=True)),
                ("ano", models.IntegerField(default=django.utils.timezone.now().year, verbose_name="Ano de Exercício")),
            ],
            options={"ordering": ["nome"]},
        ),
        # ------------------------------------------------------------------ #
        # CustomUser.entidades M2M
        # ------------------------------------------------------------------ #
        migrations.AddField(
            model_name="customuser",
            name="entidades",
            field=models.ManyToManyField(blank=True, help_text="Entidades às quais o usuário pertence.", related_name="usuarios", to="api.entidade", verbose_name="Entidades vinculadas"),
        ),
        migrations.AddField(
            model_name="customuser",
            name="usuarios_bloqueados",
            field=models.ManyToManyField(blank=True, help_text="Usuários bloqueados não podem compartilhar anotações.", related_name="bloqueado_por", symmetrical=False, to=settings.AUTH_USER_MODEL, verbose_name="Usuários bloqueados"),
        ),
        # ------------------------------------------------------------------ #
        # Orgao
        # ------------------------------------------------------------------ #
        migrations.CreateModel(
            name="Orgao",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("nome", models.CharField(max_length=255)),
                ("codigo_unidade", models.CharField(blank=True, help_text="Código da Unidade Compradora (ex.: 1010)", max_length=32, null=True)),
                ("entidade", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="orgaos", to="api.entidade")),
            ],
            options={"ordering": ["nome"]},
        ),
        # ------------------------------------------------------------------ #
        # ProcessoLicitatorio
        # ------------------------------------------------------------------ #
        migrations.CreateModel(
            name="ProcessoLicitatorio",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("numero_processo", models.CharField(blank=True, max_length=50, null=True)),
                ("numero_certame", models.CharField(blank=True, max_length=50, null=True)),
                ("objeto", models.TextField(blank=True, null=True)),
                ("modalidade", models.IntegerField(
                    blank=True,
                    choices=[(6,"Pregão - Eletrônico"),(4,"Concorrência - Eletrônica"),(8,"Dispensa de Licitação"),(9,"Inexigibilidade"),(11,"Pré-Qualificação"),(12,"Credenciamento")],
                    db_index=True, null=True, verbose_name="Modalidade (ID)")),
                ("classificacao", models.CharField(blank=True, max_length=50, null=True)),
                ("tipo_organizacao", models.CharField(
                    blank=True,
                    choices=[("O","Órgão"),("E","Entidade")],
                    max_length=10)),
                ("situacao", models.CharField(
                    blank=True,
                    choices=[("em_pesquisa","Em Pesquisa"),("em_andamento","Em Andamento"),("homologado","Homologado"),("cancelado","Cancelado"),("suspenso","Suspenso"),("revogado","Revogado"),("anulado","Anulado"),("concluido","Concluído")],
                    db_index=True, default="em_pesquisa", max_length=50)),
                ("data_processo", models.DateField(blank=True, null=True)),
                ("data_abertura", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("valor_referencia", models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True)),
                ("vigencia_meses", models.PositiveIntegerField(blank=True, null=True)),
                ("registro_preco", models.BooleanField(blank=True, default=False, verbose_name="Registro de Preço")),
                ("data_criacao_sistema", models.DateTimeField(auto_now_add=True)),
                ("instrumento_convocatorio", models.IntegerField(
                    blank=True,
                    choices=[(1,"Edital"),(2,"Aviso de Contratação Direta"),(3,"Ato que autoriza a Contratação Direta"),(4,"Edital de Chamamento Público")],
                    null=True, verbose_name="Instrumento Convocatório (ID)")),
                ("amparo_legal", models.IntegerField(blank=True, null=True, verbose_name="Amparo Legal (ID)")),
                ("modo_disputa", models.IntegerField(
                    blank=True,
                    choices=[(1,"Aberto"),(2,"Fechado"),(3,"Aberto-Fechado"),(4,"Dispensa com Disputa"),(5,"Não se aplica"),(6,"Fechado-Aberto")],
                    null=True, verbose_name="Modo de Disputa (ID)")),
                ("criterio_julgamento", models.IntegerField(
                    blank=True,
                    choices=[(1,"Menor preço"),(2,"Maior desconto"),(3,"Melhor técnica ou conteúdo artístico"),(4,"Técnica e preço"),(5,"Maior lance"),(6,"Maior retorno econômico"),(7,"Não se aplica"),(8,"Melhor técnica"),(9,"Conteúdo artístico")],
                    null=True, verbose_name="Critério de Julgamento (ID)")),
                ("fundamentacao", models.CharField(blank=True, help_text="Campo legado.", max_length=50, null=True)),
                ("pncp_publicado_em", models.DateTimeField(blank=True, null=True)),
                ("pncp_ano_compra", models.PositiveIntegerField(blank=True, null=True)),
                ("pncp_sequencial_compra", models.PositiveIntegerField(blank=True, null=True)),
                ("pncp_link", models.URLField(blank=True, null=True)),
                ("pncp_ultimo_retorno", models.JSONField(blank=True, null=True)),
                ("entidade", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="processos", to="api.entidade")),
                ("orgao", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="processos", to="api.orgao")),
            ],
            options={
                "verbose_name": "Processo Licitatório",
                "verbose_name_plural": "Processos Licitatórios",
                "ordering": ["-data_processo"],
            },
        ),
        # ------------------------------------------------------------------ #
        # DocumentoPNCP  (sem linha_documento; com constraint antiga)
        # ------------------------------------------------------------------ #
        migrations.CreateModel(
            name="DocumentoPNCP",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("tipo_documento_id", models.PositiveIntegerField()),
                ("titulo", models.CharField(default="Documento", max_length=255)),
                ("observacao", models.TextField(blank=True, null=True)),
                ("arquivo", models.FileField(upload_to="documentos_pncp/")),
                ("arquivo_nome", models.CharField(blank=True, max_length=255, null=True)),
                ("arquivo_hash", models.CharField(blank=True, max_length=80, null=True)),
                ("status", models.CharField(
                    choices=[("rascunho","Rascunho (local)"),("enviado","Enviado ao PNCP"),("erro","Erro no envio"),("removido","Removido")],
                    default="rascunho", max_length=20)),
                ("pncp_sequencial_documento", models.PositiveIntegerField(blank=True, null=True)),
                ("pncp_publicado_em", models.DateTimeField(blank=True, null=True)),
                ("ativo", models.BooleanField(default=True)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("processo", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="docs_pncp", to="api.processolicitatorio")),
            ],
        ),
        migrations.AddConstraint(
            model_name="documentopncp",
            constraint=models.UniqueConstraint(
                condition=models.Q(ativo=True) & ~models.Q(status="removido"),
                fields=("processo", "tipo_documento_id"),
                name="uniq_docpncp_processo_tipo_ativo",
            ),
        ),
        # ------------------------------------------------------------------ #
        # Lote
        # ------------------------------------------------------------------ #
        migrations.CreateModel(
            name="Lote",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("numero", models.PositiveIntegerField()),
                ("descricao", models.TextField(blank=True, null=True)),
                ("processo", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="lotes", to="api.processolicitatorio")),
            ],
            options={"ordering": ["numero"]},
        ),
        migrations.AddConstraint(
            model_name="lote",
            constraint=models.UniqueConstraint(fields=["processo", "numero"], name="uniq_lote_processo_numero"),
        ),
        # ------------------------------------------------------------------ #
        # Fornecedor
        # ------------------------------------------------------------------ #
        migrations.CreateModel(
            name="Fornecedor",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("cnpj", models.CharField(max_length=18, unique=True)),
                ("razao_social", models.CharField(max_length=255)),
                ("nome_fantasia", models.CharField(blank=True, max_length=255, null=True)),
                ("porte", models.CharField(blank=True, max_length=100, null=True)),
                ("telefone", models.CharField(blank=True, max_length=20, null=True)),
                ("email", models.EmailField(blank=True, null=True)),
                ("cep", models.CharField(blank=True, max_length=20, null=True)),
                ("logradouro", models.CharField(blank=True, max_length=255, null=True)),
                ("numero", models.CharField(blank=True, max_length=50, null=True)),
                ("bairro", models.CharField(blank=True, max_length=100, null=True)),
                ("complemento", models.CharField(blank=True, max_length=255, null=True)),
                ("uf", models.CharField(blank=True, max_length=2, null=True)),
                ("municipio", models.CharField(blank=True, max_length=100, null=True)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
            ],
            options={"ordering": ["razao_social"]},
        ),
        # ------------------------------------------------------------------ #
        # Item  (sem valor_homologado — adicionado em 0004)
        # ------------------------------------------------------------------ #
        migrations.CreateModel(
            name="Item",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("descricao", models.CharField(max_length=255)),
                ("especificacao", models.TextField(blank=True, help_text="Especificação detalhada do item.", null=True)),
                ("unidade", models.CharField(max_length=20)),
                ("quantidade", models.DecimalField(decimal_places=4, max_digits=12)),
                ("valor_estimado", models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True)),
                ("ordem", models.PositiveIntegerField(default=1)),
                ("natureza", models.CharField(
                    blank=True,
                    choices=[("339030","Material de Consumo"),("449052","Equipamentos e Material Permanente"),("339039","Outros Serviços de Terceiros - PJ"),("339036","Outros Serviços de Terceiros - PF"),("449051","Obras e Instalações"),("339040","Serviços de Tecnologia da Informação")],
                    max_length=8, null=True)),
                ("situacao_item", models.IntegerField(
                    choices=[(1,"Em Andamento"),(2,"Homologado"),(3,"Anulado/Revogado/Cancelado"),(4,"Deserto"),(5,"Fracassado")],
                    default=1, verbose_name="Situação do Item (ID)")),
                ("tipo_beneficio", models.IntegerField(
                    blank=True,
                    choices=[(1,"Participação exclusiva para ME/EPP"),(2,"Subcontratação para ME/EPP"),(3,"Cota reservada para ME/EPP"),(4,"Sem benefício"),(5,"Não se aplica")],
                    null=True, verbose_name="Tipo de Benefício (ID)")),
                ("categoria_item", models.IntegerField(
                    blank=True,
                    choices=[(1,"Material"),(2,"Serviço"),(3,"Obra"),(4,"Serviços de Engenharia"),(5,"Soluções de TIC"),(6,"Locação de Imóveis"),(7,"Alienação/Concessão/Permissão"),(8,"Obras e Serviços de Engenharia")],
                    null=True, verbose_name="Categoria do Item (ID)")),
                ("pncp_numero_item", models.PositiveIntegerField(blank=True, null=True)),
                ("pncp_ultima_atualizacao", models.DateTimeField(blank=True, null=True)),
                ("processo", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="itens", to="api.processolicitatorio")),
                ("lote", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="itens", to="api.lote")),
                ("fornecedor", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="itens", to="api.fornecedor")),
            ],
            options={"ordering": ["ordem"]},
        ),
        migrations.AddConstraint(
            model_name="item",
            constraint=models.UniqueConstraint(fields=["processo", "ordem"], name="uniq_item_processo_ordem"),
        ),
        # ------------------------------------------------------------------ #
        # FornecedorProcesso
        # ------------------------------------------------------------------ #
        migrations.CreateModel(
            name="FornecedorProcesso",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("data_participacao", models.DateField(auto_now_add=True)),
                ("habilitado", models.BooleanField(default=True)),
                ("processo", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="fornecedores_processo", to="api.processolicitatorio")),
                ("fornecedor", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="processos", to="api.fornecedor")),
            ],
            options={
                "verbose_name": "Fornecedor do Processo",
                "verbose_name_plural": "Fornecedores do Processo",
                "unique_together": {("processo", "fornecedor")},
            },
        ),
        # ------------------------------------------------------------------ #
        # ItemFornecedor
        # ------------------------------------------------------------------ #
        migrations.CreateModel(
            name="ItemFornecedor",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("valor_proposto", models.DecimalField(decimal_places=2, max_digits=14)),
                ("vencedor", models.BooleanField(default=False)),
                ("item", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="propostas", to="api.item")),
                ("fornecedor", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="propostas", to="api.fornecedor")),
            ],
            options={
                "verbose_name": "Proposta de Fornecedor",
                "verbose_name_plural": "Propostas de Fornecedores",
                "unique_together": {("item", "fornecedor")},
            },
        ),
        # ------------------------------------------------------------------ #
        # ContratoEmpenho  (sem os campos adicionados em 0007; com sequencial_publicacao)
        # ------------------------------------------------------------------ #
        migrations.CreateModel(
            name="ContratoEmpenho",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("tipo_contrato_id", models.PositiveIntegerField()),
                ("numero_contrato_empenho", models.CharField(max_length=64)),
                ("ano_contrato", models.PositiveIntegerField()),
                ("processo_ref", models.CharField(blank=True, max_length=64, null=True)),
                ("categoria_processo_id", models.PositiveIntegerField(blank=True, null=True)),
                ("receita", models.BooleanField(default=False)),
                ("unidade_codigo", models.CharField(blank=True, max_length=32, null=True)),
                ("ni_fornecedor", models.CharField(blank=True, max_length=14, null=True)),
                ("tipo_pessoa_fornecedor", models.CharField(blank=True, max_length=2, null=True)),
                ("sequencial_publicacao", models.PositiveIntegerField(blank=True, null=True)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
                ("processo", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="contratos", to="api.processolicitatorio")),
            ],
            options={
                "verbose_name": "Contrato/Empenho",
                "verbose_name_plural": "Contratos/Empenhos",
            },
        ),
        # ------------------------------------------------------------------ #
        # Anotacao
        # ------------------------------------------------------------------ #
        migrations.CreateModel(
            name="Anotacao",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("titulo", models.CharField(blank=True, max_length=160, null=True)),
                ("texto", models.TextField()),
                ("concluida", models.BooleanField(default=False)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
                ("usuario", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="anotacoes", to=settings.AUTH_USER_MODEL)),
                ("processo", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="anotacoes", to="api.processolicitatorio")),
                ("compartilhada_com", models.ManyToManyField(blank=True, related_name="anotacoes_compartilhadas", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "Anotação",
                "verbose_name_plural": "Anotações",
                "ordering": ["-criado_em"],
            },
        ),
        # ------------------------------------------------------------------ #
        # ArquivoUser
        # ------------------------------------------------------------------ #
        migrations.CreateModel(
            name="ArquivoUser",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("arquivo", models.FileField(upload_to="arquivos-user/")),
                ("descricao", models.CharField(blank=True, max_length=255, null=True)),
                ("enviado_em", models.DateTimeField(auto_now_add=True)),
                ("usuario", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="arquivos", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "Arquivo do Usuário",
                "verbose_name_plural": "Arquivos dos Usuários",
                "ordering": ["-enviado_em"],
            },
        ),
        # ------------------------------------------------------------------ #
        # AtaRegistroPrecos  (sem possibilidade_adesao e link_pncp — adicionados em 0006)
        # ------------------------------------------------------------------ #
        migrations.CreateModel(
            name="AtaRegistroPrecos",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("numero_ata", models.CharField(max_length=50)),
                ("ano_ata", models.PositiveIntegerField()),
                ("data_assinatura", models.DateField(blank=True, null=True)),
                ("data_vigencia_inicio", models.DateField(blank=True, null=True)),
                ("data_vigencia_fim", models.DateField(blank=True, null=True)),
                ("observacao", models.TextField(blank=True, null=True)),
                ("status", models.CharField(
                    choices=[("rascunho","Rascunho (local)"),("publicada","Publicada no PNCP"),("cancelada","Cancelada")],
                    default="rascunho", max_length=20)),
                ("pncp_sequencial_ata", models.PositiveIntegerField(blank=True, null=True)),
                ("numero_controle_pncp", models.CharField(blank=True, max_length=100, null=True)),
                ("pncp_publicada_em", models.DateTimeField(blank=True, null=True)),
                ("ativo", models.BooleanField(default=True)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("processo", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="atas_registro", to="api.processolicitatorio")),
            ],
            options={
                "verbose_name": "Ata de Registro de Preços",
                "verbose_name_plural": "Atas de Registro de Preços",
                "ordering": ["-criado_em"],
            },
        ),
        # ------------------------------------------------------------------ #
        # DocumentoAtaRegistroPrecos
        # ------------------------------------------------------------------ #
        migrations.CreateModel(
            name="DocumentoAtaRegistroPrecos",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("tipo_documento_id", models.PositiveIntegerField()),
                ("titulo", models.CharField(default="Documento da Ata", max_length=255)),
                ("observacao", models.TextField(blank=True, null=True)),
                ("arquivo", models.FileField(upload_to="atas_registro_pncp/")),
                ("arquivo_nome", models.CharField(blank=True, max_length=255, null=True)),
                ("arquivo_hash", models.CharField(blank=True, max_length=80, null=True)),
                ("status", models.CharField(
                    choices=[("rascunho","Rascunho (local)"),("enviado","Enviado ao PNCP"),("erro","Erro no envio"),("removido","Removido")],
                    default="rascunho", max_length=20)),
                ("pncp_sequencial_documento", models.PositiveIntegerField(blank=True, null=True)),
                ("pncp_publicado_em", models.DateTimeField(blank=True, null=True)),
                ("ativo", models.BooleanField(default=True)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("ata", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="documentos", to="api.ataregistroprecos")),
            ],
            options={"ordering": ["-criado_em"]},
        ),
    ]
