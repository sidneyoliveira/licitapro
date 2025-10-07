# backend/api/serializers.py

from rest_framework import serializers
from .models import (
    CustomUser,
    Entidade,
    Orgao,
    ProcessoLicitatorio,
    ItemProcesso,
    Fornecedor,
    ItemFornecedor
)
from django.db import models

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
    processo = serializers.PrimaryKeyRelatedField(queryset=ProcessoLicitatorio.objects.all())
    class Meta:
        model = ItemProcesso
        fields = ['id', 'processo', 'descricao', 'especificacao', 'unidade', 'quantidade', 'ordem']
        read_only_fields = ['id', 'ordem']

    def validate_quantidade(self, value):
        if value is None or value <= 0:
            raise serializers.ValidationError("Quantidade deve ser maior que zero.")
        return value

    def create(self, validated_data):
        # estabelece ordem sequencial dentro do processo
        processo = validated_data['processo']
        max_ordem = ItemProcesso.objects.filter(processo=processo).aggregate(models.Max('ordem'))['ordem__max'] or 0
        validated_data['ordem'] = max_ordem + 1
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
