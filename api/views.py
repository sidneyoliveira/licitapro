# backend/api/views.py

from rest_framework import viewsets, generics, serializers
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.views import APIView
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db import transaction, IntegrityError
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter

from .models import (
    CustomUser, Entidade, Orgao, ProcessoLicitatorio,
    ItemProcesso, Fornecedor, ItemFornecedor
)
from .serializers import (
    UserSerializer, EntidadeSerializer, OrgaoSerializer,
    ItemProcessoSerializer, FornecedorSerializer, ItemFornecedorSerializer
)


# -------------------------------
# ENTIDADES E ORGÃOS
# -------------------------------
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


# -------------------------------
# FORNECEDORES
# -------------------------------
class FornecedorViewSet(viewsets.ModelViewSet):
    queryset = Fornecedor.objects.all()
    serializer_class = FornecedorSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [SearchFilter, DjangoFilterBackend]
    search_fields = ['razao_social', 'cnpj']


# -------------------------------
# ITENS DO PROCESSO
# -------------------------------
class ItemProcessoViewSet(viewsets.ModelViewSet):
    queryset = ItemProcesso.objects.select_related('processo').all()
    serializer_class = ItemProcessoSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ['processo']
    search_fields = ['descricao', 'especificacao']

    def perform_create(self, serializer):
        processo = serializer.validated_data.get('processo')
        if not processo:
            serializer.save()
            return

        # Pega a última ordem do processo e soma 1
        with transaction.atomic():
            last_item = ItemProcesso.objects.filter(processo=processo).order_by('-ordem').first()
            nova_ordem = last_item.ordem + 1 if last_item else 1
            serializer.validated_data['ordem'] = nova_ordem
            try:
                serializer.save()
            except IntegrityError:
                raise serializers.ValidationError({
                    "non_field_errors": ["Já existe um item com esta ordem para este processo."]
                })


# -------------------------------
# PROCESSOS
# -------------------------------
class ProcessoViewSet(viewsets.ModelViewSet):
    queryset = ProcessoLicitatorio.objects.select_related('orgao', 'orgao__entidade').prefetch_related('itens').all().order_by('-data_processo')
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter]
    search_fields = ['numero_processo', 'objeto']

    def get_serializer_class(self):
        from .serializers import ItemProcessoSerializer, FornecedorSerializer

        class ProcessoSerializer(serializers.ModelSerializer):
            itens = ItemProcessoSerializer(many=True, read_only=True)
            fornecedores = FornecedorSerializer(many=True, read_only=True, source='fornecedores_related')
            orgao_nome = serializers.CharField(source='orgao.nome', read_only=True)
            entidade_nome = serializers.CharField(source='orgao.entidade.nome', read_only=True)

            class Meta:
                model = ProcessoLicitatorio
                fields = '__all__'

        return ProcessoSerializer

    @action(detail=True, methods=['post'])
    def adicionar_fornecedor(self, request, pk=None):
        processo = self.get_object()
        fornecedor_id = request.data.get('fornecedor_id')
        item_id = request.data.get('item_id')

        if not fornecedor_id:
            return Response({"error": "fornecedor_id é obrigatório."}, status=400)
        try:
            fornecedor = Fornecedor.objects.get(id=fornecedor_id)
        except Fornecedor.DoesNotExist:
            return Response({"error": "Fornecedor não encontrado."}, status=404)

        if item_id:
            try:
                item = ItemProcesso.objects.get(id=item_id, processo=processo)
            except ItemProcesso.DoesNotExist:
                return Response({"error": "Item não encontrado para este processo."}, status=404)
            try:
                with transaction.atomic():
                    obj, created = ItemFornecedor.objects.get_or_create(item=item, fornecedor=fornecedor)
                    return Response({"detail": "Fornecedor vinculado ao item.", "created": created}, status=201)
            except IntegrityError:
                return Response({"error": "Vínculo já existe."}, status=400)
        return Response({"detail": "Solicitação registrada. Fornecedor associado ao processo."}, status=200)

    @action(detail=True, methods=['post'])
    def remover_fornecedor(self, request, pk=None):
        processo = self.get_object()
        fornecedor_id = request.data.get('fornecedor_id')
        if not fornecedor_id:
            return Response({"error": "fornecedor_id é obrigatório."}, status=400)

        itens = ItemProcesso.objects.filter(processo=processo)
        deleted = ItemFornecedor.objects.filter(item__in=itens, fornecedor_id=fornecedor_id).delete()
        return Response({"detail": "Vínculos removidos.", "deleted": deleted[0]}, status=200)


# -------------------------------
# REORDENAR ITENS
# -------------------------------
class ReorderItensView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, format=None):
        item_ids = request.data.get('item_ids', [])
        if not isinstance(item_ids, list):
            return Response({"error": "'item_ids' deve ser uma lista."}, status=400)

        with transaction.atomic():
            for index, item_id in enumerate(item_ids):
                try:
                    item = ItemProcesso.objects.select_for_update().get(id=item_id)
                    item.ordem = index + 1
                    item.save(update_fields=['ordem'])
                except ItemProcesso.DoesNotExist:
                    continue

        return Response({"status": "Itens reordenados com sucesso."}, status=200)


# -------------------------------
# USUÁRIOS
# -------------------------------
class CreateUserView(generics.CreateAPIView):
    queryset = CustomUser.objects.all()
    serializer_class = UserSerializer
    permission_classes = [AllowAny]


class ManageUserView(generics.RetrieveUpdateAPIView):
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user


# -------------------------------
# DASHBOARD
# -------------------------------
class DashboardStatsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, format=None):
        total_processos = ProcessoLicitatorio.objects.count()
        processos_em_andamento = ProcessoLicitatorio.objects.filter(situacao=ProcessoLicitatorio.Situacao.EM_CONTRATACAO).count()
        total_fornecedores = Fornecedor.objects.count()
        total_orgaos = Orgao.objects.count()
        return Response({
            'total_processos': total_processos,
            'processos_em_andamento': processos_em_andamento,
            'total_fornecedores': total_fornecedores,
            'total_orgaos': total_orgaos,
        })
