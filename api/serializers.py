# backend/api/serializers.py

from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from .models import (
    ProcessoLicitatorio, Orgao, Fornecedor, Entidade, 
    CustomUser, ItemProcesso, ItemCatalogo  # ItemCatalogo foi adicionado aqui
)

# --- SERIALIZER CUSTOMIZADO PARA O TOKEN (ESSENCIAL) ---
class MyTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        # Adiciona informações extras do utilizador ao token
        token['username'] = user.username
        token['email'] = user.email
        token['first_name'] = user.first_name
        return token

# --- OUTROS SERIALIZERS ---
class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = ['id', 'username', 'email', 'password', 'first_name', 'last_name', 'cpf', 'data_nascimento']
        extra_kwargs = {'password': {'write_only': True}}

class FornecedorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Fornecedor
        fields = '__all__'

class EntidadeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Entidade
        fields = ['id', 'nome', 'cnpj', 'ano']

class OrgaoSerializer(serializers.ModelSerializer):
    entidade_nome = serializers.CharField(source='entidade.nome', read_only=True)
    
    class Meta:
        model = Orgao
        fields = ['id', 'nome', 'entidade', 'entidade_nome']

class ItemCatalogoSerializer(serializers.ModelSerializer):
    class Meta:
        model = ItemCatalogo
        fields = '__all__'

class ItemProcessoSerializer(serializers.ModelSerializer):
    descricao = serializers.CharField(source='item_catalogo.descricao', read_only=True)
    unidade = serializers.CharField(source='item_catalogo.unidade', read_only=True)
    especificacao = serializers.CharField(source='item_catalogo.especificacao', read_only=True)
    
    class Meta:
        model = ItemProcesso
        fields = ['id', 'processo', 'item_catalogo', 'quantidade', 'ordem', 'descricao', 'unidade', 'especificacao']

class ProcessoSerializer(serializers.ModelSerializer):
    itens_do_processo = ItemProcessoSerializer(many=True, read_only=True)
    fornecedores_participantes = FornecedorSerializer(many=True, read_only=True)
    orgao_nome = serializers.CharField(source='orgao.nome', read_only=True)
    entidade_nome = serializers.CharField(source='orgao.entidade.nome', read_only=True)

    class Meta:
        model = ProcessoLicitatorio
        fields = '__all__'
