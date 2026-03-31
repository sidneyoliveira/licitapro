# api/views.py

import logging
import json
import re
import requests
import hashlib

from django.db import transaction
from django.db.models import Q
from django.db.utils import ProgrammingError, OperationalError
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.contrib.auth.models import update_last_login
from django.conf import settings

from rest_framework import viewsets, permissions, filters, status, parsers, generics
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny, IsAuthenticated, IsAdminUser
from rest_framework.exceptions import PermissionDenied
from django_filters.rest_framework import DjangoFilterBackend
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from rest_framework_simplejwt.tokens import RefreshToken

from rest_framework.parsers import MultiPartParser, FormParser, JSONParser

from .services import PNCPService, ImportacaoService

from django.shortcuts import get_object_or_404



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
    DocumentoPNCP, 
    Anotacao,
    Notificacao,
    ArquivoUser,
    AtaRegistroPrecos,
    DocumentoAtaRegistroPrecos
)

# Imports Locais - Serializers
from .serializers import (
    TIPO_DOC_MAPA,
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
    AnotacaoSerializer,
    NotificacaoSerializer,
    ArquivoUserSerializer,
    DocumentoPNCPSerializer,
    AtaRegistroPrecosSerializer,
    DocumentoAtaRegistroPrecosSerializer
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


# ============================================================
# 🔒 MIXIN DE ISOLAMENTO POR ENTIDADE (MULTI-TENANT)
# ============================================================

class EntidadeFilterMixin:
    """
    Mixin que filtra automaticamente querysets pelas entidades do usuário logado.
    Superusers veem tudo. Usuários sem entidades vinculadas não veem nada.
    """
    entidade_field = 'entidade'  # Override em subclasses se o campo FK tiver outro nome

    def get_user_entidades_ids(self):
        user = self.request.user
        if user.is_superuser:
            return None  # Superuser vê tudo
        return list(user.entidades.values_list('id', flat=True))

    def filter_by_entidade(self, qs):
        entidade_ids = self.get_user_entidades_ids()
        if entidade_ids is None and self.request.user.is_superuser:
            return qs  # Superuser: sem filtro
        if entidade_ids:
            return qs.filter(**{f'{self.entidade_field}__in': entidade_ids})
        # Usuário sem entidades vinculadas: não vê nada
        return qs.none()


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

    serializer_class = UserSerializer
    permission_classes = [IsAdminUser]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter, DjangoFilterBackend]
    parser_classes = [
        parsers.MultiPartParser,
        parsers.FormParser,
        parsers.JSONParser,
    ]
    search_fields = ["username", "email", "first_name", "last_name"]
    filterset_fields = ["is_active", "is_staff"]
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

    def get_queryset(self):
        return User.objects.prefetch_related("entidades").all().order_by("id")


class CreateUserView(generics.CreateAPIView):
    queryset = CustomUser.objects.all()
    serializer_class = UserSerializer
    permission_classes = [AllowAny]


class ManageUserView(generics.RetrieveUpdateAPIView):
    """
    GET /me/  -> retorna usuário autenticado (com entidade)
    PUT/PATCH -> atualiza parcialmente
    """

    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]
    parser_classes = [parsers.MultiPartParser, parsers.FormParser, parsers.JSONParser]

    def get_object(self):
        return CustomUser.objects.prefetch_related("entidades").get(pk=self.request.user.pk)

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["request"] = self.request
        return ctx


# ============================================================
# 1️⃣ ENTIDADE / ÓRGÃO
# ============================================================


class EntidadeViewSet(EntidadeFilterMixin, viewsets.ModelViewSet):
    serializer_class = EntidadeSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = Entidade.objects.all().order_by("nome")
        if self.request.user.is_staff or self.request.user.is_superuser:
            return qs
        entidade_ids = self.get_user_entidades_ids()
        if entidade_ids is not None:
            qs = qs.filter(id__in=entidade_ids)
        return qs


class OrgaoViewSet(EntidadeFilterMixin, viewsets.ModelViewSet):
    serializer_class = OrgaoSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]

    filterset_fields = ["entidade"]

    def get_queryset(self):
        qs = Orgao.objects.select_related("entidade").order_by("nome")
        # Multi-tenant: filtra pelas entidades do usuário
        entidade_ids = self.get_user_entidades_ids()
        if entidade_ids is not None:
            if not entidade_ids:
                return qs.none()
            qs = qs.filter(entidade_id__in=entidade_ids)
        # Filtro adicional por query param
        entidade_param = self.request.query_params.get("entidade")
        if entidade_param:
            qs = qs.filter(entidade_id=entidade_param)
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


class ProcessoLicitatorioViewSet(EntidadeFilterMixin, viewsets.ModelViewSet):
    serializer_class = ProcessoLicitatorioSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    search_fields = ["numero_processo", "numero_certame", "objeto"]
    filterset_fields = ["modalidade", "situacao", "entidade", "orgao"]

    def get_queryset(self):
        qs = (
            ProcessoLicitatorio.objects.select_related("entidade", "orgao")
            .all()
            .order_by("-data_abertura")
        )
        return self.filter_by_entidade(qs)

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

    # ----------------------------------------------------------------------
    # STATUS PNCP (usado pelo modal no front)
    # ----------------------------------------------------------------------
    @action(detail=True, methods=["get"], url_path="status-pncp")
    def status_pncp(self, request, pk=None):
        processo = self.get_object()

        publicado = (
            processo.situacao == "publicado"
            or bool(getattr(processo, "pncp_sequencial_compra", None))
        )

        return Response(
            {
                "publicado": publicado,
                "situacao": processo.situacao,
                "ano_compra": getattr(processo, "pncp_ano_compra", None),
                "sequencial_pncp": getattr(processo, "pncp_sequencial_compra", None),
                "url_pncp": getattr(processo, "pncp_url", None),
            },
            status=status.HTTP_200_OK,
        )

    # ----------------------------------------------------------------------
    # PUBLICAÇÃO INICIAL NO PNCP
    # ----------------------------------------------------------------------
    @action(
        detail=True,
        methods=["post"],
        url_path="publicar-pncp",
        parser_classes=[parsers.MultiPartParser, parsers.FormParser],
    )
    def publicar_pncp(self, request, pk=None):
        """
        Publica a contratação no PNCP (cria a compra + envia um documento inicial).
        Usa PNCPService.publicar_compra.
        """
        processo = self.get_object()
        arquivo = request.FILES.get("arquivo")
        titulo = request.data.get("titulo_documento") or "Edital de Licitação"

        if not arquivo:
            return Response(
                {"detail": "O arquivo do documento é obrigatório."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not processo.entidade_id or not (processo.entidade and processo.entidade.cnpj):
            return Response(
                {
                    "detail": "Processo sem Entidade/CNPJ. Preencha a entidade e o CNPJ antes de publicar."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not processo.orgao_id or not (processo.orgao and processo.orgao.codigo_unidade):
            return Response(
                {
                    "detail": "Processo sem Órgão/código da unidade compradora. Preencha orgao.codigo_unidade."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Tipo de documento inicial (normalmente 2 = Edital)
        raw_tipo = request.data.get("tipo_documento_id") or "2"
        try:
            tipo_documento_id = int(raw_tipo)
        except (TypeError, ValueError):
            tipo_documento_id = 2

        try:
            resultado = PNCPService.publicar_compra(
                processo=processo,
                arquivo=arquivo,
                titulo_documento=titulo,
                tipo_documento_id=tipo_documento_id,
            )

            updated_fields = []

            ano_compra = resultado.get("anoCompra") or resultado.get("ano_compra")
            sequencial_compra = (
                resultado.get("sequencialCompra")
                or resultado.get("sequencial_compra")
                or resultado.get("sequencialCompraPNCP")
            )
            numero_controle = (
                resultado.get("numeroControlePNCP")
                or resultado.get("numero_controle_pncp")
            )
            link_processo = (
                resultado.get("linkProcessoEletronico")
                or resultado.get("link_processo_eletronico")
            )

            if hasattr(processo, "pncp_ano_compra") and ano_compra:
                processo.pncp_ano_compra = ano_compra
                updated_fields.append("pncp_ano_compra")

            if hasattr(processo, "pncp_sequencial_compra") and sequencial_compra:
                processo.pncp_sequencial_compra = sequencial_compra
                updated_fields.append("pncp_sequencial_compra")

            if hasattr(processo, "pncp_numero_controle") and numero_controle:
                processo.pncp_numero_controle = numero_controle
                updated_fields.append("pncp_numero_controle")

            if hasattr(processo, "pncp_url") and link_processo:
                processo.pncp_url = link_processo
                updated_fields.append("pncp_url")

            if hasattr(processo, "pncp_ultimo_retorno"):
                processo.pncp_ultimo_retorno = resultado
                updated_fields.append("pncp_ultimo_retorno")

            processo.situacao = "publicado"
            updated_fields.append("situacao")

            if updated_fields:
                processo.save(update_fields=updated_fields)

            if hasattr(arquivo, 'seek'):
                arquivo.seek(0)

            # Registra documento inicial em DocumentoPNCP (metadados)
            DocumentoPNCP.objects.create(
                processo=processo,
                tipo_documento_id=tipo_documento_id,
                titulo=titulo,
                arquivo_nome=getattr(arquivo, "name", None),
                observacao=request.data.get("observacao") or None,
                arquivo=arquivo,
            )

            return Response(
                {"detail": "Publicado no PNCP com sucesso!", "pncp_data": resultado},
                status=status.HTTP_200_OK,
            )

        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            logger.exception("Erro interno PNCP (publicar_pncp)")
            return Response(
                {"detail": f"Erro interno ao publicar: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    # ----------------------------------------------------------------------
    # RETIFICAÇÃO: INSERIR NOVO DOCUMENTO NA CONTRATAÇÃO
    # ----------------------------------------------------------------------
    @action(
        detail=True,
        methods=["post"],
        url_path="retificar-pncp",
        parser_classes=[parsers.MultiPartParser, parsers.FormParser],
    )
    def retificar_pncp(self, request, pk=None):
        """
        Retificação: anexa um novo documento à contratação já existente no PNCP.
        Usa 6.3.6 Inserir Documento a uma Contratação.
        """
        processo = self.get_object()
        arquivo = request.FILES.get("arquivo")

        if not arquivo:
            return Response(
                {"detail": "O arquivo do documento é obrigatório."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        titulo = (
            request.data.get("titulo_documento")
            or request.data.get("titulo")
            or "Retificação"
        )[:255]
        justificativa = (
            request.data.get("justificativa")
            or request.data.get("observacao")
            or ""
        ).strip()

        if not justificativa:
            return Response(
                {"detail": "Justificativa/observação é obrigatória para retificação."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        raw_tipo = (
            request.data.get("tipo_documento_id")
            or request.data.get("tipo_documento")
            or "2"  # default: Edital
        )
        try:
            tipo_documento_id = int(raw_tipo)
        except (TypeError, ValueError):
            return Response(
                {
                    "detail": "tipo_documento_id deve ser um inteiro válido (ex: 1, 2, 3, 4, 5...)."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        ano_compra = (
            getattr(processo, "pncp_ano_compra", None)
            or request.data.get("ano_compra")
            or request.data.get("ano")
        )
        sequencial_compra = (
            getattr(processo, "pncp_sequencial_compra", None)
            or request.data.get("sequencial_compra")
            or request.data.get("sequencial")
        )

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

        if not processo.entidade or not processo.entidade.cnpj:
            return Response(
                {
                    "detail": "Processo sem Entidade/CNPJ. Preencha a entidade e o CNPJ antes."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        cnpj_orgao = re.sub(r"\D", "", processo.entidade.cnpj or "")
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

            if hasattr(processo, "pncp_ultimo_retorno"):
                processo.pncp_ultimo_retorno = resultado
                processo.save(update_fields=["pncp_ultimo_retorno"])

            # Registra em DocumentoPNCP
            DocumentoPNCP.objects.create(
                processo=processo,
                tipo_documento_id=tipo_documento_id,
                titulo=titulo,
                observacao=justificativa,
                arquivo_nome=getattr(arquivo, "name", None),
                arquivo=arquivo,
            )

            return Response(
                {
                    "detail": "Retificação enviada ao PNCP (documento anexado).",
                    "pncp_data": resultado,
                },
                status=status.HTTP_200_OK,
            )

        except ValueError as e:
            msg = str(e)
            m = re.search(r"\((\d{3})\)", msg)
            code = int(m.group(1)) if m else status.HTTP_400_BAD_REQUEST
            return Response({"detail": msg}, status=code)
        except Exception as e:
            logger.exception("Erro interno retificar PNCP")
            return Response(
                {"detail": f"Erro interno ao comunicar com PNCP: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    # ----------------------------------------------------------------------
    # ARQUIVOS PNCP (LISTAR REMOTO + ANEXAR NOVO)
    # ----------------------------------------------------------------------
    @action(
        detail=True,
        methods=["get", "post"],
        url_path="pncp/arquivos",
        parser_classes=[parsers.MultiPartParser, parsers.FormParser],
    )
    def pncp_arquivos(self, request, pk=None):
        """
        GET  -> lista documentos da contratação diretamente no PNCP (6.3.8).
                Se a contratação ainda não tiver referência PNCP, retorna 200
                com publicado = False e documentos = [].
        POST -> anexa um novo documento à contratação (6.3.6).
        """
        processo = self.get_object()

        ano_compra = (
            getattr(processo, "pncp_ano_compra", None)
            or request.data.get("ano_compra")
            or request.query_params.get("ano_compra")
        )
        sequencial_compra = (
            getattr(processo, "pncp_sequencial_compra", None)
            or request.data.get("sequencial_compra")
            or request.query_params.get("sequencial_compra")
        )

        # Se ainda não publicada no PNCP, GET deve responder 200 com info amigável
        if request.method == "GET" and (not ano_compra or not sequencial_compra):
            return Response(
                {
                    "publicado": False,
                    "detail": "Processo ainda não publicado no PNCP.",
                    "documentos": [],
                },
                status=status.HTTP_200_OK,
            )

        if not ano_compra or not sequencial_compra:
            return Response(
                {
                    "detail": (
                        "Processo ainda não tem referência PNCP (ano_compra/sequencial_compra). "
                        "Publique primeiro e grave esses campos, ou envie 'ano_compra' e 'sequencial_compra'."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not processo.entidade or not processo.entidade.cnpj:
            return Response(
                {
                    "detail": "Processo sem Entidade/CNPJ. Preencha a entidade e o CNPJ antes."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        cnpj_orgao = re.sub(r"\D", "", processo.entidade.cnpj or "")
        if len(cnpj_orgao) != 14:
            return Response(
                {"detail": "CNPJ da entidade inválido/ausente."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # --- GET: lista direto do PNCP
        if request.method == "GET":
            try:
                documentos = PNCPService.listar_documentos_compra(
                    cnpj_orgao=cnpj_orgao,
                    ano_compra=int(ano_compra),
                    sequencial_compra=int(sequencial_compra),
                )
                return Response(
                    {
                        "publicado": True,
                        "ano_compra": int(ano_compra),
                        "sequencial_compra": int(sequencial_compra),
                        "documentos": documentos,
                    },
                    status=status.HTTP_200_OK,
                )
            except ValueError as e:
                msg = str(e)
                m = re.search(r"\((\d{3})\)", msg)
                code = int(m.group(1)) if m else status.HTTP_400_BAD_REQUEST
                return Response({"detail": msg}, status=code)
            except Exception as e:
                logger.exception("Erro interno ao listar documentos PNCP")
                return Response(
                    {"detail": f"Erro interno ao listar documentos: {str(e)}"},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

        # --- POST: anexar novo documento no PNCP
        arquivo = request.FILES.get("arquivo")
        if not arquivo:
            return Response(
                {"detail": "O arquivo do documento é obrigatório."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        titulo = (
            request.data.get("titulo_documento")
            or request.data.get("titulo")
            or arquivo.name
        )[:255]
        raw_tipo = (
            request.data.get("tipo_documento_id")
            or request.data.get("tipo_documento")
            or "2"
        )
        try:
            tipo_documento_id = int(raw_tipo)
        except (TypeError, ValueError):
            return Response(
                {"detail": "tipo_documento_id deve ser um inteiro válido."},
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

            # Registra em DocumentoPNCP
            DocumentoPNCP.objects.create(
                processo=processo,
                tipo_documento_id=tipo_documento_id,
                titulo=titulo,
                arquivo_nome=getattr(arquivo, "name", None),
                observacao=request.data.get("observacao") or None,
                arquivo=arquivo,
            )

            return Response(
                {
                    "detail": "Documento anexado ao PNCP com sucesso.",
                    "pncp_data": resultado,
                },
                status=status.HTTP_201_CREATED,
            )
        except ValueError as e:
            msg = str(e)
            m = re.search(r"\((\d{3})\)", msg)
            code = int(m.group(1)) if m else status.HTTP_400_BAD_REQUEST
            return Response({"detail": msg}, status=code)
        except Exception as e:
            logger.exception("Erro interno ao anexar documento PNCP")
            return Response(
                {"detail": f"Erro interno ao anexar documento: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    # ----------------------------------------------------------------------
    # EXCLUIR DOCUMENTO DO PNCP (NÃO APAGA LOCAL)
    # ----------------------------------------------------------------------
    @action(
        detail=True,
        methods=["delete"],
        url_path=r"pncp/arquivos/(?P<sequencial_documento>\d+)",
    )
    def excluir_pncp_arquivo(self, request, pk=None, sequencial_documento=None):
        """
        Exclui um documento de uma contratação no PNCP (6.3.7).
        NÃO remove os documentos locais do processo.
        """
        processo = self.get_object()

        ano_compra = (
            getattr(processo, "pncp_ano_compra", None)
            or request.data.get("ano_compra")
        )
        sequencial_compra = (
            getattr(processo, "pncp_sequencial_compra", None)
            or request.data.get("sequencial_compra")
        )

        if not ano_compra or not sequencial_compra:
            return Response(
                {
                    "detail": (
                        "Processo ainda não tem referência PNCP (ano_compra/sequencial_compra). "
                        "Publique primeiro e grave esses campos, ou envie 'ano_compra' e 'sequencial_compra'."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not processo.entidade or not processo.entidade.cnpj:
            return Response(
                {
                    "detail": "Processo sem Entidade/CNPJ. Preencha a entidade e o CNPJ antes."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        cnpj_orgao = re.sub(r"\D", "", processo.entidade.cnpj or "")
        if len(cnpj_orgao) != 14:
            return Response(
                {"detail": "CNPJ da entidade inválido/ausente."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        justificativa = (
            request.data.get("justificativa")
            or "Exclusão solicitada pelo sistema de origem."
        )

        try:
            ok = PNCPService.excluir_documento_compra(
                cnpj_orgao=cnpj_orgao,
                ano_compra=int(ano_compra),
                sequencial_compra=int(sequencial_compra),
                sequencial_arquivo=int(sequencial_documento),
                # justificativa=justificativa, # Se a API do serviço aceitar
            )
            if ok:
                return Response(
                    {"detail": "Documento excluído com sucesso do PNCP."},
                    status=status.HTTP_200_OK,
                )
            return Response(
                {"detail": "Falha ao excluir documento no PNCP."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except ValueError as e:
            msg = str(e)
            m = re.search(r"\((\d{3})\)", msg)
            code = int(m.group(1)) if m else status.HTTP_400_BAD_REQUEST
            return Response({"detail": msg}, status=code)
        except Exception as e:
            logger.exception("Erro interno ao excluir documento PNCP")
            return Response(
                {"detail": f"Erro interno ao excluir documento: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    # ----------------------------------------------------------------------
    # SUBSTITUIR DOCUMENTO NO PNCP (EXCLUI + ANEXA NOVO)
    # ----------------------------------------------------------------------
    @action(
        detail=True,
        methods=["post"],
        url_path=r"pncp/arquivos/(?P<sequencial_documento>\d+)/substituir",
        parser_classes=[parsers.MultiPartParser, parsers.FormParser],
    )
    def substituir_pncp_arquivo(self, request, pk=None, sequencial_documento=None):
        """
        Substitui um documento de uma contratação no PNCP:
        1) Exclui o arquivo antigo com justificativa
        2) Anexa o novo arquivo (6.3.6 + 6.3.7)
        """
        processo = self.get_object()
        arquivo = request.FILES.get("arquivo")

        if not arquivo:
            return Response(
                {"detail": "O novo arquivo do documento é obrigatório."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        ano_compra = (
            getattr(processo, "pncp_ano_compra", None)
            or request.data.get("ano_compra")
        )
        sequencial_compra = (
            getattr(processo, "pncp_sequencial_compra", None)
            or request.data.get("sequencial_compra")
        )

        if not ano_compra or not sequencial_compra:
            return Response(
                {
                    "detail": (
                        "Processo ainda não tem referência PNCP (ano_compra/sequencial_compra). "
                        "Publique primeiro e grave esses campos, ou envie 'ano_compra' e 'sequencial_compra'."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not processo.entidade or not processo.entidade.cnpj:
            return Response(
                {
                    "detail": "Processo sem Entidade/CNPJ. Preencha a entidade e o CNPJ antes."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        cnpj_orgao = re.sub(r"\D", "", processo.entidade.cnpj or "")
        if len(cnpj_orgao) != 14:
            return Response(
                {"detail": "CNPJ da entidade inválido/ausente."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        justificativa = (
            request.data.get("justificativa")
            or "Substituição de documento solicitada pelo sistema de origem."
        )
        titulo = (
            request.data.get("titulo_documento")
            or request.data.get("titulo")
            or arquivo.name
        )[:255]
        raw_tipo = (
            request.data.get("tipo_documento_id")
            or request.data.get("tipo_documento")
            or "2"
        )
        try:
            novo_tipo_id = int(raw_tipo)
        except (TypeError, ValueError):
            return Response(
                {"detail": "tipo_documento_id deve ser um inteiro válido."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            resultado = PNCPService.substituir_documento(
                cnpj_orgao=cnpj_orgao,
                ano_compra=int(ano_compra),
                sequencial_compra=int(sequencial_compra),
                sequencial_arquivo_antigo=int(sequencial_documento),
                novo_arquivo=arquivo,
                novo_titulo=titulo,
                novo_tipo_id=novo_tipo_id,
                # justificativa_exclusao=justificativa, # Se o serviço suportar
            )

            # Registra o novo documento em DocumentoPNCP (não mexo no antigo local)
            DocumentoPNCP.objects.create(
                processo=processo,
                tipo_documento_id=novo_tipo_id,
                titulo=titulo,
                observacao=justificativa,
                arquivo_nome=getattr(arquivo, "name", None),
                arquivo=arquivo,
            )

            return Response(
                {
                    "detail": "Documento substituído com sucesso no PNCP.",
                    "pncp_data": resultado,
                },
                status=status.HTTP_200_OK,
            )
        except ValueError as e:
            msg = str(e)
            m = re.search(r"\((\d{3})\)", msg)
            code = int(m.group(1)) if m else status.HTTP_400_BAD_REQUEST
            return Response({"detail": msg}, status=code)
        except Exception as e:
            logger.exception("Erro interno ao substituir documento PNCP")
            return Response(
                {"detail": f"Erro interno ao substituir documento: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

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

    # ----------------------------------------------------------------------
    # PUBLICAR RESULTADO DA COMPRA NO PNCP (6.3.9)
    # Envia os resultados (fornecedores vencedores por item)
    # ----------------------------------------------------------------------
    @action(detail=True, methods=["post"], url_path="pncp/resultado")
    def publicar_resultado_pncp(self, request, pk=None):
        """
        Publica os resultados da compra no PNCP.
        Monta automaticamente o payload a partir dos ItemFornecedor com vencedor=True.
        """
        processo = self.get_object()

        if not processo.pncp_ano_compra or not processo.pncp_sequencial_compra:
            return Response(
                {"detail": "Processo não publicado no PNCP ainda."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not processo.entidade or not processo.entidade.cnpj:
            return Response(
                {"detail": "Processo sem Entidade/CNPJ."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        cnpj = re.sub(r"\D", "", processo.entidade.cnpj or "")

        # Busca propostas vencedoras
        vencedores = ItemFornecedor.objects.filter(
            item__processo=processo,
            vencedor=True
        ).select_related("item", "fornecedor")

        if not vencedores.exists():
            return Response(
                {"detail": "Nenhum item possui fornecedor vencedor definido."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        resultados = []
        for v in vencedores:
            cnpj_forn = re.sub(r"\D", "", v.fornecedor.cnpj or "")
            resultados.append({
                "numeroItem": v.item.pncp_numero_item or v.item.ordem,
                "niFornecedor": cnpj_forn,
                "tipoPessoaFornecedor": "PJ" if len(cnpj_forn) == 14 else "PF",
                "valorUnitario": float(v.valor_proposto or 0),
                "quantidadeHomologada": float(v.item.quantidade or 0),
            })

        try:
            token = PNCPService._get_token()
            url = (
                f"{PNCPService.BASE_URL}/orgaos/{cnpj}/compras/"
                f"{processo.pncp_ano_compra}/{processo.pncp_sequencial_compra}/resultados"
            )
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "accept": "application/json",
            }
            payload = {"resultadosCompraItem": resultados}

            resp = requests.post(
                url,
                headers=headers,
                json=payload,
                verify=PNCPService.VERIFY_SSL,
                timeout=60,
            )

            if resp.status_code in (200, 201):
                return Response(
                    {"detail": "Resultado publicado no PNCP com sucesso!", "itens": len(resultados)},
                    status=status.HTTP_200_OK,
                )
            else:
                try:
                    err = resp.json()
                except Exception:
                    err = resp.text
                return Response(
                    {"detail": f"PNCP retornou {resp.status_code}", "pncp_error": err},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        except Exception as e:
            logger.exception("Erro ao publicar resultado no PNCP")
            return Response(
                {"detail": f"Erro: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

# ============================================================
# 4️⃣ LOTE
# ============================================================


class LoteViewSet(EntidadeFilterMixin, viewsets.ModelViewSet):
    serializer_class = LoteSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ["processo"]
    search_fields = ["descricao"]
    entidade_field = 'processo__entidade'

    def get_queryset(self):
        qs = Lote.objects.select_related("processo", "processo__entidade").all()
        return self.filter_by_entidade(qs)

    @action(detail=False, methods=["post"], url_path="bulk-delete")
    def bulk_delete(self, request):
        """Exclui múltiplos lotes de uma vez. Itens vinculados ficam sem lote."""
        ids = request.data.get("ids", [])
        if not ids or not isinstance(ids, list):
            return Response({"error": "Envie uma lista de IDs."}, status=status.HTTP_400_BAD_REQUEST)
        # desvincula itens antes de deletar
        Item.objects.filter(lote_id__in=ids).update(lote=None)
        deleted, _ = Lote.objects.filter(id__in=ids).delete()
        return Response({"deleted": deleted}, status=status.HTTP_200_OK)


# ============================================================
# 5️⃣ ITEM
# ============================================================


class ItemViewSet(EntidadeFilterMixin, viewsets.ModelViewSet):
    serializer_class = ItemSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ["processo", "lote", "fornecedor"]
    search_fields = ["descricao", "unidade", "especificacao"]
    entidade_field = 'processo__entidade'

    def get_queryset(self):
        qs = Item.objects.select_related("processo", "lote", "fornecedor", "processo__entidade").all()
        return self.filter_by_entidade(qs)

    @action(detail=False, methods=["post"], url_path="bulk-delete")
    def bulk_delete(self, request):
        """Exclui múltiplos itens de uma vez."""
        ids = request.data.get("ids", [])
        if not ids or not isinstance(ids, list):
            return Response({"error": "Envie uma lista de IDs."}, status=status.HTTP_400_BAD_REQUEST)
        deleted, _ = Item.objects.filter(id__in=ids).delete()
        return Response({"deleted": deleted}, status=status.HTTP_200_OK)

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


class FornecedorProcessoViewSet(EntidadeFilterMixin, viewsets.ModelViewSet):
    serializer_class = FornecedorProcessoSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ["processo", "fornecedor"]
    search_fields = ["fornecedor__razao_social", "fornecedor__cnpj"]
    entidade_field = 'processo__entidade'

    def get_queryset(self):
        qs = FornecedorProcesso.objects.select_related(
            "processo", "fornecedor", "processo__entidade"
        ).all()
        return self.filter_by_entidade(qs)

    @action(detail=False, methods=["post"], url_path="bulk-delete")
    def bulk_delete(self, request):
        """Remove múltiplos fornecedores de um processo de uma vez."""
        ids = request.data.get("ids", [])
        processo_id = request.data.get("processo_id")
        if not ids or not isinstance(ids, list):
            return Response({"error": "Envie uma lista de IDs de fornecedores."}, status=status.HTTP_400_BAD_REQUEST)
        if processo_id:
            deleted, _ = FornecedorProcesso.objects.filter(processo_id=processo_id, fornecedor_id__in=ids).delete()
        else:
            deleted, _ = FornecedorProcesso.objects.filter(fornecedor_id__in=ids).delete()
        return Response({"deleted": deleted}, status=status.HTTP_200_OK)


class ItemFornecedorViewSet(EntidadeFilterMixin, viewsets.ModelViewSet):
    serializer_class = ItemFornecedorSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ["item", "fornecedor", "vencedor"]
    search_fields = ["item__descricao", "fornecedor__razao_social"]
    entidade_field = 'item__processo__entidade'

    def get_queryset(self):
        qs = ItemFornecedor.objects.select_related(
            "item", "fornecedor", "item__processo"
        ).all()
        return self.filter_by_entidade(qs)


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

    def get(self, request):
        user = request.user
        entidade_ids = list(user.entidades.values_list('id', flat=True))

        # Superuser vê tudo; usuário normal vê apenas das suas entidades
        if user.is_superuser:
            processos_qs = ProcessoLicitatorio.objects.all()
            itens_qs = Item.objects.all()
            orgaos_qs = Orgao.objects.all()
        elif entidade_ids:
            processos_qs = ProcessoLicitatorio.objects.filter(entidade_id__in=entidade_ids)
            itens_qs = Item.objects.filter(processo__entidade_id__in=entidade_ids)
            orgaos_qs = Orgao.objects.filter(entidade_id__in=entidade_ids)
        else:
            # Usuário sem entidades: não vê nada
            processos_qs = ProcessoLicitatorio.objects.none()
            itens_qs = Item.objects.none()
            orgaos_qs = Orgao.objects.none()

        data = {
            "total_processos": processos_qs.count(),
            "processos_em_andamento": processos_qs.filter(situacao="em_contratacao").count(),
            "processos_publicados": processos_qs.filter(situacao="publicado").count(),
            "total_fornecedores": Fornecedor.objects.count(),
            "total_orgaos": orgaos_qs.count(),
            "total_itens": itens_qs.count(),
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


class ContratoEmpenhoViewSet(EntidadeFilterMixin, viewsets.ModelViewSet):
    serializer_class = ContratoEmpenhoSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ["processo", "ano_contrato", "tipo_contrato_id", "receita"]
    search_fields = [
        "numero_contrato_empenho",
        "processo__numero_processo",
        "ni_fornecedor",
    ]
    entidade_field = 'processo__entidade'

    def get_queryset(self):
        qs = (
            ContratoEmpenho.objects.select_related("processo", "processo__entidade")
            .all()
            .order_by("-criado_em", "id")
        )
        return self.filter_by_entidade(qs)

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

    def _safe_get_recipients(self, anotacao):
        try:
            return list(anotacao.compartilhada_com.all())
        except Exception:
            logger.exception("Falha ao obter destinatários da anotação %s", getattr(anotacao, "id", None))
            return []

    def _notify_users(self, recipients, actor, tipo_acao, titulo, mensagem, anotacao=None, processo=None):
        try:
            rows = []
            for u in recipients:
                if not u or not getattr(u, "id", None):
                    continue
                if actor and u.id == actor.id:
                    continue
                rows.append(
                    Notificacao(
                        usuario=u,
                        ator=actor,
                        tipo_acao=tipo_acao,
                        titulo=titulo,
                        mensagem=mensagem,
                        anotacao=anotacao,
                        processo=processo,
                    )
                )
            if rows:
                Notificacao.objects.bulk_create(rows)
        except (ProgrammingError, OperationalError):
            logger.exception("Falha de banco ao criar notificações de anotação; ignorando para não quebrar fluxo")
        except Exception:
            logger.exception("Falha inesperada ao criar notificações de anotação; ignorando para não quebrar fluxo")

    def _allowed_process_ids(self):
        user = self.request.user
        if user.is_superuser or user.is_staff:
            return None
        entidade_ids = list(user.entidades.values_list("id", flat=True))
        if not entidade_ids:
            return []
        return list(
            ProcessoLicitatorio.objects.filter(entidade_id__in=entidade_ids).values_list("id", flat=True)
        )

    def get_queryset(self):
        user = self.request.user
        qs = (
            Anotacao.objects.select_related("usuario", "processo")
            .prefetch_related("compartilhada_com")
            .filter(Q(usuario=user) | Q(compartilhada_com=user))
            .distinct()
            .order_by('-criado_em')
        )

        processo_id = self.request.query_params.get("processo")
        if processo_id:
            qs = qs.filter(processo_id=processo_id)

        allowed_process_ids = self._allowed_process_ids()
        if allowed_process_ids is not None:
            qs = qs.filter(Q(processo__isnull=True) | Q(processo_id__in=allowed_process_ids))

        return qs

    def _assert_processo_permitido(self, processo_id):
        if not processo_id:
            return
        allowed_process_ids = self._allowed_process_ids()
        if allowed_process_ids is None:
            return
        try:
            processo_id = int(processo_id)
        except (TypeError, ValueError):
            raise PermissionDenied("Processo inválido.")
        if processo_id not in set(allowed_process_ids):
            raise PermissionDenied("Você não tem acesso a este processo.")

    def perform_create(self, serializer):
        processo_id = self.request.data.get("processo")
        self._assert_processo_permitido(processo_id)
        anotacao = serializer.save(usuario=self.request.user)

        recipients = self._safe_get_recipients(anotacao)
        if recipients:
            titulo = "Nova anotação compartilhada"
            mensagem = f"@{self.request.user.username} compartilhou uma anotação com você."
            self._notify_users(
                recipients=recipients,
                actor=self.request.user,
                tipo_acao="create",
                titulo=titulo,
                mensagem=mensagem,
                anotacao=anotacao,
                processo=anotacao.processo,
            )

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        before_done = instance.concluida
        recipients_before = self._safe_get_recipients(instance)

        # Quem recebeu a anotação pode apenas marcar/desmarcar concluída
        if instance.usuario_id != request.user.id:
            allowed_keys = {"concluida"}
            incoming_keys = set(request.data.keys())
            if not incoming_keys.issubset(allowed_keys):
                return Response(
                    {"detail": "Você só pode marcar/desmarcar a tarefa compartilhada."},
                    status=status.HTTP_403_FORBIDDEN,
                )

        processo_id = request.data.get("processo")
        if processo_id is not None:
            self._assert_processo_permitido(processo_id)

        response = super().update(request, *args, **kwargs)

        instance.refresh_from_db()
        recipients_after = self._safe_get_recipients(instance)

        # CHECK: quando muda concluída
        if before_done != instance.concluida:
            check_targets = {u.id: u for u in (recipients_before + recipients_after)}
            if instance.usuario:
                check_targets[instance.usuario.id] = instance.usuario
            titulo = "Status da anotação alterado"
            mensagem = f"@{request.user.username} marcou a anotação como {'concluída' if instance.concluida else 'pendente'}."
            self._notify_users(
                recipients=list(check_targets.values()),
                actor=request.user,
                tipo_acao="check",
                titulo=titulo,
                mensagem=mensagem,
                anotacao=instance,
                processo=instance.processo,
            )
        else:
            # EDIÇÃO de conteúdo/compartilhamento
            targets = {u.id: u for u in (recipients_before + recipients_after)}
            if instance.usuario_id != request.user.id:
                targets[instance.usuario.id] = instance.usuario
            if targets:
                titulo = "Anotação atualizada"
                mensagem = f"@{request.user.username} atualizou uma anotação compartilhada."
                self._notify_users(
                    recipients=list(targets.values()),
                    actor=request.user,
                    tipo_acao="update",
                    titulo=titulo,
                    mensagem=mensagem,
                    anotacao=instance,
                    processo=instance.processo,
                )

        return response

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.usuario_id != request.user.id:
            return Response(
                {"detail": "Somente o autor pode excluir a anotação."},
                status=status.HTTP_403_FORBIDDEN,
            )

        recipients = self._safe_get_recipients(instance)
        processo = instance.processo
        titulo_note = instance.titulo or (instance.texto[:40] if instance.texto else "anotação")

        try:
            response = super().destroy(request, *args, **kwargs)
        except (ProgrammingError, OperationalError):
            logger.exception(
                "Falha ao excluir anotação %s via collector; tentando exclusão direta (possível migração pendente)",
                instance.id,
            )
            try:
                using = instance._state.db or "default"
                deleted = Anotacao.objects.using(using).filter(pk=instance.pk)._raw_delete(using)
                if deleted:
                    return Response(status=status.HTTP_204_NO_CONTENT)
            except Exception:
                logger.exception("Fallback de exclusão direta falhou para anotação %s", instance.id)
            return Response(
                {
                    "detail": (
                        "Não foi possível excluir a anotação por inconsistência de banco. "
                        "Execute as migrações do backend e tente novamente."
                    )
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        if recipients:
            self._notify_users(
                recipients=recipients,
                actor=request.user,
                tipo_acao="delete",
                titulo="Anotação excluída",
                mensagem=f"@{request.user.username} excluiu a anotação: {titulo_note}",
                anotacao=None,
                processo=processo,
            )

        return response


class UsuarioLookupView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        term = (request.query_params.get("q") or "").strip()
        processo_id = (request.query_params.get("processo") or "").strip()
        qs = User.objects.all().order_by("username")

        if request.user.is_superuser or request.user.is_staff:
            pass
        else:
            entidade_ids = list(request.user.entidades.values_list("id", flat=True))
            if processo_id:
                try:
                    processo = ProcessoLicitatorio.objects.get(pk=int(processo_id))
                    if not entidade_ids or processo.entidade_id not in entidade_ids:
                        qs = qs.none()
                    else:
                        qs = qs.filter(entidades__id=processo.entidade_id).distinct()
                except Exception:
                    qs = qs.none()
            else:
                if entidade_ids:
                    qs = qs.filter(entidades__id__in=entidade_ids).distinct()
                else:
                    qs = qs.filter(id=request.user.id)

        if term:
            qs = qs.filter(
                Q(username__icontains=term)
                | Q(first_name__icontains=term)
                | Q(last_name__icontains=term)
            )

        data = [
            {
                "id": u.id,
                "username": u.username,
                "nome": u.get_full_name() or u.username,
            }
            for u in qs[:20]
        ]
        return Response(data)


class NotificacaoViewSet(viewsets.ModelViewSet):
    serializer_class = NotificacaoSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "patch", "head", "options"]

    def get_queryset(self):
        return Notificacao.objects.filter(usuario=self.request.user).order_by("-criado_em")

# ============================================================
# 🗂️ ARQUIVOS USUÁRIO VIEWSET
# ============================================================

class ArquivoUserViewSet(viewsets.ModelViewSet):
    serializer_class = ArquivoUserSerializer
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_queryset(self):
        # Retorna apenas os arquivos do usuário logado
        return ArquivoUser.objects.filter(usuario=self.request.user).order_by('-enviado_em')

    def perform_create(self, serializer):
        # Vincula automaticamente o arquivo ao usuário logado
        serializer.save(usuario=self.request.user)




class DocumentoPNCPViewSet(EntidadeFilterMixin, viewsets.ModelViewSet):
    serializer_class = DocumentoPNCPSerializer
    permission_classes = [IsAuthenticated]
    parser_classes = (MultiPartParser, FormParser, JSONParser)
    entidade_field = 'processo__entidade'

    def get_queryset(self):
        qs = DocumentoPNCP.objects.select_related("processo", "processo__entidade").all().order_by("-criado_em")
        return self.filter_by_entidade(qs)

    def _extrair_sequencial_location(self, location: str):
        """
        PNCP normalmente devolve um header Location com o recurso criado.
        Ex.: .../arquivos/123 -> extrai 123
        """
        if not location:
            return None
        m = re.search(r"/(\d+)\s*$", str(location).strip())
        return int(m.group(1)) if m else None

    @action(detail=True, methods=["post"], url_path="enviar-ao-pncp")
    def enviar_ao_pncp(self, request, pk=None):
        doc = self.get_object()
        processo = doc.processo

        # 1) Validar se existe arquivo
        if not doc.arquivo:
            return Response(
                {"detail": "Documento não possui arquivo para envio."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 2) Validar se o processo já existe no PNCP (compra publicada)
        if not processo.pncp_ano_compra or not processo.pncp_sequencial_compra:
            return Response(
                {
                    "detail": (
                        "Este processo ainda não foi publicado no PNCP. "
                        "Publique a contratação primeiro (processo.pncp_ano_compra e processo.pncp_sequencial_compra)."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 3) Validar CNPJ
        if not processo.entidade or not processo.entidade.cnpj:
            return Response(
                {"detail": "Entidade/CNPJ não configurado no processo."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        cnpj_orgao = re.sub(r"\D", "", processo.entidade.cnpj or "")
        if len(cnpj_orgao) != 14:
            return Response(
                {"detail": "CNPJ da entidade inválido."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 4) Se já enviado e tem sequencial, você decide a regra:
        # aqui eu bloqueio reenvio para evitar duplicidade.
        if doc.status == "enviado" and doc.pncp_sequencial_documento:
            return Response(
                {"detail": "Documento já foi enviado ao PNCP."},
                status=status.HTTP_409_CONFLICT,
            )

        # 5) Envio ao PNCP (6.3.6 – Inserir Documento a uma Contratação)
        try:
            # garante ponteiro no início
            with doc.arquivo.open("rb") as f:
                result = PNCPService.anexar_documento_compra(
                    cnpj_orgao=cnpj_orgao,
                    ano_compra=int(processo.pncp_ano_compra),
                    sequencial_compra=int(processo.pncp_sequencial_compra),
                    arquivo=f,
                    titulo_documento=doc.titulo or "Documento",
                    tipo_documento_id=int(doc.tipo_documento_id),
                    content_type="application/pdf",  # ajuste se você detectar mimetype real
                )
        except Exception as exc:
            # marca erro local
            doc.status = "erro"
            doc.save(update_fields=["status"])
            return Response(
                {"detail": f"Falha ao enviar documento ao PNCP: {str(exc)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # 6) Atualiza metadados locais após sucesso
        location = (result or {}).get("location")
        sequencial = (
            (result or {}).get("sequencialDocumento")
            or (result or {}).get("sequencial_arquivo")
            or self._extrair_sequencial_location(location)
        )

        doc.pncp_sequencial_documento = sequencial
        doc.pncp_publicado_em = timezone.now()
        doc.status = "enviado"
        doc.save(update_fields=["pncp_sequencial_documento", "pncp_publicado_em", "status"])

        return Response(self.get_serializer(doc).data, status=status.HTTP_200_OK)
    
class AtaRegistroPrecosViewSet(EntidadeFilterMixin, viewsets.ModelViewSet):
    serializer_class = AtaRegistroPrecosSerializer
    permission_classes = [IsAuthenticated]
    entidade_field = 'processo__entidade'

    def get_queryset(self):
        qs = AtaRegistroPrecos.objects.select_related(
            "processo", "processo__entidade"
        ).filter(ativo=True).order_by("-criado_em")
        qs = self.filter_by_entidade(qs)
        processo_id = self.request.query_params.get("processo")
        if processo_id:
            qs = qs.filter(processo_id=processo_id)
        return qs

    def perform_destroy(self, instance):
        instance.ativo = False
        instance.status = "cancelada"
        instance.save(update_fields=["ativo", "status"])

    @action(detail=False, methods=["post"], url_path="bulk-delete")
    def bulk_delete(self, request):
        """Cancela (soft-delete) múltiplas atas de uma vez."""
        ids = request.data.get("ids", [])
        if not ids or not isinstance(ids, list):
            return Response({"error": "Envie uma lista de IDs."}, status=status.HTTP_400_BAD_REQUEST)
        updated = AtaRegistroPrecos.objects.filter(id__in=ids, ativo=True).update(ativo=False, status="cancelada")
        return Response({"deleted": updated}, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"], url_path="publicar-no-pncp")
    def publicar_no_pncp(self, request, pk=None):
        ata = self.get_object()
        processo = ata.processo

        if not processo.pncp_ano_compra or not processo.pncp_sequencial_compra:
            return Response(
                {"detail": "Processo ainda não foi publicado no PNCP."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not processo.entidade or not processo.entidade.cnpj:
            return Response(
                {"detail": "Entidade/CNPJ da contratação não configurados."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        cnpj = re.sub(r"\D", "", processo.entidade.cnpj or "")
        if len(cnpj) != 14:
            return Response(
                {"detail": "CNPJ da entidade inválido."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # valida campos obrigatórios da ata
        if not ata.numero_ata or not ata.ano_ata:
            return Response(
                {"detail": "Número e ano da Ata são obrigatórios."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not ata.data_assinatura or not ata.data_vigencia_inicio or not ata.data_vigencia_fim:
            return Response(
                {"detail": "Datas de assinatura, início e fim de vigência são obrigatórias."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            result = PNCPService.inserir_ata_registro_preco(
                cnpj_orgao=cnpj,
                ano_compra=processo.pncp_ano_compra,
                sequencial_compra=processo.pncp_sequencial_compra,
                numero_ata_registro_preco=ata.numero_ata,
                ano_ata=ata.ano_ata,
                data_assinatura=ata.data_assinatura.isoformat(),
                data_vigencia_inicio=ata.data_vigencia_inicio.isoformat(),
                data_vigencia_fim=ata.data_vigencia_fim.isoformat(),
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        ata.pncp_sequencial_ata = result.get("sequencialAta")
        ata.numero_controle_pncp = result.get("numeroControlePNCP")  # se futuramente você buscar
        ata.status = "publicada"
        ata.pncp_publicada_em = timezone.now()
        ata.save(update_fields=[
            "pncp_sequencial_ata",
            "numero_controle_pncp",
            "status",
            "pncp_publicada_em",
        ])

        ser = self.get_serializer(ata)
        return Response(ser.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"], url_path="excluir-do-pncp")
    def excluir_do_pncp(self, request, pk=None):
        ata = self.get_object()
        processo = ata.processo

        if not processo.pncp_ano_compra or not processo.pncp_sequencial_compra:
            return Response(
                {"detail": "Processo ainda não foi publicado no PNCP."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not ata.pncp_sequencial_ata:
            return Response(
                {"detail": "Ata não possui sequencial no PNCP."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not processo.entidade or not processo.entidade.cnpj:
            return Response(
                {"detail": "Entidade/CNPJ da contratação não configurados."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        cnpj = re.sub(r"\D", "", processo.entidade.cnpj or "")
        if len(cnpj) != 14:
            return Response(
                {"detail": "CNPJ da entidade inválido."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        justificativa = request.data.get(
            "justificativa",
            "Exclusão de Ata de Registro de Preços solicitada pelo sistema de origem.",
        )

        try:
            PNCPService.excluir_ata_registro_preco(
                cnpj_orgao=cnpj,
                ano_compra=processo.pncp_ano_compra,
                sequencial_compra=processo.pncp_sequencial_compra,
                sequencial_ata=ata.pncp_sequencial_ata,
                justificativa=justificativa,
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        # localmente, marca como cancelada mas mantém registro
        ata.status = "cancelada"
        ata.save(update_fields=["status"])

        ser = self.get_serializer(ata)
        return Response(ser.data, status=status.HTTP_200_OK)
    
class DocumentoAtaRegistroPrecosViewSet(EntidadeFilterMixin, viewsets.ModelViewSet):
    serializer_class = DocumentoAtaRegistroPrecosSerializer
    permission_classes = [IsAuthenticated]
    parser_classes = (MultiPartParser, FormParser, JSONParser)
    entidade_field = 'ata__processo__entidade'

    def get_queryset(self):
        qs = DocumentoAtaRegistroPrecos.objects.select_related(
            "ata", "ata__processo", "ata__processo__entidade"
        ).filter(ativo=True).order_by("-criado_em")
        qs = self.filter_by_entidade(qs)
        ata_id = self.request.query_params.get("ata")
        if ata_id:
            qs = qs.filter(ata_id=ata_id)
        return qs

    def create(self, request, *args, **kwargs):
        ata_id = request.data.get("ata")
        tipo_id = request.data.get("tipo_documento_id")
        arquivo = request.FILES.get("arquivo")

        if not ata_id or not tipo_id:
            return Response(
                {"detail": "Campos 'ata' e 'tipo_documento_id' são obrigatórios."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not arquivo:
            return Response(
                {"detail": "Campo 'arquivo' é obrigatório."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        ata = get_object_or_404(AtaRegistroPrecos, pk=ata_id, ativo=True)

        # hash do arquivo
        content = arquivo.read()
        file_hash = hashlib.sha256(content).hexdigest()
        arquivo.seek(0)

        # upsert por (ata, tipo_documento_id)
        existing = (
            DocumentoAtaRegistroPrecos.objects.filter(
                ata=ata,
                tipo_documento_id=tipo_id,
                ativo=True,
            )
            .exclude(status="removido")
            .order_by("-criado_em")
            .first()
        )

        titulo = request.data.get("titulo") or TIPO_DOC_MAPA.get(int(tipo_id), "Documento")

        if existing and existing.status != "enviado":
            existing.arquivo = arquivo
            existing.arquivo_nome = arquivo.name
            existing.arquivo_hash = file_hash
            existing.titulo = titulo
            existing.status = "rascunho"
            existing.ativo = True
            existing.save()
            ser = self.get_serializer(existing)
            return Response(ser.data, status=status.HTTP_200_OK)

        doc = DocumentoAtaRegistroPrecos.objects.create(
            ata=ata,
            tipo_documento_id=tipo_id,
            titulo=titulo,
            observacao=request.data.get("observacao") or None,
            arquivo=arquivo,
            arquivo_nome=arquivo.name,
            arquivo_hash=file_hash,
            status="rascunho",
            ativo=True,
        )
        ser = self.get_serializer(doc)
        return Response(ser.data, status=status.HTTP_201_CREATED)

    def destroy(self, request, *args, **kwargs):
        obj = self.get_object()
        obj.ativo = False
        obj.status = "removido"
        obj.save(update_fields=["ativo", "status"])
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"], url_path="enviar-ao-pncp")
    def enviar_ao_pncp(self, request, pk=None):
        """
        Envia o DOCUMENTO da Ata ao PNCP (6.4.6 – inserir documento de uma Ata).
        Usa os dados de publicação da COMPRA (processo) + sequencial da ATA.
        """
        doc = self.get_object()
        ata = doc.ata
        processo = ata.processo

        # Compra precisa estar publicada
        if not processo.pncp_ano_compra or not processo.pncp_sequencial_compra:
            return Response(
                {"detail": "Processo ainda não publicado no PNCP (ano/seq)."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Ata precisa ter sido inserida no PNCP (sequencialAta)
        if not ata.pncp_sequencial_ata:
            return Response(
                {"detail": "Ata ainda não publicada no PNCP (sequencialAta ausente)."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not processo.entidade or not processo.entidade.cnpj:
            return Response(
                {"detail": "Entidade/CNPJ da contratação não configurados."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        cnpj = re.sub(r"\D", "", processo.entidade.cnpj or "")
        if len(cnpj) != 14:
            return Response(
                {"detail": "CNPJ da entidade inválido."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not doc.arquivo:
            return Response(
                {"detail": "Documento sem arquivo para envio."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # tenta pegar o content_type, mas se não vier, assume PDF
        content_type = getattr(getattr(doc.arquivo, "file", None), "content_type", "application/pdf")

        try:
            # 6.4.6 – Inserir Documento de uma Ata
            result = PNCPService.anexar_documento_ata(
                cnpj_orgao=cnpj,
                ano_compra=processo.pncp_ano_compra,
                sequencial_compra=processo.pncp_sequencial_compra,
                sequencial_ata=ata.pncp_sequencial_ata,
                arquivo=doc.arquivo,
                titulo_documento=doc.titulo,
                tipo_documento_id=doc.tipo_documento_id,
                content_type=content_type,
            )
        except ValueError as exc:
            # marca como erro se der falha de integração
            doc.status = "erro"
            doc.save(update_fields=["status"])
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        seq = (
            result.get("sequencialDocumento")
            or result.get("sequencialArquivo")
            or result.get("sequencial")
        )

        doc.status = "enviado"
        doc.pncp_sequencial_documento = seq
        doc.pncp_publicado_em = timezone.now()
        doc.save(update_fields=["status", "pncp_sequencial_documento", "pncp_publicado_em"])

        # se quiser, pode marcar a ata como publicada (ainda que já esteja)
        if ata.status != "publicada":
            ata.status = "publicada"
            ata.pncp_publicada_em = ata.pncp_publicada_em or timezone.now()
            ata.save(update_fields=["status", "pncp_publicada_em"])

        ser = self.get_serializer(doc)
        return Response(ser.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"], url_path="excluir-do-pncp")
    def excluir_do_pncp(self, request, pk=None):
        """
        Remove o DOCUMENTO da Ata no PNCP (6.4.7 – excluir documento de uma Ata)
        e volta o status local para rascunho.
        """
        doc = self.get_object()
        ata = doc.ata
        processo = ata.processo

        if not processo.pncp_ano_compra or not processo.pncp_sequencial_compra:
            return Response(
                {"detail": "Processo ainda não publicado no PNCP (ano/seq)."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not ata.pncp_sequencial_ata:
            return Response(
                {"detail": "Ata ainda não publicada no PNCP (sequencialAta ausente)."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not doc.pncp_sequencial_documento:
            return Response(
                {"detail": "Documento não possui sequencial no PNCP para exclusão."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not processo.entidade or not processo.entidade.cnpj:
            return Response(
                {"detail": "Entidade/CNPJ da contratação não configurados."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        cnpj = re.sub(r"\D", "", processo.entidade.cnpj or "")
        if len(cnpj) != 14:
            return Response(
                {"detail": "CNPJ da entidade inválido."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        justificativa = request.data.get(
            "justificativa",
            "Exclusão de documento de Ata solicitada pelo sistema de origem.",
        )

        try:
            # 6.4.7 – Excluir Documento de uma Ata
            PNCPService.excluir_documento_ata(
                cnpj_orgao=cnpj,
                ano_compra=processo.pncp_ano_compra,
                sequencial_compra=processo.pncp_sequencial_compra,
                sequencial_ata=ata.pncp_sequencial_ata,
                sequencial_documento=doc.pncp_sequencial_documento,
                justificativa=justificativa,
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        # volta a ser rascunho local
        doc.status = "rascunho"
        doc.pncp_sequencial_documento = None
        doc.pncp_publicado_em = None
        doc.save(update_fields=["status", "pncp_sequencial_documento", "pncp_publicado_em"])

        ser = self.get_serializer(doc)
        return Response(ser.data, status=status.HTTP_200_OK)
