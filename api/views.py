# backend/api/views.py

from rest_framework import viewsets, generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.decorators import action
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter
from django.db import IntegrityError

from .models import (
    ProcessoLicitatorio, Orgao, Fornecedor, Entidade, 
    CustomUser, ItemProcesso, ItemCatalogo
)
from .serializers import (
    ProcessoSerializer, OrgaoSerializer, FornecedorSerializer, EntidadeSerializer, 
    UserSerializer, ItemProcessoSerializer, MyTokenObtainPairSerializer, ItemCatalogoSerializer
)
from rest_framework_simplejwt.views import TokenObtainPairView
from .filters import ProcessoFilter

class MyTokenObtainPairView(TokenObtainPairView):
    serializer_class = MyTokenObtainPairSerializer

class EntidadeViewSet(viewsets.ModelViewSet):
    queryset = Entidade.objects.all().order_by('nome')
    serializer_class = EntidadeSerializer
    permission_classes = [IsAuthenticated]

class OrgaoViewSet(viewsets.ModelViewSet):
    queryset = Orgao.objects.all().order_by('nome')
    serializer_class = OrgaoSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['entidade']

class FornecedorViewSet(viewsets.ModelViewSet):
    queryset = Fornecedor.objects.all()
    serializer_class = FornecedorSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter]
    search_fields = ['razao_social', 'cnpj']

class ItemCatalogoViewSet(viewsets.ModelViewSet):
    queryset = ItemCatalogo.objects.all()
    serializer_class = ItemCatalogoSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [SearchFilter]
    search_fields = ['descricao', 'especificacao']

# --- CORREÇÃO PRINCIPAL AQUI ---
class ItemProcessoViewSet(viewsets.ModelViewSet):
    queryset = ItemProcesso.objects.all()
    serializer_class = ItemProcessoSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ['processo']

    def perform_create(self, serializer):
        """ Este método é agora chamado corretamente e define a ordem. """
        processo = serializer.validated_data['processo']
        try:
            ordem_max = ItemProcesso.objects.filter(processo=processo).latest('ordem').ordem
            serializer.save(ordem=ordem_max + 1)
        except ItemProcesso.DoesNotExist:
            serializer.save(ordem=1)

    def create(self, request, *args, **kwargs):
        """ Sobrescreve o create para lidar com a lógica do catálogo de itens. """
        descricao = request.data.get('descricao')
        unidade = request.data.get('unidade')
        especificacao = request.data.get('especificacao', '')
        processo_id = request.data.get('processo')
        quantidade = request.data.get('quantidade')

        if not all([descricao, unidade, processo_id, quantidade]):
            return Response({'error': 'Todos os campos obrigatórios devem ser fornecidos.'}, status=status.HTTP_400_BAD_REQUEST)

        item_catalogo, created = ItemCatalogo.objects.get_or_create(
            descricao=descricao,
            unidade=unidade,
            defaults={'especificacao': especificacao}
        )
        
        data = {
            'processo': processo_id,
            'item_catalogo': item_catalogo.id,
            'quantidade': quantidade
        }

        serializer = self.get_serializer(data=data)
        try:
            serializer.is_valid(raise_exception=True)
            self.perform_create(serializer)
            headers = self.get_success_headers(serializer.data)
            return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)
        except IntegrityError:
             return Response({'error': 'Este item já foi adicionado a este processo.'}, status=status.HTTP_400_BAD_REQUEST)
        except Exception:
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ReorderItensView(APIView):
    permission_classes = [IsAuthenticated]
    def post(self, request, *args, **kwargs):
        item_ids = request.data.get('item_ids', [])
        if not isinstance(item_ids, list):
            return Response({"error": "O corpo do pedido deve conter uma lista de 'item_ids'."}, status=status.HTTP_400_BAD_REQUEST)
        for index, item_id in enumerate(item_ids):
            try:
                item = ItemProcesso.objects.get(id=item_id)
                item.ordem = index + 1
                item.save()
            except ItemProcesso.DoesNotExist:
                continue
        return Response({"status": "Itens reordenados com sucesso."}, status=status.HTTP_200_OK)

class ProcessoViewSet(viewsets.ModelViewSet):
    queryset = ProcessoLicitatorio.objects.select_related('orgao', 'orgao__entidade').all().order_by('-data_processo')
    serializer_class = ProcessoSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_class = ProcessoFilter
    search_fields = ['numero_processo', 'objeto']

    @action(detail=True, methods=['post'])
    def adicionar_fornecedor(self, request, pk=None):
        processo = self.get_object()
        fornecedor_id = request.data.get('fornecedor_id')
        if not fornecedor_id:
            return Response({'error': 'fornecedor_id é obrigatório'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            fornecedor = Fornecedor.objects.get(id=fornecedor_id)
            processo.fornecedores_participantes.add(fornecedor)
            return Response(ProcessoSerializer(processo).data, status=status.HTTP_200_OK)
        except Fornecedor.DoesNotExist:
            return Response({'error': 'Fornecedor não encontrado'}, status=status.HTTP_404_NOT_FOUND)

    @action(detail=True, methods=['post'])
    def remover_fornecedor(self, request, pk=None):
        processo = self.get_object()
        fornecedor_id = request.data.get('fornecedor_id')
        if not fornecedor_id:
            return Response({'error': 'fornecedor_id é obrigatório'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            fornecedor = Fornecedor.objects.get(id=fornecedor_id)
            processo.fornecedores_participantes.remove(fornecedor)
            return Response(ProcessoSerializer(processo).data, status=status.HTTP_200_OK)
        except Fornecedor.DoesNotExist:
            return Response({'error': 'Fornecedor não encontrado'}, status=status.HTTP_404_NOT_FOUND)

class CreateUserView(generics.CreateAPIView):
    queryset = CustomUser.objects.all()
    serializer_class = UserSerializer
    permission_classes = [AllowAny]

class ManageUserView(generics.RetrieveUpdateAPIView):
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]
    def get_object(self):
        return self.request.user

class DashboardStatsView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request, format=None):
        total_processos = ProcessoLicitatorio.objects.count()
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