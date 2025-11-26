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
    """
    Integração profissional com a API do Portal Nacional de Contratações Públicas (PNCP).
    Utiliza os dados já validados e persistidos no Banco de Dados (IDs inteiros).
    """
    
    BASE_URL = getattr(settings, 'PNCP_BASE_URL', "https://treina.pncp.gov.br/api/pncp/v1")
    ACCESS_TOKEN = getattr(settings, 'PNCP_ACCESS_TOKEN', '')

    @classmethod
    def publicar_compra(cls, processo: ProcessoLicitatorio, arquivo: Any, titulo_documento: str) -> Dict[str, Any]:
        """
        Executa o fluxo completo de publicação.
        Assumes que o objeto 'processo' já tem os campos modalidade, amparo_legal, etc.
        preenchidos com os IDs CORRETOS (Inteiros) do choices.py.
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
        
        # Como o model agora é IntegerField, verificamos se é > 0
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
        ano_compra = int(processo.data_processo.year) if processo.data_processo else datetime.now().year
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
        # 4. CONSTRUÇÃO DO PAYLOAD (Usando IDs do Model diretamente)
        # ------------------------------------------------------------------
        data_abertura = processo.data_abertura.isoformat() if processo.data_abertura else datetime.now().isoformat()
        
        payload = {
            "codigoUnidadeCompradora": codigo_unidade,
            "cnpjOrgao": cnpj_orgao,
            "anoCompra": ano_compra,
            "numeroCompra": str(processo.numero_certame),
            "numeroProcesso": str(processo.numero_processo or processo.numero_certame),
            
            # AQUI: Mapeamento direto pois o Model já guarda o ID Integer do PNCP
            "tipoInstrumentoConvocatorioId": processo.instrumento_convocatorio or 1, # Default Edital
            "modalidadeId": processo.modalidade,
            "modoDisputaId": processo.modo_disputa,
            "amparoLegalId": processo.amparo_legal,
            
            "srp": bool(processo.registro_preco),
            "objetoCompra": processo.objeto or f"Licitação {processo.numero_processo}",
            "informacaoComplementar": "Processo integrado via API Licitapro.",
            
            "dataAberturaProposta": data_abertura,
            "dataEncerramentoProposta": data_abertura, # TODO: Adicionar campo data_encerramento no model
            
            "linkSistemaOrigem": "http://l3solution.net.br",
            "itensCompra": []
        }

        # Construção dos Itens
        for idx, item in enumerate(itens, 1):
            vl_unitario = float(item.valor_estimado or 0)
            qtd = float(item.quantidade or 0)
            
            item_payload = {
                "numeroItem": item.ordem or idx,
                "materialOuServico": "M", # TODO: Melhorar lógica M/S baseada em categoria_item
                "tipoBeneficioId": item.tipo_beneficio or 1, # 1 = Sem benefício
                "incentivoProdutivoBasico": False,
                "descricao": item.descricao[:255],
                "quantidade": qtd,
                "unidadeMedida": item.unidade,
                "valorUnitarioEstimado": vl_unitario,
                "valorTotal": vl_unitario * qtd,
                
                # IDs do Item (Model já atualizado para integer)
                "criterioJulgamentoId": processo.criterio_julgamento or 1, # Herda do processo ou item
                "itemCategoriaId": item.categoria_item or 1, # 1 = Bens
                
                # Catálogo (Valores padrão por enquanto, implementar busca se necessário)
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

        files = {
            'documento': (arquivo.name, arquivo, 'application/pdf'),
            'compra': (None, json.dumps(payload), 'application/json')
        }

        url = f"{cls.BASE_URL}/orgaos/{cnpj_orgao}/compras"
        headers = {
            "Authorization": f"Bearer {cls.ACCESS_TOKEN}",
            "Titulo-Documento": titulo_documento,
            "Tipo-Documento-Id": "1"
        }

        try:
            response = requests.post(url, headers=headers, files=files, verify=False, timeout=60)
            if response.status_code in [200, 201]:
                return response.json()
            else:
                cls._handle_error_response(response)

        except requests.exceptions.RequestException as e:
            logger.error(f"Erro de Conexão PNCP: {e}")
            raise ValueError(f"Falha de comunicação com o PNCP: {str(e)}")

    # --------------------------------------------------------------------------
    # MÉTODOS AUXILIARES
    # --------------------------------------------------------------------------

    @staticmethod
    def _handle_error_response(response: requests.Response):
        try:
            err_json = response.json()
            msgs = []
            if 'erros' in err_json and isinstance(err_json['erros'], list):
                for e in err_json['erros']:
                    campo = e.get('nomeCampo') or ''
                    msg = e.get('mensagem') or e.get('message') or ''
                    msgs.append(f"{campo}: {msg}")
            
            if not msgs:
                msgs.append(err_json.get('message') or err_json.get('detail') or response.text)
                
            raise ValueError(f"PNCP Recusou ({response.status_code}): {' | '.join(msgs)}")
        except json.JSONDecodeError:
            raise ValueError(f"Erro PNCP ({response.status_code}): {response.text[:200]}")

    @staticmethod
    def _extrair_user_id_token(token: str) -> Optional[str]:
        if not token: return None
        try:
            parts = token.split(".")
            payload = parts[1] + "=" * ((4 - len(parts[1]) % 4) % 4)
            decoded = json.loads(base64.urlsafe_b64decode(payload).decode('utf-8'))
            return decoded.get("idBaseDados") or decoded.get("sub")
        except:
            return None

    @classmethod
    def _vincular_usuario_ao_orgao(cls, user_id: str, cnpj: str) -> None:
        url = f"{cls.BASE_URL}/usuarios/{user_id}/orgaos"
        headers = {"Authorization": f"Bearer {cls.ACCESS_TOKEN}", "Content-Type": "application/json"}
        try:
            requests.post(url, headers=headers, json={"entesAutorizados": [cnpj]}, verify=False, timeout=5)
        except:
            pass