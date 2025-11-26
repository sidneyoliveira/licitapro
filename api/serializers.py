# api/serializers.py

from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import (
    CustomUser, Entidade, Orgao, ProcessoLicitatorio, Lote,
    Fornecedor, Item, FornecedorProcesso, ItemFornecedor, ContratoEmpenho
)
from .choices import (
    MAP_MODALIDADE_PNCP, MAP_MODO_DISPUTA_PNCP, MAP_INSTRUMENTO_CONVOCATORIO_PNCP,
    MAP_AMPARO_LEGAL_PNCP, MAP_SITUACAO_ITEM_PNCP, MAP_TIPO_BENEFICIO_PNCP,
    MAP_CATEGORIA_ITEM_PNCP
)

User = get_user_model()

# --- USUÁRIO ---
class CustomUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = ("id", "username", "first_name", "last_name", "email", "cpf", "data_nascimento", "phone", "profile_image", "is_active", "is_staff", "date_joined", "last_login")

class GroupNameField(serializers.StringRelatedField):
    def to_representation(self, value): return value.name

class UsuarioSerializer(serializers.ModelSerializer):
    groups = GroupNameField(many=True, read_only=True)
    password = serializers.CharField(write_only=True, required=False, allow_blank=True)
    class Meta:
        model = User
        fields = ["id", "username", "email", "first_name", "last_name", "cpf", "data_nascimento", "phone", "profile_image", "is_active", "last_login", "date_joined", "groups", "password"]
        read_only_fields = ["date_joined", "groups"]
    def create(self, validated_data):
        password = validated_data.pop("password", None)
        user = User(**validated_data)
        if password: user.set_password(password)
        else: user.set_unusable_password()
        user.save()
        return user
    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        for attr, value in validated_data.items(): setattr(instance, attr, value)
        if password: instance.set_password(password)
        instance.save()
        return instance

# --- ENTIDADE / ÓRGÃO ---
class EntidadeSerializer(serializers.ModelSerializer):
    class Meta: model = Entidade; fields = ("id", "nome", "cnpj", "ano")
class OrgaoSerializer(serializers.ModelSerializer):
    class Meta: model = Orgao; fields = ("id", "nome", "codigo_unidade", "entidade")
class EntidadeMiniSerializer(serializers.ModelSerializer):
    class Meta: model = Entidade; fields = ("id", "nome", "cnpj", "ano")
class OrgaoMiniSerializer(serializers.ModelSerializer):
    class Meta: model = Orgao; fields = ("id", "nome", "codigo_unidade", "entidade")


# ============================================================
# 📄 PROCESSO LICITATÓRIO (SEM FUNDAMENTAÇÃO)
# ============================================================

class ProcessoLicitatorioSerializer(serializers.ModelSerializer):
    entidade_nome = serializers.CharField(source="entidade.nome", read_only=True)
    orgao_nome = serializers.CharField(source="orgao.nome", read_only=True)
    entidade_obj = EntidadeMiniSerializer(source="entidade", read_only=True)
    orgao_obj = OrgaoMiniSerializer(source="orgao", read_only=True)

    modalidade = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    modo_disputa = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    instrumento_convocatorio = serializers.CharField(required=False, allow_blank=True, allow_null=True) 
    amparo_legal = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    
    # REMOVIDO: fundamentacao

    class Meta:
        model = ProcessoLicitatorio
        fields = (
            "id",
            "numero_processo",
            "numero_certame",
            "objeto",
            "modalidade",       
            "modo_disputa",     
            "instrumento_convocatorio", 
            "amparo_legal",     
            
            "classificacao",
            "tipo_organizacao",
            "situacao",         
            "criterio_julgamento",
            
            "data_processo",
            "data_abertura",
            "valor_referencia",
            "vigencia_meses",
            "registro_preco",
            "entidade",
            "orgao",
            "data_criacao_sistema",

            "entidade_nome", "orgao_nome", "entidade_obj", "orgao_obj",
        )
        read_only_fields = ("data_criacao_sistema", "entidade_nome", "orgao_nome")

    def to_internal_value(self, data):
        data = data.copy()

        # Conversão de Slugs para IDs (Frontend -> Backend)
        if 'modalidade' in data and data['modalidade']:
            slug = data['modalidade']
            data['modalidade'] = MAP_MODALIDADE_PNCP.get(slug, slug)

        if 'modo_disputa' in data and data['modo_disputa']:
            slug = data['modo_disputa']
            data['modo_disputa'] = MAP_MODO_DISPUTA_PNCP.get(slug, slug)

        if 'amparo_legal' in data and data['amparo_legal']:
            slug = data['amparo_legal']
            data['amparo_legal'] = MAP_AMPARO_LEGAL_PNCP.get(slug, slug)

        if 'instrumento_convocatorio' in data and data['instrumento_convocatorio']:
            slug = data['instrumento_convocatorio']
            data['instrumento_convocatorio'] = MAP_INSTRUMENTO_CONVOCATORIO_PNCP.get(slug, slug)
        
        return super().to_internal_value(data)

# --- OUTROS SERIALIZERS ---
class LoteSerializer(serializers.ModelSerializer):
    class Meta: model = Lote; fields = ("id", "processo", "numero", "descricao")
class FornecedorSerializer(serializers.ModelSerializer):
    class Meta: model = Fornecedor; fields = ("id", "cnpj", "razao_social", "nome_fantasia", "porte", "telefone", "email", "cep", "logradouro", "numero", "bairro", "complemento", "uf", "municipio", "criado_em")
class ItemSerializer(serializers.ModelSerializer):
    situacao_item = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    tipo_beneficio = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    categoria_item = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    class Meta:
        model = Item
        fields = ("id", "processo", "lote", "ordem", "descricao", "especificacao", "unidade", "quantidade", "valor_estimado", "natureza", "situacao_item", "tipo_beneficio", "categoria_item", "fornecedor")
    def to_internal_value(self, data):
        data = data.copy()
        if 'situacao_item' in data: data['situacao_item'] = MAP_SITUACAO_ITEM_PNCP.get(data['situacao_item'], data['situacao_item'])
        if 'tipo_beneficio' in data: data['tipo_beneficio'] = MAP_TIPO_BENEFICIO_PNCP.get(data['tipo_beneficio'], data['tipo_beneficio'])
        if 'categoria_item' in data: data['categoria_item'] = MAP_CATEGORIA_ITEM_PNCP.get(data['categoria_item'], data['categoria_item'])
        return super().to_internal_value(data)
class FornecedorProcessoSerializer(serializers.ModelSerializer):
    class Meta: model = FornecedorProcesso; fields = ("id", "processo", "fornecedor", "data_participacao", "habilitado")
class ItemFornecedorSerializer(serializers.ModelSerializer):
    class Meta: model = ItemFornecedor; fields = ("id", "item", "fornecedor", "valor_proposto", "vencedor")
class ContratoEmpenhoSerializer(serializers.ModelSerializer):
    class Meta: model = ContratoEmpenho; fields = ("id", "processo", "tipo_contrato_id", "numero_contrato_empenho", "ano_contrato", "processo_ref", "categoria_processo_id", "receita", "unidade_codigo", "ni_fornecedor", "tipo_pessoa_fornecedor", "sequencial_publicacao", "criado_em", "atualizado_em")