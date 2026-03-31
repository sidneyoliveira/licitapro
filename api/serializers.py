from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import (
    CustomUser,
    Entidade,
    Orgao,
    ProcessoLicitatorio,
    Lote,
    Fornecedor,
    Item,
    FornecedorProcesso,
    ItemFornecedor,
    ContratoEmpenho,
    Anotacao,
    Notificacao,
    ArquivoUser,
    DocumentoPNCP,
    AtaRegistroPrecos,
    DocumentoAtaRegistroPrecos,
)
from .choices import (
    MAP_MODALIDADE_PNCP,
    MAP_MODO_DISPUTA_PNCP,
    MAP_INSTRUMENTO_CONVOCATORIO_PNCP,
    MAP_AMPARO_LEGAL_PNCP,
    MAP_SITUACAO_ITEM_PNCP,
    MAP_TIPO_BENEFICIO_PNCP,
    MAP_CATEGORIA_ITEM_PNCP,
    MAP_CRITERIO_JULGAMENTO_PNCP,
    MAP_INSTRUMENTO_CONVOCATORIO_PNCP,
)

User = get_user_model()


# Reutiliza o mesmo mapa de tipos que você já usa
TIPO_DOC_MAPA = {
    1: "Aviso de Contratação Direta",
    2: "Edital",
    3: "Minuta do Contrato",
    4: "Termo de Referência",
    5: "Anteprojeto",
    6: "Projeto Básico",
    7: "Estudo Técnico Preliminar",
    9: "Mapa de Riscos",
    10: "DFD",
    19: "Minuta de Ata de Registro de Preços",
    20: "Ato que autoriza a Contratação Direta",
}

# ============================================================
# 👤 USER
# ============================================================

class UserSerializer(serializers.ModelSerializer):
    entidades_nomes = serializers.SerializerMethodField()
    password = serializers.CharField(write_only=True, required=False, min_length=6)
    entidades = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=Entidade.objects.all(),
        required=False,
    )
    usuarios_bloqueados = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=CustomUser.objects.all(),
        required=False,
    )
    usuarios_bloqueados_nomes = serializers.SerializerMethodField()

    class Meta:
        model = CustomUser
        fields = (
            "id", "username", "first_name", "last_name", "email",
            "cpf", "phone", "profile_image", "data_nascimento",
            "entidades", "entidades_nomes", "password",
            "receber_anotacoes_compartilhadas", "usuarios_bloqueados", "usuarios_bloqueados_nomes",
            "is_active", "is_staff", "is_superuser",
            "date_joined", "last_login",
        )
        read_only_fields = ("date_joined", "last_login", "entidades_nomes", "usuarios_bloqueados_nomes")

    def get_entidades_nomes(self, obj):
        return [
            {"id": e.id, "nome": e.nome}
            for e in obj.entidades.all()
        ]

    def get_usuarios_bloqueados_nomes(self, obj):
        return [
            {"id": u.id, "username": u.username, "nome": (u.get_full_name() or u.username)}
            for u in obj.usuarios_bloqueados.all()
        ]

    def _is_admin_request(self):
        request = self.context.get("request")
        return bool(request and request.user and request.user.is_authenticated and request.user.is_staff)

    def create(self, validated_data):
        password = validated_data.pop("password", None)
        entidades = validated_data.pop("entidades", [])
        usuarios_bloqueados = validated_data.pop("usuarios_bloqueados", [])

        # Campos administrativos só podem ser definidos por admin
        if not self._is_admin_request():
            validated_data.pop("is_active", None)
            validated_data.pop("is_staff", None)
            validated_data.pop("is_superuser", None)
            entidades = []

        user = CustomUser(**validated_data)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save()
        if entidades:
            user.entidades.set(entidades)
        if usuarios_bloqueados:
            user.usuarios_bloqueados.set([u for u in usuarios_bloqueados if u.id != user.id])
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        entidades = validated_data.pop("entidades", None)
        usuarios_bloqueados = validated_data.pop("usuarios_bloqueados", None)

        # Se NÃO é admin, remove campos administrativos
        if not self._is_admin_request():
            for field in ("is_active", "is_staff", "is_superuser"):
                validated_data.pop(field, None)
            validated_data.pop("username", None)
            entidades = None  # Não-admin não pode alterar entidades

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if password:
            instance.set_password(password)
        instance.save()

        if entidades is not None:
            instance.entidades.set(entidades)
        if usuarios_bloqueados is not None:
            instance.usuarios_bloqueados.set([u for u in usuarios_bloqueados if u.id != instance.id])

        return instance

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get("request")

        # Usuário comum em /me/ vê apenas dados pessoais (sem campos administrativos)
        if (
            request
            and request.user.is_authenticated
            and not request.user.is_staff
            and not request.user.is_superuser
            and request.user.pk == instance.pk
        ):
            for field in ("is_active", "is_staff", "is_superuser", "entidades", "entidades_nomes"):
                data.pop(field, None)

        return data


# ============================================================
# 🏛️ ENTIDADE / ÓRGÃO
# ============================================================

class EntidadeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Entidade
        fields = ("id", "nome", "cnpj", "ano")


class OrgaoSerializer(serializers.ModelSerializer):
    entidade_nome = serializers.CharField(source="entidade.nome", read_only=True)

    class Meta:
        model = Orgao
        fields = ("id", "nome", "codigo_unidade", "entidade", "entidade_nome")


# ============================================================
# 📄 PROCESSO LICITATÓRIO
# ============================================================

class ProcessoLicitatorioSerializer(serializers.ModelSerializer):
    entidade_nome = serializers.CharField(source="entidade.nome", read_only=True)
    orgao_nome = serializers.CharField(source="orgao.nome", read_only=True)

    modalidade_nome = serializers.SerializerMethodField()
    instrumento_convocatorio_nome = serializers.SerializerMethodField()
    amparo_legal_nome = serializers.SerializerMethodField()
    modo_disputa_nome = serializers.SerializerMethodField()
    criterio_julgamento_nome = serializers.SerializerMethodField()

    class Meta:
        model = ProcessoLicitatorio
        fields = (
            "id",
            "numero_processo",
            "numero_certame",
            "objeto",
            "modalidade",
            "modalidade_nome",
            "classificacao",
            "tipo_organizacao",
            "situacao",
            "data_processo",
            "data_abertura",
            "valor_referencia",
            "vigencia_meses",
            "registro_preco",
            "registro_precos",
            "entidade",
            "entidade_nome",
            "orgao",
            "orgao_nome",
            "instrumento_convocatorio",
            "instrumento_convocatorio_nome",
            "amparo_legal",
            "amparo_legal_nome",
            "modo_disputa",
            "modo_disputa_nome",
            "criterio_julgamento",
            "criterio_julgamento_nome",
            "fundamentacao",
            "pncp_publicado_em",
            "pncp_ano_compra",
            "pncp_sequencial_compra",
            "pncp_link",
            "pncp_ultimo_retorno",
            "data_criacao_sistema",
        )

    def get_modalidade_nome(self, obj):
        return MAP_MODALIDADE_PNCP.get(obj.modalidade)

    def get_instrumento_convocatorio_nome(self, obj):
        return MAP_INSTRUMENTO_CONVOCATORIO_PNCP.get(obj.instrumento_convocatorio)

    def get_amparo_legal_nome(self, obj):
        return MAP_AMPARO_LEGAL_PNCP.get(obj.amparo_legal)

    def get_modo_disputa_nome(self, obj):
        return MAP_MODO_DISPUTA_PNCP.get(obj.modo_disputa)

    def get_criterio_julgamento_nome(self, obj):
        return MAP_CRITERIO_JULGAMENTO_PNCP.get(obj.criterio_julgamento)


# ============================================================
# 📦 LOTE
# ============================================================

class LoteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Lote
        fields = ("id", "processo", "numero", "descricao")


# ============================================================
# 🏭 FORNECEDOR
# ============================================================

class FornecedorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Fornecedor
        fields = (
            "id",
            "cnpj",
            "razao_social",
            "nome_fantasia",
            "porte",
            "telefone",
            "email",
            "cep",
            "logradouro",
            "numero",
            "bairro",
            "complemento",
            "uf",
            "municipio",
            "criado_em",
        )


# ============================================================
# 📋 ITEM
# ============================================================

class ItemSerializer(serializers.ModelSerializer):
    processo_numero = serializers.CharField(source="processo.numero_processo", read_only=True)
    lote_numero = serializers.IntegerField(source="lote.numero", read_only=True)
    fornecedor_nome = serializers.CharField(source="fornecedor.razao_social", read_only=True)

    situacao_item_nome = serializers.SerializerMethodField()
    tipo_beneficio_nome = serializers.SerializerMethodField()
    categoria_item_nome = serializers.SerializerMethodField()

    class Meta:
        model = Item
        fields = (
            "id",
            "processo",
            "processo_numero",
            "lote",
            "lote_numero",
            "fornecedor",
            "fornecedor_nome",
            "descricao",
            "especificacao",
            "unidade",
            "quantidade",
            "valor_estimado",
            "valor_homologado",
            "ordem",
            "natureza",
            "situacao_item",
            "situacao_item_nome",
            "tipo_beneficio",
            "tipo_beneficio_nome",
            "categoria_item",
            "categoria_item_nome",
            "pncp_numero_item",
            "pncp_ultima_atualizacao",
        )

    def get_situacao_item_nome(self, obj):
        return MAP_SITUACAO_ITEM_PNCP.get(obj.situacao_item)

    def get_tipo_beneficio_nome(self, obj):
        return MAP_TIPO_BENEFICIO_PNCP.get(obj.tipo_beneficio)

    def get_categoria_item_nome(self, obj):
        return MAP_CATEGORIA_ITEM_PNCP.get(obj.categoria_item)


# ============================================================
# 🔗 FORNECEDOR ↔ PROCESSO
# ============================================================

class FornecedorProcessoSerializer(serializers.ModelSerializer):
    fornecedor_razao_social = serializers.CharField(source="fornecedor.razao_social", read_only=True)
    fornecedor_cnpj = serializers.CharField(source="fornecedor.cnpj", read_only=True)

    class Meta:
        model = FornecedorProcesso
        fields = (
            "id",
            "processo",
            "fornecedor",
            "fornecedor_razao_social",
            "fornecedor_cnpj",
            "data_participacao",
            "habilitado",
        )


# ============================================================
# 💰 ITEM ↔ FORNECEDOR (Propostas)
# ============================================================

class ItemFornecedorSerializer(serializers.ModelSerializer):
    item_descricao = serializers.CharField(source="item.descricao", read_only=True)
    fornecedor_razao_social = serializers.CharField(source="fornecedor.razao_social", read_only=True)

    class Meta:
        model = ItemFornecedor
        fields = (
            "id",
            "item",
            "item_descricao",
            "fornecedor",
            "fornecedor_razao_social",
            "valor_proposto",
            "vencedor",
        )


# ============================================================
# 📑 CONTRATO / EMPENHO
# ============================================================

class ContratoEmpenhoSerializer(serializers.ModelSerializer):
    processo_numero = serializers.CharField(source="processo.numero_processo", read_only=True)

    class Meta:
        model = ContratoEmpenho
        fields = (
            "id",
            "processo",
            "processo_numero",
            "tipo_contrato_id",
            "numero_contrato_empenho",
            "ano_contrato",
            "processo_ref",
            "categoria_processo_id",
            "receita",
            "unidade_codigo",
            "ni_fornecedor",
            "tipo_pessoa_fornecedor",
            "sequencial_publicacao",
            "criado_em",
            "atualizado_em",
        )


# ============================================================
# 📝 ANOTAÇÕES
# ============================================================

class AnotacaoSerializer(serializers.ModelSerializer):
    usuario_nome = serializers.CharField(source="usuario.username", read_only=True)
    # Aliases: o frontend envia/lê "text" e "date"
    text = serializers.CharField(source="texto")
    date = serializers.DateTimeField(source="criado_em", read_only=True)
    processo_numero = serializers.CharField(source="processo.numero_processo", read_only=True)
    compartilhada_com = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=CustomUser.objects.all(),
        required=False,
    )
    compartilhada_com_nomes = serializers.SerializerMethodField()
    shared_usernames = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        write_only=True,
    )

    class Meta:
        model = Anotacao
        fields = (
            "id", "usuario", "usuario_nome", "titulo", "text", "concluida",
            "processo", "processo_numero", "compartilhada_com", "compartilhada_com_nomes", "shared_usernames",
            "date", "criado_em", "atualizado_em"
        )
        read_only_fields = ("usuario", "criado_em", "atualizado_em", "date")

    def get_compartilhada_com_nomes(self, obj):
        return [
            {"id": u.id, "username": u.username, "nome": (u.get_full_name() or u.username)}
            for u in obj.compartilhada_com.all()
        ]

    def _resolve_shared_users(self, validated_data):
        request = self.context.get("request")
        actor = getattr(request, "user", None)
        shared_usernames = validated_data.pop("shared_usernames", None)
        recipients = validated_data.pop("compartilhada_com", None)
        processo = validated_data.get("processo") or getattr(self.instance, "processo", None)

        if shared_usernames is not None:
            usernames = [u.strip() for u in shared_usernames if str(u).strip()]
            recipients = list(CustomUser.objects.filter(username__in=usernames))

        if recipients is None:
            return None

        actor_entidade_ids = set(actor.entidades.values_list("id", flat=True)) if actor else set()

        filtered = []
        for user in recipients:
            if actor and user.id == actor.id:
                continue
            if not user.receber_anotacoes_compartilhadas:
                continue
            if actor and user.usuarios_bloqueados.filter(id=actor.id).exists():
                continue

            # Regra de privacidade por entidade
            if processo and processo.entidade_id:
                if not user.entidades.filter(id=processo.entidade_id).exists():
                    continue
            else:
                # Sem processo: só compartilha com quem intersecta entidade do ator
                if not actor_entidade_ids:
                    continue
                if not user.entidades.filter(id__in=actor_entidade_ids).exists():
                    continue

            filtered.append(user)
        return filtered

    def create(self, validated_data):
        recipients = self._resolve_shared_users(validated_data)
        anotacao = super().create(validated_data)
        if recipients is not None:
            anotacao.compartilhada_com.set(recipients)
        return anotacao

    def update(self, instance, validated_data):
        recipients = self._resolve_shared_users(validated_data)
        anotacao = super().update(instance, validated_data)
        if recipients is not None:
            anotacao.compartilhada_com.set(recipients)
        return anotacao


class NotificacaoSerializer(serializers.ModelSerializer):
    ator_nome = serializers.CharField(source="ator.username", read_only=True)
    anotacao_titulo = serializers.SerializerMethodField()

    class Meta:
        model = Notificacao
        fields = (
            "id",
            "usuario",
            "ator",
            "ator_nome",
            "anotacao",
            "anotacao_titulo",
            "processo",
            "tipo_acao",
            "titulo",
            "mensagem",
            "lida",
            "criado_em",
        )
        read_only_fields = (
            "usuario",
            "ator",
            "ator_nome",
            "anotacao",
            "anotacao_titulo",
            "processo",
            "tipo_acao",
            "titulo",
            "mensagem",
            "criado_em",
        )

    def get_anotacao_titulo(self, obj):
        if obj.anotacao and obj.anotacao.titulo:
            return obj.anotacao.titulo
        return None


# ============================================================
# 🗂️ ARQUIVOS DO USUÁRIO
# ============================================================

class ArquivoUserSerializer(serializers.ModelSerializer):
    arquivo_url = serializers.SerializerMethodField()

    class Meta:
        model = ArquivoUser
        fields = ("id", "usuario", "arquivo", "arquivo_url", "descricao", "enviado_em")
        read_only_fields = ("usuario", "arquivo_url", "enviado_em")

    def get_arquivo_url(self, obj):
        try:
            return obj.arquivo.url if obj.arquivo else None
        except Exception:
            return None


# ============================================================
# 🌐 DOCUMENTOS PNCP
# ============================================================

class DocumentoPNCPSerializer(serializers.ModelSerializer):
    # Permite upload via multipart/form-data
    arquivo = serializers.FileField(required=False)

    # Para o frontend abrir/baixar o arquivo
    arquivo_url = serializers.SerializerMethodField()
    tipo_documento_nome = serializers.SerializerMethodField()

    class Meta:
        model = DocumentoPNCP
        fields = (
            "id",
            "processo",
            "tipo_documento_id",
            "tipo_documento_nome",
            "titulo",
            "observacao",
            "arquivo",
            "arquivo_nome",
            "arquivo_url",
            "arquivo_hash",
            "status",
            "pncp_sequencial_documento",
            "pncp_publicado_em",
            "ativo",
            "criado_em",
        )
        read_only_fields = (
            "arquivo_nome",
            "arquivo_url",
            "arquivo_hash",
            "pncp_sequencial_documento",
            "pncp_publicado_em",
            "ativo",
            "criado_em",
        )

    def get_arquivo_url(self, obj):
        try:
            return obj.arquivo.url if obj.arquivo else None
        except Exception:
            return None

    def get_tipo_documento_nome(self, obj):
        mapa = {
            1: "Aviso de Contratação Direta",
            2: "Edital",
            3: "Minuta do Contrato",
            4: "Termo de Referência",
            5: "Anteprojeto",
            6: "Projeto Básico",
            7: "Estudo Técnico Preliminar",
            9: "Mapa de Riscos",
            10: "DFD",
            19: "Minuta de Ata de Registro de Preços",
            20: "Ato que autoriza a Contratação Direta",
        }
        return mapa.get(obj.tipo_documento_id, f"Tipo {obj.tipo_documento_id}")




class AtaRegistroPrecosSerializer(serializers.ModelSerializer):
    processo_numero = serializers.CharField(
        source="processo.numero_processo",
        read_only=True,
    )

    class Meta:
        model = AtaRegistroPrecos
        fields = (
            "id",
            "processo",
            "processo_numero",
            "numero_ata",
            "ano_ata",
            "data_assinatura",
            "data_vigencia_inicio",
            "data_vigencia_fim",
            "observacao",
            "status",
            "pncp_sequencial_ata",
            "numero_controle_pncp",
            "pncp_publicada_em",
            "ativo",
            "criado_em",
        )
        read_only_fields = (
            "status",
            "pncp_sequencial_ata",
            "numero_controle_pncp",
            "pncp_publicada_em",
            "ativo",
            "criado_em",
        )


class DocumentoAtaRegistroPrecosSerializer(serializers.ModelSerializer):
    arquivo = serializers.FileField(required=False)
    arquivo_url = serializers.SerializerMethodField()
    tipo_documento_nome = serializers.SerializerMethodField()
    ata_display = serializers.SerializerMethodField()

    class Meta:
        model = DocumentoAtaRegistroPrecos
        fields = (
            "id",
            "ata",
            "ata_display",
            "tipo_documento_id",
            "tipo_documento_nome",
            "titulo",
            "observacao",
            "arquivo",
            "arquivo_nome",
            "arquivo_url",
            "arquivo_hash",
            "status",
            "pncp_sequencial_documento",
            "pncp_publicado_em",
            "ativo",
            "criado_em",
        )
        read_only_fields = (
            "arquivo_nome",
            "arquivo_url",
            "arquivo_hash",
            "status",
            "pncp_sequencial_documento",
            "pncp_publicado_em",
            "ativo",
            "criado_em",
        )

    def get_arquivo_url(self, obj):
        try:
            return obj.arquivo.url if obj.arquivo else None
        except Exception:
            return None

    def get_tipo_documento_nome(self, obj):
        return TIPO_DOC_MAPA.get(obj.tipo_documento_id, f"Tipo {obj.tipo_documento_id}")

    def get_ata_display(self, obj):
        if not obj.ata:
            return None
        return f"Ata {obj.ata.numero_ata}/{obj.ata.ano_ata}"