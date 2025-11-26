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
from openpyxl.utils.datetime import from_excel as excel_to_datetime
import pytz 

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
    Converte as strings do Excel para os IDs do PNCP usando os mapas do choices.py.
    """

    @staticmethod
    def _normalize_key(s: Any) -> str:
        """Normaliza strings para chave de busca (igual ao choices.py)."""
        if not s:
            return ""
        s = str(s).strip()
        s = unicodedata.normalize("NFD", s)
        s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
        s = s.replace("º", "").replace("°", "").replace("§", "")
        return re.sub(r"\s+", "_", s).lower() # Slugify simples: 'Pregão Eletrônico' -> 'pregao_eletronico'

    @classmethod
    def get_id_from_map(cls, mapa: Dict[str, int], valor: Any) -> Optional[int]:
        """
        Tenta encontrar o ID PNCP baseado no texto do Excel.
        Ex: "Pregão Eletrônico" -> "pregao_eletronico" -> 6
        """
        if not valor:
            return None
        
        # 1. Se já for inteiro, retorna
        if isinstance(valor, int):
            return valor
        if str(valor).isdigit():
            return int(valor)

        # 2. Normaliza para slug e busca no mapa
        slug = cls._normalize_key(valor)
        
        # Tenta match exato no slug
        if slug in mapa:
            return mapa[slug]
        
        # Tenta match parcial ou reverso se necessário (opcional)
        return None

    @staticmethod
    def _normalize(s: Any) -> str:
        if s is None:
            return ""
        s = str(s).strip()
        s = unicodedata.normalize("NFD", s)
        s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
        return re.sub(r"\s+", " ", s).upper()

    @staticmethod
    def _to_decimal(v: Any) -> Optional[Decimal]:
        if v in (None, ""):
            return None
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
            for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
                try:
                    return datetime.strptime(v.strip(), fmt).date()
                except ValueError:
                    continue
        return None


# ==============================================================================
# SERVIÇO 2: INTEGRAÇÃO PNCP (V1)
# ==============================================================================

class PNCPService:
    BASE_URL = getattr(settings, 'PNCP_BASE_URL', 'https://pncp.gov.br/api/pncp/v1')
    ACCESS_TOKEN = getattr(settings, 'PNCP_ACCESS_TOKEN', '')

    @staticmethod
    def _extrair_user_id_token(token):
        """Extrai o ID do usuário do JWT (payload) de forma simples."""
        try:
            # O JWT é dividido em 3 partes. O payload é a segunda (índice 1).
            payload_b64 = token.split('.')[1]
            # Ajusta padding base64 se necessário
            payload_b64 += '=' * (-len(payload_b64) % 4)
            payload_json = base64.b64decode(payload_b64).decode('utf-8')
            payload = json.loads(payload_json)
            return payload.get('sub') or payload.get('user_id')
        except Exception as e:
            logger.error(f"Erro ao decodificar JWT do PNCP: {e}")
            return None

    @classmethod
    def _vincular_usuario_ao_orgao(cls, user_id, cnpj):
        """Tenta vincular o usuário ao órgão no ambiente de teste/treinamento."""
        # Nota: Em produção isso geralmente não é necessário ou é feito manualmente.
        url = f"{cls.BASE_URL}/orgaos/{cnpj}/usuarios/{user_id}"
        headers = {"Authorization": f"Bearer {cls.ACCESS_TOKEN}"}
        try:
            requests.post(url, headers=headers, verify=False, timeout=10)
        except Exception:
            pass # Falha silenciosa pois pode já estar vinculado

    @staticmethod
    def _handle_error_response(response):
        """Trata erros da API padronizando a exceção."""
        try:
            err_json = response.json()
            detail = err_json.get("message") or err_json.get("detail") or str(err_json)
        except:
            detail = response.text[:200]
        
        msg = f"PNCP Recusou ({response.status_code}): {detail}"
        logger.error(msg)
        raise ValueError(msg)

    @classmethod
    def publicar_compra(cls, processo, arquivo: Any, titulo_documento: str) -> Dict[str, Any]:
        """
        Executa o fluxo completo de publicação.
        """
        
        # 0. Verificação Inicial de Token
        if not cls.ACCESS_TOKEN:
            raise ValueError("Configuração Crítica Ausente: 'PNCP_ACCESS_TOKEN'.")

        # ------------------------------------------------------------------
        # 1. VALIDAÇÃO
        # ------------------------------------------------------------------
        erros = []
        if not processo.numero_certame:
            erros.append("Número do Certame é obrigatório.")
        if not processo.entidade or not processo.entidade.cnpj:
            erros.append("Entidade/CNPJ inválido.")
        
        if not processo.modalidade:
            erros.append("Modalidade não definida (ID inválido).")
        if not processo.modo_disputa:
            erros.append("Modo de Disputa não definido (ID inválido).")
        if not processo.amparo_legal:
            erros.append("Amparo Legal não definido (ID inválido).")

        itens = processo.itens.all()
        if not itens.exists():
            erros.append("É necessário cadastrar ao menos um Item.")
        
        if erros:
            raise ValueError("Validação Falhou:\n" + "\n".join(f"- {msg}" for msg in erros))

        # ------------------------------------------------------------------
        # 2. PREPARAÇÃO
        # ------------------------------------------------------------------
        cnpj_orgao = re.sub(r'\D', '', processo.entidade.cnpj)
        
        # Extrai ano do processo ou usa ano atual
        if processo.data_processo:
            ano_compra = int(processo.data_processo.year)
        else:
            ano_compra = datetime.now().year

        codigo_unidade = processo.orgao.codigo_unidade if (processo.orgao and processo.orgao.codigo_unidade) else "000000"

        # ------------------------------------------------------------------
        # 3. AUTENTICAÇÃO / VINCULAÇÃO (Preventiva)
        # ------------------------------------------------------------------
        try:
            user_id = cls._extrair_user_id_token(cls.ACCESS_TOKEN)
            if user_id:
                cls._vincular_usuario_ao_orgao(user_id, cnpj_orgao)
        except Exception as e:
            logger.warning(f"Falha na vinculação automática (pode ser ignorado se já vinculado): {e}")

        # ------------------------------------------------------------------
        # 4. CONSTRUÇÃO DO PAYLOAD
        # ------------------------------------------------------------------
        
        # === CORREÇÃO CRÍTICA DA DATA (ISO 8601 com Fuso Horário) ===
        dt_abertura = processo.data_abertura
        if not dt_abertura:
             # Se não tiver data, usa agora (apenas para evitar crash, mas o PNCP pode rejeitar datas passadas)
             dt_abertura = datetime.now()

        # Garante que a data tenha fuso horário (PNCP exige o offset, ex: -03:00)
        if not dt_abertura.tzinfo:
            sp_tz = pytz.timezone('America/Sao_Paulo')
            dt_abertura = sp_tz.localize(dt_abertura)
        
        # Formata para string ISO completa
        data_abertura_str = dt_abertura.isoformat()
        # ============================================================

        payload = {
            "codigoUnidadeCompradora": codigo_unidade,
            "cnpjOrgao": cnpj_orgao,
            "anoCompra": ano_compra,
            "numeroCompra": str(processo.numero_certame.split('/')[0] if '/' in str(processo.numero_certame) else processo.numero_certame),
            "numeroProcesso": str(processo.numero_processo or processo.numero_certame),
            
            "tipoInstrumentoConvocatorioId": processo.instrumento_convocatorio or 1, # Default Edital
            "modalidadeId": int(processo.modalidade),
            "modoDisputaId": int(processo.modo_disputa),
            "amparoLegalId": int(processo.amparo_legal),
            
            "srp": bool(processo.registro_preco),
            "objetoCompra": processo.objeto or f"Licitação {processo.numero_processo}",
            "informacaoComplementar": "Processo integrado via API Licitapro.",
            
            "dataAberturaProposta": data_abertura_str,
            "dataEncerramentoProposta": data_abertura_str, # Geralmente igual ou posterior à abertura
            
            "linkSistemaOrigem": "http://l3solution.net.br",
            "itensCompra": []
        }

        # Construção dos Itens
        for idx, item in enumerate(itens, 1):
            vl_unitario = float(item.valor_estimado or 0)
            qtd = float(item.quantidade or 0)
            
            item_payload = {
                "numeroItem": item.ordem or idx,
                "materialOuServico": "M", # Poderia ser dinâmico se tivesse esse dado
                "tipoBeneficioId": int(item.tipo_beneficio or 1),
                "incentivoProdutivoBasico": False,
                "descricao": item.descricao[:255],
                "quantidade": qtd,
                "unidadeMedida": item.unidade[:20], # Limita tamanho
                "valorUnitarioEstimado": vl_unitario,
                "valorTotal": vl_unitario * qtd,
                
                "criterioJulgamentoId": int(processo.criterio_julgamento or 1),
                "itemCategoriaId": int(item.categoria_item or 1),
                
                # Dados de Catálogo (Obrigatórios, usando genérico 'Outros' se não houver)
                "catalogoId": 1, 
                "catalogoCodigoItem": "15055", # Código genérico de exemplo
                "categoriaItemCatalogoId": 1
            }
            payload["itensCompra"].append(item_payload)

        # ------------------------------------------------------------------
        # 5. ENVIO
        # ------------------------------------------------------------------
        if hasattr(arquivo, 'seek'):
            arquivo.seek(0)

        files = {
            'documento': (getattr(arquivo, 'name', 'edital.pdf'), arquivo, 'application/pdf'),
            'compra': (None, json.dumps(payload), 'application/json')
        }

        url = f"{cls.BASE_URL}/orgaos/{cnpj_orgao}/compras"
        headers = {
            "Authorization": f"Bearer {cls.ACCESS_TOKEN}",
            "Titulo-Documento": titulo_documento,
            "Tipo-Documento-Id": "1" # 1 = Edital
        }

        try:
            # Verify=False apenas se certificado do PNCP for auto-assinado ou ambiente de teste
            response = requests.post(url, headers=headers, files=files, verify=False, timeout=60)
            
            if response.status_code in [200, 201]:
                return response.json()
            else:
                cls._handle_error_response(response)

        except requests.exceptions.RequestException as e:
            logger.error(f"Erro de Conexão PNCP: {e}")
            raise ValueError(f"Falha de comunicação com o PNCP: {str(e)}")