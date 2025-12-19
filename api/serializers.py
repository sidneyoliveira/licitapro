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
    MAP_CRITERIO_JULGAMENTO_PNCP,
    MAP_INSTRUMENTO_CONVOCATORIO_PNCP,
)

User = get_user_model()


# ============================================================
# 👤 USER
# ============================================================

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = ("id", "username", "first_name", "last_name", "email", "cpf", "phone", "profile_image")


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

    class Meta:
        model = Anotacao
        fields = ("id", "usuario", "usuario_nome", "texto", "criado_em", "atualizado_em")


# ============================================================
# 🗂️ ARQUIVOS DO USUÁRIO
# ============================================================

class ArquivoUserSerializer(serializers.ModelSerializer):
    arquivo_url = serializers.SerializerMethodField()

    class Meta:
        model = ArquivoUser
        fields = ("id", "usuario", "arquivo", "arquivo_url", "descricao", "enviado_em")
        read_only_fields = ("arquivo_url", "enviado_em")

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
