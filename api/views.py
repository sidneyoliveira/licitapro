# backend/api/views.py
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from rest_framework import status, viewsets, permissions, parsers, generics, filters
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated, AllowAny, IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter

from urllib import request as urlrequest
from urllib.error import URLError, HTTPError
import json
import re
import logging

import openpyxl
from datetime import datetime, date

from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from rest_framework_simplejwt.tokens import RefreshToken

from .models import (
    CustomUser,
    Entidade,
    Orgao,
    ProcessoLicitatorio,
    Lote,
    Item,
    Fornecedor,
    FornecedorProcesso,
    ItemFornecedor,
    ContratoEmpenho,
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
    ItemFornecedorSerializer,
    ContratoEmpenhoSerializer,
    UsuarioSerializer,
)

logger = logging.getLogger(__name__)
User = get_user_model()

# ============================================================
# 0️⃣ USUÁRIOS (ADMIN)
# ============================================================
class UsuarioViewSet(viewsets.ModelViewSet):
    """
    CRUD de usuários do sistema (apenas staff/admin).
    Aceita JSON, form e multipart (para foto).
    """
    queryset = User.objects.all().order_by("id")
    serializer_class = UsuarioSerializer
    permission_classes = [IsAdminUser]
    filter_backends = [SearchFilter, OrderingFilter]
    parser_classes = [parsers.MultiPartParser, parsers.FormParser, parsers.JSONParser]

    search_fields = ["username", "email", "first_name", "last_name", "cpf", "phone"]
    ordering_fields = [
        "id", "username", "email", "first_name", "last_name",
        "last_login", "date_joined",
    ]
    ordering = ["username"]


# ============================================================
# 1️⃣ ENTIDADE / ÓRGÃO
# ============================================================
class EntidadeViewSet(viewsets.ModelViewSet):
    queryset = Entidade.objects.all().order_by('nome')
    serializer_class = EntidadeSerializer
    permission_classes = [IsAuthenticated]


def _normalize(txt: str) -> str:
    import unicodedata
    if not txt:
        return ""
    txt = unicodedata.normalize("NFD", txt)
    txt = "".join(ch for ch in txt if unicodedata.category(ch) != "Mn")
    return txt.upper().strip()


class OrgaoViewSet(viewsets.ModelViewSet):
    serializer_class = OrgaoSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['entidade']

    def get_queryset(self):
        qs = Orgao.objects.select_related('entidade').order_by('nome')
        entidade_id = self.request.query_params.get('entidade')
        if entidade_id:
            qs = qs.filter(entidade_id=entidade_id)
        return qs

    @action(detail=False, methods=['post'], url_path='importar-pncp')
    def importar_pncp(self, request):
        raw_cnpj = (request.data.get('cnpj') or '').strip()
        cnpj_digits = re.sub(r'\D', '', raw_cnpj)
        if len(cnpj_digits) != 14:
            return Response({"detail": "CNPJ inválido. Informe 14 dígitos."},
                            status=status.HTTP_400_BAD_REQUEST)

        url = f"https://pncp.gov.br/api/pncp/v1/orgaos/{cnpj_digits}/unidades"

        try:
            with urlrequest.urlopen(url, timeout=20) as resp:
                if resp.status != 200:
                    return Response({"detail": f"PNCP respondeu {resp.status}"},
                                    status=status.HTTP_502_BAD_GATEWAY)
                data = json.loads(resp.read().decode('utf-8'))
        except HTTPError as e:
            return Response({"detail": f"Falha ao consultar PNCP: HTTP {e.code}"},
                            status=status.HTTP_502_BAD_GATEWAY)
        except URLError:
            return Response({"detail": "Não foi possível alcançar o PNCP."},
                            status=status.HTTP_502_BAD_GATEWAY)
        except Exception as e:
            return Response({"detail": f"Erro inesperado ao consultar PNCP: {e}"},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        if not isinstance(data, list) or not data:
            return Response({"detail": "Nenhuma unidade retornada pelo PNCP."},
                            status=status.HTTP_404_NOT_FOUND)

        ALLOW_KEYWORDS = ["SECRETARIA", "FUNDO", "CONTROLADORIA", "GABINETE"]
        EXCLUDE_KEYWORDS = ["PREFEITURA"]
        EXCLUDE_CODES = {"000000001", "000000000", "1"}

        def deve_incluir(nome_unidade: str, codigo_unidade: str) -> bool:
            n = _normalize(nome_unidade or "")
            c = (codigo_unidade or "").strip()
            if c in EXCLUDE_CODES:
                return False
            if any(word in n for word in EXCLUDE_KEYWORDS):
                return False
            return any(word in n for word in ALLOW_KEYWORDS)

        def find_entidade_by_cnpj_digits(digits: str):
            for ent in Entidade.objects.all():
                ent_digits = re.sub(r'\D', '', ent.cnpj or '')
                if ent_digits == digits:
                    return ent
            return None

        razao = (data[0].get('orgao') or {}).get('razaoSocial') or ''
        ano_atual = timezone.now().year

        with transaction.atomic():
            entidade = find_entidade_by_cnpj_digits(cnpj_digits)
            if not entidade:
                entidade = Entidade.objects.create(
                    nome=razao or f"Entidade {cnpj_digits}",
                    cnpj=cnpj_digits,
                    ano=ano_atual
                )
            else:
                if razao and entidade.nome != razao:
                    entidade.nome = razao
                    entidade.save(update_fields=['nome'])

            created, updated, ignorados = 0, 0, 0

            for u in data:
                codigo = (u.get('codigoUnidade') or '').strip()
                nome = (u.get('nomeUnidade') or '').strip()
                if not deve_incluir(nome, codigo):
                    ignorados += 1
                    continue

                orgao = None
                if codigo:
                    orgao = Orgao.objects.filter(entidade=entidade, codigo_unidade=codigo).first()
                if not orgao:
                    orgao = Orgao.objects.filter(entidade=entidade, nome__iexact=nome).first()

                if orgao:
                    changed = False
                    if codigo and orgao.codigo_unidade != codigo:
                        orgao.codigo_unidade = codigo
                        changed = True
                    if orgao.nome != nome:
                        orgao.nome = nome
                        changed = True
                    if changed:
                        orgao.save(update_fields=['nome', 'codigo_unidade'])
                        updated += 1
                else:
                    Orgao.objects.create(
                        entidade=entidade,
                        nome=nome,
                        codigo_unidade=codigo or None
                    )
                    created += 1

            orgaos_entidade = Orgao.objects.filter(entidade=entidade).order_by('nome')
            return Response({
                "entidade": {"id": entidade.id, "nome": entidade.nome, "cnpj": entidade.cnpj, "ano": entidade.ano},
                "created": created, "updated": updated, "ignored": ignorados,
                "total_orgaos_entidade": orgaos_entidade.count(),
                "orgaos": OrgaoSerializer(orgaos_entidade, many=True).data
            }, status=status.HTTP_200_OK)


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
# 3️⃣ PROCESSO LICITATÓRIO (+ IMPORTAÇÕES)
# ============================================================
class ProcessoLicitatorioViewSet(viewsets.ModelViewSet):
    """
    Gerencia processos licitatórios e expõe actions auxiliares:
    - itens
    - fornecedores (adicionar/listar/remover)
    - lotes (listar/criar) e organização de lotes
    - importar-xlsx (POST multipart)
    - importar (POST JSON em lote)
    """
    queryset = (
        ProcessoLicitatorio.objects
        .select_related('entidade', 'orgao')
        .all()
        .order_by('-data_abertura')
    )
    serializer_class = ProcessoLicitatorioSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter]
    search_fields = ['numero_processo', 'numero_certame', 'objeto']
    filterset_fields = ['modalidade', 'situacao', 'entidade', 'orgao']
    parser_classes = [parsers.MultiPartParser, parsers.FormParser, parsers.JSONParser]

    # ---------------- ITENS DO PROCESSO ----------------
    @action(detail=True, methods=['get'])
    def itens(self, request, *args, **kwargs):
        processo = self.get_object()
        itens = (
            Item.objects
            .filter(processo=processo)
            .select_related('lote', 'fornecedor')
            .order_by('ordem', 'id')
        )
        serializer = ItemSerializer(itens, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    # ---------------- FORNECEDORES (VÍNCULO) ----------------
    @action(detail=True, methods=['post'], url_path='adicionar_fornecedor')
    def adicionar_fornecedor(self, request, *args, **kwargs):
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
    def fornecedores(self, request, *args, **kwargs):
        processo = self.get_object()
        fornecedores = Fornecedor.objects.filter(processos__processo=processo).order_by('razao_social')
        serializer = FornecedorSerializer(fornecedores, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='remover_fornecedor')
    def remover_fornecedor(self, request, *args, **kwargs):
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
    def lotes(self, request, *args, **kwargs):
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
    def organizar_lotes(self, request, *args, **kwargs):
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

    # ---------------- IMPORTAÇÃO XLSX ----------------
    @action(detail=False, methods=['post'], url_path='importar-xlsx',
            parser_classes=[parsers.MultiPartParser, parsers.FormParser])
    def importar_xlsx(self, request, *args, **kwargs):
        """
        Envie multipart/form-data com:
          - file: <arquivo.xlsx>
        A primeira linha deve conter cabeçalhos. Os nomes serão normalizados
        (lowercase) e usados como chaves diretas no serializer.
        """
        arquivo = request.FILES.get('file') or request.FILES.get('xlsx')
        if not arquivo:
            return Response({'detail': 'Envie o arquivo XLSX no campo "file".'}, status=400)

        try:
            wb = openpyxl.load_workbook(arquivo, data_only=True)
            ws = wb.active
        except Exception as e:
            return Response({'detail': f'Não foi possível ler o XLSX: {e}'}, status=400)

        rows = list(ws.iter_rows(values_only=True))
        if not rows or len(rows) < 2:
            return Response({'detail': 'Planilha sem dados.'}, status=400)

        header = [str(c).strip().lower() if c is not None else "" for c in rows[0]]

        def normalize_cell(v):
            if isinstance(v, (datetime, date)):
                # to ISO date
                try:
                    return v.date().isoformat()
                except Exception:
                    return v.isoformat()
            return v

        dados = []
        for i in range(1, len(rows)):
            line = rows[i]
            if not line:
                continue
            item = {}
            for idx, col in enumerate(header):
                if not col:
                    continue
                val = normalize_cell(line[idx]) if idx < len(line) else None
                if val is None or val == "":
                    continue
                item[col] = val
            # Exemplo de aliases comuns (opcional)
            if 'numero' in item and 'numero_processo' not in item:
                item['numero_processo'] = item.pop('numero')
            if 'data_certame' in item and 'data_abertura' not in item:
                # se seu serializer usa data_abertura, ajuste conforme sua modelagem
                pass
            dados.append(item)

        if not dados:
            return Response({'detail': 'Nenhuma linha válida encontrada.'}, status=400)

        ser = ProcessoLicitatorioSerializer(data=dados, many=True)
        ser.is_valid(raise_exception=True)
        with transaction.atomic():
            instances = ser.save()

        return Response(
            {
                'importados': len(instances),
                'objetos': ProcessoLicitatorioSerializer(instances, many=True).data
            },
            status=status.HTTP_201_CREATED
        )

    # ---------------- IMPORTAÇÃO JSON ----------------
    @action(detail=False, methods=['post'], url_path='importar',
            parser_classes=[parsers.JSONParser])
    def importar_json(self, request, *args, **kwargs):
        """
        Envie uma LISTA JSON de processos para importação em lote.
        """
        if not isinstance(request.data, list):
            return Response({'detail': 'Envie uma LISTA JSON.'}, status=400)

        ser = ProcessoLicitatorioSerializer(data=request.data, many=True)
        ser.is_valid(raise_exception=True)
        with transaction.atomic():
            instances = ser.save()
        return Response(ProcessoLicitatorioSerializer(instances, many=True).data, status=201)


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
        serializer.save()

    @action(detail=True, methods=['post'], url_path='definir-fornecedor')
    def definir_fornecedor(self, request, *args, **kwargs):
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
    search_fields = [
        'fornecedor__razao_social', 'fornecedor__cnpj',
        'processo__numero_processo', 'processo__numero_certame'
    ]


# ============================================================
# 7️⃣ ITEM ↔ FORNECEDOR (propostas)
# ============================================================
class ItemFornecedorViewSet(viewsets.ModelViewSet):
    queryset = ItemFornecedor.objects.select_related('item', 'fornecedor').all()
    serializer_class = ItemFornecedorSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ['item', 'fornecedor', 'vencedor']
    search_fields = ['item__descricao', 'fornecedor__razao_social', 'fornecedor__cnpj']


# ============================================================
# 8️⃣ REORDENAÇÃO DE ITENS
# ============================================================
class ReorderItensView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, _format=None):
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
# 9️⃣ USUÁRIO AUTENTICADO (perfil /me/)
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
    parser_classes = [parsers.MultiPartParser, parsers.FormParser, parsers.JSONParser]

    def get_object(self):
        return self.request.user

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx['request'] = self.request  # para URLs absolutas da foto
        return ctx

    def put(self, request, *_, **__):
        serializer = self.get_serializer(self.get_object(), data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    def patch(self, request, *_, **__):
        serializer = self.get_serializer(self.get_object(), data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


# ============================================================
# 🔟 DASHBOARD
# ============================================================
class DashboardStatsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, _request, _format=None):
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
# 1️⃣1️⃣ LOGIN COM GOOGLE
# ============================================================
class GoogleLoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
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


# ============================================================
# 1️⃣2️⃣ CONTRATO/EMPENHO
# ============================================================
class ContratoEmpenhoViewSet(viewsets.ModelViewSet):
    queryset = ContratoEmpenho.objects.select_related('processo').all().order_by('-criado_em', 'id')
    serializer_class = ContratoEmpenhoSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ['processo', 'ano_contrato', 'tipo_contrato_id', 'categoria_processo_id', 'receita']
    search_fields = ['numero_contrato_empenho', 'processo__numero_processo', 'ni_fornecedor']
