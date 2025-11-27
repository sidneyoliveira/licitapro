# api/services.py

import json
import requests
import base64
import sys
import time
from typing import Dict, Any
from django.conf import settings

# Logger manual para garantir saída no terminal da Hostinger
def log_console(msg):
    sys.stderr.write(f"[PNCP TESTE] {msg}\n")
    sys.stderr.flush()

class PNCPService:
    # --- VARIÁVEIS DO SEU SCRIPT QUE FUNCIONOU ---
    TOKEN = "eyJhbGciOiJIUzUxMiJ9.eyJzdWIiOiI2ODJiYTE0YS1jMTJkLTRhOWYtOWMxOS1hNjYyNDIzMGMxMzkiLCJleHAiOjE3NjQyNTQxMTcsImFkbWluaXN0cmFkb3IiOmZhbHNlLCJjcGZDbnBqIjoiMTEwMzU1NDQwMDAxMDUiLCJlbWFpbCI6ImNvbnRhdG9fbGxAaG90bWFpbC5jb20iLCJnZXN0YW9lbnRlIjp0cnVlLCJpZEJhc2VEYWRvcyI6Mjg2NCwibm9tZSI6IkwgJiBMIEFTU0VTU09SSUEgQ09OU1VMVE9SSUEgRSBTRVJWScOHT1MgTFREQSJ9.UeDwKQtPzIX86QVXKY7e5u--em5iaGED_NcE518HSQSM_ZY6cXSSOVSxKCrukl8KWbyTLySNgUP_EfxjjZqACw"
    BASE_URL = "https://treina.pncp.gov.br/api/pncp/v1"

    @staticmethod
    def _get_user_id_from_token(token):
        try:
            payload = token.split(".")[1]
            payload += "=" * ((4 - len(payload) % 4) % 4)
            decoded = json.loads(base64.urlsafe_b64decode(payload))
            user_id = decoded.get("idBaseDados")
            log_console(f"ID Usuário extraído do Token: {user_id}")
            return user_id
        except Exception as e:
            log_console(f"Erro ao decodificar token: {e}")
            return None

    @classmethod
    def _garantir_permissao_ente(cls, user_id, cnpj_orgao):
        if not user_id: return
        
        url_permissao = f"{cls.BASE_URL}/usuarios/{user_id}/orgaos"
        headers_perm = {
            "Authorization": f"Bearer {cls.TOKEN}",
            "Content-Type": "application/json",
            "accept": "*/*"
        }
        
        payload_perm = {"entesAutorizados": [cnpj_orgao]}
        
        log_console(f"Tentando vincular usuário {user_id} ao órgão {cnpj_orgao}...")
        try:
            response = requests.post(url_permissao, headers=headers_perm, json=payload_perm, verify=False, timeout=15)
            if response.status_code in [200, 201]:
                log_console("✅ Permissão concedida/atualizada com sucesso.")
            else:
                log_console(f"⚠️ Aviso na permissão: {response.status_code} - {response.text}")
        except Exception as e:
            log_console(f"❌ Erro ao tentar vincular permissão: {e}")

    @classmethod
    def publicar_compra(cls, processo, arquivo: Any, titulo_documento: str) -> Dict[str, Any]:
        log_console(">>> INICIANDO PUBLICAÇÃO (MÓDULO REPLICADO DO SCRIPT)")

        # 1. Prepara CNPJ
        cnpj_orgao = "".join(filter(str.isdigit, processo.entidade.cnpj))
        
        # 2. Garante permissão
        user_id = cls._get_user_id_from_token(cls.TOKEN)
        cls._garantir_permissao_ente(user_id, cnpj_orgao)

        # 3. Configura URL
        url_compra = f"{cls.BASE_URL}/orgaos/{cnpj_orgao}/compras"

        # 4. Prepara Payload
        from datetime import datetime, timedelta
        
        # Datas
        dt_abertura = processo.data_abertura 
        if not dt_abertura: dt_abertura = datetime.now()
        if dt_abertura.tzinfo: dt_abertura = dt_abertura.replace(tzinfo=None)
        
        data_abertura_str = dt_abertura.strftime("%Y-%m-%dT%H:%M:%S")
        dt_fim = dt_abertura + timedelta(days=4) 
        data_encerramento_str = dt_fim.strftime("%Y-%m-%dT%H:%M:%S")

        # Sanitização
        raw_num = str(processo.numero_certame).split('/')[0]
        numero_compra = "".join(filter(str.isdigit, raw_num)) or "1"
        
        try:
            mod_id = int(processo.modalidade)
            disp_id = int(processo.modo_disputa)
            amp_id = int(processo.amparo_legal)
            inst_id = int(processo.instrumento_convocatorio or 1)
            crit_id = int(processo.criterio_julgamento or 1)
        except:
            log_console("Erro convertendo IDs. Usando fallbacks.")
            mod_id, disp_id, amp_id, inst_id, crit_id = 1, 1, 4, 1, 5

        payload = {
            "codigoUnidadeCompradora": processo.orgao.codigo_unidade or "202511",
            "numeroCompra": numero_compra,
            "anoCompra": int(processo.data_processo.year) if processo.data_processo else 2025,
            "numeroProcesso": str(processo.numero_processo or "0001"),
            "tipoInstrumentoConvocatorioId": inst_id,
            "modalidadeId": mod_id,
            "modoDisputaId": disp_id,
            "amparoLegalId": amp_id,
            "srp": bool(processo.registro_preco),
            "objetoCompra": (processo.objeto ),
            "informacaoComplementar": "Teste via API Django",
            "dataAberturaProposta": data_abertura_str,
            "dataEncerramentoProposta": data_encerramento_str,
            "linkSistemaOrigem": "http://l3solution.net.br",
            "linkProcessoEletronico": "http://l3solution.net.br",
            "justificativaPresencial": "",
            "fontesOrcamentarias": [],
            "itensCompra": []
        }

        # Itens
        for idx, item in enumerate(processo.itens.all(), 1):
            vl_unit = float(item.valor_estimado or 0)
            qtd = float(item.quantidade or 1)
            vl_total = round(vl_unit * qtd, 4)
 
            cat_id_banco = int(item.categoria_item or 0)
            cat_id_final = cat_id_banco        
                      
            if cat_id_final == 0: cat_id_final = 1 

            tipo_ms = "M" 

            if cat_id_final in [4, 8, 9]: 
                tipo_ms = "S"

            payload["itensCompra"].append({
                "numeroItem": item.ordem or idx,
                "materialOuServico": tipo_ms,
                "tipoBeneficioId": int(item.tipo_beneficio or 5),
                "incentivoProdutivoBasico": False,
                "aplicabilidadeMargemPreferenciaNormal": False,
                "aplicabilidadeMargemPreferenciaAdicional": False,
                "codigoTipoMargemPreferencia": 1,
                "inConteudoNacional": True,
                "descricao": (item.descricao)[:255],
                "informacaoComplementar": (item.especificacao)[:255],
                "quantidade": qtd,
                "unidadeMedida": (item.unidade or "Unidade")[:20],
                "valorUnitarioEstimado": vl_unit,
                "valorTotal": vl_total,
                "orcamentoSigiloso": False,
                "criterioJulgamentoId": crit_id,
                
                "itemCategoriaId": cat_id_final,
                "catalogoId": 2,
            })

        # Debug Payload
        log_console("Payload JSON:")
        log_console(json.dumps(payload, indent=2, ensure_ascii=False))

        # 5. Envio
        headers = {
            "Authorization": f"Bearer {cls.TOKEN}",
            "Titulo-Documento": titulo_documento or "Edital de Teste",
            "Tipo-Documento-Id": "1",
            "accept": "*/*"
        }

        if hasattr(arquivo, 'seek'):
            arquivo.seek(0)
        
        fname = getattr(arquivo, 'name', 'edital.pdf')
        
        files = {
            'documento': (fname, arquivo, 'application/pdf'),
            'compra': (None, json.dumps(payload), 'application/json')
        }

        try:
            log_console(f"Enviando POST para: {url_compra}")
            response = requests.post(url_compra, headers=headers, files=files, verify=False, timeout=90)
            
            log_console(f"Status Code: {response.status_code}")
            
            if response.status_code in [200, 201]:
                log_console("✅ SUCESSO! Recurso criado.")
                return response.json()
            else:
                log_console("Falha na requisição.")
                try:
                    err_json = response.json()
                    log_console(f"Erro JSON: {err_json}")
                    raise ValueError(f"PNCP Recusou ({response.status_code}): {err_json}")
                except json.JSONDecodeError:
                    log_console(f"Erro Texto: {response.text}")
                    raise ValueError(f"PNCP Recusou ({response.status_code}): {response.text[:200]}")

        except Exception as e:
            log_console(f"Erro na requisição: {e}")
            raise ValueError(str(e))

class ImportacaoService:
    @staticmethod
    def processar_planilha_padrao(arquivo):
        pass