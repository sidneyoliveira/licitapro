# backend/api/views.py

from rest_framework import viewsets, generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.decorators import action
from django_filters.rest_framework import DjangoFilterBackend

from .models import (
    ProcessoLicitatorio, Orgao, Fornecedor, Entidade, 
    CustomUser, ItemProcesso
)
from .serializers import (
    ProcessoSerializer, OrgaoSerializer, FornecedorSerializer, EntidadeSerializer, 
    UserSerializer, ItemProcessoSerializer, MyTokenObtainPairSerializer
)
from rest_framework_simplejwt.views import TokenObtainPairView
from .filters import ProcessoFilter

class MyTokenObtainPairView(TokenObtainPairView):
    serializer_class = MyTokenObtainPairSerializer

class EntidadeViewSet(viewsets.ModelViewSet):
    queryset = Entidade.objects.all().order_by('nome')
    serializer_class = EntidadeSerializer

class OrgaoViewSet(viewsets.ModelViewSet):
    queryset = Orgao.objects.all().order_by('nome')
    serializer_class = OrgaoSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['entidade']

class FornecedorViewSet(viewsets.ModelViewSet):
    """ ViewSet para o catálogo geral de fornecedores. """
    queryset = Fornecedor.objects.all()
    serializer_class = FornecedorSerializer

class ItemProcessoViewSet(viewsets.ModelViewSet):
    queryset = ItemProcesso.objects.all()
    serializer_class = ItemProcessoSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['processo']

class ProcessoViewSet(viewsets.ModelViewSet):
    queryset = ProcessoLicitatorio.objects.select_related('orgao', 'orgao__entidade').all().order_by('-data_processo')
    serializer_class = ProcessoSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_class = ProcessoFilter

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