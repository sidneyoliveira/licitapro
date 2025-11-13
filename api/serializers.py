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


class UserSerializer(serializers.ModelSerializer):
    """
    Serializer usado por CreateUserView/ManageUserView/GoogleLoginView.
    Aceita 'password' na criação/atualização e monta URL absoluta para a foto.
    """
    password = serializers.CharField(write_only=True, required=False, allow_blank=True)
    profile_image = serializers.ImageField(required=False, allow_null=True)

    class Meta:
        model = CustomUser
        fields = [
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "cpf",
            "data_nascimento",
            "phone",
            "profile_image",
            "password",
        ]

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        request = self.context.get("request")
        if rep.get("profile_image") and request:
            rep["profile_image"] = request.build_absolute_uri(rep["profile_image"])
        rep.pop("password", None)
        return rep

    def create(self, validated_data):
        password = validated_data.pop("password", None)
        user = CustomUser(**validated_data)
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
        if password:
            instance.set_password(password)
        instance.save()
        return instance


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
            "registro_preco",   # alias "registro_precos" chega e seta aqui via property
            "entidade",
            "orgao",
            "data_criacao_sistema",

            # textuais do front
            "fundamentacao",
            "amparo_legal",
            "modo_disputa",
            "criterio_julgamento",

            # janelas/identificação/links
            "numero_compra",
            "ano_compra",
            "abertura_propostas",
            "encerramento_propostas",
            "link_sistema_origem",
            "link_processo_eletronico",

            # IDs PNCP (preenchidos automaticamente)
            "instrumento_convocatorio_id",
            "modalidade_id",
            "modo_disputa_id",
            "criterio_julgamento_id",
            "amparo_legal_id",
            "situacao_contratacao_id",

            # controle de publicação
            "sequencial_publicacao",
            "id_controle_publicacao",
            "ultima_atualizacao_publicacao",
        )
        read_only_fields = ("data_criacao_sistema",)

    # ---------------------------
    # Tabelas de mapeamento (coerentes com as constantes do front)
    # ---------------------------
    FUND_MAP = {"lei_8666": 1, "lei_10520": 2, "lei_14133": 3}

    AMPARO_MAP = {
        "lei_8666": {
            "art_23": 101, "art_24": 102, "art_25": 103
        },
        "lei_10520": {
            "art_4": 201, "art_5": 202
        },
        "lei_14133": {
            "Pregão Eletrônico":     {"art_28_i": 301},
            "Concorrência Eletrônica":{"art_28_ii": 302},
            "Dispensa Eletrônica": {
                "art_75_par7": 311, "art_75_i": 312, "art_75_ii": 313,
                "art_75_iii_a": 314, "art_75_iii_b": 315,
                "art_75_iv_a": 316, "art_75_iv_b": 317, "art_75_iv_c": 318,
                "art_75_iv_d": 319, "art_75_iv_e": 320, "art_75_iv_f": 321,
                "art_75_iv_j": 322, "art_75_iv_k": 323, "art_75_iv_m": 324,
                "art_75_ix": 325, "art_75_viii": 326, "art_75_xv": 327,
                "lei_11947_art14_1": 328
            },
            "Credenciamento": {
                "art_79_i": 331, "art_79_ii": 332, "art_79_iii": 333
            },
            "Inexigibilidade Eletrônica": {
                "art_74_caput": 341, "art_74_i": 342, "art_74_ii": 343,
                "art_74_iii_a": 344, "art_74_iii_b": 345, "art_74_iii_c": 346,
                "art_74_iii_d": 347, "art_74_iii_e": 348, "art_74_iii_f": 349,
                "art_74_iii_g": 350, "art_74_iii_h": 351,
                "art_74_iv": 352, "art_74_v": 353
            },
        },
    }

    MODO_MAP = {"aberto": 1, "fechado": 2, "aberto_e_fechado": 3}
    CRITERIO_MAP = {"menor_preco": 1, "maior_desconto": 2}

    def _apply_code_mappings(self, attrs):
        # fundamentacao -> fundamentacao_id
        fund = attrs.get("fundamentacao")
        if fund:
            attrs["modalidade_id"] = attrs.get("modalidade_id")  # preserva se vier
            attrs["fundamentacao_id"] = self.FUND_MAP.get(fund)

        # amparo_legal -> amparo_legal_id (depende da fundamentação e, para 14.133, da modalidade)
        amparo = attrs.get("amparo_legal")
        modalidade_txt = attrs.get("modalidade")
        if amparo and fund:
            if fund == "lei_14133":
                bloco = self.AMPARO_MAP["lei_14133"].get(modalidade_txt or "", {})
                attrs["amparo_legal_id"] = bloco.get(amparo)
            else:
                attrs["amparo_legal_id"] = self.AMPARO_MAP.get(fund, {}).get(amparo)

        # modo_disputa -> modo_disputa_id
        modo = attrs.get("modo_disputa")
        if modo:
            attrs["modo_disputa_id"] = self.MODO_MAP.get(modo)

        # criterio_julgamento -> criterio_julgamento_id
        crit = attrs.get("criterio_julgamento")
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
        validated_data = self._apply_code_mappings(validated_data)
        return super().create(validated_data)

    def update(self, instance, validated_data):
        validated_data = self._apply_code_mappings(validated_data)
        return super().update(instance, validated_data)
    
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

            # complementos genéricos para publicação (seus campos de modelo)
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
