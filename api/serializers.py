import re

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
    DocumentoContrato,
    Anotacao,
    Notificacao,
    ArquivoUser,
    DocumentoPNCP,
    ProcessoDocumentoLinha,
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
    16: "Outros Documentos",
    1: "Aviso de Contratação Direta",
    2: "Edital",
    3: "Minuta do Contrato",
    4: "Termo de Referência",
    5: "Anteprojeto",
    6: "Projeto Básico",
    7: "Estudo Técnico Preliminar",
    8: "Projeto Executivo",
    9: "Mapa de Riscos",
    10: "DFD",
    19: "Minuta de Ata de Registro de Preços",
    20: "Ato que autoriza a Contratação Direta",
}

CONTRATO_DOCUMENTOS_OBRIGATORIOS = (
    {
        "chave": "termo_convocacao",
        "titulo": "Termo de convocação",
        "tipo_documento_id": 7,
        "tipo_documento_nome": "Outros Documentos",
    },
    {
        "chave": "contrato",
        "titulo": "Contrato",
        "tipo_documento_id": 1,
        "tipo_documento_nome": "Contrato",
    },
    {
        "chave": "extrato",
        "titulo": "Extrato",
        "tipo_documento_id": 7,
        "tipo_documento_nome": "Outros Documentos",
    },
    {
        "chave": "certidao",
        "titulo": "Certidão",
        "tipo_documento_id": 7,
        "tipo_documento_nome": "Outros Documentos",
    },
)

CONTRATO_DOCUMENTOS_OBRIGATORIOS_MAPA = {
    item["chave"]: item for item in CONTRATO_DOCUMENTOS_OBRIGATORIOS
}

CONTRATO_TIPO_DOC_MAPA = {
    1: "Contrato",
    2: "Extrato",
    3: "Termo Aditivo",
    4: "Publicação DOU",
    5: "Apostilamento",
    6: "Rescisão",
    7: "Outros Documentos",
}


def _clean_digits(value):
    return re.sub(r"\D", "", value or "")


def _add_one_year(base_date):
    if not base_date:
        return None
    try:
        return base_date.replace(year=base_date.year + 1)
    except ValueError:
        return base_date.replace(month=2, day=28, year=base_date.year + 1)


def infer_chave_documento_contrato(chave_documento=None, titulo=None, arquivo_nome=None, tipo_documento_id=None):
    if chave_documento:
        return chave_documento

    texto = " ".join(filter(None, [titulo, arquivo_nome])).strip().lower()
    texto = texto.replace("ç", "c")
    texto = texto.replace("ã", "a")
    texto = texto.replace("á", "a")
    texto = texto.replace("â", "a")
    texto = texto.replace("é", "e")
    texto = texto.replace("ê", "e")
    texto = texto.replace("í", "i")
    texto = texto.replace("ó", "o")
    texto = texto.replace("ô", "o")
    texto = texto.replace("õ", "o")
    texto = texto.replace("ú", "u")

    if "termo" in texto and "convoc" in texto:
        return "termo_convocacao"
    if "certidao" in texto or "certidão" in texto:
        return "certidao"
    if "extrato" in texto or str(tipo_documento_id or "") == "2":
        return "extrato"
    if "contrato" in texto or str(tipo_documento_id or "") == "1":
        return "contrato"

    return None

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
    fornecedor = serializers.SerializerMethodField()
    fornecedor_nome = serializers.SerializerMethodField()
    fornecedor_cnpj = serializers.SerializerMethodField()
    fornecedor_id = serializers.IntegerField(write_only=True, required=False, allow_null=True)
    unidade_nome = serializers.SerializerMethodField()
    valor_contratado = serializers.SerializerMethodField()
    documentos_obrigatorios_ok = serializers.SerializerMethodField()
    documentos_pendentes = serializers.SerializerMethodField()

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
            "fornecedor",
            "fornecedor_nome",
            "fornecedor_cnpj",
            "fornecedor_id",
            "unidade_codigo",
            "unidade_nome",
            "ni_fornecedor",
            "tipo_pessoa_fornecedor",
            "objeto",
            "valor_inicial",
            "valor_global",
            "valor_contratado",
            "data_assinatura",
            "data_vigencia_inicio",
            "data_vigencia_fim",
            "documentos_obrigatorios_ok",
            "documentos_pendentes",
            "status",
            "pncp_sequencial_contrato",
            "numero_controle_pncp",
            "link_pncp",
            "pncp_publicado_em",
            "ativo",
            "criado_em",
            "atualizado_em",
        )
        extra_kwargs = {
            "tipo_contrato_id": {"required": False},
            "receita": {"required": False},
        }
        read_only_fields = (
            "tipo_contrato_id",
            "receita",
            "status",
            "pncp_sequencial_contrato",
            "numero_controle_pncp",
            "link_pncp",
            "pncp_publicado_em",
            "ativo",
            "criado_em",
            "atualizado_em",
        )

    def _get_fornecedor_obj(self, obj):
        cnpj = _clean_digits(obj.ni_fornecedor)
        if not cnpj or not obj.processo_id:
            return None

        queryset = Fornecedor.objects.filter(processos__processo=obj.processo).distinct()
        for fornecedor in queryset:
            if _clean_digits(fornecedor.cnpj) == cnpj:
                return fornecedor
        return None

    def get_fornecedor(self, obj):
        fornecedor = self._get_fornecedor_obj(obj)
        return fornecedor.id if fornecedor else None

    def get_fornecedor_nome(self, obj):
        fornecedor = self._get_fornecedor_obj(obj)
        return fornecedor.razao_social if fornecedor else None

    def get_fornecedor_cnpj(self, obj):
        fornecedor = self._get_fornecedor_obj(obj)
        return fornecedor.cnpj if fornecedor else obj.ni_fornecedor

    def get_unidade_nome(self, obj):
        if not obj.unidade_codigo or not obj.processo_id or not obj.processo.entidade_id:
            return None
        orgao = obj.processo.entidade.orgaos.filter(codigo_unidade=obj.unidade_codigo).first()
        return orgao.nome if orgao else None

    def get_valor_contratado(self, obj):
        return obj.valor_global if obj.valor_global is not None else obj.valor_inicial

    def get_documentos_pendentes(self, obj):
        docs = obj.documentos.filter(ativo=True).exclude(status="removido")
        presentes = {
            infer_chave_documento_contrato(doc.chave_documento, doc.titulo, doc.arquivo_nome, doc.tipo_documento_id)
            for doc in docs
            if doc.arquivo
        }
        return [
            item["titulo"]
            for item in CONTRATO_DOCUMENTOS_OBRIGATORIOS
            if item["chave"] not in presentes
        ]

    def get_documentos_obrigatorios_ok(self, obj):
        return len(self.get_documentos_pendentes(obj)) == 0

    def validate(self, attrs):
        processo = attrs.get("processo") or getattr(self.instance, "processo", None)
        if not processo:
            return attrs

        fornecedor_id = attrs.pop("fornecedor_id", serializers.empty)
        if fornecedor_id is not serializers.empty:
            if fornecedor_id in (None, ""):
                attrs["ni_fornecedor"] = None
                attrs["tipo_pessoa_fornecedor"] = None
            else:
                fornecedor = Fornecedor.objects.filter(pk=fornecedor_id).first()
                if not fornecedor:
                    raise serializers.ValidationError({"fornecedor_id": "Fornecedor inválido."})
                if not FornecedorProcesso.objects.filter(processo=processo, fornecedor=fornecedor).exists():
                    raise serializers.ValidationError({"fornecedor_id": "Selecione um fornecedor vinculado a este processo."})
                attrs["ni_fornecedor"] = _clean_digits(fornecedor.cnpj)
                attrs["tipo_pessoa_fornecedor"] = "PJ"
        elif not self.instance and not attrs.get("ni_fornecedor"):
            raise serializers.ValidationError({"fornecedor_id": "Selecione um fornecedor."})

        attrs["tipo_contrato_id"] = 1
        attrs["receita"] = False

        if not attrs.get("objeto"):
            attrs["objeto"] = processo.objeto or ""
        if not attrs.get("processo_ref"):
            attrs["processo_ref"] = processo.numero_processo or ""

        unidade_codigo = attrs.get("unidade_codigo", getattr(self.instance, "unidade_codigo", None))
        if unidade_codigo and processo.entidade_id and not processo.entidade.orgaos.filter(codigo_unidade=unidade_codigo).exists():
            raise serializers.ValidationError({"unidade_codigo": "Selecione uma unidade vinculada a entidade do processo."})

        valor_global = attrs.get("valor_global", getattr(self.instance, "valor_global", None))
        valor_inicial = attrs.get("valor_inicial", getattr(self.instance, "valor_inicial", None))
        if valor_global is not None and attrs.get("valor_inicial", serializers.empty) in (serializers.empty, None, ""):
            attrs["valor_inicial"] = valor_global
        elif valor_inicial is not None and attrs.get("valor_global", serializers.empty) in (serializers.empty, None, ""):
            attrs["valor_global"] = valor_inicial

        assinatura_informada = attrs.get("data_assinatura", serializers.empty)
        data_assinatura = attrs.get("data_assinatura", getattr(self.instance, "data_assinatura", None))
        data_inicio = attrs.get("data_vigencia_inicio", getattr(self.instance, "data_vigencia_inicio", None))
        data_fim = attrs.get("data_vigencia_fim", getattr(self.instance, "data_vigencia_fim", None))

        if assinatura_informada is not serializers.empty and data_assinatura:
            attrs["data_vigencia_inicio"] = data_assinatura
            data_inicio = data_assinatura

        if data_inicio and attrs.get("data_vigencia_fim", serializers.empty) in (serializers.empty, None, ""):
            attrs["data_vigencia_fim"] = _add_one_year(data_inicio)
            data_fim = attrs["data_vigencia_fim"]

        if data_inicio and data_fim and data_fim < data_inicio:
            raise serializers.ValidationError(
                {"data_vigencia_fim": "O fim da vigência não pode ser anterior ao início da vigência."}
            )

        return attrs


class DocumentoContratoSerializer(serializers.ModelSerializer):
    arquivo = serializers.FileField(required=False)
    arquivo_url = serializers.SerializerMethodField()
    tipo_documento_nome = serializers.SerializerMethodField()
    contrato_display = serializers.SerializerMethodField()
    chave_documento_nome = serializers.SerializerMethodField()

    class Meta:
        model = DocumentoContrato
        fields = (
            "id",
            "contrato",
            "contrato_display",
            "chave_documento",
            "chave_documento_nome",
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

    def get_arquivo_url(self, obj):
        if obj.arquivo and hasattr(obj.arquivo, "url"):
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(obj.arquivo.url)
            return obj.arquivo.url
        return None

    def get_tipo_documento_nome(self, obj):
        return CONTRATO_TIPO_DOC_MAPA.get(obj.tipo_documento_id, f"Tipo {obj.tipo_documento_id}")

    def get_contrato_display(self, obj):
        c = obj.contrato
        return f"{c.numero_contrato_empenho}/{c.ano_contrato}" if c else ""

    def get_chave_documento_nome(self, obj):
        chave = infer_chave_documento_contrato(
            obj.chave_documento,
            obj.titulo,
            obj.arquivo_nome,
            obj.tipo_documento_id,
        )
        spec = CONTRATO_DOCUMENTOS_OBRIGATORIOS_MAPA.get(chave)
        return spec["titulo"] if spec else obj.titulo


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
    linha_nome = serializers.CharField(source="linha_documento.nome", read_only=True)
    linha_ordem = serializers.IntegerField(source="linha_documento.ordem", read_only=True)

    class Meta:
        model = DocumentoPNCP
        fields = (
            "id",
            "processo",
            "linha_documento",
            "linha_nome",
            "linha_ordem",
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
            16: "Outros Documentos",
            1: "Aviso de Contratação Direta",
            2: "Edital",
            3: "Minuta do Contrato",
            4: "Termo de Referência",
            5: "Anteprojeto",
            6: "Projeto Básico",
            7: "Estudo Técnico Preliminar",
            8: "Projeto Executivo",
            9: "Mapa de Riscos",
            10: "DFD",
            19: "Minuta de Ata de Registro de Preços",
            20: "Ato que autoriza a Contratação Direta",
        }
        return mapa.get(obj.tipo_documento_id, f"Tipo {obj.tipo_documento_id}")


class ProcessoDocumentoLinhaSerializer(serializers.ModelSerializer):
    tipo_documento_nome = serializers.SerializerMethodField()

    class Meta:
        model = ProcessoDocumentoLinha
        fields = (
            "id",
            "processo",
            "nome",
            "tipo_documento_id",
            "tipo_documento_nome",
            "ordem",
            "custom",
            "ativo",
            "criado_em",
            "atualizado_em",
        )
        read_only_fields = ("ativo", "criado_em", "atualizado_em")

    def get_tipo_documento_nome(self, obj):
        return TIPO_DOC_MAPA.get(obj.tipo_documento_id, f"Tipo {obj.tipo_documento_id}")




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
            "possibilidade_adesao",
            "observacao",
            "status",
            "pncp_sequencial_ata",
            "numero_controle_pncp",
            "link_pncp",
            "pncp_publicada_em",
            "ativo",
            "criado_em",
        )
        read_only_fields = (
            "status",
            "pncp_sequencial_ata",
            "numero_controle_pncp",
            "link_pncp",
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