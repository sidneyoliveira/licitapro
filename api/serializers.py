from rest_framework import serializers
from django.db import models
from django.db.models import Max
from .models import (
    CustomUser,
    Entidade,
    Orgao,
    ProcessoLicitatorio,
    Lote,
    Item,
    Fornecedor,
    FornecedorProcesso,
    ItemFornecedor
)


# ============================================================
# 1️⃣ USUÁRIO
# ============================================================

class UserSerializer(serializers.ModelSerializer):
    profile_image = serializers.ImageField(required=False, allow_null=True)

    class Meta:
        model = CustomUser
        fields = [
            'id',
            'username',
            'email',
            'first_name',
            'last_name',
            'cpf',
            'phone',
            'data_nascimento',
            'password',
            'profile_image',
        ]
        read_only_fields = ['id', 'username']
        extra_kwargs = {
            'password': {'write_only': True, 'required': False}
        }

    def get_profile_image(self, obj):
        request = self.context.get('request')
        if obj.profile_image and hasattr(obj.profile_image, 'url'):
            return request.build_absolute_uri(obj.profile_image.url)
        return None

    def update(self, instance, validated_data):
        password = validated_data.pop('password', None)
        user = super().update(instance, validated_data)

        if password:
            user.set_password(password)
            user.save()

        return user

# ============================================================
# 2️⃣ ENTIDADE / ÓRGÃO
# ============================================================

class EntidadeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Entidade
        fields = '__all__'
        read_only_fields = ['id']


class OrgaoSerializer(serializers.ModelSerializer):
    entidade_nome = serializers.CharField(source='entidade.nome', read_only=True)

    class Meta:
        model = Orgao
        fields = '__all__'
        read_only_fields = ['id', 'entidade_nome']


# ============================================================
# 3️⃣ FORNECEDOR
# ============================================================

class FornecedorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Fornecedor
        fields = [
            'id', 'cnpj', 'razao_social', 'nome_fantasia', 'porte',
            'telefone', 'email', 'cep', 'logradouro', 'numero',
            'bairro', 'complemento', 'uf', 'municipio', 'criado_em'
        ]
        read_only_fields = ['id', 'criado_em']

# ============================================================
# 4️⃣ LOTE
# ============================================================

class LoteSerializer(serializers.ModelSerializer):
    processo_numero = serializers.CharField(source='processo.numero_processo', read_only=True)

    class Meta:
        model = Lote
        fields = ['id', 'processo', 'processo_numero', 'numero', 'descricao']
        read_only_fields = ['id', 'processo_numero']


# ============================================================
# 5️⃣ ITEM (substitui ItemProcesso)
# ============================================================

class ItemSerializer(serializers.ModelSerializer):
    processo_numero = serializers.CharField(source='processo.numero_processo', read_only=True)
    lote_numero = serializers.CharField(source='lote.numero', read_only=True)
    fornecedor_nome = serializers.CharField(source='fornecedor.nome', read_only=True)

    class Meta:
        model = Item
        fields = [
            'id',
            'processo',
            'processo_numero',
            'descricao',
            'unidade',
            'quantidade',
            'valor_estimado',
            'lote',
            'lote_numero',
            'fornecedor',
            'fornecedor_nome'
        ]
        read_only_fields = ['id', 'processo_numero', 'lote_numero', 'fornecedor_nome']

    def create(self, validated_data):
        # Define uma ordem automática se quiser manter lógica parecida à anterior
        processo = validated_data.get('processo')
        if processo:
            last_item = Item.objects.filter(processo=processo).order_by('-id').first()
            validated_data['ordem'] = (last_item.id + 1) if last_item else 1
        return super().create(validated_data)


# ============================================================
# 6️⃣ PROCESSO LICITATÓRIO
# ============================================================
class ProcessoLicitatorioSerializer(serializers.ModelSerializer):
    entidade_nome = serializers.CharField(source='entidade.nome', read_only=True)
    orgao_nome = serializers.CharField(source='orgao.nome', read_only=True)
    registro_preco_display = serializers.SerializerMethodField()

    class Meta:
        model = ProcessoLicitatorio
        fields = [
            'id',
            'objeto',
            'modalidade',
            'data_abertura',
            'situacao',
            'entidade',
            'entidade_nome',       
            'orgao',
            'orgao_nome',         
            'valor_referencia',
            'vigencia_meses',
            'classificacao',
            'tipo_organizacao',
            'registro_preco',      
            'registro_preco_display',  
            'data_processo',
            'numero_processo',
            'numero_certame',
        ]

    def get_registro_preco_display(self, obj):
        return "Sim" if obj.registro_preco else "Não"

# ============================================================
# 7️⃣ FORNECEDOR ↔ PROCESSO (participantes)
# ============================================================

class FornecedorProcessoSerializer(serializers.ModelSerializer):
    fornecedor_nome = serializers.CharField(source='fornecedor.nome', read_only=True)
    processo_numero = serializers.CharField(source='processo.numero_processo', read_only=True)

    class Meta:
        model = FornecedorProcesso
        fields = [
            'id',
            'processo',
            'processo_numero',
            'fornecedor',
            'fornecedor_nome',
            'data_participacao',
            'habilitado'
        ]
        read_only_fields = ['id', 'data_participacao', 'fornecedor_nome', 'processo_numero']


# ============================================================
# 8️⃣ ITEM ↔ FORNECEDOR (propostas e vencedores)
# ============================================================

class ItemFornecedorSerializer(serializers.ModelSerializer):
    item_descricao = serializers.CharField(source='item.descricao', read_only=True)
    fornecedor_nome = serializers.CharField(source='fornecedor.nome', read_only=True)

    class Meta:
        model = ItemFornecedor
        fields = [
            'id',
            'item',
            'item_descricao',
            'fornecedor',
            'fornecedor_nome',
            'valor_proposto',
            'vencedor'
        ]
        read_only_fields = ['id', 'item_descricao', 'fornecedor_nome']
