# api/services.py

import json
import re
import requests
import base64
import sys  # <--- Importante para logs
import pytz
from datetime import datetime, timedelta
from typing import Dict, Any
from django.conf import settings
from decimal import Decimal

# Não vamos depender só do logger, vamos forçar a saída no erro padrão
def log_debug(msg):
    sys.stderr.write(f"\n[PNCP DEBUG] {msg}\n")
    sys.stderr.flush()

class PNCPService:
    BASE_URL = getattr(settings, 'PNCP_BASE_URL', 'https://treina.pncp.gov.br/api/pncp/v1')
    
    # SEU TOKEN (MANTIDO HARDCODED PARA TESTE)
    ACCESS_TOKEN = "eyJhbGciOiJIUzUxMiJ9.eyJzdWIiOiI2ODJiYTE0YS1jMTJkLTRhOWYtOWMxOS1hNjYyNDIzMGMxMzkiLCJleHAiOjE3NjQxMDgzNzgsImFkbWluaXN0cmFkb3IiOmZhbHNlLCJjcGZDbnBqIjoiMTEwMzU1NDQwMDAxMDUiLCJlbWFpbCI6ImNvbnRhdG9fbGxAaG90bWFpbC5jb20iLCJnZXN0YW9lbnRlIjp0cnVlLCJpZEJhc2VEYWRvcyI6Mjg2NCwibm9tZSI6IkwgJiBMIEFTU0VTU09SSUEgQ09OU1VMVE9SSUEgRSBTRVJWScOHT1MgTFREQSJ9.z_WK_EbWuJrK9HFPQUMFa4IZLG-8IUfYjZzSHBey8WXHyHSnHAOIcrWCxXlBG39JICac2QV5B8qnCiF-tP_9NA"

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
            log_debug(f"Erro decode token: {e}")
            return None

    @classmethod
    def _vincular_usuario_ao_orgao(cls, user_id, cnpj):
        if not user_id or not cnpj: return
        url = f"{cls.BASE_URL}/usuarios/{user_id}/orgaos"
        headers = {"Authorization": f"Bearer {cls.ACCESS_TOKEN}", "Content-Type": "application/json"}
        try:
            log_debug(f"Vinculando User {user_id} ao CNPJ {cnpj}...")
            requests.post(url, headers=headers, json={"entesAutorizados": [cnpj]}, verify=False, timeout=5)
        except Exception as e:
            log_debug(f"Erro vinculação (ignorado): {e}")

    @classmethod
    def publicar_compra(cls, processo, arquivo: Any, titulo_documento: str) -> Dict[str, Any]:
        log_debug(">>> INICIANDO PUBLICACAO")

        if not cls.ACCESS_TOKEN:
            raise ValueError("Token não configurado.")

        # 1. Preparação
        cnpj_orgao = re.sub(r'\D', '', processo.entidade.cnpj)
        user_id = cls._extrair_user_id_token(cls.ACCESS_TOKEN)
        if user_id: cls._vincular_usuario_ao_orgao(user_id, cnpj_orgao)

        # 2. Datas (Ajuste para formato YYYY-MM-DDTHH:MM:SS sem offset)
        dt_abertura = processo.data_abertura or datetime.now()
        
        # Converte para Brasil
        sp_tz = pytz.timezone('America/Sao_Paulo')
        if not dt_abertura.tzinfo:
            dt_abertura = sp_tz.localize(dt_abertura)
        else:
            dt_abertura = dt_abertura.astimezone(sp_tz)
        
        # Remove a informação de timezone para ficar "naive" (local puro)
        # Isso garante que o .isoformat() NÃO adicione -03:00 no final
        dt_local = dt_abertura.replace(tzinfo=None)
        
        # Formata explicitamente
        data_abertura_str = dt_local.isoformat(timespec='seconds') 
        # Ex: "2025-11-27T12:30:00"
        
        dt_encerr = dt_local + timedelta(days=30)
        data_encerramento_str = dt_encerr.isoformat(timespec='seconds')

        log_debug(f"Data Formatada: {data_abertura_str}")

        # 3. Payload
        raw_numero = str(processo.numero_certame).split('/')[0]
        numero_compra_clean = re.sub(r'\D', '', raw_numero) or "1"

        try:
            inst_id = int(processo.instrumento_convocatorio or 1)
            mod_id = int(processo.modalidade)
            disp_id = int(processo.modo_disputa)
            amp_id = int(processo.amparo_legal)
        except:
            raise ValueError("IDs de domínio inválidos (não são números).")

        payload = {
            "codigoUnidadeCompradora": processo.orgao.codigo_unidade or "000000",
            "cnpjOrgao": cnpj_orgao,
            "anoCompra": int(processo.data_processo.year) if processo.data_processo else datetime.now().year,
            "numeroCompra": numero_compra_clean,
            "numeroProcesso": str(processo.numero_processo or processo.numero_certame),
            "tipoInstrumentoConvocatorioId": inst_id,
            "modalidadeId": mod_id,
            "modoDisputaId": disp_id,
            "amparoLegalId": amp_id,
            "srp": bool(processo.registro_preco),
            "objetoCompra": (processo.objeto or "Objeto")[:5000],
            "informacaoComplementar": "Integrado via API",
            "dataAberturaProposta": data_abertura_str,       # <--- Verifique no log
            "dataEncerramentoProposta": data_encerramento_str,
            "linkSistemaOrigem": "http://l3solution.net.br",
            "itensCompra": []
        }

        # Itens
        itens = processo.itens.all()
        if not itens.exists(): raise ValueError("Adicione itens ao processo.")

        for idx, item in enumerate(itens, 1):
            cat_id = int(item.categoria_item or 1)
            tipo_ms = "M"
            if cat_id in [2, 4, 6, 8, 9]: tipo_ms = "S"

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

        # --- PRINT DO JSON NO TERMINAL ---
        log_debug("PAYLOAD JSON:")
        log_debug(json.dumps(payload, indent=2, ensure_ascii=False))
        # ---------------------------------

        # 4. Envio
        if hasattr(arquivo, 'seek'): arquivo.seek(0)
        
        files = {
            'documento': (getattr(arquivo, 'name', 'edital.pdf'), arquivo, 'application/pdf'),
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
            response = requests.post(url, headers=headers, files=files, verify=False, timeout=60)
            log_debug(f"Status: {response.status_code}")
            
            if response.status_code in [200, 201]:
                log_debug("SUCESSO!")
                return response.json()
            else:
                # Pega erro detalhado
                try:
                    resp_json = response.json()
                    log_debug(f"Erro JSON: {resp_json}")
                    msg = f"PNCP Recusou ({response.status_code}): {resp_json}"
                except:
                    msg = f"PNCP Recusou ({response.status_code}): {response.text[:200]}"
                    log_debug(f"Erro Texto: {response.text[:200]}")
                
                raise ValueError(msg)

        except Exception as e:
            log_debug(f"Exception fatal: {e}")
            raise ValueError(str(e))

class ImportacaoService:
    @staticmethod
    def processar_planilha_padrao(arquivo):
        raise NotImplementedError("Importação não implementada.")