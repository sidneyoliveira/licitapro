from rest_framework import viewsets, permissions, filters
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework import permissions
from rest_framework.views import APIView
from rest_framework import generics
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db import transaction
from rest_framework.filters import SearchFilter
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets, status
from django.utils import timezone
import re, json
from urllib import request as urlrequest
from urllib.error import URLError, HTTPError
from django.contrib.auth import get_user_model
from rest_framework import viewsets, permissions, parsers

# 👉 novos imports p/ importação XLSX
from openpyxl import load_workbook
from openpyxl.utils import datetime as openpyxl_datetime
from decimal import Decimal, InvalidOperation
from datetime import datetime

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
    ContratoEmpenho
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
    UsuarioSerializer
)

User = get_user_model()


class UsuarioViewSet(viewsets.ModelViewSet):
    """
    CRUD de usuários do sistema.
    Acesso restrito a staff/admin.
    """
    queryset = User.objects.all().order_by("id")
    serializer_class = UsuarioSerializer
    permission_classes = [permissions.IsAdminUser]  # só staff/admin acessa
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    parser_classes = [parsers.MultiPartParser, parsers.FormParser, parsers.JSONParser]
    search_fields = ["username", "email", "first_name", "last_name"]
    ordering_fields = ["id", "username", "email", "first_name", "last_name", "last_login", "date_joined"]
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
    filter_backends = [DjangoFilterBackend]  # pode ficar, mas não dependemos dele
    filterset_fields = ['entidade']

    # ✅ filtro garantido via código (independente do DjangoFilterBackend)
    def get_queryset(self):
        qs = Orgao.objects.select_related('entidade').order_by('nome')
        entidade_id = self.request.query_params.get('entidade')
        if entidade_id:
            qs = qs.filter(entidade_id=entidade_id)
        return qs

    # ====== sua action importar_pncp permanece igual, apenas mantida aqui ======
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
# 3️⃣ PROCESSO LICITATÓRIO
# ============================================================

class ProcessoLicitatorioViewSet(viewsets.ModelViewSet):
    """
    Gerencia os processos licitatórios e expõe actions de:
    - importação via XLSX (modelo CADASTRO INICIAL)
    - itens do processo
    - fornecedores (adicionar/listar/remover)
    - lotes (listar/criar) e organização de lotes
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

   # ---------------- IMPORTAÇÃO VIA XLSX (PLANILHA PADRÃO) ----------------
    @action(
        detail=False,
        methods=['post'],
        url_path='importar-xlsx',
        parser_classes=[parsers.MultiPartParser, parsers.FormParser],
    )
    def importar_xlsx(self, request, *args, **kwargs):
        """
        POST /api/processos/importar-xlsx/

        Espera um arquivo .xlsx no campo "arquivo", seguindo o modelo PADRÃO
        baseado na aba "CADASTRO INICIAL" / "PLANILHA PADRAO IMPORTACAO":

        - Cabeçalho de processo (células fixas do modelo original):
          A10 NUM PROCESSO
          B10 DATA CADASTRO PROCESSO
          C10 NUMERO CERTAME
          D10 DATA CERTAME ( DD/MM/AAAA HH:MM )
          E10 LOTE OU ITEM
          F10 ENTIDADE
          G10 ORGÃO
          H10 VALOR GLOBAL
          A11 OBJETO

        - Itens: linha de cabeçalho detectada dinamicamente procurando
          colunas como DESCRIÇÃO, QUANTIDADE, UNIDADE etc.

        - As linhas com "FORNECEDOR DO LOTE / NUMERO LOTE" definem novos lotes.
        """

        arquivo = request.FILES.get("arquivo")
        if not arquivo:
            return Response(
                {"detail": "Campo 'arquivo' é obrigatório (envie um .xlsx)."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not arquivo.name.lower().endswith(".xlsx"):
            return Response(
                {"detail": "Envie um arquivo .xlsx."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            wb = load_workbook(arquivo, data_only=True)
        except Exception:
            return Response(
                {"detail": "Não foi possível ler o arquivo .xlsx."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ---------- helpers internos de normalização/conversão ----------
        def normalize_header(s):
            if not isinstance(s, str):
                return ""
            import unicodedata, re as _re
            s = unicodedata.normalize("NFD", s)
            s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
            s = _re.sub(r"\s+", " ", s)
            return s.strip().upper()

        def to_decimal(v):
            if v is None or v == "":
                return None
            try:
                # aceita 5,99 ou 5.99
                return Decimal(str(v).replace(".", "").replace(",", ".")) \
                    if isinstance(v, str) and "," in str(v) and "." in str(v) else \
                    Decimal(str(v).replace(",", "."))
            except (InvalidOperation, AttributeError):
                return None

        def to_date(v):
            if v is None or v == "":
                return None
            from datetime import date
            if isinstance(v, datetime):
                return v.date()
            if isinstance(v, date):
                return v
            # data serial do excel
            if isinstance(v, (int, float)):
                try:
                    dt = openpyxl_datetime.from_excel(v, wb.epoch)
                    return dt.date()
                except Exception:
                    return None
            if isinstance(v, str):
                txt = v.strip()
                for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
                    try:
                        dt = datetime.strptime(txt, fmt)
                        return dt.date()
                    except ValueError:
                        continue
            return None

        def to_datetime(v):
            if v is None or v == "":
                return None
            if isinstance(v, datetime):
                return v
            # serial excel
            if isinstance(v, (int, float)):
                try:
                    return openpyxl_datetime.from_excel(v, wb.epoch)
                except Exception:
                    return None
            if isinstance(v, str):
                txt = v.strip()
                for fmt in ("%d/%m/%Y %H:%M", "%d/%m/%Y", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
                    try:
                        dt = datetime.strptime(txt, fmt)
                        return dt
                    except ValueError:
                        continue
            return None

        def to_bool(v):
            if v is None or v == "":
                return None
            s = str(v).strip().lower()
            if s in ("sim", "s", "yes", "true", "1"):
                return True
            if s in ("nao", "não", "n", "no", "false", "0"):
                return False
            return None

        def get_cell(ws, coord, header_keyword=None):
            """
            Lê uma célula e, se ainda estiver com o texto do cabeçalho
            (ex.: 'NUM PROCESSO'), devolve string vazia.
            Compatível com o modelo em que o usuário sobrescreve o texto.
            """
            v = ws[coord].value
            if header_keyword:
                if v is None:
                    return ""
                s = str(v).strip().upper()
                if header_keyword.upper() in s:
                    return ""
            return v if v is not None else ""

        def find_label_value(ws, label_keywords, search_rows=30, search_cols=15):
            """
            Procura uma célula cujo texto contenha todas as palavras
            de label_keywords (normalizadas) e tenta pegar o valor na
            célula à direita ou logo abaixo.
            Útil para campos técnicos (modalidade, situação, etc).
            """
            keys = [normalize_header(k) for k in label_keywords]
            max_row = min(search_rows, ws.max_row)
            max_col = min(search_cols, ws.max_column)
            for row in range(1, max_row + 1):
                for col in range(1, max_col + 1):
                    v = ws.cell(row=row, column=col).value
                    if not isinstance(v, str):
                        continue
                    norm = normalize_header(v)
                    if all(k in norm for k in keys):
                        # tenta à direita
                        if col + 1 <= ws.max_column:
                            right = ws.cell(row=row, column=col + 1).value
                            if right not in (None, ""):
                                return right
                        # tenta abaixo
                        if row + 1 <= ws.max_row:
                            below = ws.cell(row=row + 1, column=col).value
                            if below not in (None, ""):
                                return below
            return None

        def detect_items_header(ws):
            """
            Detecta dinamicamente a linha de cabeçalho dos itens.
            Procura linha que contenha pelo menos DESCRIÇÃO + QUANTIDADE/UNIDADE.
            Retorna (row_header, cols_map_normalizado).
            """
            for row in range(1, ws.max_row + 1):
                tmp_map = {}
                for col in range(1, ws.max_column + 1):
                    v = ws.cell(row=row, column=col).value
                    if not v:
                        continue
                    norm = normalize_header(str(v))
                    if norm:
                        tmp_map[norm] = col
                keys = set(tmp_map.keys())
                if {"DESCRICAO", "QUANTIDADE"}.issubset(keys) or {"DESCRICAO", "UNIDADE"}.issubset(keys):
                    return row, tmp_map
            return None, {}

        # ---------- escolhe a planilha principal (CADASTRO INICIAL / CADASTRO / 1ª aba) ----------
        sheet_name = None
        for name in wb.sheetnames:
            n = normalize_header(name)
            if n.startswith("CADASTRO INICIAL"):
                sheet_name = name
                break
        if not sheet_name:
            for name in wb.sheetnames:
                n = normalize_header(name)
                if "CADASTRO" in n:
                    sheet_name = name
                    break
        if not sheet_name:
            # fallback para primeira aba
            sheet_name = wb.sheetnames[0]

        ws = wb[sheet_name]

        # ---------- meta do processo (layout base) ----------
        numero_processo = str(get_cell(ws, "A10", "NUM PROCESSO") or "").strip()
        data_cadastro_raw = get_cell(ws, "B10", "DATA CADASTRO PROCESSO")
        numero_certame = str(get_cell(ws, "C10", "NUMERO CERTAME") or "").strip()
        data_certame_raw = get_cell(ws, "D10", "DATA CERTAME")
        tipo_lote_item_raw = get_cell(ws, "E10", "LOTE OU ITEM")
        entidade_nome = str(get_cell(ws, "F10", "ENTIDADE") or "").strip()
        orgao_nome = str(get_cell(ws, "G10", "ORG") or "").strip()
        valor_global_raw = get_cell(ws, "H10", "VALOR GLOBAL")
        objeto = str(get_cell(ws, "A11", "OBJETO") or "").strip()

        # ---------- dados técnicos extra (se existirem na planilha padrão) ----------
        modalidade_raw = find_label_value(ws, ["MODALIDADE"])
        classificacao_raw = find_label_value(ws, ["CLASSIFICACAO"])
        tipo_organizacao_extra = find_label_value(ws, ["TIPO", "ORGANIZACAO"])
        registro_preco_raw = find_label_value(ws, ["REGISTRO", "PRECO"])
        vigencia_raw = find_label_value(ws, ["VIGENCIA"])
        situacao_raw = find_label_value(ws, ["SITUACAO"])
        fundamentacao_raw = find_label_value(ws, ["FUNDAMENTACAO"])
        amparo_legal_raw = find_label_value(ws, ["AMPARO", "LEGAL"])
        modo_disputa_raw = find_label_value(ws, ["MODO", "DISPUTA"])
        criterio_julgamento_raw = find_label_value(ws, ["CRITERIO", "JULGAMENTO"])

        # ---------- cabeçalho de itens: linha dinâmica ----------
        row_header, cols_map = detect_items_header(ws)
        if not row_header:
            return Response(
                {"detail": "Cabeçalho da tabela de itens não encontrado. "
                           "Certifique-se de que existam colunas como DESCRIÇÃO, QUANTIDADE e UNIDADE."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        def col(key):
            # 'key' deve ser passado já em versão "normalizada"
            return cols_map.get(key)

        itens_data = []
        lotes_data = []
        current_lote_num = None

        for row in range(row_header + 1, ws.max_row + 1):
            c_fornec = col("FORNECEDOR")
            c_ident = col("IDENTIFICADOR")
            c_desc = col("DESCRICAO")
            c_esp = col("ESPECIFICACAO")
            c_qtd = col("QUANTIDADE")
            c_und = col("UNIDADE")
            c_val = col("VALOR REFERENCIA")
            c_nat = col("NATUREZA / DESPESA")

            f = ws.cell(row=row, column=c_fornec).value if c_fornec else None
            idf = ws.cell(row=row, column=c_ident).value if c_ident else None
            desc = ws.cell(row=row, column=c_desc).value if c_desc else None
            esp = ws.cell(row=row, column=c_esp).value if c_esp else None
            qtd = ws.cell(row=row, column=c_qtd).value if c_qtd else None
            unidade = ws.cell(row=row, column=c_und).value if c_und else None
            valor_ref = ws.cell(row=row, column=c_val).value if c_val else None
            natureza_raw = ws.cell(row=row, column=c_nat).value if c_nat else None

            # linha totalmente vazia -> ignora
            if all(v in (None, "") for v in (f, idf, desc, esp, qtd, unidade, valor_ref, natureza_raw)):
                continue

            fstr = str(f or "").strip().upper()
            idstr = str(idf or "").strip().upper()

            # linha que define cabeçalho de LOTE
            if "FORNECEDOR DO LOTE" in fstr or "NUMERO LOTE" in idstr:
                lote_desc = str(desc or idf or f or "").strip()
                if not lote_desc:
                    continue
                current_lote_num = len(lotes_data) + 1
                lotes_data.append({"numero": current_lote_num, "descricao": lote_desc})
                continue

            # linha de ITEM
            has_desc = bool(desc)
            has_qtd = qtd not in (None, "")
            has_unid = bool(unidade)

            if has_desc and has_unid:
                itens_data.append({
                    "lote_numero": current_lote_num,
                    "descricao": str(desc).strip(),
                    "especificacao": str(esp).strip() if esp else "",
                    "quantidade": qtd,
                    "unidade": str(unidade).strip(),
                    "valor_referencia": valor_ref,
                    "natureza": natureza_raw,
                    "fornecedor_raw": f,
                })

        if not itens_data:
            return Response(
                {"detail": "Nenhum item encontrado na planilha (verifique o modelo e as colunas de itens)."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ---------- leitura da aba de fornecedores (se existir) ----------
        fornecedores_by_cnpj = {}
        fornecedores_by_razao = {}
        fornecedores_criados = 0

        for name in wb.sheetnames:
            n = normalize_header(name)
            if "FORNECEDOR" not in n:
                continue
            ws_f = wb[name]

            # detecta linha de cabeçalho (precisa pelo menos de CNPJ e RAZAO SOCIAL)
            header_row = None
            f_cols = {}
            for row in range(1, ws_f.max_row + 1):
                tmp_map = {}
                for col_idx in range(1, ws_f.max_column + 1):
                    v = ws_f.cell(row=row, column=col_idx).value
                    if not v:
                        continue
                    norm = normalize_header(str(v))
                    if norm:
                        tmp_map[norm] = col_idx
                if "CNPJ" in tmp_map and ("RAZAO SOCIAL" in tmp_map or "RAZAO_SOCIAL" in tmp_map):
                    header_row = row
                    f_cols = tmp_map
                    break

            if not header_row:
                # não parece ser a aba de fornecedores padrão -> tenta próxima
                continue

            def fcol(k):
                return f_cols.get(k)

            import re as _re

            for row in range(header_row + 1, ws_f.max_row + 1):
                cnpj_raw = ws_f.cell(row=row, column=fcol("CNPJ")).value if fcol("CNPJ") else None
                razao_raw = ws_f.cell(row=row, column=fcol("RAZAO SOCIAL")).value if fcol("RAZAO SOCIAL") else None
                nome_fantasia_raw = ws_f.cell(row=row, column=fcol("NOME FANTASIA")).value if fcol("NOME FANTASIA") else None
                telefone_raw = ws_f.cell(row=row, column=fcol("TELEFONE")).value if fcol("TELEFONE") else None
                email_raw = ws_f.cell(row=row, column=fcol("EMAIL")).value if fcol("EMAIL") else None
                cep_raw = ws_f.cell(row=row, column=fcol("CEP")).value if fcol("CEP") else None
                logradouro_raw = ws_f.cell(row=row, column=fcol("LOGRADOURO")).value if fcol("LOGRADOURO") else None
                numero_raw = ws_f.cell(row=row, column=fcol("NUMERO")).value if fcol("NUMERO") else None
                bairro_raw = ws_f.cell(row=row, column=fcol("BAIRRO")).value if fcol("BAIRRO") else None
                complemento_raw = ws_f.cell(row=row, column=fcol("COMPLEMENTO")).value if fcol("COMPLEMENTO") else None
                municipio_raw = ws_f.cell(row=row, column=fcol("MUNICIPIO")).value if fcol("MUNICIPIO") else None
                uf_raw = ws_f.cell(row=row, column=fcol("UF")).value if fcol("UF") else None

                if not cnpj_raw and not razao_raw:
                    continue

                cnpj_digits = _re.sub(r"\D", "", str(cnpj_raw or ""))
                if len(cnpj_digits) != 14:
                    # não consigo criar fornecedor sem CNPJ válido; ignora
                    continue

                razao = (str(razao_raw).strip() or cnpj_digits) if razao_raw else cnpj_digits

                fornecedor, created = Fornecedor.objects.get_or_create(
                    cnpj=cnpj_digits,
                    defaults={
                        "razao_social": razao,
                        "nome_fantasia": str(nome_fantasia_raw).strip() if nome_fantasia_raw else None,
                        "telefone": str(telefone_raw).strip() if telefone_raw else None,
                        "email": str(email_raw).strip() if email_raw else None,
                        "cep": str(cep_raw).strip() if cep_raw else None,
                        "logradouro": str(logradouro_raw).strip() if logradouro_raw else None,
                        "numero": str(numero_raw).strip() if numero_raw else None,
                        "bairro": str(bairro_raw).strip() if bairro_raw else None,
                        "complemento": str(complemento_raw).strip() if complemento_raw else None,
                        "municipio": str(municipio_raw).strip() if municipio_raw else None,
                        "uf": str(uf_raw).strip() if uf_raw else None,
                    }
                )
                if created:
                    fornecedores_criados += 1

                fornecedores_by_cnpj[cnpj_digits] = fornecedor
                fornecedores_by_razao[normalize_header(razao)] = fornecedor

            # achou e processou uma aba de fornecedores -> não precisa olhar outras
            break

        # ---------- criação no banco ----------
        with transaction.atomic():
            # tenta localizar entidade/orgão por nome (case-insensitive)
            entidade = None
            if entidade_nome:
                entidade = Entidade.objects.filter(nome__iexact=entidade_nome).first()

            orgao = None
            if orgao_nome:
                qs_or = Orgao.objects.all()
                if entidade:
                    qs_or = qs_or.filter(entidade=entidade)
                orgao = qs_or.filter(nome__iexact=orgao_nome).first()

            # Tipo de organização (lote / item)
            tipo_organizacao = ""
            tipo_norm_base = str(tipo_lote_item_raw or "").strip().lower()
            if "lote" in tipo_norm_base:
                tipo_organizacao = "Lote"
            elif "item" in tipo_norm_base:
                tipo_organizacao = "Item"
            elif lotes_data:
                tipo_organizacao = "Lote"
            else:
                tipo_organizacao = "Item"

            proc_kwargs = {
                "numero_processo": numero_processo or None,
                "numero_certame": numero_certame or None,
                "objeto": objeto or "",
                "tipo_organizacao": tipo_organizacao or "",
                "data_processo": to_date(data_cadastro_raw),
                "data_abertura": to_datetime(data_certame_raw),
                "valor_referencia": to_decimal(valor_global_raw),
                "entidade": entidade,
                "orgao": orgao,
            }

            # aplica campos técnicos se encontrados
            if modalidade_raw:
                proc_kwargs["modalidade"] = str(modalidade_raw).strip()
            if classificacao_raw:
                proc_kwargs["classificacao"] = str(classificacao_raw).strip()
            if tipo_organizacao_extra:
                # se vier algo diferente em outro campo, ele sobrescreve
                proc_kwargs["tipo_organizacao"] = str(tipo_organizacao_extra).strip()

            rp_bool = to_bool(registro_preco_raw)
            if rp_bool is not None:
                proc_kwargs["registro_preco"] = rp_bool

            if vigencia_raw not in (None, ""):
                try:
                    proc_kwargs["vigencia_meses"] = int(str(vigencia_raw).split()[0])
                except Exception:
                    pass

            if situacao_raw:
                proc_kwargs["situacao"] = str(situacao_raw).strip()

            # fundamentação -> mapeia texto para códigos do model (lei_8666 / lei_10520 / lei_14133)
            import re as _re
            if fundamentacao_raw:
                fund_txt = str(fundamentacao_raw)
                digits = _re.sub(r"\D", "", fund_txt)
                code = None
                if "14133" in digits or "14133" in fund_txt:
                    code = "lei_14133"
                elif "8666" in digits or "8666" in fund_txt:
                    code = "lei_8666"
                elif "10520" in digits or "10520" in fund_txt:
                    code = "lei_10520"
                # se já veio no formato de código, aceita direto
                if fund_txt.strip() in ("lei_14133", "lei_8666", "lei_10520"):
                    code = fund_txt.strip()
                if code:
                    proc_kwargs["fundamentacao"] = code

            if amparo_legal_raw:
                proc_kwargs["amparo_legal"] = str(amparo_legal_raw).strip()
            if modo_disputa_raw:
                proc_kwargs["modo_disputa"] = str(modo_disputa_raw).strip()
            if criterio_julgamento_raw:
                proc_kwargs["criterio_julgamento"] = str(criterio_julgamento_raw).strip()

            processo = ProcessoLicitatorio.objects.create(**proc_kwargs)

            # cria lotes
            lote_objs = {}
            for l in lotes_data:
                num = l.get("numero") or (len(lote_objs) + 1)
                desc = l.get("descricao", "")
                lote = Lote.objects.create(processo=processo, numero=num, descricao=desc)
                lote_objs[l["numero"]] = lote

            # cria itens
            itens_criados = 0
            ordem = 0
            fornecedores_vinculados = set()

            for it in itens_data:
                qtd_dec = to_decimal(it["quantidade"])
                if qtd_dec is None:
                    continue
                valor_dec = to_decimal(it["valor_referencia"])
                natureza_raw_it = it.get("natureza")
                natureza_code = None
                if natureza_raw_it not in (None, ""):
                    s_nat = str(natureza_raw_it).strip().upper()
                    if s_nat.startswith("M"):
                        natureza_code = "M"
                    elif s_nat.startswith("S"):
                        natureza_code = "S"

                fornecedor_obj = None
                fornec_ref = it.get("fornecedor_raw")
                if fornec_ref:
                    txt_f = str(fornec_ref).strip()
                    cnpj_digits = _re.sub(r"\D", "", txt_f)
                    # tenta por CNPJ
                    if len(cnpj_digits) == 14:
                        fornecedor_obj = fornecedores_by_cnpj.get(cnpj_digits)
                        if not fornecedor_obj:
                            fornecedor_obj, _created = Fornecedor.objects.get_or_create(
                                cnpj=cnpj_digits,
                                defaults={"razao_social": cnpj_digits}
                            )
                    else:
                        # tenta por razão social (normalizada)
                        rn = normalize_header(txt_f)
                        fornecedor_obj = fornecedores_by_razao.get(rn)
                        if not fornecedor_obj:
                            fornecedor_obj = Fornecedor.objects.filter(
                                razao_social__iexact=txt_f
                            ).first()

                ordem += 1
                item = Item.objects.create(
                    processo=processo,
                    descricao=it["descricao"],
                    unidade=it["unidade"],
                    quantidade=qtd_dec,
                    valor_estimado=valor_dec,
                    lote=lote_objs.get(it["lote_numero"]),
                    ordem=ordem,
                    natureza=natureza_code,
                    fornecedor=fornecedor_obj,
                )
                itens_criados += 1

                if fornecedor_obj:
                    FornecedorProcesso.objects.get_or_create(
                        processo=processo,
                        fornecedor=fornecedor_obj,
                    )
                    fornecedores_vinculados.add(fornecedor_obj.id)

        serializer = self.get_serializer(processo)
        return Response(
            {
                "detail": "Importação concluída.",
                "processo": serializer.data,
                "lotes_criados": len(lote_objs),
                "itens_importados": itens_criados,
                "fornecedores_criados": fornecedores_criados,
                "fornecedores_vinculados": len(fornecedores_vinculados),
            },
            status=status.HTTP_201_CREATED,
        )

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
    def definir_fornecedor(self, request, ):
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

    def post(self, request, _format=None):
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


class ContratoEmpenhoViewSet(viewsets.ModelViewSet):
    queryset = ContratoEmpenho.objects.select_related('processo').all().order_by('-criado_em', 'id')
    serializer_class = ContratoEmpenhoSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter]
    # filtros úteis para publicação/consulta
    filterset_fields = ['processo', 'ano_contrato', 'tipo_contrato_id', 'categoria_processo_id', 'receita']
    search_fields = ['numero_contrato_empenho', 'processo__numero_processo', 'ni_fornecedor']
