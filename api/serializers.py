# backend/api/serializers.py

from rest_framework import serializers
from .models import (
    ProcessoLicitatorio, Orgao, Fornecedor, Entidade, CustomUser, ItemProcesso
)

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

class ItemProcessoSerializer(serializers.ModelSerializer):
    class Meta:
        model = ItemProcesso
        fields = '__all__'

class ProcessoSerializer(serializers.ModelSerializer):
    itens = ItemProcessoSerializer(many=True, read_only=True)
    fornecedores_participantes = FornecedorSerializer(many=True, read_only=True)
    orgao_nome = serializers.CharField(source='orgao.nome', read_only=True)
    entidade_nome = serializers.CharField(source='orgao.entidade.nome', read_only=True)

    class Meta:
        model = ProcessoLicitatorio
        fields = '__all__'