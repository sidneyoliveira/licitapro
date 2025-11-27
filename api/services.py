# api/services.py

import logging
import json
import re
import requests
import base64
import sys
import time # Adicionado para delay de segurança
import pytz
from datetime import datetime, timedelta
from typing import Dict, Any
from decimal import Decimal
from django.core.files.base import File

# Força logs no console (stderr) para aparecer no journalctl
def log_console(msg):
    sys.stderr.write(f"[PNCP] {msg}\n")
    sys.stderr.flush()

class PNCPService:
    # --- CONFIGURAÇÕES HARDCODED (IGNORANDO .ENV PARA TESTE) ---
    BASE_URL = "https://treina.pncp.gov.br/api/pncp/v1"
    
    # SEU TOKEN DE TREINAMENTO
    ACCESS_TOKEN = "eyJhbGciOiJIUzUxMiJ9.eyJzdWIiOiI2ODJiYTE0YS1jMTJkLTRhOWYtOWMxOS1hNjYyNDIzMGMxMzkiLCJleHAiOjE3NjQyNTE5MTAsImFkbWluaXN0cmFkb3IiOmZhbHNlLCJjcGZDbnBqIjoiMTEwMzU1NDQwMDAxMDUiLCJlbWFpbCI6ImNvbnRhdG9fbGxAaG90bWFpbC5jb20iLCJnZXN0YW9lbnRlIjp0cnVlLCJpZEJhc2VEYWRvcyI6Mjg2NCwibm9tZSI6IkwgJiBMIEFTU0VTU09SSUEgQ09OU1VMVE9SSUEgRSBTRVJWScOHT1MgTFREQSJ9.M4re0rPu7PmbN2F10Yz5QM-C568Zp62p7a62JopOheJXGeIx4_HQFMYHHJ7-UNSbsRQmZVoLKW05-whXVgsMvA"

    @staticmethod
    def _extrair_user_id_token(token):
        try:
            if not token: return None
            parts = token.split('.')
            if len(parts) < 2: return None
            
            payload_b64 = parts[1]
            payload_b64 += '=' * ((4 - len(payload_b64) % 4) % 4)
            decoded = base64.urlsafe_b64decode(payload_b64)
            payload = json.loads(decoded)
            
            return payload.get('idBaseDados') or payload.get('sub')
        except Exception as e:
            log_console(f"Erro decode token: {e}")
            return None

    @classmethod
    def _vincular_usuario_ao_orgao(cls, user_id, cnpj):
        """
        Garante permissão de escrita (Manual 6.1.5).
        """
        url = f"{cls.BASE_URL}/usuarios/{user_id}/orgaos"
        
        headers = {
            "Authorization": f"Bearer {cls.ACCESS_TOKEN}",
            "Content-Type": "application/json",
            "accept": "*/*"
        }
        
        payload = {"entesAutorizados": [cnpj]}

        try:
            log_console(f"Vinculando User {user_id} ao CNPJ {cnpj} na URL {url}...")
            response = requests.post(url, headers=headers, json=payload, verify=False, timeout=15)
            
            if response.status_code in [200, 201]:
                log_console("✅ Vinculação OK.")
            else:
                log_console(f"⚠️ Aviso Vinculação: {response.status_code} - {response.text}")
                
        except Exception as e:
            log_console(f"❌ Erro Conexão Vinculação: {e}")

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
        log_console(f"❌ ERRO FINAL: {msg}")
        raise ValueError(msg)

    @classmethod
    def publicar_compra(cls, processo, arquivo: Any, titulo_documento: str) -> Dict[str, Any]:
        log_console(">>> INICIANDO PUBLICAÇÃO")

        # 1. Preparação
        cnpj_orgao = re.sub(r'\D', '', processo.entidade.cnpj)
        user_id = cls._extrair_user_id_token(cls.ACCESS_TOKEN)
        
        if user_id:
            cls._vincular_usuario_ao_orgao(user_id, cnpj_orgao)
            # Pequena pausa para garantir que o PNCP processe a permissão
            time.sleep(1)
        else:
            log_console("ALERTA: User ID não encontrado no token.")

        # Validações
        if not processo.numero_certame: raise ValueError("Número do Certame obrigatório")
        if not processo.itens.exists(): raise ValueError("Itens obrigatórios")

        # 2. Dados Gerais
        ano_compra = int(processo.data_processo.year) if processo.data_processo else datetime.now().year
        codigo_unidade = processo.orgao.codigo_unidade or "000000"

        # 3. Datas (Formato Estrito: YYYY-MM-DDTHH:MM:SS)
        dt_abertura = processo.data_abertura or datetime.now()
        
        # Garante Timezone Brasília
        sp_tz = pytz.timezone('America/Sao_Paulo')
        if not dt_abertura.tzinfo:
            dt_abertura = sp_tz.localize(dt_abertura)
        else:
            dt_abertura = dt_abertura.astimezone(sp_tz)
        
        data_abertura_str = dt_abertura.strftime('%Y-%m-%dT%H:%M:%S')
        data_encerramento_str = (dt_abertura + timedelta(days=30)).strftime('%Y-%m-%dT%H:%M:%S')

        # 4. Payload
        raw_numero = str(processo.numero_certame).split('/')[0]
        numero_compra_clean = re.sub(r'\D', '', raw_numero) or "1"

        try:
            # Conversão segura de IDs
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
            "informacaoComplementar": "Integrado via API",
            
            "dataAberturaProposta": data_abertura_str,
            "dataEncerramentoProposta": data_encerramento_str,
            
            "linkSistemaOrigem": "http://l3solution.net.br",
            "itensCompra": []
        }

        # Itens
        for idx, item in enumerate(processo.itens.all(), 1):
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

        # Debug Payload
        log_console(f"Payload (Amostra): {json.dumps(payload)[:200]}...")

        # 5. Envio
        if hasattr(arquivo, 'seek'): arquivo.seek(0)
        
        files = {
            'documento': ('edital.pdf', arquivo, 'application/pdf'),
            'compra': (None, json.dumps(payload), 'application/json')
        }

        url = f"{cls.BASE_URL}/orgaos/{cnpj_orgao}/compras"
        headers = {
            "Authorization": f"Bearer {cls.ACCESS_TOKEN}",
            "Titulo-Documento": titulo_documento,
            "Tipo-Documento-Id": "1",
            "accept": "*/*" # Adicionado conforme script
        }

        try:
            log_console(f"Enviando POST para: {url}")
            response = requests.post(url, headers=headers, files=files, verify=False, timeout=90)
            
            log_console(f"Status Code: {response.status_code}")
            
            if response.status_code in [200, 201]:
                return response.json()
            else:
                cls._handle_error_response(response)

        except Exception as e:
            log_console(f"Exception Fatal: {e}")
            raise ValueError(f"Erro: {str(e)}")

class ImportacaoService:
    @staticmethod
    def processar_planilha_padrao(arquivo):
        raise NotImplementedError("Importação não implementada.")