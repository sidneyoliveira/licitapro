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
    BASE_URL = getattr(settings, 'PNCP_BASE_URL', 'https://treina.pncp.gov.br/api/pncp/v1')
    
    # --- TOKEN HARDCODED PARA TESTE (TEMPORÁRIO) ---
    ACCESS_TOKEN = "eyJhbGciOiJIUzUxMiJ9.eyJzdWIiOiI2ODJiYTE0YS1jMTJkLTRhOWYtOWMxOS1hNjYyNDIzMGMxMzkiLCJleHAiOjE3NjQxMDgzNzgsImFkbWluaXN0cmFkb3IiOmZhbHNlLCJjcGZDbnBqIjoiMTEwMzU1NDQwMDAxMDUiLCJlbWFpbCI6ImNvbnRhdG9fbGxAaG90bWFpbC5jb20iLCJnZXN0YW9lbnRlIjp0cnVlLCJpZEJhc2VEYWRvcyI6Mjg2NCwibm9tZSI6IkwgJiBMIEFTU0VTU09SSUEgQ09OU1VMVE9SSUEgRSBTRVJWScOHT1MgTFREQSJ9.z_WK_EbWuJrK9HFPQUMFa4IZLG-8IUfYjZzSHBey8WXHyHSnHAOIcrWCxXlBG39JICac2QV5B8qnCiF-tP_9NA"

    @staticmethod
    def _extrair_user_id_token(token):
        """
        Extrai o ID do usuário (idBaseDados) do JWT para usar na vinculação.
        """
        try:
            if not token: return None
            parts = token.split('.')
            if len(parts) < 2: return None
            
            payload_b64 = parts[1]
            payload_b64 += '=' * (-len(payload_b64) % 4)
            payload_json = base64.b64decode(payload_b64).decode('utf-8')
            payload = json.loads(payload_json)
            
            # Pega ID base de dados (prioritário) ou outros
            return payload.get('idBaseDados') or payload.get('sub') or payload.get('user_id')
        except Exception as e:
            logger.error(f"Erro ao decodificar JWT do PNCP: {e}")
            return None

    @classmethod
    def _vincular_usuario_ao_orgao(cls, user_id, cnpj):
        """
        Vincula o usuário ao órgão usando o endpoint correto (Manual 6.1.5).
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
            logger.info(f"Tentando vincular Usuario {user_id} ao Orgao {cnpj}...")
            # verify=False para evitar erros de SSL em ambiente de teste
            response = requests.post(url, headers=headers, json=payload, verify=False, timeout=10)
            
            if response.status_code in [200, 201]:
                logger.info("Vinculação realizada/confirmada com sucesso.")
            else:
                logger.warning(f"Aviso na vinculação: {response.status_code} - {response.text}")
                
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
        
        if not cls.ACCESS_TOKEN:
            raise ValueError("Token ausente no Serviço.")

        # ------------------------------------------------------------------
        # 1. PREPARAÇÃO E VINCULAÇÃO
        # ------------------------------------------------------------------
        cnpj_orgao = re.sub(r'\D', '', processo.entidade.cnpj)
        
        try:
            # Extrai ID do token hardcoded e tenta vincular
            user_id = cls._extrair_user_id_token(cls.ACCESS_TOKEN)
            if user_id:
                cls._vincular_usuario_ao_orgao(user_id, cnpj_orgao)
            else:
                logger.warning("Não foi possível extrair ID do usuário do token.")
        except Exception as e:
            logger.error(f"Falha na vinculação: {e}")

        # ------------------------------------------------------------------
        # 2. VALIDAÇÃO
        # ------------------------------------------------------------------
        erros = []
        if not processo.numero_certame: erros.append("Número do Certame é obrigatório.")
        if not processo.entidade or not processo.entidade.cnpj: erros.append("CNPJ inválido.")
        
        # Validação simples de IDs > 0
        if not processo.modalidade: erros.append("Modalidade não definida.")
        if not processo.modo_disputa: erros.append("Modo de Disputa não definido.")
        if not processo.amparo_legal: erros.append("Amparo Legal não definido.")

        itens = processo.itens.all()
        if not itens.exists(): erros.append("É necessário cadastrar ao menos um Item.")
        
        if erros:
            raise ValueError("Validação Falhou: " + " | ".join(erros))

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
        # 4. DATAS (CORREÇÃO ISO SEM OFFSET E MICROSEGUNDOS)
        # ------------------------------------------------------------------
        dt_abertura = processo.data_abertura
        if not dt_abertura:
             dt_abertura = datetime.now()

        if not dt_abertura.tzinfo:
            sp_tz = pytz.timezone('America/Sao_Paulo')
            dt_abertura = sp_tz.localize(dt_abertura)
        else:
            sp_tz = pytz.timezone('America/Sao_Paulo')
            dt_abertura = dt_abertura.astimezone(sp_tz)
        
        # Formato YYYY-MM-DDTHH:MM:SS
        data_abertura_str = dt_abertura.strftime('%Y-%m-%dT%H:%M:%S')
        
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
            
            cat_id = int(item.categoria_item or 1)
            tipo_ms = "M"
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
                
                "catalogoId": 1, 
                "catalogoCodigoItem": "15055", 
                "categoriaItemCatalogoId": 1
            }
            payload["itensCompra"].append(item_payload)

        # ------------------------------------------------------------------
        # 6. ENVIO
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
            "Tipo-Documento-Id": "1" 
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

class ImportacaoService:
    @staticmethod
    def processar_planilha_padrao(arquivo):
        raise NotImplementedError("Importação via planilha não implementada.")