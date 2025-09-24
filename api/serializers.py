# backend/api/serializers.py

from rest_framework import serializers
from .models import ProcessoLicitatorio, Orgao, Fornecedor, Municipio, CustomUser

# Serializer para o modelo de usuário
class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = ['id', 'username', 'email', 'password', 'first_name', 'last_name', 'cpf', 'data_nascimento']
        extra_kwargs = {'password': {'write_only': True}}

# Serializer para o modelo de fornecedor
class FornecedorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Fornecedor
        fields = '__all__'


class MunicipioSerializer(serializers.ModelSerializer):
    class Meta:
        model = Municipio
        fields = '__all__'

# 2. Serializer para Órgão (Atualizado para incluir o nome do município)
class OrgaoSerializer(serializers.ModelSerializer):
    # Este campo busca o nome do município relacionado e o inclui na resposta da API
    municipio_nome = serializers.CharField(source='municipio.nome', read_only=True)
    
    class Meta:
        model = Orgao
        fields = ['id', 'nome', 'municipio', 'municipio_nome']

# 3. Serializer para Processo (Atualizado para incluir nomes em vez de IDs)
class ProcessoSerializer(serializers.ModelSerializer):
    # Estes campos retornam informações legíveis para o frontend
    orgao_nome = serializers.CharField(source='orgao.nome', read_only=True)
    municipio_nome = serializers.CharField(source='orgao.municipio.nome', read_only=True)
    
    class Meta:
        model = ProcessoLicitatorio
        fields = '__all__' # Inclui todos os campos do modelo, mais os campos customizados acima