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

logger = logging.getLogger(__name__)

class PNCPService:
    # URL de Treinamento (Padrão)
    BASE_URL = getattr(settings, 'PNCP_BASE_URL', 'https://treina.pncp.gov.br/api/pncp/v1')
    
    # SEU TOKEN (HARDCODED PARA TESTE - REMOVA EM PRODUÇÃO)
    ACCESS_TOKEN = "eyJhbGciOiJIUzUxMiJ9.eyJzdWIiOiI2ODJiYTE0YS1jMTJkLTRhOWYtOWMxOS1hNjYyNDIzMGMxMzkiLCJleHAiOjE3NjQxMDgzNzgsImFkbWluaXN0cmFkb3IiOmZhbHNlLCJjcGZDbnBqIjoiMTEwMzU1NDQwMDAxMDUiLCJlbWFpbCI6ImNvbnRhdG9fbGxAaG90bWFpbC5jb20iLCJnZXN0YW9lbnRlIjp0cnVlLCJpZEJhc2VEYWRvcyI6Mjg2NCwibm9tZSI6IkwgJiBMIEFTU0VTU09SSUEgQ09OU1VMVE9SSUEgRSBTRVJWScOHT1MgTFREQSJ9.z_WK_EbWuJrK9HFPQUMFa4IZLG-8IUfYjZzSHBey8WXHyHSnHAOIcrWCxXlBG39JICac2QV5B8qnCiF-tP_9NA"

    @staticmethod
    def _extrair_user_id_token(token):
        """Decodifica o JWT para pegar o ID do usuário."""
        try:
            if not token: return None
            parts = token.split('.')
            if len(parts) < 2: return None
            
            payload_b64 = parts[1]
            payload_b64 += '=' * ((4 - len(payload_b64) % 4) % 4)
            decoded = base64.urlsafe_b64decode(payload_b64)
            payload = json.loads(decoded)
            
            # Prioriza idBaseDados (igual ao seu script Python)
            return payload.get('idBaseDados') or payload.get('sub')
        except Exception as e:
            print(f"❌ [DEBUG] Erro ao decodificar token: {e}")
            return None

    @classmethod
    def _vincular_usuario_ao_orgao(cls, user_id, cnpj):
        """Vincula usuário ao órgão (Necessário no ambiente de Treina)."""
        if not user_id or not cnpj: return

        url = f"{cls.BASE_URL}/usuarios/{user_id}/orgaos"
        headers = {
            "Authorization": f"Bearer {cls.ACCESS_TOKEN}",
            "Content-Type": "application/json"
        }
        payload = {"entesAutorizados": [cnpj]}

        print(f"🔄 [DEBUG] Vinculando Usuário {user_id} ao Órgão {cnpj}...")
        try:
            requests.post(url, headers=headers, json=payload, verify=False, timeout=10)
            # Não bloqueia se der erro, pois pode já estar vinculado
        except Exception as e:
            print(f"⚠️ [DEBUG] Erro na vinculação (pode ser ignorado): {e}")

    @staticmethod
    def _handle_error_response(response):
        """Lê o erro do PNCP e exibe no console."""
        try:
            err_json = response.json()
            detail = err_json.get("message") or err_json.get("detail") or err_json.get("errors") or str(err_json)
        except:
            detail = response.text[:300]
        
        msg = f"PNCP Recusou ({response.status_code}): {detail}"
        print(f"❌ [ERRO PNCP] {msg}") 
        raise ValueError(msg)

    @classmethod
    def publicar_compra(cls, processo, arquivo: Any, titulo_documento: str) -> Dict[str, Any]:
        
        print("\n🚀 === INICIANDO PUBLICAÇÃO (COM DEBUG) ===")

        # 1. CNPJ e Token
        cnpj_orgao = re.sub(r'\D', '', processo.entidade.cnpj)
        user_id = cls._extrair_user_id_token(cls.ACCESS_TOKEN)
        
        if user_id:
            cls._vincular_usuario_ao_orgao(user_id, cnpj_orgao)
        else:
            print("⚠️ [DEBUG] ID do usuário não encontrado no token.")

        # 2. Datas (Ajuste Crítico para erro 400)
        # O PNCP exige: YYYY-MM-DDTHH:MM:SS (Sem fuso horário explícito na string)
        dt_abertura = processo.data_abertura or datetime.now()
        
        # Converte para Brasília se necessário, mas remove o offset da string final
        if not dt_abertura.tzinfo:
            sp_tz = pytz.timezone('America/Sao_Paulo')
            dt_abertura = sp_tz.localize(dt_abertura)
        
        # Formato exato que funcionou no seu script: "2025-10-01T14:30:01"
        data_abertura_str = dt_abertura.strftime('%Y-%m-%dT%H:%M:%S')
        
        # Encerramento (ex: +30 dias)
        dt_encerramento = dt_abertura + timedelta(days=30)
        data_encerramento_str = dt_encerramento.strftime('%Y-%m-%dT%H:%M:%S')

        # 3. Tratamento de IDs
        try:
            mod_id = int(processo.modalidade)
            disp_id = int(processo.modo_disputa)
            amp_id = int(processo.amparo_legal)
            inst_id = int(processo.instrumento_convocatorio or 1)
            crit_id = int(processo.criterio_julgamento or 1)
        except:
            raise ValueError("IDs de domínio (Modalidade, Amparo, etc) devem ser números inteiros.")

        # 4. Payload (JSON)
        # Número da compra apenas dígitos
        num_compra = re.sub(r'\D', '', str(processo.numero_certame).split('/')[0]) or "1"

        payload = {
            "codigoUnidadeCompradora": processo.orgao.codigo_unidade or "000000",
            "cnpjOrgao": cnpj_orgao,
            "anoCompra": int(processo.data_processo.year) if processo.data_processo else datetime.now().year,
            "numeroCompra": num_compra,
            "numeroProcesso": str(processo.numero_processo or processo.numero_certame),
            
            "tipoInstrumentoConvocatorioId": inst_id,
            "modalidadeId": mod_id,
            "modoDisputaId": disp_id,
            "amparoLegalId": amp_id,
            
            "srp": bool(processo.registro_preco),
            "objetoCompra": (processo.objeto or "Objeto")[:5000],
            "informacaoComplementar": "Integrado via API",
            
            # DATAS FORMATADAS CORRETAMENTE
            "dataAberturaProposta": data_abertura_str,
            "dataEncerramentoProposta": data_encerramento_str,
            
            "linkSistemaOrigem": "http://l3solution.net.br",
            "itensCompra": []
        }

        # Itens
        itens = processo.itens.all()
        if not itens.exists():
            raise ValueError("Adicione itens ao processo antes de publicar.")

        for idx, item in enumerate(itens, 1):
            cat_id = int(item.categoria_item or 1) # 1=Bens Imóveis (cuidado), 2=Bens Móveis, etc. 
            # Ajuste fino: Geralmente Bens Móveis é 2 ou 1 dependendo do ambiente, validar no choices.
            
            # Lógica Material (M) vs Serviço (S)
            tipo_ms = "M"
            # IDs comuns de serviço: 4 (Serviços), 9 (Engenharia) - Ajuste conforme seu choices.py
            if cat_id in [4, 8, 9]: 
                tipo_ms = "S"

            payload["itensCompra"].append({
                "numeroItem": item.ordem or idx,
                "materialOuServico": tipo_ms,
                "tipoBeneficioId": int(item.tipo_beneficio or 1),
                "incentivoProdutivoBasico": False,
                "descricao": (item.descricao or "Item")[:255],
                "quantidade": float(item.quantidade or 1),
                "unidadeMedida": (item.unidade or "UN")[:20],
                "valorUnitarioEstimado": float(item.valor_estimado or 0),
                "valorTotal": float((item.valor_estimado or 0) * (item.quantidade or 1)),
                "criterioJulgamentoId": crit_id,
                "itemCategoriaId": cat_id,
                "catalogoId": 1, 
                "catalogoCodigoItem": "15055", 
                "categoriaItemCatalogoId": 1
            })

        # === AQUI ESTÁ O DEBUG QUE VOCÊ PEDIU ===
        print("\n📝 [DEBUG] PAYLOAD GERADO (Copie e valide se necessário):")
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        print("----------------------------------------------------------\n")

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
            "Tipo-Documento-Id": "1"
        }

        try:
            print(f"📡 [DEBUG] Enviando POST para: {url}")
            response = requests.post(url, headers=headers, files=files, verify=False, timeout=60)
            
            print(f"🔙 [DEBUG] Status Code: {response.status_code}")
            
            if response.status_code in [200, 201]:
                print("✅ [DEBUG] SUCESSO! Retorno do PNCP:")
                print(response.json())
                return response.json()
            else:
                cls._handle_error_response(response)

        except Exception as e:
            print(f"❌ [DEBUG] Erro Fatal de Conexão: {e}")
            raise ValueError(f"Erro: {str(e)}")

class ImportacaoService:
    @staticmethod
    def processar_planilha_padrao(arquivo):
        raise NotImplementedError("Importação não implementada.")