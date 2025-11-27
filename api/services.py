# api/services.py

import json
import re
import requests
import base64
import sys
import time
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from decimal import Decimal
from django.conf import settings
import pytz
# Configuração de Logs
logger = logging.getLogger("api")

class PNCPService:
    """
    Serviço para integração com o Portal Nacional de Contratações Públicas (PNCP).
    Documentação: https://pncp.gov.br/
    """
    
    # Configurações de Ambiente
    # Prioriza URL de Treinamento para evitar acidentes em Produção durante desenvolvimento
    BASE_URL = getattr(settings, 'PNCP_BASE_URL', "https://treina.pncp.gov.br/api/pncp/v1")
    
    # Credenciais (Via .env)
    # USERNAME = getattr(settings, 'PNCP_USERNAME', '')
    # PASSWORD = getattr(settings, 'PNCP_PASSWORD', '')

    USERNAME = '682ba14a-c12d-4a9f-9c19-a6624230c139'
    PASSWORD = 'mqBM3Ju6ZtiP45jg'
    
    # Token de Fallback (Apenas para desenvolvimento/testes rápidos)
    # _FALLBACK_TOKEN = "eyJhbGciOiJIUzUxMiJ9.eyJzdWIiOiI2ODJiYTE0YS1jMTJkLTRhOWYtOWMxOS1hNjYyNDIzMGMxMzkiLCJleHAiOjE3NjQxMDgzNzgsImFkbWluaXN0cmFkb3IiOmZhbHNlLCJjcGZDbnBqIjoiMTEwMzU1NDQwMDAxMDUiLCJlbWFpbCI6ImNvbnRhdG9fbGxAaG90bWFpbC5jb20iLCJnZXN0YW9lbnRlIjp0cnVlLCJpZEJhc2VEYWRvcyI6Mjg2NCwibm9tZSI6IkwgJiBMIEFTU0VTU09SSUEgQ09OU1VMVE9SSUEgRSBTRVJWScOHT1MgTFREQSJ9.z_WK_EbWuJrK9HFPQUMFa4IZLG-8IUfYjZzSHBey8WXHyHSnHAOIcrWCxXlBG39JICac2QV5B8qnCiF-tP_9NA"

    @classmethod
    def _log(cls, msg: str, level: str = "info"):
        """Helper para garantir saída no console do servidor (Gunicorn/Docker)."""
        formatted_msg = f"[PNCP] {msg}"
        if level == "error":
            sys.stderr.write(f"❌ {formatted_msg}\n")
        else:
            sys.stderr.write(f"ℹ️ {formatted_msg}\n")
        sys.stderr.flush()

    @classmethod
    def _get_token(cls) -> str:
        """
        Obtém um token válido. 
        1. Tenta login com usuário/senha do .env.
        2. Se falhar ou não existir, usa o token de fallback.
        """
        if cls.USERNAME and cls.PASSWORD:
            try:
                url = f"{cls.BASE_URL}/usuarios/login"
                payload = {"login": cls.USERNAME, "senha": cls.PASSWORD}
                cls._log(f"Autenticando usuário: {cls.USERNAME}...")
                
                response = requests.post(url, json=payload, verify=False, timeout=10)
                if response.status_code == 200:
                    token = response.headers.get("Authorization", "").replace("Bearer ", "")
                    cls._log("Novo token gerado com sucesso.")
                    return token
                else:
                    cls._log(f"Falha no login automático: {response.status_code}", "error")
            except Exception as e:
                cls._log(f"Erro ao conectar para login: {e}", "error")

        # cls._log("Usando token estático (Fallback).")
        # return cls._FALLBACK_TOKEN
        return

    @staticmethod
    def _extrair_user_id(token: str) -> Optional[int]:
        """Decodifica o JWT para extrair o ID do usuário (idBaseDados)."""
        try:
            if not token: return None
            parts = token.split('.')
            if len(parts) < 2: return None
            
            # Ajuste de padding Base64
            payload_b64 = parts[1] + '=' * ((4 - len(parts[1]) % 4) % 4)
            decoded = json.loads(base64.urlsafe_b64decode(payload_b64))
            
            return decoded.get("idBaseDados") or decoded.get("sub")
        except Exception as e:
            logger.error(f"Erro ao decodificar token: {e}")
            return None

    @classmethod
    def _garantir_permissao(cls, token: str, user_id: int, cnpj: str):
        """
        Verifica e vincula o usuário ao órgão (Endpoint: /usuarios/{id}/orgaos).
        Essencial para o ambiente de Treinamento.
        """
        if not user_id or not cnpj: return

        url = f"{cls.BASE_URL}/usuarios/{user_id}/orgaos"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        payload = {"entesAutorizados": [cnpj]}

        try:
            cls._log(f"Verificando permissão para Usuário {user_id} no Órgão {cnpj}...")
            requests.post(url, headers=headers, json=payload, verify=False, timeout=10)
            # Sucesso ou 400/422 (já vinculado) são aceitáveis aqui
        except Exception as e:
            cls._log(f"Erro não-bloqueante na vinculação: {e}", "error")

    @classmethod
    def publicar_compra(cls, processo, arquivo: Any, titulo_documento: str) -> Dict[str, Any]:
        """
        Orquestra a publicação da compra (edital/aviso) no PNCP.
        """
        cls._log(f"Iniciando publicação do Processo: {processo.numero_processo}")

        # 1. Autenticação
        token = cls._get_token()
        if not token:
            raise ValueError("Não foi possível obter um token de acesso ao PNCP.")

        # 2. Preparação de Dados
        cnpj_orgao = re.sub(r'\D', '', processo.entidade.cnpj)
        user_id = cls._extrair_user_id(token)
        
        # Garante permissão (Delay para propagação)
        if user_id:
            cls._garantir_permissao(token, user_id, cnpj_orgao)
            time.sleep(1) 

        # 3. Formatação de Datas (Estrito: YYYY-MM-DDTHH:MM:SS)
        dt_abertura = processo.data_abertura or datetime.now()
        
        # Timezone
        sp_tz = pytz.timezone('America/Sao_Paulo')
        if not dt_abertura.tzinfo:
            dt_abertura = sp_tz.localize(dt_abertura)
        else:
            dt_abertura = dt_abertura.astimezone(sp_tz)
            
        # Strings limpas para o payload
        data_abertura_str = dt_abertura.strftime("%Y-%m-%dT%H:%M:%S")
        dt_fim = dt_abertura + timedelta(days=30) # Default +30 dias
        data_encerramento_str = dt_fim.strftime("%Y-%m-%dT%H:%M:%S")

        # 4. Sanitização de Campos
        raw_num_compra = str(processo.numero_certame).split('/')[0]
        numero_compra = "".join(filter(str.isdigit, raw_num_compra)) or "1"
        
        # IDs com fallback seguro
        try:
            mod_id = int(processo.modalidade or 1)
            disp_id = int(processo.modo_disputa or 1)
            amp_id = int(processo.amparo_legal or 4) # 4 = Lei 14.133 (Exemplo)
            inst_id = int(processo.instrumento_convocatorio or 1)
            crit_id = int(processo.criterio_julgamento or 1)
        except ValueError:
            raise ValueError("IDs de domínio (Modalidade, Amparo, etc.) devem ser números inteiros.")

        # 5. Construção do Payload
        payload = {
            "codigoUnidadeCompradora": processo.orgao.codigo_unidade or "000000",
            "cnpjOrgao": cnpj_orgao,
            "anoCompra": int(processo.data_processo.year) if processo.data_processo else datetime.now().year,
            "numeroCompra": numero_compra,
            "numeroProcesso": str(processo.numero_processo),
            
            "tipoInstrumentoConvocatorioId": inst_id,
            "modalidadeId": mod_id,
            "modoDisputaId": disp_id,
            "amparoLegalId": amp_id,
            
            "srp": bool(processo.registro_preco),
            "objetoCompra": (processo.objeto or "Objeto não informado")[:5000],
            "informacaoComplementar": "Integrado via API Licitapro",
            
            "dataAberturaProposta": data_abertura_str,
            "dataEncerramentoProposta": data_encerramento_str,
            
            "linkSistemaOrigem": "http://l3solution.net.br",
            "itensCompra": []
        }

        # Itens
        if not processo.itens.exists():
            raise ValueError("A contratação deve possuir ao menos um item.")

        for idx, item in enumerate(processo.itens.all(), 1):
            vl_unit = float(item.valor_estimado or 0)
            qtd = float(item.quantidade or 1)
            
            # Correção Inteligente da Categoria para Pregão (ID 6)
            cat_id = int(item.categoria_item or 1)
            if mod_id == 6 and cat_id == 1: 
                cat_id = 2 # Força Bens Móveis se for Pregão e estiver como Imóveis

            # Tipo Material (M) ou Serviço (S)
            tipo_ms = "S" if cat_id in [2, 4, 8, 9] else "M"

            payload["itensCompra"].append({
                "numeroItem": item.ordem or idx,
                "materialOuServico": tipo_ms,
                "tipoBeneficioId": int(item.tipo_beneficio or 1),
                "incentivoProdutivoBasico": False,
                "aplicabilidadeMargemPreferenciaNormal": False,
                "aplicabilidadeMargemPreferenciaAdicional": False,
                "codigoTipoMargemPreferencia": 1,
                "inConteudoNacional": True,
                "descricao": (item.descricao or "Item")[:255],
                "quantidade": qtd,
                "unidadeMedida": (item.unidade or "UN")[:20],
                "valorUnitarioEstimado": vl_unit,
                "valorTotal": round(vl_unit * qtd, 4),
                "criterioJulgamentoId": crit_id,
                "itemCategoriaId": cat_id,
                "catalogoId": 1, 
                "catalogoCodigoItem": "15055", 
                "categoriaItemCatalogoId": 1
            })

        # 6. Envio
        if hasattr(arquivo, 'seek'): arquivo.seek(0)
        
        files = {
            'documento': (getattr(arquivo, 'name', 'edital.pdf'), arquivo, 'application/pdf'),
            'compra': (None, json.dumps(payload), 'application/json')
        }

        url = f"{cls.BASE_URL}/orgaos/{cnpj_orgao}/compras"
        headers = {
            "Authorization": f"Bearer {token}",
            "Titulo-Documento": titulo_documento or "Edital",
            "Tipo-Documento-Id": "1"
        }

        try:
            cls._log(f"Enviando requisição para: {url}")
            response = requests.post(url, headers=headers, files=files, verify=False, timeout=90)
            
            if response.status_code in [200, 201]:
                cls._log("Compra publicada com sucesso!")
                return response.json()
            else:
                cls._handle_error(response)

        except requests.exceptions.RequestException as e:
            cls._log(f"Erro de conexão: {e}", "error")
            raise ValueError(f"Falha de comunicação com PNCP: {str(e)}")

    @staticmethod
    def _handle_error(response):
        """Processa e levanta erro formatado."""
        try:
            err = response.json()
            msg = err.get("message") or err.get("detail") or str(err)
        except:
            msg = response.text[:200]
        
        full_msg = f"PNCP Recusou ({response.status_code}): {msg}"
        logger.error(full_msg)
        raise ValueError(full_msg)

# Classe utilitária para importação (Stub)
class ImportacaoService:
    @staticmethod
    def processar_planilha_padrao(arquivo):
        raise NotImplementedError("Importação não implementada.")