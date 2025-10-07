# backend/api/serializers.py
from rest_framework import serializers
from .models import *

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = ['id', 'username', 'email', 'password', 'first_name', 'last_name']
        extra_kwargs = {'password': {'write_only': True}}

class EntidadeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Entidade
        fields = '__all__'

class OrgaoSerializer(serializers.ModelSerializer):
    entidade_nome = serializers.CharField(source='entidade.nome', read_only=True)
    class Meta:
        model = Orgao
        fields = '__all__'

class ItemProcessoSerializer(serializers.ModelSerializer):
    class Meta:
        model = ItemProcesso
        fields = '__all__'

class FornecedorProcessoSerializer(serializers.ModelSerializer):
    class Meta:
        model = FornecedorProcesso
        fields = '__all__'

class ProcessoSerializer(serializers.ModelSerializer):
    itens = ItemProcessoSerializer(many=True, read_only=True)
    fornecedores = FornecedorProcessoSerializer(many=True, read_only=True)
    orgao_nome = serializers.CharField(source='orgao.nome', read_only=True)
    entidade_nome = serializers.CharField(source='orgao.entidade.nome', read_only=True)
    
    class Meta:
        model = ProcessoLicitatorio
        fields = '__all__'