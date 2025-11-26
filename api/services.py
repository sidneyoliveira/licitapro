# api/services.py

import logging
import json
import re
import requests
import base64
import pytz
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from django.conf import settings
from decimal import Decimal

# Configuração de Logger
logger = logging.getLogger(__name__)

class PNCPService:
    BASE_URL = getattr(settings, 'PNCP_BASE_URL', 'https://pncp.gov.br/api/pncp/v1')
    ACCESS_TOKEN = getattr(settings, 'PNCP_ACCESS_TOKEN', '')

    @staticmethod
    def _extrair_user_id_token(token):
        """
        Extrai o ID do usuário (idBaseDados) do JWT para usar na vinculação.
        """
        try:
            if not token: return None
            # O JWT é dividido em 3 partes. O payload é a segunda.
            parts = token.split('.')
            if len(parts) < 2: return None
            
            payload_b64 = parts[1]
            # Ajusta padding base64 se necessário
            payload_b64 += '=' * (-len(payload_b64) % 4)
            payload_json = base64.b64decode(payload_b64).decode('utf-8')
            payload = json.loads(payload_json)
            
            # Tenta pegar o idBaseDados (comum no PNCP) ou sub/user_id
            return payload.get('idBaseDados') or payload.get('sub') or payload.get('user_id')
        except Exception as e:
            logger.error(f"Erro ao decodificar JWT do PNCP: {e}")
            return None

    @classmethod
    def _vincular_usuario_ao_orgao(cls, user_id, cnpj):
        """
        CORREÇÃO: Vincula o usuário ao órgão usando o endpoint correto (Manual 6.1.5).
        URL: /v1/usuarios/{id}/orgaos
        Payload: { "entesAutorizados": [ "CNPJ" ] }
        """
        if not user_id or not cnpj:
            return

        url = f"{cls.BASE_URL}/usuarios/{user_id}/orgaos"
        headers = {
            "Authorization": f"Bearer {cls.ACCESS_TOKEN}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "entesAutorizados": [cnpj]
        }

        try:
            # verify=False para evitar erros de SSL em ambientes de teste/homologação
            logger.info(f"Tentando vincular Usuario {user_id} ao Orgao {cnpj}...")
            response = requests.post(url, headers=headers, json=payload, verify=False, timeout=10)
            
            if response.status_code in [200, 201]:
                logger.info("Vinculação realizada/confirmada com sucesso.")
            else:
                # Não levantamos erro aqui para não bloquear o fluxo caso já esteja vinculado
                logger.warning(f"Aviso na vinculação (pode já existir): {response.status_code} - {response.text}")
                
        except Exception as e:
            logger.error(f"Erro ao tentar vincular usuário ao órgão: {e}")

    @staticmethod
    def _handle_error_response(response):
        try:
            err_json = response.json()
            detail = err_json.get("message") or err_json.get("detail") or err_json.get("errors") or str(err_json)
            if isinstance(detail, list):
                detail = " | ".join([str(e) for e in detail])
        except:
            detail = response.text[:300]
        
        msg = f"PNCP Recusou ({response.status_code}): {detail}"
        logger.error(msg)
        raise ValueError(msg)

    @classmethod
    def publicar_compra(cls, processo, arquivo: Any, titulo_documento: str) -> Dict[str, Any]:
        """
        Executa o fluxo completo de publicação.
        """
        
        # 0. Verificação Inicial
        if not cls.ACCESS_TOKEN:
            raise ValueError("Configuração Crítica Ausente: 'PNCP_ACCESS_TOKEN' não encontrado.")

        # ------------------------------------------------------------------
        # 1. PREPARAÇÃO E VINCULAÇÃO (CRÍTICO PARA O ERRO 401)
        # ------------------------------------------------------------------
        cnpj_orgao = re.sub(r'\D', '', processo.entidade.cnpj)
        
        # Tenta vincular o usuário ao órgão antes de enviar a compra
        try:
            user_id = cls._extrair_user_id_token(cls.ACCESS_TOKEN)
            if user_id:
                cls._vincular_usuario_ao_orgao(user_id, cnpj_orgao)
            else:
                logger.warning("Não foi possível extrair ID do usuário do token para vinculação automática.")
        except Exception as e:
            logger.error(f"Falha no processo de vinculação: {e}")

        # ------------------------------------------------------------------
        # 2. VALIDAÇÃO BÁSICA
        # ------------------------------------------------------------------
        erros = []
        if not processo.numero_certame: erros.append("Número do Certame é obrigatório.")
        if not processo.entidade or not processo.entidade.cnpj: erros.append("Entidade/CNPJ inválido.")
        if not processo.modalidade: erros.append("Modalidade não definida.")
        if not processo.modo_disputa: erros.append("Modo de Disputa não definido.")
        if not processo.amparo_legal: erros.append("Amparo Legal não definido.")

        itens = processo.itens.all()
        if not itens.exists(): erros.append("É necessário cadastrar ao menos um Item.")
        
        if erros:
            raise ValueError("Validação Falhou:\n" + "\n".join(f"- {msg}" for msg in erros))

        # ------------------------------------------------------------------
        # 3. DADOS GERAIS
        # ------------------------------------------------------------------
        if processo.data_processo:
            ano_compra = int(processo.data_processo.year)
        else:
            ano_compra = datetime.now().year

        codigo_unidade = "000000"
        if processo.orgao and processo.orgao.codigo_unidade:
            codigo_unidade = processo.orgao.codigo_unidade

        # ------------------------------------------------------------------
        # 4. DATAS (CORREÇÃO DO ERRO 400 DE DATA)
        # ------------------------------------------------------------------
        dt_abertura = processo.data_abertura
        if not dt_abertura:
             dt_abertura = datetime.now()

        # 1. Garante Timezone Brasília
        if not dt_abertura.tzinfo:
            sp_tz = pytz.timezone('America/Sao_Paulo')
            dt_abertura = sp_tz.localize(dt_abertura)
        else:
            sp_tz = pytz.timezone('America/Sao_Paulo')
            dt_abertura = dt_abertura.astimezone(sp_tz)
        
        # 2. Remove microssegundos e formata sem offset (Requisito PNCP)
        data_abertura_str = dt_abertura.strftime('%Y-%m-%dT%H:%M:%S')
        
        # Data Encerramento (Abertura + 30min para garantir validade)
        dt_encerramento = dt_abertura + timedelta(minutes=30)
        data_encerramento_str = dt_encerramento.strftime('%Y-%m-%dT%H:%M:%S')

        # ------------------------------------------------------------------
        # 5. PAYLOAD
        # ------------------------------------------------------------------
        raw_numero = str(processo.numero_certame).split('/')[0]
        numero_compra_clean = re.sub(r'\D', '', raw_numero)
        if not numero_compra_clean: numero_compra_clean = "1"

        payload = {
            "codigoUnidadeCompradora": codigo_unidade,
            "cnpjOrgao": cnpj_orgao,
            "anoCompra": ano_compra,
            "numeroCompra": numero_compra_clean,
            "numeroProcesso": str(processo.numero_processo or processo.numero_certame),
            
            "tipoInstrumentoConvocatorioId": int(processo.instrumento_convocatorio or 1),
            "modalidadeId": int(processo.modalidade),
            "modoDisputaId": int(processo.modo_disputa),
            "amparoLegalId": int(processo.amparo_legal),
            
            "srp": bool(processo.registro_preco),
            "objetoCompra": (processo.objeto or f"Licitação {processo.numero_processo}")[:5000],
            "informacaoComplementar": "Processo integrado via API Licitapro.",
            
            "dataAberturaProposta": data_abertura_str,
            "dataEncerramentoProposta": data_encerramento_str,
            
            "linkSistemaOrigem": "http://l3solution.net.br",
            "itensCompra": []
        }

        # Itens
        for idx, item in enumerate(itens, 1):
            vl_unitario = float(item.valor_estimado or 0)
            qtd = float(item.quantidade or 0)
            vl_total = round(vl_unitario * qtd, 4)
            
            # Define Material ou Serviço
            cat_id = int(item.categoria_item or 1)
            tipo_ms = "M"
            # Lista de IDs que representam serviços/obras (Ajuste conforme necessário)
            if cat_id in [2, 4, 6, 8, 9]: 
                tipo_ms = "S"

            item_payload = {
                "numeroItem": item.ordem or idx,
                "materialOuServico": tipo_ms,
                "tipoBeneficioId": int(item.tipo_beneficio or 1),
                "incentivoProdutivoBasico": False,
                "descricao": (item.descricao or "Item sem descrição")[:255],
                "quantidade": qtd,
                "unidadeMedida": (item.unidade or "UN")[:20],
                "valorUnitarioEstimado": vl_unitario,
                "valorTotal": vl_total,
                
                "criterioJulgamentoId": int(processo.criterio_julgamento or 1),
                "itemCategoriaId": cat_id,
                
                # Catálogo Genérico (15055 = Outros Materiais de Consumo)
                "catalogoId": 1, 
                "catalogoCodigoItem": "15055", 
                "categoriaItemCatalogoId": 1
            }
            payload["itensCompra"].append(item_payload)

        # ------------------------------------------------------------------
        # 6. ENVIO (MULTIPART)
        # ------------------------------------------------------------------
        if hasattr(arquivo, 'seek'):
            arquivo.seek(0)

        filename = getattr(arquivo, 'name', 'edital.pdf')
        
        files = {
            'documento': (filename, arquivo, 'application/pdf'),
            'compra': (None, json.dumps(payload), 'application/json')
        }

        url = f"{cls.BASE_URL}/orgaos/{cnpj_orgao}/compras"
        headers = {
            "Authorization": f"Bearer {cls.ACCESS_TOKEN}",
            "Titulo-Documento": titulo_documento,
            "Tipo-Documento-Id": "1" # 1 = Edital
        }

        try:
            logger.info(f"Enviando para PNCP: {url}")
            response = requests.post(url, headers=headers, files=files, verify=False, timeout=90)
            
            if response.status_code in [200, 201]:
                return response.json()
            else:
                cls._handle_error_response(response)

        except requests.exceptions.RequestException as e:
            logger.error(f"Erro de Conexão PNCP: {e}")
            raise ValueError(f"Falha de comunicação com o PNCP: {str(e)}")

# Mantido para compatibilidade
class ImportacaoService:
    @staticmethod
    def processar_planilha_padrao(arquivo):
        raise NotImplementedError("Importação via planilha ainda não implementada.")