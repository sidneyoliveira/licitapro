# api/views.py

import logging
import json
import re
import requests

from django.db import transaction
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.contrib.auth.models import update_last_login
from django.conf import settings

from rest_framework import viewsets, permissions, filters, status, parsers, generics
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny, IsAuthenticated, IsAdminUser
from django_filters.rest_framework import DjangoFilterBackend
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from rest_framework_simplejwt.tokens import RefreshToken

from .services import PNCPService, ImportacaoService

# Imports Locais - Models
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
    Anotacao,
    ArquivoUser
)

# Imports Locais - Serializers
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
    AnotacaoSerializer,
    ArquivoUserSerializers
)

# Imports Locais - Choices (Atualizado para nova lógica sem Fundamentação)
from .choices import (
    MODALIDADE_CHOICES,
    AMPARO_LEGAL_CHOICES,
    MAP_MODALIDADE_AMPARO,  
    MODO_DISPUTA_CHOICES,
    INSTRUMENTO_CONVOCATORIO_CHOICES,
    CRITERIO_JULGAMENTO_CHOICES,
    SITUACAO_ITEM_CHOICES,
    TIPO_BENEFICIO_CHOICES,
    CATEGORIA_ITEM_CHOICES,
    SITUACAO_CHOICES,
    TIPO_ORGANIZACAO_CHOICES,
    NATUREZAS_DESPESA_CHOICES,
    MAP_INSTRUMENTO_CONVOCATORIO_PNCP
)

User = get_user_model()
logger = logging.getLogger(__name__)

GOOGLE_CLIENT_ID = getattr(settings, "GOOGLE_CLIENT_ID", "") or ""

def parse_pncp_id(raw, slug_map, field_name="campo"):
    if raw is None or str(raw).strip() == "":
        raise ValueError(f"{field_name} é obrigatório.")
    raw = str(raw).strip()

    # tenta int primeiro
    try:
        return int(raw)
    except ValueError:
        pass

    # tenta slug
    _id = slug_map.get(raw)
    if not _id:
        raise ValueError(f"{field_name} inválido: '{raw}'. Envie um ID numérico ou um slug conhecido.")
    return int(_id)

# ============================================================
# 0️⃣ API DE CONSTANTES DO SISTEMA (ATUALIZADA)
# ============================================================


class ConstantesSistemaView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        # Helper robusto
        def format_choices_pncp(choices_tuple):
            results = []
            for c in choices_tuple:
                if c[0] is None:
                    continue
                if len(c) >= 3:
                    results.append({"id": c[0], "slug": c[1], "label": c[2]})
                else:
                    results.append({"id": c[0], "slug": str(c[0]), "label": c[1]})
            return results

        def format_choices_simple(choices_tuple):
            return [{"id": c[0], "label": c[1]} for c in choices_tuple]

        data = {
            # --- LISTAS DE OPÇÕES (PNCP) ---
            "modalidades": format_choices_pncp(MODALIDADE_CHOICES),
            "amparos_legais": format_choices_simple(AMPARO_LEGAL_CHOICES),
            "modos_disputa": format_choices_pncp(MODO_DISPUTA_CHOICES),
            "instrumentos_convocatorios": format_choices_pncp(
                INSTRUMENTO_CONVOCATORIO_CHOICES
            ),
            "criterios_julgamento": format_choices_pncp(CRITERIO_JULGAMENTO_CHOICES),
            "situacoes_item": format_choices_pncp(SITUACAO_ITEM_CHOICES),
            "tipos_beneficio": format_choices_pncp(TIPO_BENEFICIO_CHOICES),
            "categorias_item": format_choices_pncp(CATEGORIA_ITEM_CHOICES),
            # --- LISTAS INTERNAS ---
            "situacoes_processo": format_choices_simple(SITUACAO_CHOICES),
            "tipos_organizacao": format_choices_simple(TIPO_ORGANIZACAO_CHOICES),
            "naturezas_despesa": format_choices_simple(NATUREZAS_DESPESA_CHOICES),
            # --- MAPA DE DEPENDÊNCIA (CÉREBRO DO FILTRO) ---
            # Envia o mapa { ID_MODALIDADE: [LISTA_IDS_AMPARO] }
            "mapa_modalidade_amparo": MAP_MODALIDADE_AMPARO,
        }

        return Response(data)


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
    permission_classes = [IsAdminUser]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    parser_classes = [
        parsers.MultiPartParser,
        parsers.FormParser,
        parsers.JSONParser,
    ]
    search_fields = ["username", "email", "first_name", "last_name"]
    ordering_fields = [
        "id",
        "username",
        "email",
        "first_name",
        "last_name",
        "last_login",
        "date_joined",
    ]
    ordering = ["username"]


class CreateUserView(generics.CreateAPIView):
    queryset = CustomUser.objects.all()
    serializer_class = UserSerializer
    permission_classes = [AllowAny]


class ManageUserView(generics.RetrieveUpdateAPIView):
    """
    GET /me/  -> retorna usuário autenticado
    PUT/PATCH -> atualiza parcialmente
    """

    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["request"] = self.request
        return ctx


# ============================================================
# 1️⃣ ENTIDADE / ÓRGÃO
# ============================================================


class EntidadeViewSet(viewsets.ModelViewSet):
    queryset = Entidade.objects.all().order_by("nome")
    serializer_class = EntidadeSerializer
    permission_classes = [IsAuthenticated]


class OrgaoViewSet(viewsets.ModelViewSet):
    serializer_class = OrgaoSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]

    filterset_fields = ["entidade"]

    def get_queryset(self):
        qs = Orgao.objects.select_related("entidade").order_by("nome")
        entidade_id = self.request.query_params.get("entidade")
        if entidade_id:
            qs = qs.filter(entidade_id=entidade_id)
        return qs

    @action(detail=False, methods=["post"], url_path="importar-pncp")
    def importar_pncp(self, request):
        """
        Consulta API do PNCP para importar Órgãos vinculados a um CNPJ.
        """
        raw_cnpj = (request.data.get("cnpj") or "").strip()
        cnpj_digits = re.sub(r"\D", "", raw_cnpj)

        if len(cnpj_digits) != 14:
            return Response(
                {"detail": "CNPJ inválido. Informe 14 dígitos."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        url = f"https://pncp.gov.br/api/pncp/v1/orgaos/{cnpj_digits}/unidades"

        try:
            resp = requests.get(url, timeout=20)

            if resp.status_code != 200:
                return Response(
                    {"detail": f"PNCP respondeu {resp.status_code}"},
                    status=status.HTTP_502_BAD_GATEWAY,
                )

            data = resp.json()

        except requests.RequestException as e:
            return Response(
                {"detail": f"Erro ao consultar PNCP: {str(e)}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        if not isinstance(data, list) or not data:
            return Response(
                {"detail": "Nenhuma unidade retornada pelo PNCP."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Lógica de Filtragem e Criação
        ALLOW_KEYWORDS = [
            "SECRETARIA",
            "FUNDO",
            "CONTROLADORIA",
            "GABINETE",
            "PREFEITURA",
            "CAMARA",
        ]
        EXCLUDE_KEYWORDS = []
        EXCLUDE_CODES = {"000000001", "000000000", "1"}

        def _normalize(txt):
            import unicodedata

            if not txt:
                return ""
            s = str(txt).strip().upper().replace("_", " ")
            s = unicodedata.normalize("NFD", s)
            s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
            return re.sub(r"\s+", " ", s)

        def deve_incluir(nome_unidade, codigo_unidade):
            c = (codigo_unidade or "").strip()
            if c in EXCLUDE_CODES:
                return False
            return True

        razao = (data[0].get("orgao") or {}).get("razaoSocial") or ""
        ano_atual = timezone.now().year

        with transaction.atomic():
            # Busca ou Cria Entidade
            entidade = None
            for ent in Entidade.objects.all():
                if re.sub(r"\D", "", ent.cnpj or "") == cnpj_digits:
                    entidade = ent
                    break

            if not entidade:
                entidade = Entidade.objects.create(
                    nome=razao or f"Entidade {cnpj_digits}",
                    cnpj=cnpj_digits,
                    ano=ano_atual,
                )
            elif razao and entidade.nome != razao:
                entidade.nome = razao
                entidade.save(update_fields=["nome"])

            created, updated, ignorados = 0, 0, 0

            for u in data:
                codigo = (u.get("codigoUnidade") or "").strip()
                nome = (u.get("nomeUnidade") or "").strip()

                if not deve_incluir(nome, codigo):
                    ignorados += 1
                    continue

                orgao = Orgao.objects.filter(
                    entidade=entidade, codigo_unidade=codigo
                ).first()
                if not orgao:
                    orgao = Orgao.objects.filter(
                        entidade=entidade, nome__iexact=nome
                    ).first()

                if orgao:
                    changed = False
                    if codigo and orgao.codigo_unidade != codigo:
                        orgao.codigo_unidade = codigo
                        changed = True
                    if orgao.nome != nome:
                        orgao.nome = nome
                        changed = True
                    if changed:
                        orgao.save(update_fields=["nome", "codigo_unidade"])
                        updated += 1
                else:
                    Orgao.objects.create(
                        entidade=entidade,
                        nome=nome,
                        codigo_unidade=codigo or None,
                    )
                    created += 1

            orgaos_entidade = Orgao.objects.filter(entidade=entidade).order_by("nome")
            return Response(
                {
                    "entidade": {
                        "id": entidade.id,
                        "nome": entidade.nome,
                        "cnpj": entidade.cnpj,
                    },
                    "created": created,
                    "updated": updated,
                    "ignored": ignorados,
                    "total_orgaos_entidade": orgaos_entidade.count(),
                    "orgaos": OrgaoSerializer(orgaos_entidade, many=True).data,
                },
                status=status.HTTP_200_OK,
            )


# ============================================================
# 2️⃣ FORNECEDOR
# ============================================================


class FornecedorViewSet(viewsets.ModelViewSet):
    queryset = Fornecedor.objects.all().order_by("razao_social")
    serializer_class = FornecedorSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter, DjangoFilterBackend]
    search_fields = ["razao_social", "cnpj"]
    filterset_fields = ["cnpj"]


# ============================================================
# 3️⃣ PROCESSO LICITATÓRIO
# ============================================================


class ProcessoLicitatorioViewSet(viewsets.ModelViewSet):
    queryset = (
        ProcessoLicitatorio.objects.select_related("entidade", "orgao")
        .all()
        .order_by("-data_abertura")
    )
    serializer_class = ProcessoLicitatorioSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    search_fields = ["numero_processo", "numero_certame", "objeto"]

    filterset_fields = ["modalidade", "situacao", "entidade", "orgao"]

    # ----------------------------------------------------------------------
    # IMPORTAÇÃO XLSX
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
            return Response(
                {"detail": "Envie um arquivo XLSX no campo 'arquivo'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not arquivo.name.lower().endswith(".xlsx"):
            return Response(
                {"detail": "O arquivo deve ser .xlsx."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            resultado = ImportacaoService.processar_planilha_padrao(arquivo)
            processo_serializer = self.get_serializer(resultado["processo"])

            return Response(
                {
                    "detail": "Importação concluída.",
                    "processo": processo_serializer.data,
                    "lotes_criados": resultado.get("lotes_criados", 0),
                    "itens_importados": resultado.get("itens_importados", 0),
                    "fornecedores_vinculados": resultado.get(
                        "fornecedores_vinculados", 0
                    ),
                },
                status=status.HTTP_201_CREATED,
            )

        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception:
            logger.exception("Erro na importação XLSX")
            return Response(
                {"detail": "Erro interno ao processar arquivo."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
    @action(detail=True, methods=["get"], url_path="status-pncp")
    def status_pncp(self, request, pk=None):
        processo = self.get_object()

        # ajuste conforme seus campos reais
        publicado = (processo.situacao == "publicado")

        return Response(
            {
                "publicado": publicado,
                "situacao": processo.situacao,
                # se você tiver campos PNCP no model, exponha aqui:
                "ano_compra": getattr(processo, "pncp_ano_compra", None),
                "sequencial_pncp": getattr(processo, "pncp_sequencial_compra", None),
                "url_pncp": getattr(processo, "pncp_url", None),
            },
            status=status.HTTP_200_OK,
        )
    @action(
        detail=True,
        methods=["post"],
        url_path="retificar-pncp",
        parser_classes=[parsers.MultiPartParser, parsers.FormParser],
    )
    def retificar_pncp(self, request, pk=None):
        """
        Retificação: anexa um novo documento à contratação já existente no PNCP.
        Requer que o processo já tenha ano/sequencial PNCP.
        """
        processo = self.get_object()
        arquivo = request.FILES.get("arquivo")

        if not arquivo:
            return Response(
                {"detail": "O arquivo do documento é obrigatório."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        titulo = (request.data.get("titulo_documento") or request.data.get("titulo") or "Retificação")[:255]
        justificativa = (request.data.get("justificativa") or request.data.get("observacao") or "").strip()

        # (opcional, mas recomendado)
        if not justificativa:
            return Response(
                {"detail": "Justificativa/observação é obrigatória para retificação."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Tipo do documento (aceita id numérico ou slug)
        raw_tipo = request.data.get("tipo_documento_id") or request.data.get("tipo_documento")
        try:
            tipo_documento_id = _parse_pncp_id(raw_tipo, MAP_INSTRUMENTO_CONVOCATORIO_PNCP, "tipo_documento")
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        # Ano/sequencial: tenta no model (se existir) e depois no request
        ano_compra = getattr(processo, "pncp_ano_compra", None) or request.data.get("ano_compra") or request.data.get("ano")
        sequencial_compra = getattr(processo, "pncp_sequencial_compra", None) or request.data.get("sequencial_compra") or request.data.get("sequencial")

        if not ano_compra or not sequencial_compra:
            return Response(
                {
                    "detail": (
                        "Processo ainda não tem referência PNCP (ano_compra/sequencial_compra). "
                        "Publique primeiro e grave esses campos, ou envie 'ano_compra' e 'sequencial_compra' no body."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # CNPJ do órgão/entidade
        cnpj_orgao = re.sub(r"\D", "", (processo.entidade.cnpj or ""))
        if len(cnpj_orgao) != 14:
            return Response(
                {"detail": "CNPJ da entidade inválido/ausente."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            resultado = PNCPService.anexar_documento_compra(
                cnpj_orgao=cnpj_orgao,
                ano_compra=int(ano_compra),
                sequencial_compra=int(sequencial_compra),
                arquivo=arquivo,
                titulo_documento=titulo,
                tipo_documento_id=tipo_documento_id,
            )

            # Se você tiver campos PNCP no model, grave aqui (opcional)
            if hasattr(processo, "pncp_ultimo_retorno"):
                processo.pncp_ultimo_retorno = resultado
                processo.save(update_fields=["pncp_ultimo_retorno"])

            return Response(
                {"detail": "Retificação enviada ao PNCP (documento anexado).", "pncp_data": resultado},
                status=status.HTTP_200_OK,
            )

        except ValueError as e:
            # tenta extrair (400), (422) etc da mensagem do service, se você usou esse padrão
            msg = str(e)
            m = re.search(r"\((\d{3})\)", msg)
            code = int(m.group(1)) if m else 400
            return Response({"detail": msg}, status=code)

        except Exception as e:
            logger.exception("Erro interno retificar PNCP")
            return Response(
                {"detail": f"Erro interno ao comunicar com PNCP: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
    @action(
    detail=True,
    methods=["post"],
    url_path="publicar-pncp",
    parser_classes=[parsers.MultiPartParser, parsers.FormParser],
)
    def publicar_pncp(self, request, pk=None):
        processo = self.get_object()
        arquivo = request.FILES.get("arquivo")
        titulo = request.data.get("titulo_documento") or "Edital de Licitação"

        if not arquivo:
            return Response({"detail": "O arquivo do documento é obrigatório."}, status=400)

        if not processo.entidade_id or not (processo.entidade and processo.entidade.cnpj):
            return Response({"detail": "Processo sem Entidade/CNPJ. Preencha a entidade e o CNPJ antes de publicar."}, status=400)

        if not processo.orgao_id or not (processo.orgao and processo.orgao.codigo_unidade):
            return Response({"detail": "Processo sem Órgão/código da unidade compradora. Preencha orgao.codigo_unidade."}, status=400)

        try:
            resultado = PNCPService.publicar_compra(processo, arquivo, titulo)
            processo.situacao = "publicado"
            processo.save(update_fields=["situacao"])
            return Response({"detail": "Publicado no PNCP com sucesso!", "pncp_data": resultado}, status=200)

        except ValueError as e:
            # Erro esperado (PNCP, validações, etc)
            return Response({"detail": str(e)}, status=400)

        except Exception as e:
            logger.exception("Erro interno PNCP (publicar_pncp)")
            return Response({"detail": f"Erro interno ao publicar: {str(e)}"}, status=500)
        
    
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
            return Response(
                {"error": "fornecedor_id é obrigatório."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            fornecedor = Fornecedor.objects.get(id=fornecedor_id)
        except Fornecedor.DoesNotExist:
            return Response(
                {"error": "Fornecedor não encontrado."},
                status=status.HTTP_404_NOT_FOUND,
            )

        with transaction.atomic():
            obj, created = FornecedorProcesso.objects.get_or_create(
                processo=processo,
                fornecedor=fornecedor,
            )

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
        fornecedores = Fornecedor.objects.filter(
            processos__processo=processo
        ).order_by("razao_social")
        serializer = FornecedorSerializer(fornecedores, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"], url_path="remover_fornecedor")
    def remover_fornecedor(self, request, *args, **kwargs):
        processo = self.get_object()
        fornecedor_id = request.data.get("fornecedor_id")

        if not fornecedor_id:
            return Response(
                {"error": "fornecedor_id é obrigatório."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        deleted, _ = FornecedorProcesso.objects.filter(
            processo=processo,
            fornecedor_id=fornecedor_id,
        ).delete()

        if deleted:
            return Response(
                {"detail": "Fornecedor removido com sucesso."},
                status=status.HTTP_200_OK,
            )
        return Response(
            {"detail": "Nenhum vínculo encontrado para remover."},
            status=status.HTTP_404_NOT_FOUND,
        )

    # ----------------------------------------------------------------------
    # GERENCIAMENTO DE LOTES
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
                if hasattr(processo, "criar_lotes"):
                    if isinstance(payload, list):
                        created = processo.criar_lotes(lotes=payload)
                    elif "quantidade" in payload:
                        created = processo.criar_lotes(
                            quantidade=int(payload.get("quantidade")),
                            descricao_prefixo=payload.get(
                                "descricao_prefixo", "Lote "
                            ),
                        )
                    else:
                        created = processo.criar_lotes(
                            numero=payload.get("numero"),
                            descricao=payload.get("descricao"),
                        )
                else:
                    created = []

            return Response(
                LoteSerializer(created, many=True).data,
                status=status.HTTP_201_CREATED,
            )
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["patch"], url_path="lotes/organizar")
    def organizar_lotes(self, request, *args, **kwargs):
        processo = self.get_object()
        data = request.data

        try:
            with transaction.atomic():
                if hasattr(processo, "organizar_lotes"):
                    qs = processo.organizar_lotes(
                        ordem_ids=data.get("ordem_ids"),
                        normalizar=data.get("normalizar"),
                        inicio=int(data.get("inicio") or 1),
                        mapa=data.get("mapa"),
                    )
                    return Response(
                        LoteSerializer(qs, many=True).data,
                        status=status.HTTP_200_OK,
                    )
                return Response(
                    {
                        "detail": "Método organizar_lotes não implementado no Model."
                    },
                    status=status.HTTP_501_NOT_IMPLEMENTED,
                )
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)


# ============================================================
# 4️⃣ LOTE
# ============================================================


class LoteViewSet(viewsets.ModelViewSet):
    queryset = Lote.objects.select_related("processo").all()
    serializer_class = LoteSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ["processo"]
    search_fields = ["descricao"]


# ============================================================
# 5️⃣ ITEM
# ============================================================


class ItemViewSet(viewsets.ModelViewSet):
    queryset = Item.objects.select_related("processo", "lote", "fornecedor").all()
    serializer_class = ItemSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ["processo", "lote", "fornecedor"]
    search_fields = ["descricao", "unidade", "especificacao"]

    @action(detail=True, methods=["post"], url_path="definir-fornecedor")
    def definir_fornecedor(self, request, pk=None):
        """
        Vincula um fornecedor ao item.
        """
        item = self.get_object()
        fornecedor_id = request.data.get("fornecedor_id")

        if not fornecedor_id:
            return Response(
                {"error": "fornecedor_id é obrigatório."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            fornecedor = Fornecedor.objects.get(id=fornecedor_id)
        except Fornecedor.DoesNotExist:
            return Response(
                {"error": "Fornecedor não encontrado."},
                status=status.HTTP_404_NOT_FOUND,
            )

        item.fornecedor = fornecedor
        item.save(update_fields=["fornecedor"])
        return Response(
            {"detail": "Fornecedor vinculado ao item com sucesso."},
            status=status.HTTP_200_OK,
        )


# ============================================================
# 6️⃣ RELACIONAMENTOS (Participantes e Propostas)
# ============================================================


class FornecedorProcessoViewSet(viewsets.ModelViewSet):
    queryset = FornecedorProcesso.objects.select_related(
        "processo", "fornecedor"
    ).all()
    serializer_class = FornecedorProcessoSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ["processo", "fornecedor"]
    search_fields = ["fornecedor__razao_social", "fornecedor__cnpj"]


class ItemFornecedorViewSet(viewsets.ModelViewSet):
    queryset = ItemFornecedor.objects.select_related("item", "fornecedor").all()
    serializer_class = ItemFornecedorSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ["item", "fornecedor", "vencedor"]
    search_fields = ["item__descricao", "fornecedor__razao_social"]


# ============================================================
# 7️⃣ UTILS & DASHBOARD
# ============================================================


class ReorderItensView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, _format=None):
        item_ids = request.data.get("item_ids", [])
        if not isinstance(item_ids, list):
            return Response(
                {"error": "item_ids deve ser uma lista."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            for index, item_id in enumerate(item_ids):
                Item.objects.filter(id=item_id).update(ordem=index + 1)

        return Response(
            {"status": "Itens reordenados com sucesso."},
            status=status.HTTP_200_OK,
        )


class DashboardStatsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, _request):
        data = {
            "total_processos": ProcessoLicitatorio.objects.count(),
            "processos_em_andamento": ProcessoLicitatorio.objects.filter(
                situacao="em_contratacao"
            ).count(),
            "total_fornecedores": Fornecedor.objects.count(),
            "total_orgaos": Orgao.objects.count(),
            "total_itens": Item.objects.count(),
        }
        return Response(data)


# ============================================================
# 8️⃣ AUTH (Google Login)
# ============================================================


class GoogleLoginView(APIView):
    permission_classes = [AllowAny]

    @staticmethod
    def _debug_google_env(google_token):
        """
        Loga o GOOGLE_CLIENT_ID configurado e um trecho do token recebido.
        Não expõe o token inteiro por segurança.
        """
        client_id_visivel = GOOGLE_CLIENT_ID or "<vazio>"

        if google_token:
            if len(google_token) > 20:
                token_mascarado = (
                    google_token[:8] + "..." + google_token[-8:]
                )
            else:
                token_mascarado = "<token muito curto para mascarar>"
        else:
            token_mascarado = "<ausente>"

        logger.info(
            "[GOOGLE AUTH] GOOGLE_CLIENT_ID='%s' | token(recebido)='%s'",
            client_id_visivel,
            token_mascarado,
        )

    def post(self, request):
        google_token = request.data.get("token")
        if not google_token:
            return Response(
                {"detail": "Token ausente."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Log de ambiente e token (mascarado)
        self._debug_google_env(google_token)

        try:
            id_info = id_token.verify_oauth2_token(
                google_token,
                google_requests.Request(),
                GOOGLE_CLIENT_ID,
            )

            if not id_info.get("email_verified"):
                return Response(
                    {"detail": "Email não verificado pelo Google."},
                    status=status.HTTP_401_UNAUTHORIZED,
                )

            email = id_info.get("email")
            nome = id_info.get("name") or ""
            picture = id_info.get("picture") or ""

            if not email:
                return Response(
                    {"detail": "Não foi possível obter o email do Google."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            first_name = nome.split(" ")[0] if nome else ""
            last_name = " ".join(nome.split(" ")[1:]) if nome else ""

            user, created = CustomUser.objects.get_or_create(
                email=email,
                defaults={
                    "username": email,
                    "first_name": first_name,
                    "last_name": last_name,
                },
            )

            refresh = RefreshToken.for_user(user)
            update_last_login(None, user)

            return Response(
                {
                    "access": str(refresh.access_token),
                    "refresh": str(refresh),
                    "user": {
                        "id": user.id,
                        "email": user.email,
                        "name": nome,
                        "picture": picture,
                    },
                    "new_user": created,
                },
                status=status.HTTP_200_OK,
            )

        except ValueError as e:
            # Erro típico do verify_oauth2_token (token inválido, expirado, etc.)
            logger.warning("[GOOGLE AUTH] Token inválido do Google: %s", e)
            return Response(
                {"detail": "Token inválido do Google."},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        except Exception as e:
            logger.exception("Erro login Google: %s", e)
            return Response(
                {"detail": "Erro interno."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


# ============================================================
# 9️⃣ CONTRATO EMPENHO
# ============================================================


class ContratoEmpenhoViewSet(viewsets.ModelViewSet):
    queryset = (
        ContratoEmpenho.objects.select_related("processo")
        .all()
        .order_by("-criado_em", "id")
    )
    serializer_class = ContratoEmpenhoSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ["processo", "ano_contrato", "tipo_contrato_id", "receita"]
    search_fields = [
        "numero_contrato_empenho",
        "processo__numero_processo",
        "ni_fornecedor",
    ]

class SystemConfigView(APIView):
    
    """
    Retorna configurações públicas do sistema para o Frontend.
    NUNCA retorne SECRET_KEY ou senhas aqui.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({
            "google_client_id": settings.GOOGLE_CLIENT_ID,
            "api_url": "http://l3solution.net.br/api/", # Opcional, para confirmação
            "environment": "production" if not settings.DEBUG else "development"
        })
    

# ============================================================
# 📝 ANOTAÇÕES VIEWSET
# ============================================================

class AnotacaoViewSet(viewsets.ModelViewSet):
    serializer_class = AnotacaoSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # Retorna apenas as anotações do usuário logado
        return Anotacao.objects.filter(usuario=self.request.user).order_by('-criado_em')

    def perform_create(self, serializer):
        # Vincula automaticamente a nota ao usuário logado
        serializer.save(usuario=self.request.user)

# ============================================================
# 🗂️ ARQUIVOS USUÁRIO VIEWSET
# ============================================================

class ArquivoUserViewSet(viewsets.ModelViewSet):
    serializer_class = ArquivoUserSerializers
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # Retorna apenas os arquivos do usuário logado
        return ArquivoUser.objects.filter(usuario=self.request.user).order_by('-criado_em')

    def perform_create(self, serializer):
        # Vincula automaticamente o arquivo ao usuário logado
        serializer.save(usuario=self.request.user)