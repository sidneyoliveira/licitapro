# api/services.py

import json
import re
import requests
import base64
import unicodedata
import logging
from typing import Optional, Dict, List, Any, Union
from datetime import datetime, time
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.core.files.base import File
# Tenta importar from_excel, se falhar define função dummy (caso openpyxl não esteja instalado)
try:
    from openpyxl.utils.datetime import from_excel as excel_to_datetime
except ImportError:
    excel_to_datetime = None

import pytz  # Essencial para o PNCP

# Models e Choices
from .models import (
    Entidade, Orgao, ProcessoLicitatorio, Lote, Item, Fornecedor, FornecedorProcesso
)
from .choices import (
    MAP_MODALIDADE_PNCP,
    MAP_MODO_DISPUTA_PNCP,
    MAP_AMPARO_LEGAL_PNCP,
    MAP_INSTRUMENTO_CONVOCATORIO_PNCP,
    MAP_SITUACAO_ITEM_PNCP,
    MAP_TIPO_BENEFICIO_PNCP,
    MAP_CATEGORIA_ITEM_PNCP
)

logger = logging.getLogger(__name__)

# ==============================================================================
# SERVIÇO 1: IMPORTAÇÃO EXCEL
# ==============================================================================

class ImportacaoService:
    """
    Serviço responsável pela normalização e tratamento de dados vindos de planilhas Excel.
    """

    @staticmethod
    def _normalize_key(s: Any) -> str:
        if not s: return ""
        s = str(s).strip()
        s = unicodedata.normalize("NFD", s)
        s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
        s = s.replace("º", "").replace("°", "").replace("§", "")
        return re.sub(r"\s+", "_", s).lower()

    @classmethod
    def get_id_from_map(cls, mapa: Dict[str, int], valor: Any) -> Optional[int]:
        if not valor: return None
        if isinstance(valor, int): return valor
        if str(valor).isdigit(): return int(valor)
        slug = cls._normalize_key(valor)
        return mapa.get(slug)

    @staticmethod
    def _normalize(s: Any) -> str:
        if s is None: return ""
        s = str(s).strip()
        s = unicodedata.normalize("NFD", s)
        s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
        return re.sub(r"\s+", " ", s).upper()

    @staticmethod
    def _to_decimal(v: Any) -> Optional[Decimal]:
        if v in (None, ""): return None
        try:
            sv = str(v).strip()
            if "," in sv and "." in sv:
                sv = sv.replace(".", "").replace(",", ".")
            else:
                sv = sv.replace(",", ".")
            return Decimal(sv)
        except (ValueError, InvalidOperation):
            return None

    @staticmethod
    def _to_date(v: Any, wb_epoch: Optional[datetime] = None) -> Optional[datetime.date]:
        if not v: return None
        if isinstance(v, datetime): return v.date()
        if isinstance(v, (int, float)) and wb_epoch and excel_to_datetime:
            try:
                return excel_to_datetime(v, wb_epoch).date()
            except Exception:
                return None
        if isinstance(v, str):
            for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
                try:
                    return datetime.strptime(v.strip(), fmt).date()
                except ValueError:
                    continue
        return None
    
    @staticmethod
    def processar_planilha_padrao(arquivo):
        # Placeholder mantido para compatibilidade com views.py
        # A implementação real da leitura do Excel deve vir aqui
        raise NotImplementedError("Lógica de importação via Excel deve ser implementada ou restaurada.")


# ==============================================================================
# SERVIÇO 2: INTEGRAÇÃO PNCP (V1) - CORRIGIDO
# ==============================================================================

class PNCPService:
    BASE_URL = getattr(settings, 'PNCP_BASE_URL', 'https://pncp.gov.br/api/pncp/v1')
    ACCESS_TOKEN = getattr(settings, 'PNCP_ACCESS_TOKEN', '')

    @staticmethod
    def _extrair_user_id_token(token):
        try:
            if not token: return None
            parts = token.split('.')
            if len(parts) < 2: return None
            payload_b64 = parts[1]
            payload_b64 += '=' * (-len(payload_b64) % 4)
            payload_json = base64.b64decode(payload_b64).decode('utf-8')
            payload = json.loads(payload_json)
            return payload.get('sub') or payload.get('user_id')
        except Exception as e:
            logger.error(f"Erro ao decodificar JWT do PNCP: {e}")
            return None

    @classmethod
    def _vincular_usuario_ao_orgao(cls, user_id, cnpj):
        url = f"{cls.BASE_URL}/orgaos/{cnpj}/usuarios/{user_id}"
        headers = {"Authorization": f"Bearer {cls.ACCESS_TOKEN}"}
        try:
            requests.post(url, headers=headers, verify=False, timeout=10)
        except Exception:
            pass

    @staticmethod
    def _handle_error_response(response):
        try:
            err_json = response.json()
            detail = err_json.get("message") or err_json.get("detail") or err_json.get("errors") or str(err_json)
            # Se for lista de erros, junta
            if isinstance(detail, list):
                detail = " | ".join([str(e) for e in detail])
        except:
            detail = response.text[:300]
        
        msg = f"PNCP Recusou ({response.status_code}): {detail}"
        logger.error(msg)
        raise ValueError(msg)

    @classmethod
    def publicar_compra(cls, processo: ProcessoLicitatorio, arquivo: Any, titulo_documento: str) -> Dict[str, Any]:
        """
        Executa o fluxo completo de publicação.
        """
        
        # 0. Verificação Inicial
        if not cls.ACCESS_TOKEN:
            raise ValueError("Configuração Crítica Ausente: 'PNCP_ACCESS_TOKEN' não encontrado no settings/env.")

        # ------------------------------------------------------------------
        # 1. VALIDAÇÃO
        # ------------------------------------------------------------------
        erros = []
        if not processo.numero_certame:
            erros.append("Número do Certame é obrigatório.")
        if not processo.entidade or not processo.entidade.cnpj:
            erros.append("Entidade/CNPJ inválido.")
        
        if not processo.modalidade: erros.append("Modalidade não definida.")
        if not processo.modo_disputa: erros.append("Modo de Disputa não definido.")
        if not processo.amparo_legal: erros.append("Amparo Legal não definido.")

        itens = processo.itens.all()
        if not itens.exists():
            erros.append("É necessário cadastrar ao menos um Item.")
        
        if erros:
            raise ValueError("Validação Falhou:\n" + "\n".join(f"- {msg}" for msg in erros))

        # ------------------------------------------------------------------
        # 2. PREPARAÇÃO
        # ------------------------------------------------------------------
        cnpj_orgao = re.sub(r'\D', '', processo.entidade.cnpj)
        
        if processo.data_processo:
            ano_compra = int(processo.data_processo.year)
        else:
            ano_compra = datetime.now().year

        # Código da Unidade (Obrigatório ter 6 dígitos no PNCP geralmente, ou vazio se for órgão principal)
        codigo_unidade = "000000" # Valor padrão caso não tenha
        if processo.orgao and processo.orgao.codigo_unidade:
            codigo_unidade = processo.orgao.codigo_unidade

        # ------------------------------------------------------------------
        # 3. VINCULAÇÃO PREVENTIVA
        # ------------------------------------------------------------------
        try:
            user_id = cls._extrair_user_id_token(cls.ACCESS_TOKEN)
            if user_id:
                cls._vincular_usuario_ao_orgao(user_id, cnpj_orgao)
        except Exception:
            pass

        # ------------------------------------------------------------------
        # 4. CONSTRUÇÃO DO PAYLOAD
        # ------------------------------------------------------------------
        
        # === TRATAMENTO DA DATA (CRÍTICO PARA ERRO 400) ===
        dt_abertura = processo.data_abertura
        if not dt_abertura:
             dt_abertura = datetime.now()

        # 1. Garante Timezone (America/Sao_Paulo)
        if not dt_abertura.tzinfo:
            sp_tz = pytz.timezone('America/Sao_Paulo')
            dt_abertura = sp_tz.localize(dt_abertura)
        
        # 2. Remove microssegundos e converte para ISO
        # PNCP rejeita: 2025-10-08T09:00:00.123456-03:00
        # PNCP aceita: 2025-10-08T09:00:00-03:00
        data_abertura_str = dt_abertura.replace(microsecond=0).isoformat()
        # ===================================================

        # Sanitização do Número da Compra (Apenas dígitos)
        # Ex: "015/2025" -> "015" | "PE 015/25" -> "015"
        raw_numero = str(processo.numero_certame).split('/')[0]
        numero_compra_clean = re.sub(r'\D', '', raw_numero)
        if not numero_compra_clean:
            numero_compra_clean = "1" # Fallback para não quebrar

        payload = {
            "codigoUnidadeCompradora": codigo_unidade,
            "cnpjOrgao": cnpj_orgao,
            "anoCompra": ano_compra,
            "numeroCompra": numero_compra_clean,
            "numeroProcesso": str(processo.numero_processo or processo.numero_certame),
            
            "tipoInstrumentoConvocatorioId": processo.instrumento_convocatorio or 1,
            "modalidadeId": int(processo.modalidade),
            "modoDisputaId": int(processo.modo_disputa),
            "amparoLegalId": int(processo.amparo_legal),
            
            "srp": bool(processo.registro_preco),
            "objetoCompra": (processo.objeto or f"Licitação {processo.numero_processo}")[:5000], # Limite PNCP
            "informacaoComplementar": "Processo integrado via API Licitapro.",
            
            "dataAberturaProposta": data_abertura_str,
            "dataEncerramentoProposta": data_abertura_str, 
            
            "linkSistemaOrigem": "http://l3solution.net.br",
            "itensCompra": []
        }

        # Construção dos Itens
        for idx, item in enumerate(itens, 1):
            vl_unitario = float(item.valor_estimado or 0)
            qtd = float(item.quantidade or 0)
            vl_total = round(vl_unitario * qtd, 4) # Arredondar para evitar dízimas
            
            # Define Material (M) ou Serviço (S) baseado na categoria
            # IDs de Serviços/Obras comuns: 2, 3, 4, 6, 8, 9 (Exemplo genérico base)
            # Se não tiver certeza, o padrão é M, mas pode dar erro se a unidade for 'H' ou similar.
            cat_id = int(item.categoria_item or 1)
            tipo_ms = "M"
            if cat_id in [2, 3, 4, 6, 8, 9]: # IDs que representam serviços/obras no PNCP
                tipo_ms = "S"

            item_payload = {
                "numeroItem": item.ordem or idx,
                "materialOuServico": tipo_ms,
                "tipoBeneficioId": int(item.tipo_beneficio or 1),
                "incentivoProdutivoBasico": False,
                "descricao": (item.descricao or "Item sem descrição")[:255], # Limite
                "quantidade": qtd,
                "unidadeMedida": (item.unidade or "UN")[:20],
                "valorUnitarioEstimado": vl_unitario,
                "valorTotal": vl_total,
                
                "criterioJulgamentoId": int(processo.criterio_julgamento or 1),
                "itemCategoriaId": cat_id,
                
                # Dados de Catálogo Obrigatórios
                # Usando código genérico 'Outros' (15055) se não houver integração com catálogo
                "catalogoId": 1, 
                "catalogoCodigoItem": "15055", 
                "categoriaItemCatalogoId": 1
            }
            payload["itensCompra"].append(item_payload)

        # ------------------------------------------------------------------
        # 5. ENVIO
        # ------------------------------------------------------------------
        if hasattr(arquivo, 'seek'):
            arquivo.seek(0)

        # Nome do arquivo seguro
        filename = getattr(arquivo, 'name', 'edital.pdf')
        
        files = {
            'documento': (filename, arquivo, 'application/pdf'),
            'compra': (None, json.dumps(payload), 'application/json')
        }

        url = f"{cls.BASE_URL}/orgaos/{cnpj_orgao}/compras"
        headers = {
            "Authorization": f"Bearer {cls.ACCESS_TOKEN}",
            "Titulo-Documento": titulo_documento,
            "Tipo-Documento-Id": "1" # 1 = Edital/Aviso
        }

        try:
            # Timeout aumentado para uploads
            response = requests.post(url, headers=headers, files=files, verify=False, timeout=60)
            
            if response.status_code in [200, 201]:
                return response.json()
            else:
                cls._handle_error_response(response)

        except requests.exceptions.RequestException as e:
            logger.error(f"Erro de Conexão PNCP: {e}")
            raise ValueError(f"Falha de comunicação com o PNCP: {str(e)}")