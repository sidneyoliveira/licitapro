# backend/api/views.py

from rest_framework import viewsets, generics, status, serializers
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.views import APIView
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db import IntegrityError, transaction
from django.db.models import Max
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter

from rest_framework_simplejwt.views import TokenObtainPairView

from .models import (
    CustomUser,
    Entidade,
    Orgao,
    ProcessoLicitatorio,
    ItemProcesso,
    Fornecedor,
    ItemFornecedor
)
from .serializers import (
    UserSerializer,
    EntidadeSerializer,
    OrgaoSerializer,
    ItemProcessoSerializer,
    FornecedorSerializer,
    ItemFornecedorSerializer
)


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
    filter_backends = [SearchFilter, DjangoFilterBackend]
    search_fields = ['razao_social', 'cnpj']


class ItemProcessoViewSet(viewsets.ModelViewSet):
    queryset = ItemProcesso.objects.select_related('processo').all()
    serializer_class = ItemProcessoSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ['processo']
    search_fields = ['descricao', 'especificacao']

    def perform_create(self, serializer):
        # serializer.create já cuida da ordem, por causa do create no serializer
        return serializer.save()

    def partial_update(self, request, *args, **kwargs):
        # permitir atualizar quantidade/especificacao sem tocar ordem automaticamente
        return super().partial_update(request, *args, **kwargs)


class ProcessoViewSet(viewsets.ModelViewSet):
    """
    Exponha processos com nested itens e fornecedores.
    Também provê actions para adicionar/remover fornecedor a um processo.
    """
    queryset = ProcessoLicitatorio.objects.all().order_by('-data_processo')
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter]
    search_fields = ['numero_processo', 'objeto']

    # serializer dinâmico: queremos incluir itens e fornecedores
    def get_serializer_class(self):
        # import aqui para evitar ciclos
        from .serializers import EntidadeSerializer, OrgaoSerializer, ItemProcessoSerializer, FornecedorSerializer
        # cria um serializer dinâmico para incluir nested
        class _ProcessoSerializer(serializers.ModelSerializer):
            itens = ItemProcessoSerializer(many=True, read_only=True)
            fornecedores = FornecedorSerializer(many=True, read_only=True, source='fornecedor_set')
            orgao_nome = serializers.CharField(source='orgao.nome', read_only=True)
            entidade_nome = serializers.CharField(source='orgao.entidade.nome', read_only=True)

            class Meta:
                model = ProcessoLicitatorio
                fields = '__all__'

        # mas para simplicidade, se o módulo serializer já define algo, importar e usar
        from .serializers import EntidadeSerializer as _E  # noqa
        # fallback para o serializer "processo custom" manualmente definido abaixo
        # porém para evitar ambiguidade, usaremos um explicit serializer class:
        from .serializers import ItemProcessoSerializer as _IPS  # noqa

        # We'll create and return a simple serializer built inline to ensure items are nested.
        # Simpler: reuse a minimal serializer class constructed here:
        class ProcessoSerializerForViews(serializers.ModelSerializer):
            itens = ItemProcessoSerializer(many=True, read_only=True)
            fornecedores = FornecedorSerializer(many=True, read_only=True, source='fornecedores_related')
            orgao_nome = serializers.CharField(source='orgao.nome', read_only=True)
            entidade_nome = serializers.CharField(source='orgao.entidade.nome', read_only=True)

            class Meta:
                model = ProcessoLicitatorio
                fields = '__all__'

        # To avoid complexity return a stable serializer defined below: fallback to ProcessoLicitatorio default
        # But for reliability, return ProcessoSerializerForViews
        return ProcessoSerializerForViews

    def get_queryset(self):
        # inclui select_related para performace
        return ProcessoLicitatorio.objects.select_related('orgao', 'orgao__entidade').prefetch_related('itens').all().order_by('-data_processo')

    @action(detail=True, methods=['post'], url_path='adicionar_fornecedor')
    def adicionar_fornecedor(self, request, pk=None):
        """
        Vincula um fornecedor existente ao processo.
        Se você quiser vincular criando fornecedor, use /fornecedores/ primeiro.
        """
        processo = self.get_object()
        fornecedor_id = request.data.get('fornecedor_id')
        if not fornecedor_id:
            return Response({'error': 'fornecedor_id é obrigatório.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            fornecedor = Fornecedor.objects.get(id=fornecedor_id)
        except Fornecedor.DoesNotExist:
            return Response({'error': 'Fornecedor não encontrado.'}, status=status.HTTP_404_NOT_FOUND)
        item_id = request.data.get('item_id')
        if item_id:
            try:
                item = ItemProcesso.objects.get(id=item_id, processo=processo)
            except ItemProcesso.DoesNotExist:
                return Response({'error': 'Item não encontrado para este processo.'}, status=status.HTTP_404_NOT_FOUND)
            try:
                with transaction.atomic():
                    obj, created = ItemFornecedor.objects.get_or_create(item=item, fornecedor=fornecedor)
                    return Response({'detail': 'Fornecedor vinculado ao item com sucesso.', 'created': created}, status=status.HTTP_201_CREATED)
            except IntegrityError:
                return Response({'error': 'Vínculo já existe.'}, status=status.HTTP_400_BAD_REQUEST)
        else:
            # Sem item_id: envia OK. Frontend deverá depois associar fornecedores ao processo lendo /fornecedores/
            return Response({'detail': 'Solicitação registrada. Fornecedor: OK.'}, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='remover_fornecedor')
    def remover_fornecedor(self, request, pk=None):
        processo = self.get_object()
        fornecedor_id = request.data.get('fornecedor_id')
        if not fornecedor_id:
            return Response({'error': 'fornecedor_id é obrigatório.'}, status=status.HTTP_400_BAD_REQUEST)

        # remove vínculos ItemFornecedor relacionados aos itens do processo para esse fornecedor
        itens_do_processo = ItemProcesso.objects.filter(processo=processo)
        deleted = ItemFornecedor.objects.filter(item__in=itens_do_processo, fornecedor_id=fornecedor_id).delete()
        return Response({'detail': 'Vínculos removidos (se existiam).', 'deleted': deleted[0]}, status=status.HTTP_200_OK)


# class ReorderItensView(APIView):
#     permission_classes = [IsAuthenticated]

#     def post(self, request, format=None):
#         item_ids = request.data.get('item_ids', [])
#         if not isinstance(item_ids, list):
#             return Response({"error": "O corpo do pedido deve conter uma lista de 'item_ids'."}, status=status.HTTP_400_BAD_REQUEST)

#         with transaction.atomic():
#             # Passo 1: aplica um offset temporário para evitar conflito
#             for index, item_id in enumerate(item_ids):
#                 try:
#                     item = ItemProcesso.objects.get(id=item_id)
#                 except ItemProcesso.DoesNotExist:
#                     continue
#                 item.ordem = index + 1000  # valor temporário
#                 item.save(update_fields=['ordem'])

#             # Passo 2: aplica valores finais
#             for index, item_id in enumerate(item_ids):
#                 item = ItemProcesso.objects.get(id=item_id)
#                 item.ordem = index + 1
#                 item.save(update_fields=['ordem'])

#         return Response({"status": "Itens reordenados com sucesso."}, status=status.HTTP_200_OK)


# NOVA VIEW DE REORDENAÇÃO -------------------------
class ReorderItemView(APIView):
    """
    Reordena os itens de um processo, movendo um item específico para a posição desejada.
    Exemplo de payload:
    {
        "processo_id": 3,
        "item_id": 10,
        "nova_ordem": 2
    }
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, format=None):
        processo_id = request.data.get('processo_id')
        item_id = request.data.get('item_id')
        nova_ordem = request.data.get('nova_ordem')

        if not all([processo_id, item_id, nova_ordem]):
            return Response(
                {"error": "Campos 'processo_id', 'item_id' e 'nova_ordem' são obrigatórios."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            nova_ordem = int(nova_ordem)
        except ValueError:
            return Response({"error": "nova_ordem deve ser um número inteiro."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            itens = list(ItemProcesso.objects.filter(processo_id=processo_id).order_by('ordem'))
            item = next((i for i in itens if i.id == item_id), None)
            if not item:
                return Response({"error": "Item não encontrado."}, status=status.HTTP_404_NOT_FOUND)

            # Remove o item e insere na nova posição
            itens.remove(item)
            itens.insert(nova_ordem - 1, item)

            # Reatribui as ordens
            with transaction.atomic():
                for idx, i in enumerate(itens, start=1):
                    ItemProcesso.objects.filter(id=i.id).update(ordem=idx)

            return Response({"success": True, "message": "Itens reordenados com sucesso."}, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
# ---------------------------------------------------



# Usuários
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
        processos_em_andamento = ProcessoLicitatorio.objects.filter(situacao=ProcessoLicitatorio.Situacao.EM_CONTRATACAO).count()
        total_fornecedores = Fornecedor.objects.count()
        total_orgaos = Orgao.objects.count()

        data = {
            'total_processos': total_processos,
            'processos_em_andamento': processos_em_andamento,
            'total_fornecedores': total_fornecedores,
            'total_orgaos': total_orgaos,
        }
        return Response(data)