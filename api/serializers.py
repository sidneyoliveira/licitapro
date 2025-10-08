# backend/api/serializers.py

from rest_framework import serializers
from django.db import models
from django.db.models import Max
from .models import (
    CustomUser,
    Entidade,
    Orgao,
    ProcessoLicitatorio,
    ItemProcesso,
    Fornecedor,
    ItemFornecedor
)

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = ['id', 'username', 'email', 'first_name', 'last_name']
        read_only_fields = ['id']


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


class ItemProcessoSerializer(serializers.ModelSerializer):
    class Meta:
        model = ItemProcesso
        fields = ['id', 'processo', 'descricao', 'especificacao', 'unidade', 'quantidade', 'ordem']

    def create(self, validated_data):
        # Se não for enviado 'ordem', calcula automaticamente
        if 'ordem' not in validated_data or validated_data['ordem'] is None:
            processo = validated_data['processo']
            last_item = ItemProcesso.objects.filter(processo=processo).order_by('-ordem').first()
            validated_data['ordem'] = (last_item.ordem + 1) if last_item else 1
        return super().create(validated_data)

class FornecedorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Fornecedor
        fields = ['id', 'razao_social', 'cnpj', 'email', 'telefone', 'criado_em']
        read_only_fields = ['id', 'criado_em']

    def validate(self, attrs):
        # validações mínimas: cnpj + razao
        if not attrs.get('razao_social') or not attrs.get('cnpj'):
            raise serializers.ValidationError("Razão social e CNPJ são obrigatórios.")
        return attrs


class ItemFornecedorSerializer(serializers.ModelSerializer):
    item = serializers.PrimaryKeyRelatedField(queryset=ItemProcesso.objects.all())
    fornecedor = serializers.PrimaryKeyRelatedField(queryset=Fornecedor.objects.all())

    class Meta:
        model = ItemFornecedor
        fields = ['id', 'item', 'fornecedor', 'preco_unitario', 'observacao', 'criado_em']
        read_only_fields = ['id', 'criado_em']