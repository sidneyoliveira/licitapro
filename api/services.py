# api/services.py

import json
import re
import unicodedata
import requests
from datetime import datetime, time
from decimal import Decimal
from urllib import request as urlrequest

from django.db import transaction
from django.conf import settings
from openpyxl import load_workbook
from openpyxl.utils.datetime import from_excel as excel_to_datetime

from .models import (
    Entidade,
    Orgao,
    ProcessoLicitatorio,
    Lote,
    Item,
    Fornecedor,
    FornecedorProcesso
)

# ==============================================================================
# CONSTANTES DE MAPEAMENTO (IMPORTAÇÃO EXCEL)
# ==============================================================================

AMPARO_EXCEL_TO_VALUE = {
    "ART. 23": "art_23",
    "ART. 24": "art_24",
    "ART. 25": "art_25",
    "ART. 4º": "art_4",
    "ART. 4O": "art_4",
    "ART. 5º": "art_5",
    "ART. 5O": "art_5",
    "ART. 28, INCISO I": "art_28_i",
    "ART. 28, INCISO II": "art_28_ii",
    "ART. 75, § 7º": "art_75_par7",
    "ART. 75, § 7O": "art_75_par7",
    "ART. 75, INCISO I": "art_75_i",
    "ART. 75, INCISO II": "art_75_ii",
    "ART. 75, INCISO III, A": "art_75_iii_a",
    "ART. 75, INCISO III, B": "art_75_iii_b",
    "ART. 75, INCISO IV, A": "art_75_iv_a",
    "ART. 75, INCISO IV, B": "art_75_iv_b",
    "ART. 75, INCISO IV, C": "art_75_iv_c",
    "ART. 75, INCISO IV, D": "art_75_iv_d",
    "ART. 75, INCISO IV, E": "art_75_iv_e",
    "ART. 75, INCISO IV, F": "art_75_iv_f",
    "ART. 75, INCISO IV, J": "art_75_iv_j",
    "ART. 75, INCISO IV, K": "art_75_iv_k",
    "ART. 75, INCISO IV, M": "art_75_iv_m",
    "ART. 75, INCISO IX": "art_75_ix",
    "ART. 75, INCISO VIII": "art_75_viii",
    "ART. 75, INCISO XV": "art_75_xv",
    "LEI 11.947/2009, ART. 14, § 1º": "lei_11947_art14_1",
    "LEI 11.947/2009, ART. 14, § 1O": "lei_11947_art14_1",
    "ART. 79, INCISO I": "art_79_i",
    "ART. 79, INCISO II": "art_79_ii",
    "ART. 79, INCISO III": "art_79_iii",
    "ART. 74, CAPUT": "art_74_caput",
    "ART. 74, I": "art_74_i",
    "ART. 74, II": "art_74_ii",
    "ART. 74, III, A": "art_74_iii_a",
    "ART. 74, III, B": "art_74_iii_b",
    "ART. 74, III, C": "art_74_iii_c",
    "ART. 74, III, D": "art_74_iii_d",
    "ART. 74, III, E": "art_74_iii_e",
    "ART. 74, III, F": "art_74_iii_f",
    "ART. 74, III, G": "art_74_iii_g",
    "ART. 74, III, H": "art_74_iii_h",
    "ART. 74, IV": "art_74_iv",
    "ART. 74, V": "art_74_v",
    "ART. 86, § 2º": "art_86_2",
    "ART. 86, § 2O": "art_86_2",
}

# ==============================================================================
# SERVIÇO 1: IMPORTAÇÃO DE EXCEL (XLSX)
# ==============================================================================

class ImportacaoService:
    """
    Serviço responsável por processar a importação de planilhas XLSX
    para criação de Processos Licitatórios, Lotes, Itens e Fornecedores.
    """

    @staticmethod
    def _normalize(s):
        if s is None:
            return ""
        s = str(s).strip()
        s = unicodedata.normalize("NFD", s)
        s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
        s = s.upper()
        s = re.sub(r"\s+", " ", s)
        return s

    @staticmethod
    def _to_decimal(v):
        if v in (None, ""):
            return None
        try:
            sv = str(v)
            if "," in sv and "." in sv:
                sv = sv.replace(".", "").replace(",", ".")
            else:
                sv = sv.replace(",", ".")
            return Decimal(sv)
        except Exception:
            return None

    @staticmethod
    def _to_date(v, wb_epoch=None):
        if not v:
            return None
        if isinstance(v, datetime):
            return v.date()
        if isinstance(v, (int, float)) and wb_epoch:
            try:
                return excel_to_datetime(v, wb_epoch).date()
            except Exception:
                return None
        if isinstance(v, str):
            txt = v.strip()
            for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
                try:
                    return datetime.strptime(txt, fmt).date()
                except Exception:
                    continue
        return None

    @classmethod
    def _to_datetime(cls, date_v, time_v=None, wb_epoch=None):
        dt_date = cls._to_date(date_v, wb_epoch)
        if not dt_date:
            return None

        if not time_v:
            dt_time = time(0, 0, 0)
        else:
            if isinstance(time_v, datetime):
                dt_time = time_v.time()
            elif isinstance(time_v, time):
                dt_time = time_v
            elif isinstance(time_v, (int, float)) and wb_epoch:
                try:
                    t_dt = excel_to_datetime(time_v, wb_epoch)
                    dt_time = t_dt.time()
                except Exception:
                    dt_time = time(0, 0, 0)
            elif isinstance(time_v, str):
                txt = time_v.strip()
                dt_time = None
                for fmt in ("%H:%M", "%H:%M:%S"):
                    try:
                        dt_time = datetime.strptime(txt, fmt).time()
                        break
                    except Exception:
                        continue
                if dt_time is None:
                    dt_time = time(0, 0, 0)
            else:
                dt_time = time(0, 0, 0)

        return datetime.combine(dt_date, dt_time)

    @staticmethod
    def _fetch_cnpj_brasilapi(cnpj_digits: str) -> dict:
        if not cnpj_digits or len(cnpj_digits) != 14:
            return {}
        url = f"https://brasilapi.com.br/api/cnpj/v1/{cnpj_digits}"
        try:
            with urlrequest.urlopen(url, timeout=10) as resp:
                if resp.status != 200:
                    return {}
                return json.loads(resp.read().decode("utf-8")) or {}
        except Exception:
            return {}

    @classmethod
    def processar_planilha_padrao(cls, arquivo):
        try:
            wb = load_workbook(arquivo, data_only=True)
        except Exception as e:
            raise ValueError(f"Erro ao ler arquivo Excel: {e}")

        # --- Mapeamentos ---
        AMPARO_EXCEL_NORMALIZED = {cls._normalize(k): v for k, v in AMPARO_EXCEL_TO_VALUE.items()}
        
        MODALIDADE_EXCEL_NORMALIZED = {
            cls._normalize("Pregão Eletrônico"): "Pregão Eletrônico",
            cls._normalize("Concorrência Eletrônica"): "Concorrência Eletrônica",
            cls._normalize("Dispensa Eletrônica"): "Dispensa Eletrônica",
            cls._normalize("Inexigibilidade Eletrônica"): "Inexigibilidade Eletrônica",
            cls._normalize("Adesão a Registro de Preços"): "Adesão a Registro de Preços",
            cls._normalize("Credenciamento"): "Credenciamento",
        }
        CLASSIFICACAO_EXCEL_NORMALIZED = {
            cls._normalize("Compras"): "Compras",
            cls._normalize("Serviços Comuns"): "Serviços Comuns",
            cls._normalize("Serviços de Engenharia Comuns"): "Serviços de Engenharia Comuns",
            cls._normalize("Obras Comuns"): "Obras Comuns",
        }
        TIPO_ORG_EXCEL_NORMALIZED = {
            cls._normalize("Lote"): "Lote",
            cls._normalize("Item"): "Item",
        }

        # --- Localizar Aba ---
        ws = None
        for name in wb.sheetnames:
            if cls._normalize(name).startswith("CADASTRO INICIAL"):
                ws = wb[name]
                break
        if ws is None:
            ws = wb[wb.sheetnames[0]]

        def get(coord):
            v = ws[coord].value
            return "" if v is None else v

        # --- Ler Metadados ---
        numero_processo = str(get("B7")).strip()
        data_processo_raw = get("C7")
        numero_certame = str(get("D7")).strip()
        data_certame_raw = get("E7")
        hora_certame_raw = get("F7")
        entidade_nome = str(get("G7") or "").strip()
        orgao_nome = str(get("H7") or "").strip()
        valor_global_raw = get("I7")
        objeto_raw = get("A7")

        modalidade_raw = get("A11")
        tipo_disputa_raw = get("B11")
        registro_preco_raw = get("C11")
        tipo_organizacao_raw = get("D11")
        criterio_julgamento_raw = get("E11")
        classificacao_raw = get("F11")
        fundamentacao_raw = get("G11")
        amparo_legal_raw = get("H11")
        vigencia_raw = get("I11")

        # --- Ler Itens ---
        row_header = 15
        col_map = {
            "LOTE": 1, "Nº ITEM": 2, "DESCRICAO DO ITEM": 3, "ESPECIFICACAO": 4,
            "QUANTIDADE": 5, "UNIDADE": 6, "NATUREZA / DESPESA": 7,
            "VALOR REFERENCIA UNITARIO": 8, "CNPJ DO FORNECEDOR": 9,
        }
        def col(key): return col_map[key]

        itens_data = []
        for row in range(row_header + 1, ws.max_row + 1):
            desc = ws.cell(row=row, column=col("DESCRICAO DO ITEM")).value
            if not desc: continue
            itens_data.append({
                "descricao": desc,
                "especificacao": ws.cell(row=row, column=col("ESPECIFICACAO")).value,
                "quantidade": ws.cell(row=row, column=col("QUANTIDADE")).value,
                "unidade": ws.cell(row=row, column=col("UNIDADE")).value,
                "natureza": ws.cell(row=row, column=col("NATUREZA / DESPESA")).value,
                "valor_referencia": ws.cell(row=row, column=col("VALOR REFERENCIA UNITARIO")).value,
                "lote": ws.cell(row=row, column=col("LOTE")).value,
                "cnpj": ws.cell(row=row, column=col("CNPJ DO FORNECEDOR")).value,
            })

        if not itens_data:
            raise ValueError("Nenhum item encontrado na planilha.")

        # --- Ler Fornecedores (Aba Opcional) ---
        fornecedores_cache = {}
        for name in wb.sheetnames:
            if "FORNECEDOR" not in cls._normalize(name): continue
            ws_f = wb[name]
            header = None
            cols = {}
            for r in range(1, ws_f.max_row + 1):
                temp = {}
                for c in range(1, ws_f.max_column + 1):
                    v = ws_f.cell(r, c).value
                    if v: temp[cls._normalize(v)] = c
                if "CNPJ" in temp and "RAZAO SOCIAL" in temp:
                    header = r
                    cols = temp
                    break
            if not header: continue

            for r in range(header + 1, ws_f.max_row + 1):
                cnpj_raw = ws_f.cell(r, cols["CNPJ"]).value
                razao_raw = ws_f.cell(r, cols["RAZAO SOCIAL"]).value
                if not cnpj_raw: continue
                cnpj = re.sub(r"\D", "", str(cnpj_raw))
                if len(cnpj) != 14: continue
                fornecedores_cache[cnpj] = (str(razao_raw).strip() if razao_raw else "") or cnpj
            break

        # --- Persistência ---
        with transaction.atomic():
            # 1. Entidade/Orgao
            entidade = None
            if entidade_nome:
                entidade = Entidade.objects.filter(nome__iexact=entidade_nome).first()
            
            orgao = None
            if orgao_nome:
                qs_or = Orgao.objects.all()
                if entidade: qs_or = qs_or.filter(entidade=entidade)
                orgao = qs_or.filter(nome__iexact=orgao_nome).first()

            # 2. Normalização
            mod_txt = None
            if modalidade_raw not in (None, ""):
                mod_txt = MODALIDADE_EXCEL_NORMALIZED.get(cls._normalize(modalidade_raw), str(modalidade_raw).strip())

            class_txt = None
            if classificacao_raw not in (None, ""):
                class_txt = CLASSIFICACAO_EXCEL_NORMALIZED.get(cls._normalize(classificacao_raw), str(classificacao_raw).strip())

            org_txt = None
            if tipo_organizacao_raw not in (None, ""):
                org_txt = TIPO_ORG_EXCEL_NORMALIZED.get(cls._normalize(tipo_organizacao_raw), str(tipo_organizacao_raw).strip())

            # Modos e Critérios
            modo_disputa_txt = ""
            if tipo_disputa_raw not in (None, ""):
                s = str(tipo_disputa_raw).strip().lower()
                if "aberto" in s and "fechado" in s: modo_disputa_txt = "aberto_e_fechado"
                elif "aberto" in s: modo_disputa_txt = "aberto"
                elif "fechado" in s: modo_disputa_txt = "fechado"

            criterio_txt = ""
            if criterio_julgamento_raw not in (None, ""):
                cj = str(criterio_julgamento_raw).strip().lower()
                if "menor" in cj: criterio_txt = "menor_preco"
                elif "maior" in cj: criterio_txt = "maior_desconto"

            # Fundamentação
            fundamentacao_txt = None
            if fundamentacao_raw not in (None, ""):
                f = str(fundamentacao_raw).strip()
                f_lower = f.lower()
                digits = "".join(ch for ch in f if ch.isdigit())
                if "14133" in digits or "14133" in f_lower: fundamentacao_txt = "lei_14133"
                elif "8666" in digits or "8666" in f_lower: fundamentacao_txt = "lei_8666"
                elif "10520" in digits or "10520" in f_lower: fundamentacao_txt = "lei_10520"
                elif f in ("lei_14133", "lei_8666", "lei_10520"): fundamentacao_txt = f

            # Amparo
            amparo_legal_txt = None
            if amparo_legal_raw not in (None, ""):
                a = str(amparo_legal_raw).strip()
                if a in AMPARO_EXCEL_TO_VALUE.values():
                    amparo_legal_txt = a
                else:
                    a_norm = cls._normalize(a)
                    amparo_legal_txt = AMPARO_EXCEL_NORMALIZED.get(a_norm, a)

            # 3. Criar Processo
            processo = ProcessoLicitatorio.objects.create(
                numero_processo=numero_processo or None,
                numero_certame=numero_certame or None,
                objeto=str(objeto_raw or "").strip(),
                modalidade=mod_txt or None,
                classificacao=class_txt or None,
                tipo_organizacao=org_txt or None,
                situacao="Em Pesquisa",
                data_processo=cls._to_date(data_processo_raw, wb.epoch),
                data_abertura=cls._to_datetime(data_certame_raw, hora_certame_raw, wb.epoch),
                valor_referencia=cls._to_decimal(valor_global_raw),
                vigencia_meses=int(str(vigencia_raw).split()[0]) if vigencia_raw else None,
                registro_preco=str(registro_preco_raw or "").strip().lower() in ("sim", "s"),
                entidade=entidade,
                orgao=orgao,
                fundamentacao=fundamentacao_txt,
                amparo_legal=amparo_legal_txt,
                modo_disputa=modo_disputa_txt or None,
                criterio_julgamento=criterio_txt or None,
            )

            # 4. Lotes
            lotes_map = {}
            for it in itens_data:
                lote_num = it["lote"]
                if lote_num and lote_num not in lotes_map:
                    lotes_map[lote_num] = Lote.objects.create(
                        processo=processo, numero=lote_num, descricao=f"Lote {lote_num}",
                    )

            # 5. Itens e Fornecedores
            ordem = 0
            fornecedores_vinculados = set()

            for it in itens_data:
                ordem += 1
                lote_obj = lotes_map.get(it["lote"])
                fornecedor = None

                cnpj_raw_item = it.get("cnpj")
                if cnpj_raw_item:
                    cnpj_digits = re.sub(r"\D", "", str(cnpj_raw_item))
                    if len(cnpj_digits) == 14:
                        fornecedor = Fornecedor.objects.filter(cnpj=cnpj_digits).first()
                        if not fornecedor:
                            dados_api = cls._fetch_cnpj_brasilapi(cnpj_digits)
                            razao_social = (
                                fornecedores_cache.get(cnpj_digits) 
                                or dados_api.get("razao_social") 
                                or cnpj_digits
                            )
                            fornecedor = Fornecedor.objects.create(
                                cnpj=cnpj_digits,
                                razao_social=razao_social,
                                nome_fantasia=dados_api.get("nome_fantasia") or "",
                                telefone=dados_api.get("ddd_telefone_1") or "",
                                email=dados_api.get("email") or "",
                                cep=dados_api.get("cep") or "",
                                logradouro=dados_api.get("logradouro") or "",
                                numero=dados_api.get("numero") or "",
                                bairro=dados_api.get("bairro") or "",
                                complemento=dados_api.get("complemento") or "",
                                municipio=dados_api.get("municipio") or "",
                                uf=dados_api.get("uf") or "",
                            )
                        fornecedores_vinculados.add(fornecedor.id)

                Item.objects.create(
                    processo=processo,
                    lote=lote_obj,
                    descricao=it["descricao"],
                    especificacao=it["especificacao"],
                    quantidade=cls._to_decimal(it["quantidade"]),
                    unidade=str(it["unidade"] or "").strip(),
                    valor_estimado=cls._to_decimal(it["valor_referencia"]),
                    natureza=it["natureza"],
                    ordem=ordem,
                    fornecedor=fornecedor,
                )

                if fornecedor:
                    FornecedorProcesso.objects.get_or_create(processo=processo, fornecedor=fornecedor)

            return {
                "processo": processo,
                "lotes_criados": len(lotes_map),
                "itens_importados": len(itens_data),
                "fornecedores_vinculados": len(fornecedores_vinculados),
            }


# ==============================================================================
# SERVIÇO 2: INTEGRAÇÃO PNCP (PORTAL NACIONAL DE CONTRATAÇÕES PÚBLICAS)
# ==============================================================================

class PNCPService:
    """
    Serviço para integração com a API do PNCP.
    Endpoint de Homologação: https://treina.pncp.gov.br/api/pncp
    """
    BASE_URL = "https://treina.pncp.gov.br/api/pncp"
    
    # Idealmente, use variáveis de ambiente: config('PNCP_TOKEN')
    ACCESS_TOKEN = getattr(settings, 'PNCP_ACCESS_TOKEN', '') 

    @classmethod
    def publicar_compra(cls, processo: ProcessoLicitatorio, arquivo, titulo_documento: str):
        """
        Envia os dados da compra e o arquivo (Edital/Aviso) para o PNCP.
        """
        if not cls.ACCESS_TOKEN:
            raise ValueError("Token de acesso do PNCP não configurado no settings.")

        # 1. Validar dados mínimos
        if not processo.numero_certame:
            raise ValueError("Número do certame é obrigatório para publicação.")
        if not processo.entidade or not processo.entidade.cnpj:
            raise ValueError("CNPJ da Entidade é obrigatório.")
        
        # 2. Mapeamento (Simplificado - deve ser ajustado conforme Tabela de Domínio do PNCP)
        modalidade_id = cls._map_modalidade(processo.modalidade)
        
        # Estrutura JSON exigida pelo PNCP (conforme manual)
        compra_data = {
            "anoCompra": processo.data_processo.year if processo.data_processo else datetime.now().year,
            "numeroCompra": processo.numero_certame,
            "numeroProcesso": processo.numero_processo or processo.numero_certame,
            "objetoCompra": processo.objeto or "Objeto não informado",
            "modalidadeId": modalidade_id,
            "srp": processo.registro_preco,
            "unidadeOrgao": {
                "codigoUnidade": processo.orgao.codigo_unidade if (processo.orgao and processo.orgao.codigo_unidade) else "000000"
            },
            "orgao": {
                "cnpj": re.sub(r'\D', '', processo.entidade.cnpj)
            },
            "amparoLegalId": cls._map_amparo_legal(processo.amparo_legal),
            "dataAberturaProposta": processo.data_abertura.isoformat() if processo.data_abertura else None,
            "tipoInstrumentoConvocatorioId": "1", # 1=Edital
            "modoDisputaId": cls._map_modo_disputa(processo.modo_disputa),
            "itensCompra": [] # Lista de itens se necessário enviar detalhado
        }

        # 3. Preparação do Multipart
        files = {
            'documento': (arquivo.name, arquivo, 'application/pdf'),
            'compra': (None, json.dumps(compra_data), 'application/json')
        }

        # URL com CNPJ do órgão (apenas dígitos)
        cnpj_orgao = re.sub(r'\D', '', processo.entidade.cnpj)
        url = f"{cls.BASE_URL}/v1/orgaos/{cnpj_orgao}/compras"

        headers = {
            "Authorization": f"Bearer {cls.ACCESS_TOKEN}",
            "Titulo-Documento": titulo_documento,
            "Tipo-Documento-Id": "1" # 1 = Aviso de Contratação
        }

        try:
            # verify=False para homologação (evita erro de SSL auto-assinado)
            response = requests.post(url, headers=headers, files=files, verify=False)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            error_msg = e.response.text if e.response else str(e)
            raise ValueError(f"Erro na API do PNCP: {error_msg}")

    @staticmethod
    def _map_modalidade(nome):
        # Mapa conforme manual (IDs fictícios, ajustar com tabela real)
        mapa = {
            "Pregão Eletrônico": "6",
            "Concorrência Eletrônica": "13",
            "Dispensa Eletrônica": "8",
            "Inexigibilidade Eletrônica": "9",
            "Credenciamento": "10"
        }
        return mapa.get(nome, "6") # Default para Pregão se não achar

    @staticmethod
    def _map_amparo_legal(amparo_key):
        # Mapeia as chaves do seu sistema (art_23, etc) para IDs do PNCP
        # Exemplo: 'art_75_ii' -> ID 45 do PNCP
        # Retornando um ID padrão de teste
        return 1 

    @staticmethod
    def _map_modo_disputa(modo_key):
        # aberto -> 1, fechado -> 2
        mapa = {"aberto": "1", "fechado": "2", "aberto_e_fechado": "3"}
        return mapa.get(modo_key, "1")