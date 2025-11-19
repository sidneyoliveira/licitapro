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
    # Exibição amigável
    entidade_nome = serializers.CharField(source="entidade.nome", read_only=True)
    orgao_nome = serializers.CharField(source="orgao.nome", read_only=True)
    entidade_obj = EntidadeMiniSerializer(source="entidade", read_only=True)
    orgao_obj = OrgaoMiniSerializer(source="orgao", read_only=True)

    # Recebe códigos (front) e converte para rótulos do modelo
    # 🔹 Agora opcionais para permitir importações com campos em branco
    modalidade = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    situacao = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    classificacao = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    tipo_organizacao = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    # Campos de entrada (front) para mapear PNCP → IDs (não existem no model)
    fundamentacao = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True,
        write_only=True
    )
    amparo_legal = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True,
        write_only=True
    )
    modo_disputa = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True,
        write_only=True
    )
    criterio_julgamento = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True,
        write_only=True
    )

    # Códigos de volta no response (somente leitura)
    modalidade_code = serializers.SerializerMethodField(read_only=True)
    situacao_code = serializers.SerializerMethodField(read_only=True)
    classificacao_code = serializers.SerializerMethodField(read_only=True)
    tipo_organizacao_code = serializers.SerializerMethodField(read_only=True)

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

            # campos de entrada (write-only) para mapear PNCP
            "fundamentacao",
            "amparo_legal",
            "modo_disputa",
            "criterio_julgamento",

            # identificação / janelas / links
            "numero_compra",
            "ano_compra",
            "abertura_propostas",
            "encerramento_propostas",
            "link_sistema_origem",
            "link_processo_eletronico",

            # IDs PNCP
            "instrumento_convocatorio_id",
            "modalidade_id",
            "modo_disputa_id",
            "criterio_julgamento_id",
            "amparo_legal_id",
            "situacao_contratacao_id",

            # publicação
            "sequencial_publicacao",
            "id_controle_publicacao",
            "ultima_atualizacao_publicacao",

            # extras somente leitura
            "entidade_nome",
            "orgao_nome",
            "entidade_obj",
            "orgao_obj",

            # códigos para o front manter selects
            "modalidade_code",
            "situacao_code",
            "classificacao_code",
            "tipo_organizacao_code",
        )
        read_only_fields = (
            "data_criacao_sistema",
            "entidade_nome",
            "orgao_nome",
            "entidade_obj",
            "orgao_obj",
            "modalidade_code",
            "situacao_code",
            "classificacao_code",
            "tipo_organizacao_code",
        )

    # ---------------------------
    # MAPAS código <-> rótulo
    # ---------------------------
    MODALIDADE_MAP = {
        "pregao_eletronico": "Pregão Eletrônico",
        "concorrencia_eletronica": "Concorrência Eletrônica",
        "dispensa_eletronica": "Dispensa Eletrônica",
        "inexigibilidade_eletronica": "Inexigibilidade Eletrônica",
        "adesao_registro_precos": "Adesão a Registro de Preços",
        "credenciamento": "Credenciamento",
    }
    MODALIDADE_INV = {v: k for k, v in MODALIDADE_MAP.items()}

    CLASSIFICACAO_MAP = {
        "compras": "Compras",
        "servicos_comuns": "Serviços Comuns",
        "servicos_engenharia_comuns": "Serviços de Engenharia Comuns",
        "obras_comuns": "Obras Comuns",
    }
    CLASSIFICACAO_INV = {v: k for k, v in CLASSIFICACAO_MAP.items()}

    ORGANIZACAO_MAP = {"lote": "Lote", "item": "Item"}
    ORGANIZACAO_INV = {v: k for k, v in ORGANIZACAO_MAP.items()}

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

    # PNCP (IDs exemplificativos — ajuste conforme seu catálogo)
    FUND_MAP = {"lei_8666": 1, "lei_10520": 2, "lei_14133": 3}
    AMPARO_MAP = {
        "lei_8666": {"art_23": 101, "art_24": 102, "art_25": 103},
        "lei_10520": {"art_4": 201, "art_5": 202},
        "lei_14133": {
            "Pregão Eletrônico": {"art_28_i": 301},
            "Concorrência Eletrônica": {"art_28_ii": 302},
            "Dispensa Eletrônica": {
                "art_75_par7": 311, "art_75_i": 312, "art_75_ii": 313,
                "art_75_iii_a": 314, "art_75_iii_b": 315,
                "art_75_iv_a": 316, "art_75_iv_b": 317, "art_75_iv_c": 318,
                "art_75_iv_d": 319, "art_75_iv_e": 320, "art_75_iv_f": 321,
                "art_75_iv_j": 322, "art_75_iv_k": 323, "art_75_iv_m": 324,
                "art_75_ix": 325, "art_75_viii": 326, "art_75_xv": 327,
                "lei_11947_art14_1": 328
            },
            "Credenciamento": {"art_79_i": 331, "art_79_ii": 332, "art_79_iii": 333},
            "Inexigibilidade Eletrônica": {
                "art_74_caput": 341, "art_74_i": 342, "art_74_ii": 343,
                "art_74_iii_a": 344, "art_74_iii_b": 345, "art_74_iii_c": 346,
                "art_74_iii_d": 347, "art_74_iii_e": 348, "art_74_iii_f": 349,
                "art_74_iii_g": 350, "art_74_iii_h": 351,
                "art_74_iv": 352, "art_74_v": 353
            },
            "Adesão a Registro de Preços": {"art_86_2": 354},
        },
    }
    MODO_MAP = {"aberto": 1, "fechado": 2, "aberto_e_fechado": 3}
    CRITERIO_MAP = {"menor_preco": 1, "maior_desconto": 2}

    def _map_in_codes(self, attrs):
        """
        Converte códigos do front em rótulos do modelo e popula IDs PNCP.
        Remove do payload os campos write-only que não existem no model.
        """
        # Choices (rótulos do model)
        mod = attrs.get("modalidade")
        if mod:
            attrs["modalidade"] = self.MODALIDADE_MAP.get(mod, mod)

        cls = attrs.get("classificacao")
        if cls:
            attrs["classificacao"] = self.CLASSIFICACAO_MAP.get(cls, cls)

        orgz = attrs.get("tipo_organizacao")
        if orgz:
            attrs["tipo_organizacao"] = self.ORGANIZACAO_MAP.get(orgz, orgz)

        sit = attrs.get("situacao")
        if sit:
            attrs["situacao"] = self.SITUACAO_MAP.get(sit, sit)

        # PNCP mappings
        fund = attrs.pop("fundamentacao", None)
        if fund:
            attrs["instrumento_convocatorio_id"] = self.FUND_MAP.get(fund)

        amparo = attrs.pop("amparo_legal", None)
        if amparo and fund:
            modalidade_rotulo = attrs.get("modalidade")
            if fund == "lei_14133":
                bloco = self.AMPARO_MAP["lei_14133"].get(modalidade_rotulo or "", {})
                attrs["amparo_legal_id"] = bloco.get(amparo)
            else:
                attrs["amparo_legal_id"] = self.AMPARO_MAP.get(fund, {}).get(amparo)

        modo = attrs.pop("modo_disputa", None)
        if modo:
            attrs["modo_disputa_id"] = self.MODO_MAP.get(modo)

        crit = attrs.pop("criterio_julgamento", None)
        if crit:
            attrs["criterio_julgamento_id"] = self.CRITERIO_MAP.get(crit)

        return attrs

    def validate(self, attrs):
        ap = attrs.get("abertura_propostas")
        ep = attrs.get("encerramento_propostas")
        if ap and ep and ep <= ap:
            raise serializers.ValidationError(
                {"encerramento_propostas": "Deve ser posterior à data de abertura de propostas."}
            )
        return attrs

    def create(self, validated_data):
        validated_data = self._map_in_codes(validated_data)
        return super().create(validated_data)

    def update(self, instance, validated_data):
        validated_data = self._map_in_codes(validated_data)
        return super().update(instance, validated_data)

    # ---- getters dos *_code (somente leitura) ----
    def get_modalidade_code(self, obj):
        return self.MODALIDADE_INV.get(obj.modalidade, obj.modalidade)

    def get_situacao_code(self, obj):
        return self.SITUACAO_INV.get(obj.situacao, obj.situacao)

    def get_classificacao_code(self, obj):
        return self.CLASSIFICACAO_INV.get(obj.classificacao, obj.classificacao)

    def get_tipo_organizacao_code(self, obj):
        return self.ORGANIZACAO_INV.get(obj.tipo_organizacao, obj.tipo_organizacao)


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
