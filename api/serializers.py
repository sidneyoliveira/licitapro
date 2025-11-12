from rest_framework import serializers
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
)

# ============================================================
# 👤 USUÁRIO
# ============================================================

class CustomUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = (
            "id",
            "username",
            "first_name",
            "last_name",
            "email",
            "cpf",
            "data_nascimento",
            "phone",
            "profile_image",
            "is_active",
            "is_staff",
            "date_joined",
        )


# ============================================================
# 🏛️ ENTIDADE / ÓRGÃO
# ============================================================

class EntidadeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Entidade
        fields = (
            "id",
            "nome",
            "cnpj",
            "ano",
        )


class OrgaoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Orgao
        fields = (
            "id",
            "nome",
            "codigo_unidade",   # campo genérico que atende PNCP
            "entidade",
        )


# ============================================================
# 📄 PROCESSO LICITATÓRIO
# ============================================================

class ProcessoLicitatorioSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProcessoLicitatorio
        fields = (
            "id",
            "numero_processo",
            "numero_certame",
            "objeto",
            "modalidade",
            "classificacao",
            "tipo_organizacao",
            "situacao",
            "data_processo",
            "data_abertura",
            "valor_referencia",
            "vigencia_meses",
            "registro_preco",
            "entidade",
            "orgao",
            "data_criacao_sistema",

            # ====== campos mínimos para publicação (genéricos) ======
            "instrumento_convocatorio_id",
            "modalidade_id",
            "modo_disputa_id",
            "criterio_julgamento_id",
            "amparo_legal_id",

            "numero_compra",
            "ano_compra",

            "abertura_propostas",
            "encerramento_propostas",

            "link_sistema_origem",
            "link_processo_eletronico",

            "sequencial_publicacao",
            "id_controle_publicacao",
            "ultima_atualizacao_publicacao",
        )

    def validate(self, attrs):
        # Se as duas datas existirem, encerramento deve ser após a abertura
        ap = attrs.get("abertura_propostas")
        ep = attrs.get("encerramento_propostas")
        if ap and ep and ep <= ap:
            raise serializers.ValidationError(
                {"encerramento_propostas": "Deve ser posterior à data de abertura de propostas."}
            )
        return attrs


# ============================================================
# 📦 LOTE
# ============================================================

class LoteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Lote
        fields = (
            "id",
            "processo",
            "numero",
            "descricao",
        )


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
    class Meta:
        model = Item
        fields = (
            "id",
            "processo",
            "descricao",
            "unidade",
            "quantidade",
            "valor_estimado",
            "lote",
            "fornecedor",
            "ordem",

            # complementos genéricos para publicação
            "natureza",
            "tipo_beneficio_id",
            "criterio_julgamento_id",
            "catalogo_id",
            "categoria_item_catalogo_id",
            "catalogo_codigo_item",
        )


# ============================================================
# 🔗 FORNECEDOR ↔ PROCESSO
# ============================================================

class FornecedorProcessoSerializer(serializers.ModelSerializer):
    class Meta:
        model = FornecedorProcesso
        fields = (
            "id",
            "processo",
            "fornecedor",
            "data_participacao",
            "habilitado",
        )


# ============================================================
# 💰 ITEM ↔ FORNECEDOR (propostas)
# ============================================================

class ItemFornecedorSerializer(serializers.ModelSerializer):
    class Meta:
        model = ItemFornecedor
        fields = (
            "id",
            "item",
            "fornecedor",
            "valor_proposto",
            "vencedor",
        )


# ============================================================
# 📑 CONTRATO / EMPENHO (genérico)
# ============================================================

class ContratoEmpenhoSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContratoEmpenho
        fields = (
            "id",
            "processo",
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
