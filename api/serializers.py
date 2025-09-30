# backend/api/serializers.py

from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from .models import ProcessoLicitatorio, Orgao, Fornecedor, Entidade, CustomUser

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


class EntidadeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Entidade
        fields = '__all__'

# 2. Serializer para Órgão (Atualizado para incluir o nome do entidade)
class OrgaoSerializer(serializers.ModelSerializer):
    # Este campo busca o nome do entidade  relacionado e o inclui na resposta da API
    entidade_nome = serializers.CharField(source='entidade.nome', read_only=True)
    
    class Meta:
        model = Orgao
        fields = ['id', 'nome', 'entidade', 'entidade_nome']

class ItemProcessoSerializer(serializers.ModelSerializer):
    class Meta:
        model = ItemProcesso
        fields = '__all__'

class FornecedorProcessoSerializer(serializers.ModelSerializer):
    class Meta:
        model = FornecedorProcesso
        fields = '__all__'

class ProcessoSerializer(serializers.ModelSerializer):
    # Adiciona os itens e fornecedores diretamente na resposta do processo
    itens = ItemProcessoSerializer(many=True, read_only=True)
    fornecedores = FornecedorProcessoSerializer(many=True, read_only=True)
    orgao_nome = serializers.CharField(source='orgao.nome', read_only=True)
    entidade_nome = serializers.CharField(source='orgao.entidade.nome', read_only=True)
    
    class Meta:
        model = ProcessoLicitatorio
        fields = '__all__' # Inclui todos os campos do modelo, mais os campos customizados acima

class MyTokenObtainPairSerializer(TokenObtainPairSerializer):
    """
    Serializer customizado para o token JWT.
    Adiciona informações extras do utilizador (username, email, first_name) ao token.
    """
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)

        # Adiciona os campos customizados ao "payload" do token
        token['username'] = user.username
        token['email'] = user.email
        token['first_name'] = user.first_name
        # Adicione outros campos que desejar aqui

        return token