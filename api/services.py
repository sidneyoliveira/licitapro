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
    
    # --- TOKEN HARDCODED PARA TESTE (COMO SOLICITADO) ---
    # Substitua pelo token real quando for para produção
    ACCESS_TOKEN = "eyJhbGciOiJIUzUxMiJ9.eyJzdWIiOiI2ODJiYTE0YS1jMTJkLTRhOWYtOWMxOS1hNjYyNDIzMGMxMzkiLCJleHAiOjE3NjQxMDgzNzgsImFkbWluaXN0cmFkb3IiOmZhbHNlLCJjcGZDbnBqIjoiMTEwMzU1NDQwMDAxMDUiLCJlbWFpbCI6ImNvbnRhdG9fbGxAaG90bWFpbC5jb20iLCJnZXN0YW9lbnRlIjp0cnVlLCJpZEJhc2VEYWRvcyI6Mjg2NCwibm9tZSI6IkwgJiBMIEFTU0VTU09SSUEgQ09OU1VMVE9SSUEgRSBTRVJWScOHT1MgTFREQSJ9.z_WK_EbWuJrK9HFPQUMFa4IZLG-8IUfYjZzSHBey8WXHyHSnHAOIcrWCxXlBG39JICac2QV5B8qnCiF-tP_9NA"

    @staticmethod
    def _extrair_user_id_token(token):
        """Extrai o ID do usuário (idBaseDados) do JWT."""
        try:
            if not token: return None
            parts = token.split('.')
            if len(parts) < 2: return None
            
            payload_b64 = parts[1]
            payload_b64 += '=' * (-len(payload_b64) % 4)
            payload_json = base64.b64decode(payload_b64).decode('utf-8')
            payload = json.loads(payload_json)
            
            # Prioriza idBaseDados conforme seu script de teste que funcionou
            return payload.get('idBaseDados') or payload.get('sub') or payload.get('user_id')
        except Exception as e:
            logger.error(f"Erro ao decodificar JWT: {e}")
            return None

    @classmethod
    def _vincular_usuario_ao_orgao(cls, user_id, cnpj):
        """
        Vincula o usuário ao órgão (Manual 6.1.5).
        """
        if not user_id or not cnpj:
            return

        # Endpoint correto de vinculação de usuário
        url = f"{cls.BASE_URL}/usuarios/{user_id}/orgaos"
        headers = {
            "Authorization": f"Bearer {cls.ACCESS_TOKEN}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "entesAutorizados": [cnpj]
        }

        try:
            logger.info(f"[PNCP] Vinculando Usuario {user_id} ao Orgao {cnpj}...")
            response = requests.post(url, headers=headers, json=payload, verify=False, timeout=10)
            
            if response.status_code in [200, 201]:
                logger.info("[PNCP] Vinculação SUCESSO.")
            else:
                # Log de aviso, pois pode já estar vinculado
                logger.warning(f"[PNCP] Aviso vinculação: {response.status_code} - {response.text}")
                
        except Exception as e:
            logger.error(f"[PNCP] Erro de conexão na vinculação: {e}")

    @staticmethod
    def _handle_error_response(response):
        """
        Trata erros da API e loga o corpo da resposta para debug.
        """
        try:
            err_json = response.json()
            detail = err_json.get("message") or err_json.get("detail") or err_json.get("errors") or str(err_json)
            if isinstance(detail, list):
                detail = " | ".join([str(e) for e in detail])
        except:
            detail = response.text[:500] # Pega os primeiros 500 chars do erro
        
        msg = f"PNCP Recusou ({response.status_code}): {detail}"
        logger.error(f"[PNCP ERROR] {msg}") # Log no terminal
        raise ValueError(msg)

    @classmethod
    def publicar_compra(cls, processo, arquivo: Any, titulo_documento: str) -> Dict[str, Any]:
        """
        Executa o fluxo completo de publicação.
        """
        
        if not cls.ACCESS_TOKEN:
            raise ValueError("Token de Acesso PNCP não configurado.")

        # 1. PREPARAÇÃO
        cnpj_orgao = re.sub(r'\D', '', processo.entidade.cnpj)
        
        # Tenta vincular (igual ao seu script Python que funcionou)
        try:
            user_id = cls._extrair_user_id_token(cls.ACCESS_TOKEN)
            if user_id:
                cls._vincular_usuario_ao_orgao(user_id, cnpj_orgao)
        except Exception:
            pass

        # Validações básicas
        erros = []
        if not processo.numero_certame: erros.append("Número do Certame obrigatório")
        if not processo.modalidade: erros.append("Modalidade obrigatória")
        
        itens = processo.itens.all()
        if not itens.exists(): erros.append("Pelo menos um Item é obrigatório")
        
        if erros:
            raise ValueError(" | ".join(erros))

        # 2. DADOS GERAIS
        if processo.data_processo:
            ano_compra = int(processo.data_processo.year)
        else:
            ano_compra = datetime.now().year

        codigo_unidade = "000000"
        if processo.orgao and processo.orgao.codigo_unidade:
            codigo_unidade = processo.orgao.codigo_unidade

        # ------------------------------------------------------------------
        # [cite_start]3. DATAS (CORREÇÃO DEFINITIVA) [cite: 1397, 1398]
        # ------------------------------------------------------------------
        dt_abertura = processo.data_abertura
        if not dt_abertura:
             dt_abertura = datetime.now()

        # Garante Fuso Horário de Brasília (America/Sao_Paulo)
        sp_tz = pytz.timezone('America/Sao_Paulo')
        
        if not dt_abertura.tzinfo:
            # Se a data do banco vier sem fuso (naive), assume que é Brasília
            dt_abertura = sp_tz.localize(dt_abertura)
        else:
            # Se já tiver fuso, converte para Brasília
            dt_abertura = dt_abertura.astimezone(sp_tz)
        
        # O PNCP espera o formato YYYY-MM-DDTHH:MM:SS (Sem o offset -03:00 no final da string)
        # Exemplo do manual: "2022-07-21T08:00:00"
        data_abertura_str = dt_abertura.strftime('%Y-%m-%dT%H:%M:%S')
        
        # Data de Encerramento (Opcional para algumas modalidades, mas bom enviar)
        # Adiciona 1 hora por padrão se não tiver lógica específica
        dt_encerramento = dt_abertura + timedelta(minutes=60)
        data_encerramento_str = dt_encerramento.strftime('%Y-%m-%dT%H:%M:%S')

        # ------------------------------------------------------------------
        # 4. PAYLOAD
        # ------------------------------------------------------------------
        # Limpa numero da compra (apenas digitos)
        raw_numero = str(processo.numero_certame).split('/')[0]
        numero_compra_clean = re.sub(r'\D', '', raw_numero)
        if not numero_compra_clean: numero_compra_clean = "1"
        
        # Converte IDs para int para evitar erro de tipo
        try:
            modalidade_id = int(processo.modalidade)
            modo_disputa_id = int(processo.modo_disputa)
            amparo_id = int(processo.amparo_legal)
            inst_id = int(processo.instrumento_convocatorio or 1)
        except (ValueError, TypeError):
            raise ValueError("IDs de Modalidade/Disputa/Amparo devem ser numéricos.")

        payload = {
            "codigoUnidadeCompradora": codigo_unidade,
            "cnpjOrgao": cnpj_orgao,
            "anoCompra": ano_compra,
            "numeroCompra": numero_compra_clean,
            "numeroProcesso": str(processo.numero_processo or processo.numero_certame),
            
            "tipoInstrumentoConvocatorioId": inst_id,
            "modalidadeId": modalidade_id,
            "modoDisputaId": modo_disputa_id,
            "amparoLegalId": amparo_id,
            
            "srp": bool(processo.registro_preco),
            "objetoCompra": (processo.objeto or "Objeto não informado")[:5000],
            "informacaoComplementar": "Integrado via Licitapro",
            
            # DATAS SEM OFFSET
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
            
            # Lógica simples M/S baseada na categoria
            cat_id = int(item.categoria_item or 1)
            tipo_ms = "M"
            if cat_id in [2, 4, 6, 8, 9]: tipo_ms = "S"

            item_payload = {
                "numeroItem": item.ordem or idx,
                "materialOuServico": tipo_ms,
                "tipoBeneficioId": int(item.tipo_beneficio or 1),
                "incentivoProdutivoBasico": False,
                "descricao": (item.descricao or "Item")[:255],
                "quantidade": qtd,
                "unidadeMedida": (item.unidade or "UN")[:20],
                "valorUnitarioEstimado": vl_unitario,
                "valorTotal": vl_total,
                "criterioJulgamentoId": int(processo.criterio_julgamento or 1),
                "itemCategoriaId": cat_id,
                # Valores Padrão de Catálogo (Para evitar erro 400 se faltar)
                "catalogoId": 1, 
                "catalogoCodigoItem": "15055", 
                "categoriaItemCatalogoId": 1
            }
            payload["itensCompra"].append(item_payload)

        # ------------------------------------------------------------------
        # DEBUG LOGGING (MECANISMO DE IDENTIFICAÇÃO DE ERRO)
        # ------------------------------------------------------------------
        logger.info("=== PAYLOAD SENDO ENVIADO AO PNCP ===")
        logger.info(json.dumps(payload, indent=2, ensure_ascii=False))
        logger.info("=====================================")

        # ------------------------------------------------------------------
        # 5. ENVIO
        # ------------------------------------------------------------------
        if hasattr(arquivo, 'seek'):
            arquivo.seek(0)

        filename = getattr(arquivo, 'name', 'edital.pdf')
        
        # Atenção: O JSON deve ir como 'compra' com content-type application/json
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
            logger.info(f"Enviando POST para: {url}")
            # Timeout alto para upload
            response = requests.post(url, headers=headers, files=files, verify=False, timeout=90)
            
            logger.info(f"Status Code PNCP: {response.status_code}")
            
            if response.status_code in [200, 201]:
                return response.json()
            else:
                cls._handle_error_response(response)

        except requests.exceptions.RequestException as e:
            logger.error(f"Erro Conexão: {e}")
            raise ValueError(f"Falha de comunicação: {str(e)}")

class ImportacaoService:
    @staticmethod
    def processar_planilha_padrao(arquivo):
        raise NotImplementedError("Importação não implementada.")