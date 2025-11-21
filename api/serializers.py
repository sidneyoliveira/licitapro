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

from django.contrib.auth import get_user_model
from rest_framework import serializers

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

UserSerializer = CustomUserSerializer


User = get_user_model()


class GroupNameField(serializers.StringRelatedField):
    def to_representation(self, value):
        # retorna apenas o nome do grupo
        return value.name


class UsuarioSerializer(serializers.ModelSerializer):
    groups = GroupNameField(many=True, read_only=True)
    # senha opcional na criação/edição
    password = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "email",
            "cpf",
            "data_nascimento",
            "phone",
            "profile_image",
            "is_active",
            "last_login",
            "date_joined",
            "groups",
            "password",
        ]
        read_only_fields = ["last_login", "date_joined", "groups"]

    def create(self, validated_data):
        password = validated_data.pop("password", None)
        user = User(**validated_data)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save()
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if password is not None and password != "":
            instance.set_password(password)
        instance.save()
        return instance


# ============================================================
# 🏛️ ENTIDADE / ÓRGÃO
# ============================================================

class EntidadeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Entidade
        fields = ("id", "nome", "cnpj", "ano")


class OrgaoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Orgao
        fields = ("id", "nome", "codigo_unidade", "entidade")


# Mini serializers para embutir no Processo
class EntidadeMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = Entidade
        fields = ("id", "nome", "cnpj", "ano")


class OrgaoMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = Orgao
        fields = ("id", "nome", "codigo_unidade", "entidade")


# ============================================================
# 📄 PROCESSO LICITATÓRIO
# ============================================================
class ProcessoLicitatorioSerializer(serializers.ModelSerializer):
    entidade_nome = serializers.SerializerMethodField()
    orgao_nome = serializers.SerializerMethodField()

    modalidade_code = serializers.SerializerMethodField()
    situacao_code = serializers.SerializerMethodField()
    classificacao_code = serializers.SerializerMethodField()
    tipo_organizacao_code = serializers.SerializerMethodField()

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
            "fundamentacao",
            "amparo_legal",
            "modo_disputa",
            "criterio_julgamento",
            "data_processo",
            "data_abertura",
            "valor_referencia",
            "vigencia_meses",
            "registro_preco",
            "entidade",
            "orgao",
            "data_criacao_sistema",
            "abertura_propostas",
            "encerramento_propostas",
            "link_sistema_origem",
            "link_processo_eletronico",
            # helpers
            "entidade_nome",
            "orgao_nome",
            "modalidade_code",
            "situacao_code",
            "classificacao_code",
            "tipo_organizacao_code",
        )
        read_only_fields = ("data_criacao_sistema",)

    # ---------- Maps código <-> label para front ----------

    MODALIDADE_MAP = {
        "pregao_eletronico": "Pregão Eletrônico",
        "concorrencia_eletronica": "Concorrência Eletrônica",
        "dispensa_eletronica": "Dispensa Eletrônica",
        "inexigibilidade_eletronica": "Inexigibilidade Eletrônica",
        "adesao_registro_precos": "Adesão a Registro de Preços",
        "credenciamento": "Credenciamento",
    }
    MODALIDADE_INV = {v: k for k, v in MODALIDADE_MAP.items()}

    SITUACAO_MAP = {
        "aberto": "Aberto",
        "em_pesquisa": "Em Pesquisa",
        "aguardando_publicacao": "Aguardando Publicação",
        "publicado": "Publicado",
        "em_contratacao": "Em Contratação",
        "adjudicado_homologado": "Adjudicado/Homologado",
        "revogado_cancelado": "Revogado/Cancelado",
    }
    SITUACAO_INV = {v: k for k, v in SITUACAO_MAP.items()}

    CLASSIFICACAO_MAP = {
        "compras": "Compras",
        "servicos_comuns": "Serviços Comuns",
        "servicos_engenharia_comuns": "Serviços de Engenharia Comuns",
        "obras_comuns": "Obras Comuns",
    }
    CLASSIFICACAO_INV = {v: k for k, v in CLASSIFICACAO_MAP.items()}

    TIPO_ORG_MAP = {
        "lote": "Lote",
        "item": "Item",
    }
    TIPO_ORG_INV = {v: k for k, v in TIPO_ORG_MAP.items()}

    # ---------- Normalização na entrada ----------

    def validate(self, attrs):
        attrs = self._map_in_codes(attrs)
        return super().validate(attrs)

    def _map_in_codes(self, attrs):
        """
        Front geralmente envia códigos (modalidade_code, classificacao_code, etc).
        Aqui traduzimos os códigos para os labels usados no model.
        """
        modal = attrs.get("modalidade")
        if modal:
            attrs["modalidade"] = self.MODALIDADE_MAP.get(modal, modal)

        sit = attrs.get("situacao")
        if sit:
            attrs["situacao"] = self.SITUACAO_MAP.get(sit, sit)

        cls = attrs.get("classificacao")
        if cls:
            attrs["classificacao"] = self.CLASSIFICACAO_MAP.get(cls, cls)

        tipo = attrs.get("tipo_organizacao")
        if tipo:
            attrs["tipo_organizacao"] = self.TIPO_ORG_MAP.get(tipo, tipo)

        # fundamentacao, amparo_legal, modo_disputa, criterio_julgamento
        # agora são recebidos em código e salvos direto (sem *_id)
        return attrs

    # ---------- Helpers de saída ----------

    def get_entidade_nome(self, obj):
        return obj.entidade.nome if obj.entidade else None

    def get_orgao_nome(self, obj):
        return obj.orgao.nome if obj.orgao else None

    def get_modalidade_code(self, obj):
        return self.MODALIDADE_INV.get(obj.modalidade, None)

    def get_situacao_code(self, obj):
        return self.SITUACAO_INV.get(obj.situacao, None)

    def get_classificacao_code(self, obj):
        return self.CLASSIFICACAO_INV.get(obj.classificacao, None)

    def get_tipo_organizacao_code(self, obj):
        return self.TIPO_ORG_INV.get(obj.tipo_organizacao, None)


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
    class Meta:
        model = Item
        fields = (
            "id",
            "processo",
            "descricao",
            "especificacao",         
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
        fields = ("id", "processo", "fornecedor", "data_participacao", "habilitado")


# ============================================================
# 💰 ITEM ↔ FORNECEDOR (propostas)
# ============================================================

class ItemFornecedorSerializer(serializers.ModelSerializer):
    class Meta:
        model = ItemFornecedor
        fields = ("id", "item", "fornecedor", "valor_proposto", "vencedor")


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
