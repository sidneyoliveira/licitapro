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
    ArquivoUser,
    DocumentoPNCP
)
from .choices import (
    MAP_MODALIDADE_PNCP,
    MAP_MODO_DISPUTA_PNCP,
    MAP_INSTRUMENTO_CONVOCATORIO_PNCP,
    MAP_AMPARO_LEGAL_PNCP,
    MAP_SITUACAO_ITEM_PNCP,
    MAP_TIPO_BENEFICIO_PNCP,
    MAP_CATEGORIA_ITEM_PNCP,
)

User = get_user_model()

# ============================================================
# 👤 USUÁRIO
# ============================================================

# Renomeado de CustomUserSerializer para UserSerializer para evitar erros de importação
class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = (
            "id", "username", "first_name", "last_name", "email",
            "cpf", "data_nascimento", "phone", "profile_image",
            "is_staff", "is_superuser", "is_active"
        )


# ============================================================
# 🏛️ ENTIDADE / ÓRGÃO
# ============================================================

class EntidadeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Entidade
        fields = "__all__"


class OrgaoSerializer(serializers.ModelSerializer):
    entidade_nome = serializers.CharField(source="entidade.nome", read_only=True)

    class Meta:
        model = Orgao
        fields = "__all__"


# ============================================================
# 🧾 FORNECEDOR
# ============================================================

class FornecedorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Fornecedor
        fields = "__all__"


# ============================================================
# 📄 PROCESSO LICITATÓRIO
# ============================================================

class ProcessoLicitatorioSerializer(serializers.ModelSerializer):
    orgao_nome = serializers.CharField(source="orgao.nome", read_only=True)
    entidade_nome = serializers.CharField(source="orgao.entidade.nome", read_only=True)

    modalidade_nome = serializers.SerializerMethodField()
    modo_disputa_nome = serializers.SerializerMethodField()
    instrumento_convocatorio_nome = serializers.SerializerMethodField()
    amparo_legal_nome = serializers.SerializerMethodField()

    class Meta:
        model = ProcessoLicitatorio
        fields = "__all__"

    def get_modalidade_nome(self, obj):
        if obj.modalidade_id is None:
            return None
        return MAP_MODALIDADE_PNCP.get(obj.modalidade_id, str(obj.modalidade_id))

    def get_modo_disputa_nome(self, obj):
        if obj.modo_disputa_id is None:
            return None
        return MAP_MODO_DISPUTA_PNCP.get(obj.modo_disputa_id, str(obj.modo_disputa_id))

    def get_instrumento_convocatorio_nome(self, obj):
        if obj.instrumento_convocatorio is None:
            return None
        return MAP_INSTRUMENTO_CONVOCATORIO_PNCP.get(obj.instrumento_convocatorio, str(obj.instrumento_convocatorio))

    def get_amparo_legal_nome(self, obj):
        if obj.amparo_legal is None:
            return None
        return MAP_AMPARO_LEGAL_PNCP.get(obj.amparo_legal, str(obj.amparo_legal))


# ============================================================
# 📦 LOTE
# ============================================================

class LoteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Lote
        fields = "__all__"


# ============================================================
# 🧱 ITEM
# ============================================================

class ItemSerializer(serializers.ModelSerializer):
    situacao_nome = serializers.SerializerMethodField()
    tipo_beneficio_nome = serializers.SerializerMethodField()
    categoria_nome = serializers.SerializerMethodField()

    class Meta:
        model = Item
        fields = "__all__"

    def get_situacao_nome(self, obj):
        if obj.situacao_item_id is None:
            return None
        return MAP_SITUACAO_ITEM_PNCP.get(obj.situacao_item_id, str(obj.situacao_item_id))

    def get_tipo_beneficio_nome(self, obj):
        if obj.tipo_beneficio_id is None:
            return None
        return MAP_TIPO_BENEFICIO_PNCP.get(obj.tipo_beneficio_id, str(obj.tipo_beneficio_id))

    def get_categoria_nome(self, obj):
        if obj.categoria_item_id is None:
            return None
        return MAP_CATEGORIA_ITEM_PNCP.get(obj.categoria_item_id, str(obj.categoria_item_id))


# ============================================================
# 🔗 RELAÇÕES FORNECEDOR x PROCESSO
# ============================================================

class FornecedorProcessoSerializer(serializers.ModelSerializer):
    fornecedor_nome = serializers.CharField(source="fornecedor.nome", read_only=True)

    class Meta:
        model = FornecedorProcesso
        fields = "__all__"


class ItemFornecedorSerializer(serializers.ModelSerializer):
    class Meta:
        model = ItemFornecedor
        fields = "__all__"


# ============================================================
# 🧾 CONTRATO / EMPENHO
# ============================================================

class ContratoEmpenhoSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContratoEmpenho
        fields = "__all__"


# ============================================================
# 🗒️ ANOTAÇÕES
# ============================================================

class AnotacaoSerializer(serializers.ModelSerializer):
    usuario_nome = serializers.CharField(source="usuario.username", read_only=True)

    class Meta:
        model = Anotacao
        fields = "__all__"


# ============================================================
# 📁 ARQUIVO DO USUÁRIO
# ============================================================

class ArquivoUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = ArquivoUser
        fields = "__all__"


# ============================================================
# 📄 DOCUMENTOS PNCP (RAScunho local / Envio)
# ============================================================

class DocumentoPNCPSerializer(serializers.ModelSerializer):
    tipo_documento_nome = serializers.SerializerMethodField()
    arquivo_url = serializers.SerializerMethodField()

    class Meta:
        model = DocumentoPNCP
        fields = (
            "id",
            "processo",
            "tipo_documento_id",
            "tipo_documento_nome",
            "titulo",
            "observacao",
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
            "id",
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
            # Evita quebrar o serializer caso o storage/URL não esteja resolvido no ambiente
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
            8: "Projeto Executivo",
            9: "Mapa de Riscos",
            10: "DFD",
            19: "Minuta de Ata de Registro de Preços",
            20: "Ato que autoriza a Contratação Direta",
        }
        return mapa.get(obj.tipo_documento_id, f"Tipo {obj.tipo_documento_id}")
