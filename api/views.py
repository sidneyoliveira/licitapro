from rest_framework import viewsets, generics, status
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.views import APIView
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db import transaction
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter

from .models import (
    CustomUser,
    Entidade,
    Orgao,
    ProcessoLicitatorio,
    Lote,
    Item,
    Fornecedor,
    FornecedorProcesso,
    ItemFornecedor
)
from .serializers import (
    UserSerializer,
    EntidadeSerializer,
    OrgaoSerializer,
    ProcessoLicitatorioSerializer,
    LoteSerializer,
    ItemSerializer,
    FornecedorSerializer,
    FornecedorProcessoSerializer,
    ItemFornecedorSerializer
)

# ============================================================
# 1️⃣ ENTIDADE / ÓRGÃO
# ============================================================

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


# ============================================================
# 2️⃣ FORNECEDOR
# ============================================================

class FornecedorViewSet(viewsets.ModelViewSet):
    queryset = Fornecedor.objects.all().order_by('razao_social')
    serializer_class = FornecedorSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [SearchFilter, DjangoFilterBackend]
    search_fields = ['razao_social', 'cnpj']
    filterset_fields = ['cnpj']


# ============================================================
# 3️⃣ PROCESSO LICITATÓRIO
# ============================================================

class ProcessoLicitatorioViewSet(viewsets.ModelViewSet):
    """
    Gerencia os processos licitatórios e expõe actions de:
    - itens do processo
    - fornecedores (adicionar/listar/remover)
    - lotes (listar/criar) e organização de lotes
    """
    queryset = ProcessoLicitatorio.objects.all().order_by('-data_abertura')
    serializer_class = ProcessoLicitatorioSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter]
    search_fields = ['numero_processo', 'numero_certame', 'objeto']
    filterset_fields = ['modalidade', 'situacao', 'entidade', 'orgao']

    # ---------------- ITENS DO PROCESSO ----------------
    @action(detail=True, methods=['get'])
    def itens(self, request, pk=None):
        """
        GET /api/processos/<pk>/itens/
        Retorna todos os itens vinculados a um processo.
        """
        processo = self.get_object()
        itens = Item.objects.filter(processo=processo).select_related('lote', 'fornecedor').order_by('ordem', 'id')
        serializer = ItemSerializer(itens, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    # ---------------- FORNECEDORES (VÍNCULO) ----------------
    @action(detail=True, methods=['post'], url_path='adicionar_fornecedor')
    def adicionar_fornecedor(self, request, pk=None):
        """
        POST /api/processos/<pk>/adicionar_fornecedor/
        Body: { "fornecedor_id": <id> }
        Vincula um fornecedor ao processo.
        """
        processo = self.get_object()
        fornecedor_id = request.data.get('fornecedor_id')

        if not fornecedor_id:
            return Response({'error': 'fornecedor_id é obrigatório.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            fornecedor = Fornecedor.objects.get(id=fornecedor_id)
        except Fornecedor.DoesNotExist:
            return Response({'error': 'Fornecedor não encontrado.'}, status=status.HTTP_404_NOT_FOUND)

        with transaction.atomic():
            obj, created = FornecedorProcesso.objects.get_or_create(processo=processo, fornecedor=fornecedor)
        return Response(
            {
                'detail': 'Fornecedor vinculado ao processo com sucesso!',
                'fornecedor': FornecedorSerializer(fornecedor).data,
                'created': created
            },
            status=status.HTTP_201_CREATED
        )

    @action(detail=True, methods=['get'], url_path='fornecedores')
    def fornecedores(self, request, pk=None):
        """
        GET /api/processos/<pk>/fornecedores/
        Lista fornecedores vinculados a um processo.
        """
        processo = self.get_object()
        fornecedores = Fornecedor.objects.filter(processos__processo=processo).order_by('razao_social')
        serializer = FornecedorSerializer(fornecedores, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='remover_fornecedor')
    def remover_fornecedor(self, request, pk=None):
        """
        POST /api/processos/<pk>/remover_fornecedor/
        Body: { "fornecedor_id": <id> }
        Remove vínculo de fornecedor com o processo.
        """
        processo = self.get_object()
        fornecedor_id = request.data.get('fornecedor_id')

        if not fornecedor_id:
            return Response({'error': 'fornecedor_id é obrigatório.'}, status=status.HTTP_400_BAD_REQUEST)

        deleted, _ = FornecedorProcesso.objects.filter(
            processo=processo, fornecedor_id=fornecedor_id
        ).delete()

        if deleted:
            return Response({'detail': 'Fornecedor removido com sucesso.'}, status=status.HTTP_200_OK)
        return Response({'detail': 'Nenhum vínculo encontrado para remover.'}, status=status.HTTP_404_NOT_FOUND)

    # ---------------- LOTES (NESTED) ----------------
    @action(detail=True, methods=['get', 'post'], url_path='lotes')
    def lotes(self, request, pk=None):
        """
        GET  /api/processos/<pk>/lotes/  -> lista lotes do processo
        POST /api/processos/<pk>/lotes/  -> cria lote(s)

        POST payloads aceitos:
          { "numero": 3, "descricao": "Lote 3" }                      # cria único
          { "descricao": "Auto" }                                     # cria único com próximo número disponível
          [ { "numero": 1, "descricao": "A" }, { "numero": 2, ... } ] # cria vários
          { "quantidade": 5, "descricao_prefixo": "Lote " }           # cria N sequenciais
        """
        processo = self.get_object()

        if request.method.lower() == 'get':
            qs = processo.lotes.order_by('numero')
            return Response(LoteSerializer(qs, many=True).data)

        payload = request.data

        def next_numero():
            ultimo = processo.lotes.order_by('-numero').first()
            return (ultimo.numero + 1) if ultimo else 1

        created = []
        with transaction.atomic():
            # lista explícita
            if isinstance(payload, list):
                for item in payload:
                    n = item.get('numero') or next_numero()
                    d = item.get('descricao', '')
                    obj = Lote.objects.create(processo=processo, numero=n, descricao=d)
                    created.append(obj)

            # por quantidade
            elif isinstance(payload, dict) and 'quantidade' in payload:
                try:
                    qtd = int(payload.get('quantidade') or 0)
                except (TypeError, ValueError):
                    return Response({"detail": "quantidade inválida."}, status=400)
                if qtd <= 0:
                    return Response({"detail": "quantidade deve ser > 0"}, status=400)

                prefixo = payload.get('descricao_prefixo', 'Lote ')
                start = next_numero()
                for i in range(qtd):
                    n = start + i
                    d = f"{prefixo}{n}"
                    obj = Lote.objects.create(processo=processo, numero=n, descricao=d)
                    created.append(obj)

            # único
            elif isinstance(payload, dict):
                n = payload.get('numero') or next_numero()
                d = payload.get('descricao', '')
                obj = Lote.objects.create(processo=processo, numero=n, descricao=d)
                created.append(obj)

            else:
                return Response({"detail": "Payload inválido."}, status=400)

        return Response(LoteSerializer(created, many=True).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['patch'], url_path='lotes/organizar')
    def organizar_lotes(self, request, pk=None):
        """
        PATCH /api/processos/<pk>/lotes/organizar/

        Payloads aceitos:
        1) Renumerar pela ordem de IDs:
           { "ordem_ids": [5, 2, 7], "inicio": 1 }
        2) Normalizar (sem buracos) a partir de 'inicio':
           { "normalizar": true, "inicio": 1 }
        3) Mapear números explicitamente:
           { "mapa": [ {"id": 5, "numero": 10}, {"id": 2, "numero": 11} ] }
        """
        processo = self.get_object()
        data = request.data

        with transaction.atomic():
            # 1) pela ordem enviada
            ordem_ids = data.get('ordem_ids')
            if isinstance(ordem_ids, list) and ordem_ids:
                qs = list(processo.lotes.filter(id__in=ordem_ids))
                id2obj = {o.id: o for o in qs}
                numero = int(data.get('inicio') or 1)
                for _id in ordem_ids:
                    obj = id2obj.get(_id)
                    if obj:
                        obj.numero = numero
                        obj.save(update_fields=['numero'])
                        numero += 1
                out = LoteSerializer(processo.lotes.order_by('numero'), many=True).data
                return Response(out)

            # 2) normalizar
            if data.get('normalizar'):
                inicio = int(data.get('inicio') or 1)
                numero = inicio
                for obj in processo.lotes.order_by('numero', 'id'):
                    if obj.numero != numero:
                        obj.numero = numero
                        obj.save(update_fields=['numero'])
                    numero += 1
                out = LoteSerializer(processo.lotes.order_by('numero'), many=True).data
                return Response(out)

            # 3) mapear id->numero
            mapa = data.get('mapa')
            if isinstance(mapa, list) and mapa:
                ids = [m.get('id') for m in mapa if m.get('id') is not None]
                qs = processo.lotes.filter(id__in=ids)
                id2obj = {o.id: o for o in qs}
                for m in mapa:
                    _id = m.get('id')
                    num = m.get('numero')
                    if _id in id2obj and isinstance(num, int) and num > 0:
                        obj = id2obj[_id]
                        obj.numero = num
                        obj.save(update_fields=['numero'])
                out = LoteSerializer(processo.lotes.order_by('numero'), many=True).data
                return Response(out)

        return Response({"detail": "Payload inválido."}, status=status.HTTP_400_BAD_REQUEST)


# ============================================================
# 4️⃣ LOTE
# ============================================================

class LoteViewSet(viewsets.ModelViewSet):
    queryset = Lote.objects.select_related('processo').all()
    serializer_class = LoteSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ['processo']
    search_fields = ['descricao']


# ============================================================
# 5️⃣ ITEM
# ============================================================

class ItemViewSet(viewsets.ModelViewSet):
    queryset = Item.objects.select_related('processo', 'lote', 'fornecedor').all()
    serializer_class = ItemSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ['processo', 'lote', 'fornecedor']
    search_fields = ['descricao', 'unidade']

    def perform_create(self, serializer):
        # Garante que 'ordem' será sempre calculado no serializer
        serializer.save()

    @action(detail=True, methods=['post'], url_path='definir-fornecedor')
    def definir_fornecedor(self, request, pk=None):
        """
        POST /api/itens/<id>/definir-fornecedor/
        Body: { "fornecedor_id": <id> }
        Vincula um fornecedor ao item.
        """
        item = self.get_object()
        fornecedor_id = request.data.get('fornecedor_id')

        if not fornecedor_id:
            return Response({'error': 'fornecedor_id é obrigatório.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            fornecedor = Fornecedor.objects.get(id=fornecedor_id)
        except Fornecedor.DoesNotExist:
            return Response({'error': 'Fornecedor não encontrado.'}, status=status.HTTP_404_NOT_FOUND)

        item.fornecedor = fornecedor
        item.save(update_fields=['fornecedor'])
        return Response({'detail': 'Fornecedor vinculado ao item com sucesso.'}, status=status.HTTP_200_OK)


# ============================================================
# 6️⃣ FORNECEDOR ↔ PROCESSO (participantes)
# ============================================================

class FornecedorProcessoViewSet(viewsets.ModelViewSet):
    queryset = FornecedorProcesso.objects.select_related('processo', 'fornecedor').all()
    serializer_class = FornecedorProcessoSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ['processo', 'fornecedor']
    # corrigido: campos existentes
    search_fields = ['fornecedor__razao_social', 'fornecedor__cnpj', 'processo__numero_processo', 'processo__numero_certame']


# ============================================================
# 7️⃣ ITEM ↔ FORNECEDOR (propostas)
# ============================================================

class ItemFornecedorViewSet(viewsets.ModelViewSet):
    queryset = ItemFornecedor.objects.select_related('item', 'fornecedor').all()
    serializer_class = ItemFornecedorSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ['item', 'fornecedor', 'vencedor']
    # corrigido: campos existentes
    search_fields = ['item__descricao', 'fornecedor__razao_social', 'fornecedor__cnpj']


# ============================================================
# 8️⃣ REORDENAÇÃO DE ITENS
# ============================================================

class ReorderItensView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, format=None):
        """
        Body: { "item_ids": [ <id1>, <id2>, ... ] }
        Reordena itens atribuindo ordem 1..N segundo a lista enviada.
        """
        item_ids = request.data.get('item_ids', [])
        if not isinstance(item_ids, list):
            return Response({"error": "O corpo deve conter uma lista 'item_ids'."}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            for index, item_id in enumerate(item_ids):
                try:
                    item = Item.objects.get(id=item_id)
                except Item.DoesNotExist:
                    continue
                item.ordem = index + 1
                item.save(update_fields=['ordem'])

        return Response({"status": "Itens reordenados com sucesso."}, status=status.HTTP_200_OK)


# ============================================================
# 9️⃣ USUÁRIOS E DASHBOARD
# ============================================================

class CreateUserView(generics.CreateAPIView):
    queryset = CustomUser.objects.all()
    serializer_class = UserSerializer
    permission_classes = [AllowAny]


class ManageUserView(generics.RetrieveUpdateAPIView):
    """
    GET /me/  -> retorna usuário autenticado
    PUT/PATCH -> atualiza parcialmente (JSON ou multipart para foto)
    """
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user

    def get_serializer_context(self):
        # necessário para montar URL absoluta da imagem
        ctx = super().get_serializer_context()
        ctx['request'] = self.request
        return ctx

    def put(self, request, *args, **kwargs):
        serializer = self.get_serializer(self.get_object(), data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    def patch(self, request, *args, **kwargs):
        serializer = self.get_serializer(self.get_object(), data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class DashboardStatsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, format=None):
        total_processos = ProcessoLicitatorio.objects.count()
        processos_em_andamento = ProcessoLicitatorio.objects.filter(situacao="Em Contratação").count()
        total_fornecedores = Fornecedor.objects.count()
        total_orgaos = Orgao.objects.count()
        total_itens = Item.objects.count()

        data = {
            'total_processos': total_processos,
            'processos_em_andamento': processos_em_andamento,
            'total_fornecedores': total_fornecedores,
            'total_orgaos': total_orgaos,
            'total_itens': total_itens,
        }
        return Response(data)


# ============================================================
# 🔟 LOGIN COM GOOGLE
# ============================================================

from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from rest_framework_simplejwt.tokens import RefreshToken
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

class GoogleLoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        # Token vindo do front via Google Identity Services
        google_token = request.data.get("token")
        logger.info(f"Token recebido: {bool(google_token)}")

        if not google_token:
            return Response({"detail": "Token do Google ausente."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            logger.info("Validando token com Google...")
            id_info = id_token.verify_oauth2_token(
                google_token,
                google_requests.Request(),
                settings.GOOGLE_CLIENT_ID,
            )
            logger.info("Token validado com sucesso!")

            if not id_info.get("email_verified"):
                return Response({"detail": "Email não verificado pelo Google."}, status=status.HTTP_401_UNAUTHORIZED)

            email = id_info.get("email")
            nome = id_info.get("name") or ""
            picture = id_info.get("picture", "")

            if not email:
                return Response({"detail": "E-mail não fornecido pelo Google."}, status=status.HTTP_400_BAD_REQUEST)

            user, created = CustomUser.objects.get_or_create(
                email=email,
                defaults={
                    "username": email,
                    "first_name": nome.split(" ")[0],
                    "last_name": " ".join(nome.split(" ")[1:]),
                }
            )

            refresh = RefreshToken.for_user(user)
            access_token = str(refresh.access_token)

            logger.info(f"Usuário autenticado: {email}")

            return Response({
                "access": access_token,
                "refresh": str(refresh),
                "user": {
                    "id": user.id,
                    "email": user.email,
                    "name": nome,
                    "picture": picture,
                },
                "new_user": created
            }, status=status.HTTP_200_OK)

        except ValueError as e:
            logger.error(f"Token inválido: {e}")
            return Response({"detail": "Token inválido do Google."}, status=status.HTTP_401_UNAUTHORIZED)

        except Exception as e:
            logger.exception("Erro inesperado no login Google")
            return Response({"detail": "Erro no login com Google."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
