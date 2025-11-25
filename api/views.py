# api/views.py

import logging
import json
import re
from urllib import request as urlrequest
from urllib.error import URLError, HTTPError

from django.db import transaction
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.contrib.auth.models import update_last_login
from django.conf import settings

from rest_framework import viewsets, permissions, filters, status, parsers, generics
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from django_filters.rest_framework import DjangoFilterBackend
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from rest_framework_simplejwt.tokens import RefreshToken

from .services import PNCPService 

# Imports Locais
from .models import (
    CustomUser, Entidade, Orgao, ProcessoLicitatorio, Lote, Item,
    Fornecedor, FornecedorProcesso, ItemFornecedor, ContratoEmpenho
)
from .serializers import (
    UserSerializer, EntidadeSerializer, OrgaoSerializer,
    ProcessoLicitatorioSerializer, LoteSerializer, ItemSerializer,
    FornecedorSerializer, FornecedorProcessoSerializer,
    ItemFornecedorSerializer, ContratoEmpenhoSerializer, UsuarioSerializer
)
from .services import ImportacaoService  # Serviço criado anteriormente

User = get_user_model()
logger = logging.getLogger(__name__)

GOOGLE_CLIENT_ID = getattr(settings, 'GOOGLE_CLIENT_ID', '') 
# ============================================================
# 👤 USUÁRIOS
# ============================================================

class UsuarioViewSet(viewsets.ModelViewSet):
    """
    CRUD de usuários do sistema.
    Acesso restrito a staff/admin.
    """
    queryset = User.objects.all().order_by("id")
    serializer_class = UsuarioSerializer
    permission_classes = [permissions.IsAdminUser]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    parser_classes = [parsers.MultiPartParser, parsers.FormParser, parsers.JSONParser]
    search_fields = ["username", "email", "first_name", "last_name"]
    ordering_fields = ["id", "username", "email", "first_name", "last_name", "last_login", "date_joined"]
    ordering = ["username"]


class CreateUserView(generics.CreateAPIView):
    queryset = CustomUser.objects.all()
    serializer_class = UserSerializer
    permission_classes = [permissions.AllowAny]


class ManageUserView(generics.RetrieveUpdateAPIView):
    """
    GET /me/  -> retorna usuário autenticado
    PUT/PATCH -> atualiza parcialmente
    """
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx['request'] = self.request
        return ctx


# ============================================================
# 1️⃣ ENTIDADE / ÓRGÃO
# ============================================================

class EntidadeViewSet(viewsets.ModelViewSet):
    queryset = Entidade.objects.all().order_by('nome')
    serializer_class = EntidadeSerializer
    permission_classes = [permissions.IsAuthenticated]


class OrgaoViewSet(viewsets.ModelViewSet):
    serializer_class = OrgaoSerializer
    permission_classes = [permissions.IsAuthenticated]
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
        """
        Consulta API do PNCP para importar Órgãos vinculados a um CNPJ.
        Mantido na View pois é uma integração HTTP específica.
        """
        raw_cnpj = (request.data.get('cnpj') or '').strip()
        cnpj_digits = re.sub(r'\D', '', raw_cnpj)
        
        if len(cnpj_digits) != 14:
            return Response({"detail": "CNPJ inválido. Informe 14 dígitos."}, status=status.HTTP_400_BAD_REQUEST)

        url = f"https://pncp.gov.br/api/pncp/v1/orgaos/{cnpj_digits}/unidades"

        try:
            with urlrequest.urlopen(url, timeout=20) as resp:
                if resp.status != 200:
                    return Response({"detail": f"PNCP respondeu {resp.status}"}, status=status.HTTP_502_BAD_GATEWAY)
                data = json.loads(resp.read().decode('utf-8'))
        except HTTPError as e:
            return Response({"detail": f"Falha ao consultar PNCP: HTTP {e.code}"}, status=status.HTTP_502_BAD_GATEWAY)
        except URLError:
            return Response({"detail": "Não foi possível alcançar o PNCP."}, status=status.HTTP_502_BAD_GATEWAY)
        except Exception as e:
            return Response({"detail": f"Erro inesperado ao consultar PNCP: {e}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        if not isinstance(data, list) or not data:
            return Response({"detail": "Nenhuma unidade retornada pelo PNCP."}, status=status.HTTP_404_NOT_FOUND)

        # Lógica de Filtragem e Criação
        # ---------------------------------------------------------------------
        ALLOW_KEYWORDS = ["SECRETARIA", "FUNDO", "CONTROLADORIA", "GABINETE"]
        EXCLUDE_KEYWORDS = ["PREFEITURA"]
        EXCLUDE_CODES = {"000000001", "000000000", "1"}

        def _normalize(txt):
            import unicodedata
            if not txt: return ""
            s = str(txt).strip().upper().replace("_", " ")
            s = unicodedata.normalize("NFD", s)
            s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
            return re.sub(r"\s+", " ", s)

        def deve_incluir(nome_unidade, codigo_unidade):
            n = _normalize(nome_unidade or "")
            c = (codigo_unidade or "").strip()
            if c in EXCLUDE_CODES: return False
            if any(word in n for word in EXCLUDE_KEYWORDS): return False
            return any(word in n for word in ALLOW_KEYWORDS)

        razao = (data[0].get('orgao') or {}).get('razaoSocial') or ''
        ano_atual = timezone.now().year

        with transaction.atomic():
            # Busca ou Cria Entidade
            entidade = None
            for ent in Entidade.objects.all():
                if re.sub(r'\D', '', ent.cnpj or '') == cnpj_digits:
                    entidade = ent
                    break
            
            if not entidade:
                entidade = Entidade.objects.create(
                    nome=razao or f"Entidade {cnpj_digits}",
                    cnpj=cnpj_digits,
                    ano=ano_atual
                )
            elif razao and entidade.nome != razao:
                entidade.nome = razao
                entidade.save(update_fields=['nome'])

            created, updated, ignorados = 0, 0, 0

            for u in data:
                codigo = (u.get('codigoUnidade') or '').strip()
                nome = (u.get('nomeUnidade') or '').strip()
                
                if not deve_incluir(nome, codigo):
                    ignorados += 1
                    continue

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
                    Orgao.objects.create(entidade=entidade, nome=nome, codigo_unidade=codigo or None)
                    created += 1

            orgaos_entidade = Orgao.objects.filter(entidade=entidade).order_by('nome')
            return Response({
                "entidade": {"id": entidade.id, "nome": entidade.nome, "cnpj": entidade.cnpj},
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
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [filters.SearchFilter, DjangoFilterBackend]
    search_fields = ['razao_social', 'cnpj']
    filterset_fields = ['cnpj']


# ============================================================
# 3️⃣ PROCESSO LICITATÓRIO
# ============================================================

class ProcessoLicitatorioViewSet(viewsets.ModelViewSet):
    queryset = (
        ProcessoLicitatorio.objects
        .select_related("entidade", "orgao")
        .all()
        .order_by("-data_abertura")
    )
    serializer_class = ProcessoLicitatorioSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    search_fields = ["numero_processo", "numero_certame", "objeto"]
    filterset_fields = ["modalidade", "situacao", "entidade", "orgao"]

    # ----------------------------------------------------------------------
    # IMPORTAÇÃO XLSX (Via Service)
    # ----------------------------------------------------------------------
    @action(
        detail=False,
        methods=["post"],
        url_path="importar-xlsx",
        parser_classes=[parsers.MultiPartParser, parsers.FormParser],
    )
    def importar_xlsx(self, request):
        arquivo = request.FILES.get("arquivo")
        if not arquivo:
            return Response({"detail": "Envie um arquivo XLSX no campo 'arquivo'."}, status=400)
        
        if not arquivo.name.lower().endswith(".xlsx"):
            return Response({"detail": "O arquivo deve ser .xlsx."}, status=400)

        try:
            # Chama o serviço isolado
            resultado = ImportacaoService.processar_planilha_padrao(arquivo)
            
            # Serializa o resultado para o frontend
            processo_serializer = self.get_serializer(resultado['processo'])
            
            return Response(
                {
                    "detail": "Importação concluída.",
                    "processo": processo_serializer.data,
                    "lotes_criados": resultado.get('lotes_criados', 0),
                    "itens_importados": resultado.get('itens_importados', 0),
                    "fornecedores_vinculados": resultado.get('fornecedores_vinculados', 0),
                },
                status=status.HTTP_201_CREATED,
            )

        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.exception("Erro na importação XLSX")
            return Response({"detail": "Erro interno ao processar arquivo."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
   
    @action(
            detail=True,
            methods=['post'],
            url_path='publicar-pncp',
            parser_classes=[parsers.MultiPartParser, parsers.FormParser]
    )
    def publicar_pncp(self, request, pk=None):
        """
        Recebe um arquivo (Edital/Aviso) e envia o processo para o PNCP.
        """
        processo = self.get_object()
        arquivo = request.FILES.get('arquivo')
        titulo = request.data.get('titulo_documento', 'Edital de Licitação')

        if not arquivo:
            return Response({"detail": "O arquivo do documento é obrigatório."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # Chama o serviço de integração
            resultado = PNCPService.publicar_compra(processo, arquivo, titulo)
            
            # Atualiza status local se der certo
            processo.situacao = "Publicado"
            processo.save()

            return Response({
                "detail": "Publicado no PNCP com sucesso!",
                "pncp_data": resultado
            }, status=status.HTTP_200_OK)

        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_502_BAD_GATEWAY)
        except Exception as e:
            logger.error(f"Erro interno PNCP: {e}")
            return Response({"detail": "Erro interno ao comunicar com PNCP."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
   
    # ----------------------------------------------------------------------
    # ITENS DO PROCESSO
    # ----------------------------------------------------------------------
    @action(detail=True, methods=["get"])
    def itens(self, request, *args, **kwargs):
        processo = self.get_object()
        itens = (
            Item.objects.filter(processo=processo)
            .select_related("lote", "fornecedor")
            .order_by("ordem", "id")
        )
        serializer = ItemSerializer(itens, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    # ----------------------------------------------------------------------
    # VINCULAR FORNECEDORES AO PROCESSO
    # ----------------------------------------------------------------------
    @action(detail=True, methods=["post"], url_path="adicionar_fornecedor")
    def adicionar_fornecedor(self, request, *args, **kwargs):
        processo = self.get_object()
        fornecedor_id = request.data.get("fornecedor_id")

        if not fornecedor_id:
            return Response({"error": "fornecedor_id é obrigatório."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            fornecedor = Fornecedor.objects.get(id=fornecedor_id)
        except Fornecedor.DoesNotExist:
            return Response({"error": "Fornecedor não encontrado."}, status=status.HTTP_404_NOT_FOUND)

        with transaction.atomic():
            obj, created = FornecedorProcesso.objects.get_or_create(processo=processo, fornecedor=fornecedor)
            
        return Response(
            {
                "detail": "Fornecedor vinculado ao processo com sucesso!",
                "fornecedor": FornecedorSerializer(fornecedor).data,
                "created": created,
            },
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["get"], url_path="fornecedores")
    def fornecedores(self, request, *args, **kwargs):
        processo = self.get_object()
        fornecedores = Fornecedor.objects.filter(processos__processo=processo).order_by("razao_social")
        serializer = FornecedorSerializer(fornecedores, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"], url_path="remover_fornecedor")
    def remover_fornecedor(self, request, *args, **kwargs):
        processo = self.get_object()
        fornecedor_id = request.data.get("fornecedor_id")

        if not fornecedor_id:
            return Response({"error": "fornecedor_id é obrigatório."}, status=status.HTTP_400_BAD_REQUEST)

        deleted, _ = FornecedorProcesso.objects.filter(processo=processo, fornecedor_id=fornecedor_id).delete()

        if deleted:
            return Response({"detail": "Fornecedor removido com sucesso."}, status=status.HTTP_200_OK)
        return Response({"detail": "Nenhum vínculo encontrado para remover."}, status=status.HTTP_404_NOT_FOUND)

    # ----------------------------------------------------------------------
    # GERENCIAMENTO DE LOTES (NESTED)
    # ----------------------------------------------------------------------
    @action(detail=True, methods=["get", "post"], url_path="lotes")
    def lotes(self, request, *args, **kwargs):
        processo = self.get_object()

        if request.method == "GET":
            qs = processo.lotes.order_by("numero")
            return Response(LoteSerializer(qs, many=True).data)

        # POST
        payload = request.data
        try:
            with transaction.atomic():
                # Delega a lógica de criação para o Model (Fat Model) ou processa aqui se simples
                # Usando o helper do Model se existir ou lógica direta
                if hasattr(processo, 'criar_lotes'):
                    if isinstance(payload, list):
                        created = processo.criar_lotes(lotes=payload)
                    elif "quantidade" in payload:
                        created = processo.criar_lotes(
                            quantidade=int(payload.get("quantidade")),
                            descricao_prefixo=payload.get("descricao_prefixo", "Lote ")
                        )
                    else:
                        created = processo.criar_lotes(
                            numero=payload.get("numero"),
                            descricao=payload.get("descricao")
                        )
                else:
                    # Fallback caso o método não esteja no model ainda
                    created = []
                    # ... lógica manual simplificada ...
                    pass

            return Response(LoteSerializer(created, many=True).data, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({"detail": str(e)}, status=400)

    @action(detail=True, methods=["patch"], url_path="lotes/organizar")
    def organizar_lotes(self, request, *args, **kwargs):
        processo = self.get_object()
        data = request.data
        
        try:
            with transaction.atomic():
                if hasattr(processo, 'organizar_lotes'):
                    qs = processo.organizar_lotes(
                        ordem_ids=data.get("ordem_ids"),
                        normalizar=data.get("normalizar"),
                        inicio=int(data.get("inicio") or 1),
                        mapa=data.get("mapa")
                    )
                    return Response(LoteSerializer(qs, many=True).data)
                else:
                    return Response({"detail": "Método organizar_lotes não implementado no Model."}, status=501)
        except Exception as e:
            return Response({"detail": str(e)}, status=400)


# ============================================================
# 4️⃣ LOTE
# ============================================================

class LoteViewSet(viewsets.ModelViewSet):
    queryset = Lote.objects.select_related('processo').all()
    serializer_class = LoteSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['processo']
    search_fields = ['descricao']


# ============================================================
# 5️⃣ ITEM
# ============================================================

class ItemViewSet(viewsets.ModelViewSet):
    queryset = Item.objects.select_related('processo', 'lote', 'fornecedor').all()
    serializer_class = ItemSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['processo', 'lote', 'fornecedor']
    search_fields = ['descricao', 'unidade', 'especificacao']

    @action(detail=True, methods=['post'], url_path='definir-fornecedor')
    def definir_fornecedor(self, request, pk=None):
        """
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
# 6️⃣ RELACIONAMENTOS (Participantes e Propostas)
# ============================================================

class FornecedorProcessoViewSet(viewsets.ModelViewSet):
    queryset = FornecedorProcesso.objects.select_related('processo', 'fornecedor').all()
    serializer_class = FornecedorProcessoSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['processo', 'fornecedor']
    search_fields = ['fornecedor__razao_social', 'fornecedor__cnpj']


class ItemFornecedorViewSet(viewsets.ModelViewSet):
    queryset = ItemFornecedor.objects.select_related('item', 'fornecedor').all()
    serializer_class = ItemFornecedorSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['item', 'fornecedor', 'vencedor']
    search_fields = ['item__descricao', 'fornecedor__razao_social']


# ============================================================
# 7️⃣ UTILS & DASHBOARD
# ============================================================

class ReorderItensView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, _format=None):
        item_ids = request.data.get('item_ids', [])
        if not isinstance(item_ids, list):
            return Response({"error": "item_ids deve ser uma lista."}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            for index, item_id in enumerate(item_ids):
                Item.objects.filter(id=item_id).update(ordem=index + 1)

        return Response({"status": "Itens reordenados com sucesso."}, status=status.HTTP_200_OK)


class DashboardStatsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, _request):
        data = {
            'total_processos': ProcessoLicitatorio.objects.count(),
            'processos_em_andamento': ProcessoLicitatorio.objects.filter(situacao="Em Contratação").count(),
            'total_fornecedores': Fornecedor.objects.count(),
            'total_orgaos': Orgao.objects.count(),
            'total_itens': Item.objects.count(),
        }
        return Response(data)


# ============================================================
# 8️⃣ AUTH (Google Login)
# ============================================================

class GoogleLoginView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        google_token = request.data.get("token")
        if not google_token:
            return Response({"detail": "Token ausente."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            id_info = id_token.verify_oauth2_token(
                google_token,
                google_requests.Request(),
                settings.GOOGLE_CLIENT_ID,
            )

            if not id_info.get("email_verified"):
                return Response({"detail": "Email não verificado pelo Google."}, status=status.HTTP_401_UNAUTHORIZED)

            email = id_info.get("email")
            nome = id_info.get("name") or ""
            picture = id_info.get("picture", "")

            user, created = CustomUser.objects.get_or_create(
                email=email,
                defaults={
                    "username": email,
                    "first_name": nome.split(" ")[0],
                    "last_name": " ".join(nome.split(" ")[1:]),
                }
            )

            refresh = RefreshToken.for_user(user)
            update_last_login(None, user)

            return Response({
                "access": str(refresh.access_token),
                "refresh": str(refresh),
                "user": {
                    "id": user.id,
                    "email": user.email,
                    "name": nome,
                    "picture": picture,
                },
                "new_user": created
            }, status=status.HTTP_200_OK)

        except ValueError:
            return Response({"detail": "Token inválido do Google."}, status=status.HTTP_401_UNAUTHORIZED)
        except Exception as e:
            logger.error(f"Erro login Google: {e}")
            return Response({"detail": "Erro interno."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ============================================================
# 9️⃣ CONTRATO EMPENHO
# ============================================================

class ContratoEmpenhoViewSet(viewsets.ModelViewSet):
    queryset = ContratoEmpenho.objects.select_related('processo').all().order_by('-criado_em', 'id')
    serializer_class = ContratoEmpenhoSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['processo', 'ano_contrato', 'tipo_contrato_id', 'receita']
    search_fields = ['numero_contrato_empenho', 'processo__numero_processo', 'ni_fornecedor']