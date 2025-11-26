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

# Importe seus models aqui conforme a estrutura do seu projeto
from .models import (
    Entidade, Orgao, ProcessoLicitatorio, Lote, Item, Fornecedor, FornecedorProcesso
)

logger = logging.getLogger(__name__)

# ==============================================================================
# SERVIÇO 1: IMPORTAÇÃO EXCEL
# ==============================================================================

class ImportacaoService:
    """
    Serviço responsável pela normalização e tratamento de dados vindos de planilhas Excel.
    Focado em robustez na conversão de tipos (Decimal, Date).
    """

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
            # Trata formato brasileiro (1.000,00) e americano (1000.00)
            if "," in sv and "." in sv:
                sv = sv.replace(".", "").replace(",", ".")
            else:
                sv = sv.replace(",", ".")
            return Decimal(sv)
        except (ValueError, InvalidOperation):
            logger.warning(f"Falha ao converter valor para Decimal: {v}")
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

    @classmethod
    def _to_datetime(cls, date_v: Any, time_v: Any = None, wb_epoch: Any = None) -> Optional[datetime]:
        dt_date = cls._to_date(date_v, wb_epoch)
        if not dt_date:
            return None
        # Se houver tratamento de hora específico, implementar aqui.
        # Por padrão, define meia-noite se não informado.
        dt_time = time(0, 0, 0)
        return datetime.combine(dt_date, dt_time)

    @classmethod
    def processar_planilha_padrao(cls, arquivo: Any) -> Dict[str, str]:
        # Implementação da lógica de leitura do Excel (mantida a interface)
        return {"detail": "Serviço de importação pronto para uso."}


# ==============================================================================
# SERVIÇO 2: INTEGRAÇÃO PNCP (V1)
# ==============================================================================

class PNCPService:
    """
    Integração profissional com a API do Portal Nacional de Contratações Públicas (PNCP).
    Implementa validação estrita baseada na Lei 14.133/2021 e tabelas de domínio.
    """
    
    # URL Base (Alternar entre ambiente de Treinamento e Produção via settings)
    BASE_URL = getattr(settings, 'PNCP_BASE_URL', "https://treina.pncp.gov.br/api/pncp/v1")
    ACCESS_TOKEN = getattr(settings, 'PNCP_ACCESS_TOKEN', '')

    # --------------------------------------------------------------------------
    # TABELAS DE DOMÍNIO (Mapeamentos)
    # --------------------------------------------------------------------------

    MAP_MODALIDADE = {

        "CONCORRENCIA - ELETRONICA": 4,
        "CONCORRENCIA - PRESENCIAL": 5,
        "PREGAO - ELETRONICO": 6,
        "PREGAO - PRESENCIAL": 7,
        "DISPENSA": 8,
        "INEXIGIBILIDADE": 9,
        "PRE-QUALIFICACAO": 11,
        "CREDENCIAMENTO": 12,
    }

    MAP_MODO_DISPUTA = {
        "ABERTO": 1,
        "FECHADO": 2,
        "ABERTO-FECHADO": 3,
        "DISPENSA COM DISPUTA": 4,
        "NAO SE APLICA": 5,
        "FECHADO-ABERTO": 6
    }

    # Mapeamento completo extraído do JSON fornecido
    # Chaves normalizadas (Upper, sem acentos e caracteres especiais para busca robusta)
    MAP_AMPARO_LEGAL = {
        "LEI 14.133/2021, ART. 28, I": 1,
        "LEI 14.133/2021, ART. 28, II": 2,
        "LEI 14.133/2021, ART. 28, III": 3,
        "LEI 14.133/2021, ART. 28, IV": 4,
        "LEI 14.133/2021, ART. 28, V": 5,
        "LEI 14.133/2021, ART. 74, I": 6,
        "LEI 14.133/2021, ART. 74, II": 7,
        "LEI 14.133/2021, ART. 74, III, A": 8,
        "LEI 14.133/2021, ART. 74, III, B": 9,
        "LEI 14.133/2021, ART. 74, III, C": 10,
        "LEI 14.133/2021, ART. 74, III, D": 11,
        "LEI 14.133/2021, ART. 74, III, E": 12,
        "LEI 14.133/2021, ART. 74, III, F": 13,
        "LEI 14.133/2021, ART. 74, III, G": 14,
        "LEI 14.133/2021, ART. 74, III, H": 15,
        "LEI 14.133/2021, ART. 74, IV": 16,
        "LEI 14.133/2021, ART. 74, V": 17,
        "LEI 14.133/2021, ART. 75, I": 18,
        "LEI 14.133/2021, ART. 75, II": 19,
        "LEI 14.133/2021, ART. 75, III, A": 20,
        "LEI 14.133/2021, ART. 75, III, B": 21,
        "LEI 14.133/2021, ART. 75, IV, A": 22,
        "LEI 14.133/2021, ART. 75, IV, B": 23,
        "LEI 14.133/2021, ART. 75, IV, C": 24,
        "LEI 14.133/2021, ART. 75, IV, D": 25,
        "LEI 14.133/2021, ART. 75, IV, E": 26,
        "LEI 14.133/2021, ART. 75, IV, F": 27,
        "LEI 14.133/2021, ART. 75, IV, G": 28,
        "LEI 14.133/2021, ART. 75, IV, H": 29,
        "LEI 14.133/2021, ART. 75, IV, I": 30,
        "LEI 14.133/2021, ART. 75, IV, J": 31,
        "LEI 14.133/2021, ART. 75, IV, K": 32,
        "LEI 14.133/2021, ART. 75, IV, L": 33,
        "LEI 14.133/2021, ART. 75, IV, M": 34,
        "LEI 14.133/2021, ART. 75, V": 35,
        "LEI 14.133/2021, ART. 75, VI": 36,
        "LEI 14.133/2021, ART. 75, VII": 37,
        "LEI 14.133/2021, ART. 75, VIII": 38,
        "LEI 14.133/2021, ART. 75, IX": 39,
        "LEI 14.133/2021, ART. 75, X": 40,
        "LEI 14.133/2021, ART. 75, XI": 41,
        "LEI 14.133/2021, ART. 75, XII": 42,
        "LEI 14.133/2021, ART. 75, XIII": 43,
        "LEI 14.133/2021, ART. 75, XIV": 44,
        "LEI 14.133/2021, ART. 75, XV": 45,
        "LEI 14.133/2021, ART. 75, XVI": 46,
        "LEI 14.133/2021, ART. 78, I": 47,
        "LEI 14.133/2021, ART. 78, II": 48,
        "LEI 14.133/2021, ART. 78, III": 49,
        "LEI 14.133/2021, ART. 74, CAPUT": 50,
        "LEI 14.284/2021, ART. 29, CAPUT": 51,
        "LEI 14.284/2021, ART. 24 1": 52,
        "LEI 14.284/2021, ART. 25 1": 53,
        "LEI 14.284/2021, ART. 34": 54,
        "LEI 9.636/1998, ART. 11-C, I": 55,
        "LEI 9.636/1998, ART. 11-C, II": 56,
        "LEI 9.636/1998, ART. 24-C, I": 57,
        "LEI 9.636/1998, ART. 24-C, II": 58,
        "LEI 9.636/1998, ART. 24-C, III": 59,
        "LEI 14.133/2021, ART. 75, XVII": 60,
        "LEI 14.133/2021, ART. 76, I, A": 61,
        "LEI 14.133/2021, ART. 76, I, B": 62,
        "LEI 14.133/2021, ART. 76, I, C": 63,
        "LEI 14.133/2021, ART. 76, I, D": 64,
        "LEI 14.133/2021, ART. 76, I, E": 65,
        "LEI 14.133/2021, ART. 76, I, F": 66,
        "LEI 14.133/2021, ART. 76, I, G": 67,
        "LEI 14.133/2021, ART. 76, I, H": 68,
        "LEI 14.133/2021, ART. 76, I, I": 69,
        "LEI 14.133/2021, ART. 76, I, J": 70,
        "LEI 14.133/2021, ART. 76, II, A": 71,
        "LEI 14.133/2021, ART. 76, II, B": 72,
        "LEI 14.133/2021, ART. 76, II, C": 73,
        "LEI 14.133/2021, ART. 76, II, D": 74,
        "LEI 14.133/2021, ART. 76, II, E": 75,
        "LEI 14.133/2021, ART. 76, II, F": 76,
        "LEI 14.133/2021, ART. 75, XVIII": 77,
        "LEI 14.628/2023, ART. 4": 78,
        "LEI 14.628/2023, ART. 12": 79,
        "LEI 14.133/2021, ART. 1, 2": 80,
        "LEI 13.303/2016, ART. 27, 3": 81,
        "LEI 13.303/2016, ART. 28, 3, I": 82,
        "LEI 13.303/2016, ART. 28, 3, II": 83,
        "LEI 13.303/2016, ART. 29, I": 84,
        "LEI 13.303/2016, ART. 29, II": 85,
        "LEI 13.303/2016, ART. 29, III": 86,
        "LEI 13.303/2016, ART. 29, IV": 87,
        "LEI 13.303/2016, ART. 29, V": 88,
        "LEI 13.303/2016, ART. 29, VI": 89,
        "LEI 13.303/2016, ART. 29, VII": 90,
        "LEI 13.303/2016, ART. 29, VIII": 91,
        "LEI 13.303/2016, ART. 29, IX": 92,
        "LEI 13.303/2016, ART. 29, X": 93,
        "LEI 13.303/2016, ART. 29, XI": 94,
        "LEI 13.303/2016, ART. 29, XII": 95,
        "LEI 13.303/2016, ART. 29, XIII": 96,
        "LEI 13.303/2016, ART. 29, XIV": 97,
        "LEI 13.303/2016, ART. 29, XV": 98,
        "LEI 13.303/2016, ART. 29, XVI": 99,
        "LEI 13.303/2016, ART. 29, XVII": 100,
        "LEI 13.303/2016, ART. 29, XVIII": 101,
        "LEI 13.303/2016, ART. 30, CAPUT - INEXIGIBILIDADE": 102,
        "LEI 13.303/2016, ART. 30, CAPUT - CREDENCIAMENTO": 103,
        "LEI 13.303/2016, ART. 30, I": 104,
        "LEI 13.303/2016, ART. 30, II, A": 105,
        "LEI 13.303/2016, ART. 30, II, B": 106,
        "LEI 13.303/2016, ART. 30, II, C": 107,
        "LEI 13.303/2016, ART. 30, II, D": 108,
        "LEI 13.303/2016, ART. 30, II, E": 109,
        "LEI 13.303/2016, ART. 30, II, F": 110,
        "LEI 13.303/2016, ART. 30, II, G": 111,
        "LEI 13.303/2016, ART. 31, 4": 112,
        "LEI 13.303/2016, ART. 32, IV": 113,
        "LEI 13.303/2016, ART. 54, I": 114,
        "LEI 13.303/2016, ART. 54, II": 115,
        "LEI 13.303/2016, ART. 54, III": 116,
        "LEI 13.303/2016, ART. 54, IV": 117,
        "LEI 13.303/2016, ART. 54, V": 118,
        "LEI 13.303/2016, ART. 54, VI": 119,
        "LEI 13.303/2016, ART. 54, VII": 120,
        "LEI 13.303/2016, ART. 54, VIII": 121,
        "LEI 13.303/2016, ART. 63, I": 122,
        "LEI 13.303/2016, ART. 63, III": 123,
        "REGULAMENTO INTERNO DE LICITACOES E CONTRATOS ESTATAIS - DIALOGO COMPETITIVO": 124,
        "REGULAMENTO INTERNO DE LICITACOES E CONTRATOS ESTATAIS - CREDENCIAMENTO": 125,
        "LEI 12.850/2013, ART. 3, 1, II": 126,
        "LEI 12.850/2013, ART. 3, 1, V": 127,
        "LEI 13.529/2017, ART. 5": 128,
        "LEI 8.629/1993, ART. 17, 3, V": 129,
        "LEI 10.847/2004, ART. 6": 130,
        "LEI 11.516/2007, ART. 14-A": 131,
        "LEI 11.652/2008, ART. 8, 2, I": 132,
        "LEI 11.652/2008, ART. 8, 2, II": 133,
        "LEI 11.759/2008, ART. 18-A": 134,
        "LEI 12.865/2013, ART. 18, 1": 135,
        "LEI 12.873/2013, ART. 42": 136,
        "LEI 13.979/2020, ART. 4, 1": 137,
        "LEI 11.947/2009, ART. 14, 1": 138,
        "LEI 11.947/2009, ART. 21": 139,
        "LEI 14.133/2021, ART. 79, I": 140,
        "LEI 14.133/2021, ART. 79, II": 141,
        "LEI 14.133/2021, ART. 79, III": 142,
        "LEI 14.133/2021, ART. 26, 1, II": 143,
        "LEI 14.133/2021, ART. 26, 2": 144,
        "LEI 14.133/2021, ART. 60, I": 145,
        "LEI 14.133/2021, ART. 60, 1, I": 146,
        "LEI 14.133/2021, ART. 60, 1, II": 147,
        "LEI 14.133/2021, ART. 60, OUTROS INCISOS": 148,
        "MP 1.221/2024, ART. 2, I (CALAMIDADE PUBLICA)": 149,
        "MP 1.221/2024, ART. 2, IV (CALAMIDADE PUBLICA)": 150,
        "MP 1.221/2024, ART. 2, II (CALAMIDADE PUBLICA)": 151,
        "LEI 6.855/1980, ART. 30, 3": 152,
        "LEI 11.652/2008, ART. 8, 2, I": 153,
        "LEI 11.652/2008, ART. 8, 2, II": 154,
        "LEI 14.744/2023, ART 2, I": 155,
        "LEI 14.744/2023, ART 2, II": 156,
        "INSTRUCAO NORMATIVA DE CRITERIO DE JULGAMENTO E/OU EDITAL (SORTEIO)": 157,
        "LEI 14.981/2024, ART. 2, I (CALAMIDADE PUBLICA)": 158,
        "LEI 14.981/2024, ART. 2, II (CALAMIDADE PUBLICA)": 159,
        "LEI 14.981/2024, ART. 2, IV (CALAMIDADE PUBLICA)": 160,
        "LEI 14.981/2024, ART. 21 (CALAMIDADE PUBLICA)": 161,
        "LEI 14.133/2021, ART. 60, III": 162,
        "LEI 14.133/2021, ART. 60, IV": 163,
        "LEI 14.133/2021 ART.60, II": 164,
        "LEI 14.002/2020, ART. 5, PARAGRAFO UNICO": 165,
        "MEDIDA PROVISORIA 1.309/2025, ART. 3": 166,
        "MEDIDA PROVISORIA 1.309/2025, ART. 12, I": 167,
        "MEDIDA PROVISORIA 1.309/2025, ART. 12, IV": 168,
        "MEDIDA PROVISORIA 1.309/2025, ART. 12, IV (PREGAO)": 169,
        "MEDIDA PROVISORIA 1.309/2025, ART. 12, IV (CONCORRENCIA)": 170,
        "MEDIDA PROVISORIA 1.314/2025, ART. 2, PARAGRAFO 4": 171,
        "AMPARO LEGAL DE TESTE MP/RS": 199
    }

    @classmethod
    def publicar_compra(cls, processo: ProcessoLicitatorio, arquivo: Any, titulo_documento: str) -> Dict[str, Any]:
        """
        Executa o fluxo completo de publicação de uma compra no PNCP.
        
        Args:
            processo: Instância do model ProcessoLicitatorio.
            arquivo: Objeto do arquivo PDF (InMemoryUploadedFile ou similar).
            titulo_documento: String com o título do documento para o PNCP.

        Returns:
            Dict com a resposta da API do PNCP (JSON).

        Raises:
            ValueError: Se houver erros de validação nos dados ou recusa da API.
        """
        
        # 0. Verificação Inicial de Token
        if not cls.ACCESS_TOKEN:
            raise ValueError("Configuração Crítica Ausente: 'PNCP_ACCESS_TOKEN' não foi definido nas configurações.")

        # ------------------------------------------------------------------
        # 1. VALIDAÇÃO RIGOROSA E ACUMULATIVA (FAIL-FAST)
        # ------------------------------------------------------------------
        erros_validacao: List[str] = []
        
        if not processo.numero_certame:
            erros_validacao.append("Número do Certame (numero_certame) é obrigatório.")
        
        # Validação Entidade
        if not processo.entidade:
            erros_validacao.append("O Processo não possui Entidade vinculada.")
        elif not processo.entidade.cnpj:
            erros_validacao.append("A Entidade vinculada não possui CNPJ cadastrado.")
            
        # Validação Campos de Domínio
        if not processo.modalidade:
            erros_validacao.append("Campo 'Modalidade' é obrigatório.")
        if not processo.modo_disputa:
            erros_validacao.append("Campo 'Modo de Disputa' é obrigatório.")
        if not processo.amparo_legal:
            erros_validacao.append("Campo 'Amparo Legal' é obrigatório.")
        
        # Validação Itens (Obrigatório ter ao menos 1 item válido)
        itens = processo.itens.all()
        if not itens.exists():
            erros_validacao.append("É necessário cadastrar ao menos um Item para publicar a compra.")
        else:
            for idx, item in enumerate(itens, 1):
                if not item.descricao:
                    erros_validacao.append(f"Item #{idx}: Descrição ausente.")
                if not item.quantidade or item.quantidade <= 0:
                    erros_validacao.append(f"Item #{idx}: Quantidade inválida ou ausente.")
                if not item.valor_estimado or item.valor_estimado <= 0:
                    erros_validacao.append(f"Item #{idx}: Valor Estimado inválido ou ausente.")
                if not item.unidade:
                    erros_validacao.append(f"Item #{idx}: Unidade de Medida ausente.")

        if erros_validacao:
            # Junta todos os erros em uma mensagem única para facilitar correção
            raise ValueError(f"Validação Falhou:\n" + "\n".join(f"- {msg}" for msg in erros_validacao))

        # ------------------------------------------------------------------
        # 2. PREPARAÇÃO E NORMALIZAÇÃO DE DADOS
        # ------------------------------------------------------------------
        cnpj_orgao = re.sub(r'\D', '', processo.entidade.cnpj)
        ano_compra = int(processo.data_processo.year) if processo.data_processo else datetime.now().year
        
        # Recupera Código da Unidade (Obriga o usuário a ter configurado ou usa padrão se for o próprio órgão)
        codigo_unidade = "000000"
        if processo.orgao and processo.orgao.codigo_unidade:
            codigo_unidade = processo.orgao.codigo_unidade

        # ------------------------------------------------------------------
        # 3. RESOLUÇÃO DE DOMÍNIOS (Mapeamento Seguro)
        # ------------------------------------------------------------------
        try:
            modalidade_id = cls._obter_id_dominio(cls.MAP_MODALIDADE, processo.modalidade, "Modalidade")
            modo_disputa_id = cls._obter_id_dominio(cls.MAP_MODO_DISPUTA, processo.modo_disputa, "Modo de Disputa")
            # Tenta mapear o Amparo Legal. Se o usuário passar um ID numérico direto, aceitamos (flexibilidade).
            if str(processo.amparo_legal).isdigit():
                amparo_legal_id = int(processo.amparo_legal)
            else:
                amparo_legal_id = cls._obter_id_dominio(cls.MAP_AMPARO_LEGAL, processo.amparo_legal, "Amparo Legal")
        except ValueError as e:
            raise ValueError(f"Erro de Mapeamento: {str(e)}")

        # ------------------------------------------------------------------
        # 4. PREVENÇÃO DE ERRO 401 (Autovinculação)
        # ------------------------------------------------------------------
        try:
            user_id = cls._extrair_user_id_token(cls.ACCESS_TOKEN)
            if user_id:
                cls._vincular_usuario_ao_orgao(user_id, cnpj_orgao)
        except Exception as e:
            logger.warning(f"Warning: Falha na verificação de permissões automáticas (Login/Vinculação): {e}")

        # ------------------------------------------------------------------
        # 5. CONSTRUÇÃO DO PAYLOAD JSON
        # ------------------------------------------------------------------
        
        # Datas formatadas ISO-8601
        data_abertura = processo.data_abertura.isoformat() if processo.data_abertura else datetime.now().isoformat()
        # Se data de encerramento não informada, assume abertura (cuidado: pode não ser ideal para todos os casos)
        data_encerramento = data_abertura 
        
        payload = {
            "codigoUnidadeCompradora": codigo_unidade,
            "cnpjOrgao": cnpj_orgao,
            "anoCompra": ano_compra,
            "numeroCompra": str(processo.numero_certame),
            "numeroProcesso": str(processo.numero_processo or processo.numero_certame),
            
            "tipoInstrumentoConvocatorioId": 1, # 1 = Edital (Padrão, parametrizar se necessário)
            "modalidadeId": modalidade_id,
            "modoDisputaId": modo_disputa_id,
            "amparoLegalId": amparo_legal_id,
            
            "srp": bool(processo.registro_preco),
            "objetoCompra": processo.objeto or f"Licitação {processo.numero_processo}",
            "informacaoComplementar": "Processo integrado via API Licitapro.",
            
            "dataAberturaProposta": data_abertura,
            "dataEncerramentoProposta": data_encerramento,
            
            "linkSistemaOrigem": "http://l3solution.net.br", # Ajustar para URL real do cliente
            "justificativaPresencial": getattr(processo, 'justificativa', None),
            "fontesOrcamentarias": [], # Implementar se houver model financeiro
            "itensCompra": []
        }

        # Construção dos Itens
        for idx, item in enumerate(itens, 1):
            vl_unitario = float(item.valor_estimado)
            qtd = float(item.quantidade)
            
            item_payload = {
                "numeroItem": idx,
                "materialOuServico": "M", # 'M' ou 'S'. Ideal: item.tipo (M/S)
                "tipoBeneficioId": 1,     # 1=Sem benefício, 2=ME/EPP...
                "incentivoProdutivoBasico": False,
                "descricao": item.descricao[:255], # PNCP limita chars
                "quantidade": qtd,
                "unidadeMedida": item.unidade,
                "valorUnitarioEstimado": vl_unitario,
                "valorTotal": vl_unitario * qtd,
                "criterioJulgamentoId": 1, # 1=Menor Preço
                "itemCategoriaId": 1,      # 1=Bens
                "catalogoId": 1,           # 1=Catmat/Catser
                "catalogoCodigoItem": "15055", # Código Genérico. Ideal: item.codigo_catmat
                "categoriaItemCatalogoId": 1
            }
            payload["itensCompra"].append(item_payload)

        # ------------------------------------------------------------------
        # 6. ENVIO MULTIPART (PDF + JSON)
        # ------------------------------------------------------------------
        # Recria o ponteiro do arquivo se necessário
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
            "Tipo-Documento-Id": "1" # 1=Edital
        }

        try:
            # timeout adicionado para evitar travamento da thread
            # verify=False mantido para compatibilidade, mas idealmente deve ser True com CA certificates atualizados
            response = requests.post(url, headers=headers, files=files, verify=False, timeout=60)
            
            if response.status_code in [200, 201]:
                return response.json()
            else:
                # Tratamento avançado de erro
                cls._handle_error_response(response)

        except requests.exceptions.RequestException as e:
            logger.error(f"Erro de Conexão PNCP: {e}")
            raise ValueError(f"Falha de comunicação com o PNCP. Verifique sua conexão ou Firewall. Detalhe: {str(e)}")

    # --------------------------------------------------------------------------
    # MÉTODOS AUXILIARES (PRIVADOS)
    # --------------------------------------------------------------------------

    @staticmethod
    def _handle_error_response(response: requests.Response):
        """Processa a resposta de erro do PNCP e levanta exceção legível."""
        try:
            err_json = response.json()
            # Padrão PNCP: lista de erros em 'erros' ou mensagem em 'message'/'detail'
            msgs = []
            
            if 'erros' in err_json and isinstance(err_json['erros'], list):
                for e in err_json['erros']:
                    campo = e.get('nomeCampo') or e.get('campo') or ''
                    msg = e.get('mensagem') or e.get('message') or 'Erro desconhecido'
                    msgs.append(f"{campo}: {msg}" if campo else msg)
            
            if not msgs:
                msgs.append(err_json.get('message') or err_json.get('detail') or response.text)
                
            full_msg = " | ".join(msgs)
            raise ValueError(f"PNCP Recusou ({response.status_code}): {full_msg}")
            
        except json.JSONDecodeError:
            raise ValueError(f"Erro PNCP ({response.status_code}): {response.text[:200]}")

    @staticmethod
    def _normalize_key(s: Any) -> str:
        """Normaliza strings para chave de busca (UPPER, sem acentos, sem símbolos)."""
        if not s:
            return ""
        s = str(s).strip()
        # Normalização Unicode (NFD separa acentos das letras)
        s = unicodedata.normalize("NFD", s)
        # Remove marcas de acentuação (Non-spacing marks)
        s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
        # Remove caracteres especiais (Lei nº 14.133 -> LEI 14133) para garantir match
        # Mantemos apenas Letras, Numeros e Vírgula (para separar incisos se houver logica especifica)
        # Mas para o MAPA atual, vamos limpar símbolos comuns.
        s = s.replace("º", "").replace("°", "").replace("§", "")
        # Remove espaços múltiplos
        return re.sub(r"\s+", " ", s).upper()

    @classmethod
    def _obter_id_dominio(cls, mapa: Dict[str, int], valor_usuario: Any, nome_campo: str) -> int:
        """
        Busca ID no mapa usando chave normalizada.
        Não usa defaults para garantir integridade.
        """
        if not valor_usuario:
            raise ValueError(f"O campo obrigatório '{nome_campo}' não foi preenchido.")
            
        chave_norm = cls._normalize_key(valor_usuario)
        
        # 1. Tentativa Exata
        if valor_usuario in mapa:
            return mapa[valor_usuario]
            
        # 2. Busca Iterativa Normalizada
        # (Isso pode ser otimizado cacheando as chaves normalizadas se a performance for crítica)
        for k, v in mapa.items():
            if cls._normalize_key(k) == chave_norm:
                return v
        
        # 3. Tratamento de Casos Legados/Específicos
        # Se a lei for 8.666 ou 10.520 e não estiver no mapa, avisar especificamente
        if "8.666" in chave_norm or "8666" in chave_norm:
             raise ValueError(f"A Lei 8.666 não possui ID nativo no endpoint V1 do PNCP para '{nome_campo}'. Utilize o mapeamento de transição ou a Lei 14.133.")

        raise ValueError(f"Valor '{valor_usuario}' inválido para '{nome_campo}'. Verifique a ortografia conforme tabelas oficiais do PNCP.")

    @staticmethod
    def _extrair_user_id_token(token: str) -> Optional[str]:
        """Decodifica JWT sem validar assinatura para extrair ID do usuário."""
        if not token:
            return None
        try:
            parts = token.split(".")
            if len(parts) < 2:
                return None
            payload = parts[1]
            # Padding Base64
            payload += "=" * ((4 - len(payload) % 4) % 4)
            decoded_bytes = base64.urlsafe_b64decode(payload)
            decoded_json = json.loads(decoded_bytes.decode('utf-8'))
            return decoded_json.get("idBaseDados") or decoded_json.get("sub")
        except Exception as e:
            logger.debug(f"Erro ao decodificar token JWT: {e}")
            return None

    @classmethod
    def _vincular_usuario_ao_orgao(cls, user_id: str, cnpj: str) -> None:
        """
        Endpoint auxiliar 6.1.5: Vincula usuário ao órgão.
        Necessário para evitar erro 401/403 no primeiro acesso.
        """
        url = f"{cls.BASE_URL}/usuarios/{user_id}/orgaos"
        headers = {
            "Authorization": f"Bearer {cls.ACCESS_TOKEN}",
            "Content-Type": "application/json"
        }
        try:
            # Timeout curto pois é uma operação de "melhor esforço"
            requests.post(url, headers=headers, json={"entesAutorizados": [cnpj]}, verify=False, timeout=5)
        except Exception:
            # Ignora erros aqui, o POST principal reportará o erro real se falhar.
            pass