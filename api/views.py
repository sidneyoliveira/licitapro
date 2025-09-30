# backend/api/views.py

from rest_framework import viewsets, generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.views import APIView
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework_simplejwt.views import TokenObtainPairView
from .serializers import MyTokenObtainPairSerializer
from .models import ItemProcesso, FornecedorProcesso
from .serializers import ItemProcessoSerializer, FornecedorProcessoSerializer

# Importando Modelos (apenas uma vez)
from .models import (
    ProcessoLicitatorio, 
    Orgao, 
    Fornecedor, 
    Entidade, 
    CustomUser
)

# Importando Serializers (apenas uma vez)
from .serializers import (
    ProcessoSerializer, 
    OrgaoSerializer, 
    FornecedorSerializer, 
    EntidadeSerializer, 
    UserSerializer
)

# Importando a classe de filtro
from .filters import ProcessoFilter


# --- ViewSets para os Modelos Principais ---

class EntidadeViewSet(viewsets.ModelViewSet):
    """
    Fornece uma lista de todos as Entidade.
    ReadOnly porque geralmente não os criamos pela API.
    """
    queryset = Entidade.objects.all().order_by('nome')
    serializer_class = EntidadeSerializer


class OrgaoViewSet(viewsets.ModelViewSet):
    """
    Fornece uma lista de órgãos, com a capacidade de filtrar por Entidade.
    """
    queryset = Orgao.objects.all().order_by('nome')
    serializer_class = OrgaoSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['entidade'] # Permite a filtragem via /api/orgaos/?entidade=1

class FornecedorViewSet(viewsets.ModelViewSet):
    queryset = Fornecedor.objects.all()
    serializer_class = FornecedorSerializer

class ProcessoViewSet(viewsets.ModelViewSet):
    """
    ViewSet principal para Processos Licitatórios, com filtros avançados.
    """
    queryset = ProcessoLicitatorio.objects.select_related('orgao', 'orgao__entidade').all().order_by('-data_cadastro')
    serializer_class = ProcessoSerializer
    filter_backends = [DjangoFilterBackend]
    # Usa a classe de filtro customizada para permitir a busca em múltiplos campos
    filterset_class = ProcessoFilter


# --- Views para Gerenciamento de Usuário ---

class CreateUserView(generics.CreateAPIView):
    """
    Permite o registro de novos usuários.
    """
    queryset = CustomUser.objects.all()
    serializer_class = UserSerializer
    permission_classes = [AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        validated_data = serializer.validated_data
        
        try:
            # Usa o método create_user para garantir a criptografia correta da senha
            user = CustomUser.objects.create_user(
                username=validated_data['username'],
                email=validated_data.get('email', ''),
                password=validated_data['password'],
                first_name=validated_data.get('first_name', ''),
                last_name=validated_data.get('last_name', ''),
                cpf=validated_data.get('cpf'),
                data_nascimento=validated_data.get('data_nascimento')
            )
        except Exception as e:
            return Response({"detail": f"Erro ao criar usuário: {e}"}, status=status.HTTP_400_BAD_REQUEST)

        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

class ManageUserView(generics.RetrieveUpdateAPIView):
    """ 
    Permite que um usuário autenticado veja e atualize seu próprio perfil.
    """
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user


# --- Views Utilitárias ---

class DashboardStatsView(APIView):
    """
    Fornece estatísticas agregadas para a página inicial do dashboard.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, format=None):
        total_processos = ProcessoLicitatorio.objects.count()
        # Corrigido para usar o nome completo da situação, conforme o novo modelo
        processos_em_andamento = ProcessoLicitatorio.objects.filter(situacao='Em Contratação').count()
        total_fornecedores = Fornecedor.objects.count()
        total_orgaos = Orgao.objects.count()

        data = {
            'total_processos': total_processos,
            'processos_em_andamento': processos_em_andamento,
            'total_fornecedores': total_fornecedores,
            'total_orgaos': total_orgaos,
        }
        return Response(data)

class MyTokenObtainPairView(TokenObtainPairView):
    """
    Usa o serializer customizado para incluir os dados do utilizador no token.
    """
    serializer_class = MyTokenObtainPairSerializer


class ItemProcessoViewSet(viewsets.ModelViewSet):
    queryset = ItemProcesso.objects.all()
    serializer_class = ItemProcessoSerializer
    filterset_fields = ['processo'] # Permite buscar itens de um processo específico

class FornecedorProcessoViewSet(viewsets.ModelViewSet):
    queryset = FornecedorProcesso.objects.all()
    serializer_class = FornecedorProcessoSerializer
    filterset_fields = ['processo'] # Permite buscar fornecedores de um processo