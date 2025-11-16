# api/views.py
from time import time
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from rest_framework import viewsets, status, permissions, parsers, generics, filters
from rest_framework.decorators import action
from rest_framework.filters import SearchFilter, OrderingFilter
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.views import APIView

from django_filters.rest_framework import DjangoFilterBackend

from urllib import request as urlrequest
from urllib.error import URLError, HTTPError

import logging
import json
import re
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
    EntidadeMiniSerializer,
    OrgaoMiniSerializer
)

logger = logging.getLogger(__name__)
User = get_user_model()


# ============================================================
# 0) USUÁRIOS (admin)
# ============================================================
class UsuarioViewSet(viewsets.ModelViewSet):
    """
    CRUD de usuários do sistema (somente staff/admin).
    Aceita JSON e multipart (para foto).
    """
    queryset = User.objects.all().order_by("id")
    serializer_class = UsuarioSerializer
    permission_classes = [permissions.IsAdminUser]
    parser_classes = [parsers.MultiPartParser, parsers.FormParser, parsers.JSONParser]
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ["username", "email", "first_name", "last_name"]
    ordering_fields = ["id", "username", "email", "first_name", "last_name", "last_login", "date_joined"]
    ordering = ["username"]


# ============================================================
# 1) ENTIDADE / ÓRGÃO
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
# 2) FORNECEDOR
# ============================================================
class FornecedorViewSet(viewsets.ModelViewSet):
    queryset = Fornecedor.objects.all().order_by('razao_social')
    serializer_class = FornecedorSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [SearchFilter, DjangoFilterBackend]
    search_fields = ['razao_social', 'cnpj']
    filterset_fields = ['cnpj']

# ============================================================
# 3) PROCESSO LICITATÓRIO
# ============================================================
class ProcessoLicitatorioViewSet(viewsets.ModelViewSet):
    """
    Gerencia processos licitatórios + actions:
    - itens do processo
    - fornecedores (adicionar/listar/remover)
    - lotes (listar/criar) e organização de lotes
    - importar_xlsx (POST multipart)
    - importar (POST JSON)
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

    # -------------------- Helpers comuns --------------------
    @staticmethod
    def _only_digits(s):
        return re.sub(r"\D", "", str(s or ""))

    @staticmethod
    def _as_bool(v):
        if isinstance(v, bool):
            return v
        s = str(v or "").strip().lower()
        if s in ("sim", "s", "true", "1", "yes"):
            return True
        if s in ("nao", "não", "n", "false", "0", "no"):
            return False
        return None

    @staticmethod
    def _to_date_str(v):
        """
        Converte valores vindos do Excel ou string para 'YYYY-MM-DD'.
        """
        if not v:
            return None
        if isinstance(v, (datetime, date)):
            try:
                return v.date().isoformat()
            except Exception:
                return v.isoformat()[:10]
        s = str(v).strip()
        m = re.match(r"^(\d{2})/(\d{2})/(\d{4})$", s)
        if m:
            return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
        # já pode estar em ISO
        return s[:10]

    @staticmethod
    def _join_date_time(date_val, time_val):
        """
        Junta data + hora (vindo do Excel ou string "HH:MM") e devolve ISO.
        Se não houver hora, devolve só a data em ISO (00:00).
        """
        if not date_val and not time_val:
            return None

        # Resolve data
        if isinstance(date_val, datetime):
            d = date_val
        elif isinstance(date_val, date):
            d = datetime(date_val.year, date_val.month, date_val.day)
        elif isinstance(date_val, (int, float)):
            # Pode ser número serial do Excel -> trate acima se estiver usando openpyxl.utils.datetime
            # Aqui assumimos string/iso; fallback para simples parse
            try:
                d = datetime.fromordinal(datetime(1899, 12, 30).toordinal() + int(date_val))
            except Exception:
                try:
                    d = datetime.fromisoformat(str(date_val))
                except Exception:
                    d = None
        else:
            try:
                d = datetime.fromisoformat(str(date_val))
            except Exception:
                d = None

        if d is None:
            return None

        hh, mm = 0, 0
        if isinstance(time_val, datetime):
            hh, mm = time_val.hour, time_val.minute
        elif isinstance(time_val, time):
            hh, mm = time_val.hour, time_val.minute
        elif isinstance(time_val, (int, float)):
            total_minutes = round(float(time_val) * 24 * 60)
            hh, mm = total_minutes // 60, total_minutes % 60
        elif isinstance(time_val, str) and ":" in time_val:
            try:
                parts = time_val.split(":")
                hh, mm = int(parts[0]), int(parts[1])
            except Exception:
                hh, mm = 0, 0

        out = datetime(d.year, d.month, d.day, hh, mm, 0)
        return out.isoformat()

    def _resolve_entidade_id(self, ent_id, ent_nome, ent_cnpj):
        """
        Tenta resolver Entidade -> id. Não cria entidade nova aqui.
        """
        if ent_id:
            return ent_id
        if ent_cnpj:
            digits = self._only_digits(ent_cnpj)
            if digits:
                for e in Entidade.objects.only('id', 'cnpj').all():
                    if self._only_digits(e.cnpj) == digits:
                        return e.id
        if ent_nome:
            ent = Entidade.objects.filter(nome__iexact=str(ent_nome).strip()).first()
            if ent:
                return ent.id
        return None

    def _resolve_orgao_id(self, org_id, org_nome, org_cod, entidade_id):
        """
        Tenta resolver Órgão -> id. Não cria órgão novo aqui.
        """
        if org_id:
            return org_id
        if entidade_id:
            qs = Orgao.objects.filter(entidade_id=entidade_id)
            if org_cod:
                qs = qs.filter(codigo_unidade=str(org_cod).strip())
            if org_nome:
                org = qs.filter(nome__iexact=str(org_nome).strip()).first() or qs.first()
            else:
                org = qs.first()
            if org:
                return org.id
        return None

    def _apply_defaults(self, base: dict) -> dict:
        """
        Garante que campos opcionais tenham 'defaults' para evitar erros de required/not-null
        quando o serializer/modelo ainda exige algo.
        """
        return {
            # Identificação
            "numero_processo": (base.get("numero_processo") or "").strip(),
            "numero_certame": (base.get("numero_certame") or None),
            "objeto": base.get("objeto") or "",

            # Opcionais com defaults "amigáveis"
            "modalidade": base.get("modalidade") or None,                 # pode ficar None
            "classificacao": base.get("classificacao") or "OUTROS",       # default
            "tipo_organizacao": base.get("tipo_organizacao") or "MUNICIPAL",  # default
            "situacao": base.get("situacao") or "RASCUNHO",               # default

            # Datas/locais
            "data_abertura": base.get("data_abertura"),                   # ou None
            "data_sessao_iso": base.get("data_sessao_iso"),               # usado por serializer "inteligente"
            "local_sessao": base.get("local_sessao") or "",
            "tipo_disputa": base.get("tipo_disputa") or "",
            "registro_precos": self._as_bool(base.get("registro_precos")),

            # Resolução de entidade/órgão (auxiliares OU ids diretos)
            "entidade": base.get("entidade"),  # id se já resolvido
            "orgao": base.get("orgao"),        # id se já resolvido
            "entidade_id": base.get("entidade_id"),
            "entidade_nome": base.get("entidade_nome"),
            "entidade_cnpj": base.get("entidade_cnpj"),
            "orgao_codigo_unidade": base.get("orgao_codigo_unidade"),
            "orgao_nome": base.get("orgao_nome"),
        }

    # ---------------- IMPORTAÇÃO XLSX ----------------
    @action(
        detail=False,
        methods=['post'],
        url_path='importar-xlsx',
        parser_classes=[parsers.MultiPartParser, parsers.FormParser]
    )
    def importar_xlsx(self, request, *args, **kwargs):
        """
        POST /api/processos/importar-xlsx/
        Body: multipart/form-data com campo 'arquivo' (aceita também 'file'/'xlsx'/'planilha')
        Lê a planilha (aba IMPORTACAO ou ativa), resolve entidade/órgão e cria processos + (opcional) data/hora.
        """
        # Dependência
        try:
            import openpyxl
        except ImportError:
            return Response(
                {"detail": "Dependência ausente: instale 'openpyxl' (pip install openpyxl)."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        # Arquivo
        arquivo = (
            request.FILES.get('arquivo')
            or request.FILES.get('file')
            or request.FILES.get('xlsx')
            or request.FILES.get('planilha')
        )
        if not arquivo:
            return Response(
                {"detail": 'Envie o arquivo XLSX no campo "arquivo" (ou "file"/"xlsx"/"planilha").'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Abre planilha
        try:
            wb = openpyxl.load_workbook(arquivo, data_only=True)
        except Exception as e:
            return Response({"detail": f"Não foi possível ler o XLSX: {e}"}, status=400)

        # Aba IMPORTACAO (ou que contenha 'import')
        ws = wb.active
        if "IMPORTACAO" in wb.sheetnames:
            ws = wb["IMPORTACAO"]
        else:
            for name in wb.sheetnames:
                if "import" in name.lower():
                    ws = wb[name]
                    break

        rows = list(ws.iter_rows(values_only=True))
        if not rows or len(rows) < 2:
            return Response({"detail": "Planilha sem dados (precisa de cabeçalho + linhas)."}, status=400)

        header = [str(c).strip().lower() if c is not None else "" for c in rows[0]]

        def get_val(row, names):
            for name in names:
                if name in header:
                    idx = header.index(name)
                    return row[idx] if idx < len(row) else None
            return None

        items_payload = []
        for r in rows[1:]:
            if not r or all(v in (None, "", 0) for v in r):
                continue

            # Leitura robusta dos campos possíveis
            numero = get_val(r, ['numero_processo', 'nº processo', 'processo', 'numero'])
            numero_certame = get_val(r, ['numero_certame', 'certame', 'nº certame'])
            objeto = get_val(r, ['objeto', 'descricao', 'descritivo'])
            modalidade = get_val(r, ['modalidade'])
            classificacao = get_val(r, ['classificacao', 'classificação'])
            tipo_organizacao = get_val(r, ['tipo_organizacao', 'tipo de organizacao', 'tipo org'])
            situacao = get_val(r, ['situacao', 'situação'])

            data_abr = get_val(r, ['data_abertura', 'abertura', 'data do certame', 'data'])
            hora_sessao = get_val(r, ['hora_certame', 'hora', 'horario'])

            ent_id = get_val(r, ['entidade_id', 'id_entidade'])
            ent_nome = get_val(r, ['entidade', 'entidade_nome', 'nome_entidade'])
            ent_cnpj = get_val(r, ['entidade_cnpj', 'cnpj_entidade', 'cnpj'])

            org_id = get_val(r, ['orgao_id', 'id_orgao'])
            org_nome = get_val(r, ['orgao', 'órgão', 'orgao_nome', 'nome_orgao'])
            org_cod = get_val(r, ['codigo_unidade', 'orgao_codigo', 'codigo_orgao'])

            # Resolve relacionamentos (se possível)
            entidade_res = self._resolve_entidade_id(ent_id, ent_nome, ent_cnpj)
            orgao_res = self._resolve_orgao_id(org_id, org_nome, org_cod, entidade_res)

            base = {
                "numero_processo": numero,
                "numero_certame": numero_certame,
                "objeto": objeto,
                "modalidade": modalidade,
                "classificacao": classificacao,
                "tipo_organizacao": tipo_organizacao,
                "situacao": situacao,
                "data_abertura": self._to_date_str(data_abr),
                "data_sessao_iso": self._join_date_time(self._to_date_str(data_abr), hora_sessao),

                # relacionamento (id, se resolvido)
                "entidade": entidade_res,
                "orgao": orgao_res,

                # auxiliares (para serializer "inteligente")
                "entidade_id": ent_id,
                "entidade_nome": ent_nome,
                "entidade_cnpj": ent_cnpj,
                "orgao_codigo_unidade": org_cod,
                "orgao_nome": org_nome,

                # extras
                "tipo_disputa": get_val(r, ['tipo_disputa', 'tipo de disputa']),
                "registro_precos": get_val(r, ['registro_precos', 'rp', 'registro de preços']),
                "local_sessao": get_val(r, ['local_sessao', 'local', 'local da sessao']),
            }

            payload = self._apply_defaults(base)

            # filtro básico: precisa pelo menos nº processo OU objeto
            if not (payload["numero_processo"] or payload["objeto"]):
                continue

            items_payload.append(payload)

        if not items_payload:
            return Response({"detail": "Nenhuma linha válida após o mapeamento."}, status=400)

        # Criação em lote
        ser = ProcessoLicitatorioSerializer(data=items_payload, many=True, context={'request': request})
        ser.is_valid(raise_exception=True)
        with transaction.atomic():
            objs = ser.save()

        return Response(
            {"importados": len(objs), "objetos": ProcessoLicitatorioSerializer(objs, many=True).data},
            status=status.HTTP_201_CREATED
        )

    # ---------------- IMPORTAÇÃO JSON ----------------
    @action(detail=False, methods=["post"], url_path="importar")
    def importar_json(self, request):
        """
        POST /api/processos/importar/
        Body JSON:
        {
          "processos": [
            {
              ...campos do processo (podem ser parciais)...
              "itens": [
                { "item_ordem": 1, "lote": 2, "item_descricao": "...", ... }
              ]
            }
          ]
        }
        """
        processos = request.data.get("processos")
        if not isinstance(processos, list) or not processos:
            return Response({"detail": "Envie uma LISTA JSON em 'processos'."}, status=400)

        criados, erros = 0, []
        with transaction.atomic():
            for i, p in enumerate(processos, start=1):
                try:
                    # Constrói base e aplica defaults
                    ent_id = p.get("entidade_id")
                    ent_nome = p.get("entidade_nome")
                    ent_cnpj = p.get("entidade_cnpj")
                    org_nome = p.get("orgao_nome")
                    org_cod = p.get("orgao_codigo_unidade")

                    entidade_res = self._resolve_entidade_id(ent_id, ent_nome, ent_cnpj)
                    orgao_res = self._resolve_orgao_id(p.get("orgao_id"), org_nome, org_cod, entidade_res)

                    base = dict(p)
                    base.update({
                        "entidade": entidade_res,
                        "orgao": orgao_res,
                        "data_sessao_iso": self._join_date_time(
                            p.get("data_abertura") or p.get("data_sessao"),
                            p.get("hora_certame")
                        )
                    })
                    payload = self._apply_defaults(base)

                    ser = ProcessoLicitatorioSerializer(data=payload, context={"request": request})
                    ser.is_valid(raise_exception=True)
                    proc = ser.save()

                    # Itens (opcional)
                    for ordem, it in enumerate(p.get("itens") or [], start=1):
                        item_data = {
                            "processo": proc.id,
                            "descricao": it.get("item_descricao") or "",
                            "especificacao": it.get("item_especificacao") or "",
                            "quantidade": it.get("quantidade") or 0,
                            "unidade": it.get("unidade") or "",
                            "valor_unitario_estimado": it.get("valor_unitario_estimado"),
                            "ordem": it.get("item_ordem") or ordem,
                        }
                        lote_num = it.get("lote")
                        if lote_num:
                            try:
                                n = int(lote_num)
                            except Exception:
                                n = None
                            if n:
                                lote_obj, _ = Lote.objects.get_or_create(
                                    processo=proc, numero=n,
                                    defaults={"descricao": f"Lote {n}"}
                                )
                                item_data["lote"] = lote_obj.id

                        iser = ItemSerializer(data=item_data, context={"request": request})
                        iser.is_valid(raise_exception=True)
                        iser.save()

                    criados += 1
                except Exception as e:
                    erros.append({"linha": i, "erro": str(e)})

        if erros:
            return Response({"criados": criados, "erros": erros}, status=207)
        return Response({"criados": criados}, status=201)
    
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
            if isinstance(payload, list):
                for item in payload:
                    n = item.get('numero') or next_numero()
                    d = item.get('descricao', '')
                    obj = Lote.objects.create(processo=processo, numero=n, descricao=d)
                    created.append(obj)

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
# 4) LOTE
# ============================================================
class LoteViewSet(viewsets.ModelViewSet):
    queryset = Lote.objects.select_related('processo').all()
    serializer_class = LoteSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ['processo']
    search_fields = ['descricao']


# ============================================================
# 5) ITEM
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
# 6) FORNECEDOR ↔ PROCESSO (participantes)
# ============================================================
class FornecedorProcessoViewSet(viewsets.ModelViewSet):
    queryset = FornecedorProcesso.objects.select_related('processo', 'fornecedor').all()
    serializer_class = FornecedorProcessoSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ['processo', 'fornecedor']
    search_fields = ['fornecedor__razao_social', 'fornecedor__cnpj', 'processo__numero_processo', 'processo__numero_certame']


# ============================================================
# 7) ITEM ↔ FORNECEDOR (propostas)
# ============================================================
class ItemFornecedorViewSet(viewsets.ModelViewSet):
    queryset = ItemFornecedor.objects.select_related('item', 'fornecedor').all()
    serializer_class = ItemFornecedorSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ['item', 'fornecedor', 'vencedor']
    search_fields = ['item__descricao', 'fornecedor__razao_social', 'fornecedor__cnpj']


# ============================================================
# 8) REORDENAÇÃO DE ITENS
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
# 9) USUÁRIOS PÚBLICO / PERFIL
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
        ctx['request'] = self.request
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
# 10) DASHBOARD
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
# 11) LOGIN COM GOOGLE
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
# 12) CONTRATO / EMPENHO
# ============================================================
class ContratoEmpenhoViewSet(viewsets.ModelViewSet):
    queryset = ContratoEmpenho.objects.select_related('processo').all().order_by('-criado_em', 'id')
    serializer_class = ContratoEmpenhoSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ['processo', 'ano_contrato', 'tipo_contrato_id', 'categoria_processo_id', 'receita']
    search_fields = ['numero_contrato_empenho', 'processo__numero_processo', 'ni_fornecedor']
