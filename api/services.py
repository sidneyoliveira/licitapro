# api/services.py

import logging
import json
import re
import requests
import base64
import sys
import pytz
from datetime import datetime, timedelta
from typing import Dict, Any
from django.conf import settings
from decimal import Decimal

# Logger forçando saída no console
def log_debug(msg):
    sys.stderr.write(f"[PNCP DEBUG] {msg}\n")
    sys.stderr.flush()

class PNCPService:
    # --- CONFIGURAÇÃO FORÇADA PARA TREINA (IGUAL AO SEU SCRIPT) ---
    BASE_URL = "https://treina.pncp.gov.br/api/pncp/v1"
    
    # SEU TOKEN DE TESTE (Decodificado: ID 2864)
    ACCESS_TOKEN = "eyJhbGciOiJIUzUxMiJ9.eyJzdWIiOiI2ODJiYTE0YS1jMTJkLTRhOWYtOWMxOS1hNjYyNDIzMGMxMzkiLCJleHAiOjE3NjQxMDgzNzgsImFkbWluaXN0cmFkb3IiOmZhbHNlLCJjcGZDbnBqIjoiMTEwMzU1NDQwMDAxMDUiLCJlbWFpbCI6ImNvbnRhdG9fbGxAaG90bWFpbC5jb20iLCJnZXN0YW9lbnRlIjp0cnVlLCJpZEJhc2VEYWRvcyI6Mjg2NCwibm9tZSI6IkwgJiBMIEFTU0VTU09SSUEgQ09OU1VMVE9SSUEgRSBTRVJWScOHT1MgTFREQSJ9.z_WK_EbWuJrK9HFPQUMFa4IZLG-8IUfYjZzSHBey8WXHyHSnHAOIcrWCxXlBG39JICac2QV5B8qnCiF-tP_9NA"

    @staticmethod
    def _extrair_user_id_token(token):
        """
        Extrai o ID do usuário. No seu token, o ID correto é 'idBaseDados' (2864).
        """
        try:
            if not token: return None
            parts = token.split('.')
            if len(parts) < 2: return None
            
            payload_b64 = parts[1]
            payload_b64 += '=' * ((4 - len(payload_b64) % 4) % 4)
            
            # Usa urlsafe para garantir compatibilidade
            decoded_bytes = base64.urlsafe_b64decode(payload_b64)
            payload = json.loads(decoded_bytes)
            
            # Prioridade para idBaseDados conforme seu script
            user_id = payload.get('idBaseDados') or payload.get('sub')
            log_debug(f"ID Usuário Extraído: {user_id}")
            return user_id
        except Exception as e:
            log_debug(f"Erro decode token: {e}")
            return None

    @classmethod
    def _vincular_usuario_ao_orgao(cls, user_id, cnpj):
        """
        Garante permissão de escrita no órgão (Manual 6.1.5).
        """
        if not user_id or not cnpj:
            log_debug("Dados insuficientes para vinculação.")
            return

        url = f"{cls.BASE_URL}/usuarios/{user_id}/orgaos"
        
        # Headers idênticos ao script
        headers = {
            "Authorization": f"Bearer {cls.ACCESS_TOKEN}",
            "Content-Type": "application/json",
            "accept": "*/*"
        }
        
        # Payload idêntico ao script
        payload = {
            "entesAutorizados": [cnpj]
        }

        try:
            log_debug(f"Tentando vincular User {user_id} ao Orgao {cnpj}...")
            log_debug(f"URL Vinculação: {url}")
            
            response = requests.post(url, headers=headers, json=payload, verify=False, timeout=15)
            
            if response.status_code in [200, 201]:
                log_debug("✅ Vinculação realizada com SUCESSO.")
            else:
                log_debug(f"⚠️ Aviso vinculação: {response.status_code} - {response.text}")
                
        except Exception as e:
            log_debug(f"❌ Erro de conexão na vinculação: {e}")

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
        log_debug(f"❌ {msg}")
        raise ValueError(msg)

    @classmethod
    def publicar_compra(cls, processo, arquivo: Any, titulo_documento: str) -> Dict[str, Any]:
        log_debug(">>> INICIANDO PUBLICAÇÃO (AMBIENTE TREINA)")

        if not cls.ACCESS_TOKEN:
            raise ValueError("Token não configurado.")

        # 1. Preparação
        cnpj_orgao = re.sub(r'\D', '', processo.entidade.cnpj)
        log_debug(f"CNPJ Alvo: {cnpj_orgao}")

        # VINCULAÇÃO (CRUCIAL)
        user_id = cls._extrair_user_id_token(cls.ACCESS_TOKEN)
        if user_id:
            cls._vincular_usuario_ao_orgao(user_id, cnpj_orgao)
        else:
            log_debug("ALERTA: Não foi possível obter ID do usuário.")

        # Validações
        erros = []
        if not processo.numero_certame: erros.append("Número do Certame obrigatório")
        if not processo.modalidade: erros.append("Modalidade obrigatória")
        if not processo.itens.exists(): erros.append("Itens obrigatórios")
        
        if erros:
            raise ValueError(" | ".join(erros))

        # 2. Dados Gerais
        if processo.data_processo:
            ano_compra = int(processo.data_processo.year)
        else:
            ano_compra = datetime.now().year

        codigo_unidade = processo.orgao.codigo_unidade or "000000"

        # 3. Datas (Formato Estrito: YYYY-MM-DDTHH:MM:SS sem offset)
        dt_abertura = processo.data_abertura or datetime.now()
        
        # Garante Timezone Brasília
        sp_tz = pytz.timezone('America/Sao_Paulo')
        if not dt_abertura.tzinfo:
            dt_abertura = sp_tz.localize(dt_abertura)
        else:
            dt_abertura = dt_abertura.astimezone(sp_tz)
        
        # Remove fuso para string limpa
        data_abertura_str = dt_abertura.strftime('%Y-%m-%dT%H:%M:%S')
        
        dt_encerr = dt_abertura + timedelta(days=30)
        data_encerramento_str = dt_encerr.strftime('%Y-%m-%dT%H:%M:%S')

        # 4. Payload
        raw_numero = str(processo.numero_certame).split('/')[0]
        numero_compra_clean = re.sub(r'\D', '', raw_numero) or "1"

        try:
            # Garante inteiros
            inst_id = int(processo.instrumento_convocatorio or 1)
            mod_id = int(processo.modalidade)
            disp_id = int(processo.modo_disputa)
            amp_id = int(processo.amparo_legal)
        except:
            raise ValueError("IDs de domínio inválidos.")

        payload = {
            "codigoUnidadeCompradora": codigo_unidade,
            "cnpjOrgao": cnpj_orgao,
            "anoCompra": ano_compra,
            "numeroCompra": numero_compra_clean,
            "numeroProcesso": str(processo.numero_processo or processo.numero_certame),
            "tipoInstrumentoConvocatorioId": inst_id,
            "modalidadeId": mod_id,
            "modoDisputaId": disp_id,
            "amparoLegalId": amp_id,
            "srp": bool(processo.registro_preco),
            "objetoCompra": (processo.objeto or "Objeto")[:5000],
            "informacaoComplementar": "Integrado via Licitapro",
            "dataAberturaProposta": data_abertura_str,
            "dataEncerramentoProposta": data_encerramento_str,
            "linkSistemaOrigem": "http://l3solution.net.br",
            "itensCompra": []
        }

        # Itens
        for idx, item in enumerate(processo.itens.all(), 1):
            # Lógica M/S
            cat_id = int(item.categoria_item or 1)
            tipo_ms = "M"
            if cat_id in [2, 4, 8, 9]: tipo_ms = "S"

            payload["itensCompra"].append({
                "numeroItem": item.ordem or idx,
                "materialOuServico": tipo_ms,
                "tipoBeneficioId": int(item.tipo_beneficio or 1),
                "incentivoProdutivoBasico": False,
                "descricao": (item.descricao or "Item")[:255],
                "quantidade": float(item.quantidade or 1),
                "unidadeMedida": (item.unidade or "UN")[:20],
                "valorUnitarioEstimado": float(item.valor_estimado or 0),
                "valorTotal": round(float((item.valor_estimado or 0) * (item.quantidade or 1)), 4),
                "criterioJulgamentoId": int(processo.criterio_julgamento or 1),
                "itemCategoriaId": cat_id,
                "catalogoId": 1, 
                "catalogoCodigoItem": "15055", 
                "categoriaItemCatalogoId": 1
            })

        log_debug("Payload Gerado com Sucesso.")

        # 5. Envio
        if hasattr(arquivo, 'seek'): arquivo.seek(0)
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
            log_debug(f"Enviando para {url}...")
            response = requests.post(url, headers=headers, files=files, verify=False, timeout=90)
            log_debug(f"Status: {response.status_code}")
            
            if response.status_code in [200, 201]:
                log_debug("✅ SUCESSO!")
                return response.json()
            else:
                cls._handle_error_response(response)

        except Exception as e:
            log_debug(f"Exception fatal: {e}")
            raise ValueError(str(e))

class ImportacaoService:
    @staticmethod
    def processar_planilha_padrao(arquivo):
        raise NotImplementedError("Importação não implementada.")