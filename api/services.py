# api/services.py

import base64
import json
import logging
import re
import sys
import time
from datetime import datetime, timedelta
from typing import Any, Dict, IO, List, Optional

import pytz
import requests
from django.conf import settings
from django.utils import timezone

# Importação do Model para tipagem e uso no ImportacaoService
from .models import ProcessoLicitatorio
from .choices import (
    MAP_MODALIDADE_MODO_DISPUTA,
    MAP_MODALIDADE_INSTRUMENTO,
    MAP_MODALIDADE_CRITERIO_JULGAMENTO,
    MAP_MODALIDADE_AMPARO,
)

logger = logging.getLogger("api")


class PNCPService:
    """
    Serviço para integração com o Portal Nacional de Contratações Públicas (PNCP).
    Documentação de referência: Manual de Integração PNCP (ex.: v2.3.8).
    """

    # ------------------------------------------------------------------ #
    # CONFIGURAÇÃO DE AMBIENTE                                           #
    # ------------------------------------------------------------------ #

    BASE_URL: str = getattr(
        settings,
        "PNCP_BASE_URL",
        "https://treina.pncp.gov.br/api/pncp/v1",
    )

    USERNAME: str = getattr(settings, "PNCP_USERNAME", "")
    PASSWORD: str = getattr(settings, "PNCP_PASSWORD", "")

    DEFAULT_TIMEOUT: int = 30
    VERIFY_SSL: bool = getattr(settings, "PNCP_VERIFY_SSL", False)

    # ------------------------------------------------------------------ #
    # HELPERS DE LOG                                                     #
    # ------------------------------------------------------------------ #

    @classmethod
    def _log(cls, msg: str, level: str = "info") -> None:
        """
        Log simples em stderr (útil em Docker / Gunicorn) e no Logger do Django.
        """
        formatted = f"[PNCP] {msg}"
        
        # Log no console (stderr)
        prefix = "❌ " if level == "error" else "ℹ️ "
        sys.stderr.write(f"{prefix}{formatted}\n")
        sys.stderr.flush()

        # Log no sistema de arquivos/Django
        if level == "error":
            logger.error(formatted)
        else:
            logger.info(formatted)

    @classmethod
    def _debug_credenciais(cls) -> None:
        """
        Loga informações mínimas sobre as credenciais configuradas
        (sem expor senha completa).
        """
        username_visivel = cls.USERNAME or "<vazio>"
        senha_mascarada = cls.PASSWORD[:2] + "***" if cls.PASSWORD else "<vazio>"
        cls._log(
            f"Credenciais carregadas: PNCP_USERNAME='{username_visivel}', "
            f"PNCP_PASSWORD='{senha_mascarada}'"
        )

    # ------------------------------------------------------------------ #
    # AUTENTICAÇÃO / TOKEN                                               #
    # ------------------------------------------------------------------ #

    @classmethod
    def _get_token(cls) -> str:
        """
        Obtém o token Bearer no endpoint /usuarios/login.
        Levanta ValueError em caso de erro.
        """
        cls._debug_credenciais()

        if not cls.USERNAME or not cls.PASSWORD:
            msg = "Credenciais PNCP (USERNAME/PASSWORD) não configuradas."
            cls._log(msg, "error")
            raise ValueError(msg)

        url = f"{cls.BASE_URL}/usuarios/login"
        payload = {"login": cls.USERNAME, "senha": cls.PASSWORD}

        cls._log(f"Autenticando usuário no PNCP: {cls.USERNAME}...")

        try:
            response = requests.post(
                url,
                json=payload,
                verify=cls.VERIFY_SSL,
                timeout=cls.DEFAULT_TIMEOUT,
            )
        except requests.exceptions.RequestException as exc:
            msg = f"Erro ao conectar ao PNCP para login: {exc}"
            cls._log(msg, "error")
            raise ValueError(msg) from exc

        if response.status_code == 200:
            token_header = response.headers.get("Authorization", "")
            token = token_header.replace("Bearer ", "").strip()
            if not token:
                msg = (
                    "Login no PNCP retornou 200, mas sem token no header Authorization."
                )
                cls._log(msg, "error")
                raise ValueError(msg)

            cls._log("Token PNCP obtido com sucesso.")
            return token

        cls._handle_error(response)

    @staticmethod
    def _extrair_user_id(token: str) -> Optional[int]:
        """
        Decodifica o JWT (sem validar assinatura) para extrair 'idBaseDados' ou 'sub'.
        """
        try:
            if not token:
                return None

            parts = token.split(".")
            if len(parts) < 2:
                return None

            payload_b64 = parts[1] + "=" * ((4 - len(parts[1]) % 4) % 4)
            decoded = json.loads(base64.urlsafe_b64decode(payload_b64))

            user_id = decoded.get("idBaseDados") or decoded.get("sub")
            return int(user_id) if user_id is not None else None
        except Exception as exc:  # noqa: BLE001
            logger.error("Erro ao decodificar token JWT do PNCP: %s", exc)
            return None

    @classmethod
    def _garantir_permissao(cls, token: str, user_id: Optional[int], cnpj: str) -> None:
        """
        Verifica/vincula o usuário ao órgão (endpoint /usuarios/{id}/orgaos).
        Não é bloqueante em caso de erro (apenas loga).
        """
        if not user_id or not cnpj:
            return

        url = f"{cls.BASE_URL}/usuarios/{user_id}/orgaos"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        payload = {"entesAutorizados": [cnpj]}

        try:
            cls._log(
                f"Verificando/vinculando permissão do usuário {user_id} ao órgão {cnpj}..."
            )
            requests.post(
                url,
                headers=headers,
                json=payload,
                verify=cls.VERIFY_SSL,
                timeout=cls.DEFAULT_TIMEOUT,
            )
        except requests.exceptions.RequestException as exc:
            cls._log(
                f"Erro não-bloqueante ao vincular usuário ao órgão no PNCP: {exc}",
                "error",
            )

    @staticmethod
    def _handle_error(response: requests.Response) -> None:
        """
        Converte erros do PNCP em ValueError com mensagem amigável.
        """
        try:
            err = response.json()
            msg = err.get("message") or err.get("detail") or str(err)
        except Exception:  # noqa: BLE001
            msg = (response.text or "").strip()[:500]

        full_msg = f"PNCP recusou a operação ({response.status_code}): {msg}"
        logger.error("[PNCP ERROR] Status=%s | Body=%s", response.status_code, (response.text or "")[:2000])
        raise ValueError(full_msg)

    # ------------------------------------------------------------------ #
    # 6.3.5 – Consultar uma Contratação                                  #
    # ------------------------------------------------------------------ #

    @classmethod
    def consultar_compra(
        cls,
        *,
        cnpj_orgao: str,
        ano_compra: int,
        sequencial_compra: int,
    ) -> Dict[str, Any]:
        """
        Consulta uma contratação no PNCP.
        Endpoint: /orgaos/{cnpj}/compras/{ano}/{sequencial} (GET)
        """
        token = cls._get_token()

        url = (
            f"{cls.BASE_URL}/orgaos/{cnpj_orgao}/compras/"
            f"{int(ano_compra)}/{int(sequencial_compra)}"
        )
        headers = {
            "Authorization": f"Bearer {token}",
            "accept": "*/*",
        }

        cls._log(f"Consultando contratação no PNCP: {url}")

        try:
            resp = requests.get(
                url,
                headers=headers,
                verify=cls.VERIFY_SSL,
                timeout=cls.DEFAULT_TIMEOUT,
            )
        except requests.exceptions.RequestException as exc:
            msg = f"Falha de comunicação com PNCP (consultar contratação): {exc}"
            cls._log(msg, "error")
            raise ValueError(msg) from exc

        if resp.status_code == 200:
            try:
                return resp.json()
            except ValueError:
                return {"raw_response": resp.text}

        cls._handle_error(resp)

    # ------------------------------------------------------------------ #
    # 6.3.8 – Consultar TODOS Documentos de uma Contratação              #
    # ------------------------------------------------------------------ #

    @classmethod
    def listar_documentos_compra(
        cls,
        *,
        cnpj_orgao: str,
        ano_compra: int,
        sequencial_compra: int,
    ) -> List[Dict[str, Any]]:
        """
        Lista os documentos pertencentes a uma contratação.
        Endpoint: /orgaos/{cnpj}/compras/{ano}/{sequencial}/arquivos (GET)
        """
        token = cls._get_token()

        url = (
            f"{cls.BASE_URL}/orgaos/{cnpj_orgao}/compras/"
            f"{int(ano_compra)}/{int(sequencial_compra)}/arquivos"
        )
        headers = {
            "Authorization": f"Bearer {token}",
            "accept": "*/*",
        }

        cls._log(f"Listando documentos da contratação: {url}")

        try:
            resp = requests.get(
                url,
                headers=headers,
                verify=cls.VERIFY_SSL,
                timeout=cls.DEFAULT_TIMEOUT,
            )
        except requests.exceptions.RequestException as exc:
            msg = f"Falha de comunicação com PNCP (listar documentos): {exc}"
            cls._log(msg, "error")
            raise ValueError(msg) from exc

        if resp.status_code == 200:
            try:
                data = resp.json()
            except ValueError:
                return [{"raw_response": resp.text}]

            # Tratamento para variações de resposta do PNCP (Lista direta ou envelope)
            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                docs = data.get("documentos") or data.get("Documentos")
                if isinstance(docs, list):
                    return docs
            return [data]

        cls._handle_error(resp)

    # ------------------------------------------------------------------ #
    # 6.3.6 – Inserir Documento a uma Contratação                        #
    # ------------------------------------------------------------------ #

    @classmethod
    def anexar_documento_compra(
        cls,
        *,
        cnpj_orgao: str,
        ano_compra: int,
        sequencial_compra: int,
        arquivo: IO[bytes],
        titulo_documento: str,
        tipo_documento_id: int,
        content_type: str = "application/pdf",
    ) -> Dict[str, Any]:
        """
        Insere/anexa um documento à contratação já existente no PNCP.
        Endpoint: /orgaos/{cnpj}/compras/{ano}/{sequencial}/arquivos (POST)
        """
        token = cls._get_token()

        if hasattr(arquivo, "seek"):
            arquivo.seek(0)

        url = (
            f"{cls.BASE_URL}/orgaos/{cnpj_orgao}/compras/"
            f"{int(ano_compra)}/{int(sequencial_compra)}/arquivos"
        )

        headers = {
            "Authorization": f"Bearer {token}",
            "Titulo-Documento": (titulo_documento or "Documento")[:255],
            "Tipo-Documento-Id": str(int(tipo_documento_id)),
            "accept": "*/*",
        }

        files = {
            "arquivo": (
                getattr(arquivo, "name", "documento.pdf"),
                arquivo,
                content_type,
            )
        }

        cls._log(f"Anexando documento à contratação: {url}")

        try:
            resp = requests.post(
                url,
                headers=headers,
                files=files,
                verify=cls.VERIFY_SSL,
                timeout=90,
            )
        except requests.exceptions.RequestException as exc:
            msg = f"Falha de comunicação com PNCP (anexar documento): {exc}"
            cls._log(msg, "error")
            raise ValueError(msg) from exc

        if resp.status_code in (200, 201):
            location = resp.headers.get("location") or resp.headers.get("Location")
            result: Dict[str, Any] = {
                "location": location,
                "status_code": resp.status_code,
            }
            try:
                body = resp.json()
                if isinstance(body, dict):
                    result.update(body)
            except ValueError:
                result["raw_response"] = resp.text

            cls._log(f"Documento anexado com sucesso. Location: {location}")
            return result

        cls._handle_error(resp)

    # ------------------------------------------------------------------ #
    # 6.3.7 – Excluir Documento de uma Contratação                       #
    # ------------------------------------------------------------------ #

    @classmethod
    def excluir_documento_compra(
        cls,
        *,
        cnpj_orgao: str,
        ano_compra: int,
        sequencial_compra: int,
        sequencial_arquivo: int,
        justificativa: str = "Exclusão solicitada pelo sistema de origem.",
    ) -> bool:
        """
        Exclui um documento de uma contratação.
        Endpoint:
        /orgaos/{cnpj}/compras/{ano}/{sequencial}/arquivos/{sequencialDocumento} (DELETE)
        """
        token = cls._get_token()

        url = (
            f"{cls.BASE_URL}/orgaos/{cnpj_orgao}/compras/"
            f"{int(ano_compra)}/{int(sequencial_compra)}/arquivos/{int(sequencial_arquivo)}"
        )

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "accept": "*/*",
        }

        payload = {
            "justificativa": (justificativa or "")[:255],
        }

        cls._log(
            f"Excluindo documento {sequencial_arquivo} da contratação: {url}"
        )

        try:
            resp = requests.delete(
                url,
                headers=headers,
                json=payload,
                verify=cls.VERIFY_SSL,
                timeout=cls.DEFAULT_TIMEOUT,
            )
        except requests.exceptions.RequestException as exc:
            msg = f"Falha de comunicação com PNCP (excluir documento): {exc}"
            cls._log(msg, "error")
            raise ValueError(msg) from exc

        if resp.status_code in (200, 204):
            cls._log("Documento excluído com sucesso do PNCP.")
            return True

        cls._handle_error(resp)

    # ------------------------------------------------------------------ #
    # Atualização de Metadados (PUT em arquivo)                          #
    # ------------------------------------------------------------------ #

    @classmethod
    def atualizar_metadados_documento(
        cls,
        *,
        cnpj_orgao: str,
        ano_compra: int,
        sequencial_compra: int,
        sequencial_arquivo: int,
        titulo_documento: str,
        tipo_documento_id: int,
    ) -> bool:
        """
        Atualiza o título e/ou tipo de um documento já publicado no PNCP.
        Endpoint:
        /orgaos/{cnpj}/compras/{ano}/{sequencial}/arquivos/{sequencialArquivo} (PUT)
        """
        token = cls._get_token()

        url = (
            f"{cls.BASE_URL}/orgaos/{cnpj_orgao}/compras/"
            f"{int(ano_compra)}/{int(sequencial_compra)}/arquivos/{int(sequencial_arquivo)}"
        )

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "accept": "*/*",
        }

        payload = {
            "tipoDocumentoId": int(tipo_documento_id),
            "titulo": (titulo_documento or "Documento")[:255],
        }

        cls._log(f"Atualizando metadados do documento {sequencial_arquivo}: {url}")

        try:
            resp = requests.put(
                url,
                headers=headers,
                json=payload,
                verify=cls.VERIFY_SSL,
                timeout=cls.DEFAULT_TIMEOUT,
            )
        except requests.exceptions.RequestException as exc:
            msg = f"Falha de comunicação com PNCP (atualizar documento): {exc}"
            cls._log(msg, "error")
            raise ValueError(msg) from exc

        if resp.status_code in (200, 204):
            cls._log("Metadados do documento atualizados com sucesso.")
            return True

        cls._handle_error(resp)

    # ------------------------------------------------------------------ #
    # Substituição de Documento (excluir + anexar)                       #
    # ------------------------------------------------------------------ #

    @classmethod
    def substituir_documento(
        cls,
        *,
        cnpj_orgao: str,
        ano_compra: int,
        sequencial_compra: int,
        sequencial_arquivo_antigo: int,
        novo_arquivo: IO[bytes],
        novo_titulo: str,
        novo_tipo_id: int,
        justificativa_exclusao: str = "Substituição de documento solicitada pelo sistema de origem.",
        content_type: str = "application/pdf",
    ) -> Dict[str, Any]:
        """
        Helper para substituir um arquivo no PNCP:
          1. Exclui o documento anterior com justificativa.
          2. Anexa o novo documento.
        """
        cls._log(
            f"Iniciando substituição do documento {sequencial_arquivo_antigo} "
            f"da compra {ano_compra}/{sequencial_compra}..."
        )

        # 1. Tenta excluir o documento antigo
        try:
            cls.excluir_documento_compra(
                cnpj_orgao=cnpj_orgao,
                ano_compra=ano_compra,
                sequencial_compra=sequencial_compra,
                sequencial_arquivo=sequencial_arquivo_antigo,
                justificativa=justificativa_exclusao,
            )
        except Exception as exc:  # noqa: BLE001
            cls._log(
                f"Aviso: falha ao excluir documento antigo ({sequencial_arquivo_antigo}) "
                f"durante substituição: {exc}",
                "error",
            )
            # Continua para tentar anexar o novo, conforme regra de negócio comum

        # 2. Anexa o novo
        return cls.anexar_documento_compra(
            cnpj_orgao=cnpj_orgao,
            ano_compra=ano_compra,
            sequencial_compra=sequencial_compra,
            arquivo=novo_arquivo,
            titulo_documento=novo_titulo,
            tipo_documento_id=novo_tipo_id,
            content_type=content_type,
        )

    # ------------------------------------------------------------------ #
    # Publicação da COMPRA (criação da contratação + documento)          #
    # ------------------------------------------------------------------ #

    @classmethod
    def publicar_compra(
        cls,
        processo: ProcessoLicitatorio,
        arquivo: IO[bytes],
        titulo_documento: str,
        tipo_documento_id: int = 1,
    ) -> Dict[str, Any]:
        """
        Publica a contratação no PNCP (cria a compra + envia um documento inicial).

        Retorno esperado (exemplo):
            {
              "numeroControlePNCP": "...",
              "anoCompra": 2023,
              "sequencialCompra": 1,
              ...
            }
        """
        cls._log(f"Iniciando publicação do Processo: {processo.numero_processo}")

        token = cls._get_token()

        # --- CNPJ / Órgão ------------------------------------------------
        cnpj_orgao = re.sub(r"\D", "", (processo.entidade.cnpj or "")) if processo.entidade else ""
        if len(cnpj_orgao) != 14:
            raise ValueError("CNPJ da entidade inválido/ausente.")

        if not processo.orgao or not processo.orgao.codigo_unidade:
            raise ValueError(
                "Código da unidade compradora (orgao.codigo_unidade) inválido/ausente."
            )

        # Garante permissão (Delay para propagação no PNCP)
        user_id = cls._extrair_user_id(token)
        if user_id:
            cls._garantir_permissao(token, user_id, cnpj_orgao)
            time.sleep(1)

        # --- Datas (fuso São Paulo) --------------------------------------
        dt_abertura: datetime = processo.data_abertura or datetime.now()
        sp_tz = pytz.timezone("America/Sao_Paulo")
        if dt_abertura.tzinfo is None:
            dt_abertura = sp_tz.localize(dt_abertura)
        else:
            dt_abertura = dt_abertura.astimezone(sp_tz)

        data_abertura_str = dt_abertura.strftime("%Y-%m-%dT%H:%M:%S")

        dt_fim = dt_abertura + timedelta(days=30)
        data_encerramento_str = dt_fim.strftime("%Y-%m-%dT%H:%M:%S")

        # --- Número da compra (sequencial de origem) ---------------------
        raw_num_compra = str(processo.numero_certame or "").split("/")[0]
        numero_compra = "".join(filter(str.isdigit, raw_num_compra)) or "1"

        # --- IDs de domínio (já convertidos para int no modelo) ----------
        try:
            mod_id = int(processo.modalidade or 1)
            disp_id = int(processo.modo_disputa or 1)
            amp_id = int(processo.amparo_legal or 4)
            inst_id = int(processo.instrumento_convocatorio or 1)
            crit_id = int(processo.criterio_julgamento or 1)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "IDs de domínio (Modalidade, Amparo, Modo de Disputa, etc.) "
                "devem ser números inteiros."
            ) from exc

        # ===== LOG DIAGNÓSTICO: DADOS BRUTOS DO PROCESSO =====
        logger.warning("=" * 80)
        logger.warning("[PNCP DEBUG] ======= DADOS DO PROCESSO =======")
        logger.warning("  Processo ID: %s", processo.id)
        logger.warning("  Número: %s", processo.numero_processo)
        logger.warning("  Modalidade (raw): %r -> mod_id=%s", processo.modalidade, mod_id)
        logger.warning("  Modo Disputa (raw): %r -> disp_id=%s", processo.modo_disputa, disp_id)
        logger.warning("  Amparo Legal (raw): %r -> amp_id=%s", processo.amparo_legal, amp_id)
        logger.warning("  Instrumento Conv. (raw): %r -> inst_id=%s", processo.instrumento_convocatorio, inst_id)
        logger.warning("  Critério Julg. (raw): %r -> crit_id=%s", processo.criterio_julgamento, crit_id)
        logger.warning("  CNPJ Orgão: %s", cnpj_orgao)
        logger.warning("  Unidade Compradora: %s", processo.orgao.codigo_unidade if processo.orgao else 'N/A')
        logger.warning("=" * 80)

        # --- Validação cruzada de domínios PNCP -------------------------
        # Modo de Disputa x Modalidade
        modos_validos = MAP_MODALIDADE_MODO_DISPUTA.get(mod_id)
        if modos_validos and disp_id not in modos_validos:
            fallback_disp = modos_validos[0]
            logger.warning(
                "[PNCP] Modo de disputa %s inválido para modalidade %s. "
                "Normalizando para %s.", disp_id, mod_id, fallback_disp
            )
            disp_id = fallback_disp

        # Instrumento Convocatório x Modalidade
        instrumentos_validos = MAP_MODALIDADE_INSTRUMENTO.get(mod_id)
        if instrumentos_validos and inst_id not in instrumentos_validos:
            fallback_inst = instrumentos_validos[0]
            logger.warning(
                "[PNCP] Instrumento convocatório %s inválido para modalidade %s. "
                "Normalizando para %s.", inst_id, mod_id, fallback_inst
            )
            inst_id = fallback_inst

        # Critério de Julgamento x Modalidade
        criterios_validos = MAP_MODALIDADE_CRITERIO_JULGAMENTO.get(mod_id)
        if criterios_validos and crit_id not in criterios_validos:
            fallback_crit = criterios_validos[0]
            logger.warning(
                "[PNCP] Critério de julgamento %s inválido para modalidade %s. "
                "Normalizando para %s.", crit_id, mod_id, fallback_crit
            )
            crit_id = fallback_crit

        # Amparo Legal x Modalidade
        amparos_validos = MAP_MODALIDADE_AMPARO.get(mod_id)
        if amparos_validos and amp_id not in amparos_validos:
            fallback_amp = amparos_validos[0]
            logger.warning(
                "[PNCP] Amparo legal %s inválido para modalidade %s. "
                "Normalizando para %s.", amp_id, mod_id, fallback_amp
            )
            amp_id = fallback_amp

        ano_compra = (
            int(processo.data_processo.year)
            if getattr(processo, "data_processo", None)
            else datetime.now().year
        )

        # --- Montagem do payload da COMPRA -------------------------------
        payload: Dict[str, Any] = {
            "codigoUnidadeCompradora": processo.orgao.codigo_unidade,
            "anoCompra": ano_compra,
            "numeroCompra": numero_compra,
            "numeroProcesso": str(processo.numero_processo or numero_compra),
            "tipoInstrumentoConvocatorioId": inst_id,
            "modalidadeId": mod_id,
            "modoDisputaId": disp_id,
            "amparoLegalId": amp_id,
            "srp": bool(getattr(processo, "registro_preco", False)),
            "objetoCompra": (processo.objeto or "Objeto não informado")[:5000],
            "informacaoComplementar": "Integrado via API L3Solutions",
            "fontesOrcamentarias": [2],
            "dataAberturaProposta": data_abertura_str,
            "dataEncerramentoProposta": data_encerramento_str,
            "itensCompra": [],
        }

        itens_qs = getattr(processo, "itens", None)
        if not itens_qs or not itens_qs.exists():
            raise ValueError("A contratação deve possuir ao menos um item para ser publicada no PNCP.")

        # Categorias que se comportam como Serviço no PNCP (materialOuServico = "S")
        # Serviço(2), Obra(3), Serv.Eng(4), TIC(5), Locação(6), Obras+Eng(8)
        service_like_categories = {2, 3, 4, 5, 6, 8}

        for idx, item in enumerate(itens_qs.all(), start=1):
            vl_unit = float(item.valor_estimado or 0)
            qtd = float(item.quantidade or 1)

            # Categoria do item (do banco)
            cat_id_raw = item.categoria_item
            cat_id = int(cat_id_raw) if cat_id_raw else None

            # ===== LOG DIAGNÓSTICO: DADOS DE CADA ITEM =====
            logger.warning(
                "[PNCP DEBUG] Item #%s: id=%s, ordem=%s, desc=%r, "
                "cat_raw=%r, cat_id=%s, tipo_beneficio=%r",
                idx, item.id, item.ordem, item.descricao,
                cat_id_raw, cat_id, item.tipo_beneficio,
            )

            # Material (M) ou Serviço (S) – baseado na categoria do item
            if cat_id and cat_id in service_like_categories:
                tipo_ms = "S"
            else:
                tipo_ms = "M"

            # Montagem do payload do item – campos OBRIGATÓRIOS apenas
            # NOTA: itemCategoriaId NÃO é obrigatório na API PNCP e quando
            # enviado com valor incompatível com a modalidade causa 422.
            # Solução: omitir itemCategoriaId (o PNCP aceita sem ele).
            item_payload = {
                "numeroItem": item.ordem or idx,
                "materialOuServico": tipo_ms,
                "tipoBeneficioId": int(item.tipo_beneficio or 1),
                "incentivoProdutivoBasico": False,
                "orcamentoSigiloso": False,
                "aplicabilidadeMargemPreferenciaNormal": False,
                "aplicabilidadeMargemPreferenciaAdicional": False,
                "descricao": (item.descricao or "Item")[:255],
                "quantidade": qtd,
                "unidadeMedida": (item.unidade or "UN")[:20],
                "valorUnitarioEstimado": vl_unit,
                "valorTotal": round(vl_unit * qtd, 4),
                "criterioJulgamentoId": crit_id,
            }

            payload["itensCompra"].append(item_payload)

        if hasattr(arquivo, "seek"):
            arquivo.seek(0)

        # Log de validação cruzada completa
        logger.info(
            "[PNCP PRE-SEND] Validação: modalidade=%s, modo_disputa=%s, "
            "amparo=%s, instrumento=%s, criterio=%s, itens=%d",
            mod_id, disp_id, amp_id, inst_id, crit_id,
            len(payload["itensCompra"]),
        )

        # ===== LOG DIAGNÓSTICO: PAYLOAD JSON COMPLETO =====
        logger.warning("[PNCP DEBUG] ======= PAYLOAD JSON COMPLETO =======")
        logger.warning("%s", json.dumps(payload, ensure_ascii=False, indent=2))

        files = {
            "documento": (
                getattr(arquivo, "name", "edital.pdf"),
                arquivo,
                "application/pdf",
            ),
            "compra": (None, json.dumps(payload), "application/json"),
        }

        url = f"{cls.BASE_URL}/orgaos/{cnpj_orgao}/compras"
        headers = {
            "Authorization": f"Bearer {token}",
            "Titulo-Documento": (titulo_documento or "Edital")[:255],
            "Tipo-Documento-Id": str(int(tipo_documento_id)),
        }

        logger.info(
            "[PNCP SEND] URL: %s | Payload: %s | Headers: %s",
            url,
            json.dumps(payload, ensure_ascii=False),
            str(headers)[:200],
        )

        cls._log(f"Enviando requisição de publicação de compra para: {url}")

        def _send_compra(current_files: Dict[str, Any]) -> requests.Response:
            return requests.post(
                url,
                headers=headers,
                files=current_files,
                verify=cls.VERIFY_SSL,
                timeout=90,
            )

        try:
            response = _send_compra(files)
        except requests.exceptions.RequestException as exc:
            msg = f"Falha de comunicação com PNCP (publicar compra): {exc}"
            cls._log(msg, "error")
            raise ValueError(msg) from exc

        # ===== LOG DIAGNÓSTICO: RESPOSTA DO PNCP =====
        logger.warning("[PNCP DEBUG] ======= RESPOSTA DO PNCP =======")
        logger.warning("  Status Code: %s", response.status_code)
        logger.warning("  Response Body: %s", (response.text or '')[:3000])

        # Retry: se 422 por categoria inválida, remover itemCategoriaId e reenviar
        if response.status_code == 422:
            response_text = (response.text or "")
            if "Categoria de compra de item" in response_text or "modalidade de compra" in response_text:
                retry_payload = json.loads(json.dumps(payload))

                # Remover itemCategoriaId de todos os itens (campo não obrigatório)
                for item_p in retry_payload.get("itensCompra", []):
                    item_p.pop("itemCategoriaId", None)

                retry_files = {
                    "documento": files["documento"],
                    "compra": (None, json.dumps(retry_payload), "application/json"),
                }

                logger.warning(
                    "[PNCP SEND] Retentando publicação SEM itemCategoriaId para modalidade %s.",
                    mod_id,
                )

                try:
                    if hasattr(arquivo, "seek"):
                        arquivo.seek(0)
                    response = _send_compra(retry_files)
                except requests.exceptions.RequestException as exc:
                    msg = f"Falha de comunicação com PNCP (retentativa publicar compra): {exc}"
                    cls._log(msg, "error")
                    raise ValueError(msg) from exc

                logger.warning("[PNCP DEBUG] RETRY Response: %s %s",
                               response.status_code, (response.text or '')[:3000])

        if response.status_code in (200, 201):
            cls._log("Compra publicada com sucesso no PNCP.")
            try:
                return response.json()
            except ValueError:
                return {"raw_response": response.text}

        cls._handle_error(response)

    # ------------------------------------------------------------------ #
    # INSERIR ITENS EM CONTRATAÇÃO EXISTENTE (6.3.10)                    #
    # ------------------------------------------------------------------ #

    @classmethod
    def inserir_itens_compra(
        cls,
        *,
        cnpj_orgao: str,
        ano_compra: int,
        sequencial_compra: int,
        itens_payload: list,
    ) -> Dict[str, Any]:
        """
        Insere um ou vários itens a uma contratação existente no PNCP.
        Endpoint:
          POST /orgaos/{cnpj}/compras/{ano}/{seq}/itens
        """
        token = cls._get_token()

        url = (
            f"{cls.BASE_URL}/orgaos/{cnpj_orgao}/compras/"
            f"{int(ano_compra)}/{int(sequencial_compra)}/itens"
        )

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "accept": "application/json",
        }

        cls._log(f"Inserindo {len(itens_payload)} item(ns) no PNCP: {url}")
        logger.warning("[PNCP] Inserir itens payload: %s",
                       json.dumps(itens_payload, ensure_ascii=False))

        try:
            resp = requests.post(
                url,
                headers=headers,
                json=itens_payload,
                verify=cls.VERIFY_SSL,
                timeout=cls.DEFAULT_TIMEOUT,
            )
        except requests.exceptions.RequestException as exc:
            msg = f"Falha de comunicação com PNCP (inserir itens): {exc}"
            cls._log(msg, "error")
            raise ValueError(msg) from exc

        logger.warning("[PNCP] Inserir itens response: %s %s",
                       resp.status_code, (resp.text or "")[:1000])

        if resp.status_code in (200, 201):
            cls._log("Itens inseridos com sucesso no PNCP.")
            try:
                return {"status_code": resp.status_code, "body": resp.json()}
            except ValueError:
                return {"status_code": resp.status_code, "raw": resp.text}

        cls._handle_error(resp)

    # ------------------------------------------------------------------ #
    # INSERIR RESULTADO DE ITEM (Fornecedor Vencedor)                    #
    # ------------------------------------------------------------------ #

    @classmethod
    def inserir_resultado_item(
        cls,
        *,
        cnpj_orgao: str,
        ano_compra: int,
        sequencial_compra: int,
        numero_item: int,
        resultado_payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Insere o resultado (fornecedor vencedor) de um item da contratação.
        Se o PNCP retornar 422 "já existe resultado com o fornecedor",
        tenta atualizar via PUT nos sequenciais 1..5.
        """
        token = cls._get_token()

        url = (
            f"{cls.BASE_URL}/orgaos/{cnpj_orgao}/compras/"
            f"{int(ano_compra)}/{int(sequencial_compra)}/itens/"
            f"{int(numero_item)}/resultados"
        )

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "accept": "application/json",
        }

        cls._log(f"Inserindo resultado do item {numero_item} no PNCP: {url}")
        logger.warning("[PNCP] Resultado item %s payload: %s",
                       numero_item, json.dumps(resultado_payload, ensure_ascii=False))

        try:
            resp = requests.post(
                url,
                headers=headers,
                json=resultado_payload,
                verify=cls.VERIFY_SSL,
                timeout=cls.DEFAULT_TIMEOUT,
            )
        except requests.exceptions.RequestException as exc:
            msg = f"Falha de comunicação com PNCP (resultado item {numero_item}): {exc}"
            cls._log(msg, "error")
            raise ValueError(msg) from exc

        if resp.status_code in (200, 201):
            result = {"status_code": resp.status_code}
            try:
                body = resp.json()
                if isinstance(body, dict):
                    result.update(body)
            except ValueError:
                result["raw_response"] = resp.text
            cls._log(f"Resultado do item {numero_item} inserido com sucesso.")
            return result

        # Se 422 com "já existe resultado", tentar PUT para atualizar
        if resp.status_code == 422:
            resp_text = resp.text or ""
            if "resultado" in resp_text.lower() and "fornecedor" in resp_text.lower():
                logger.warning(
                    "[PNCP] POST resultado item %s deu 422 (já existe). "
                    "Tentando PUT para atualizar...", numero_item
                )
                # Tentar PUT nos sequenciais 1..5
                for seq_r in range(1, 6):
                    put_url = f"{url}/{seq_r}"
                    try:
                        put_resp = requests.put(
                            put_url,
                            headers=headers,
                            json=resultado_payload,
                            verify=cls.VERIFY_SSL,
                            timeout=cls.DEFAULT_TIMEOUT,
                        )
                    except requests.exceptions.RequestException:
                        continue

                    logger.warning(
                        "[PNCP] PUT resultado item %s seq %s -> %s: %s",
                        numero_item, seq_r, put_resp.status_code,
                        (put_resp.text or "")[:500]
                    )

                    if put_resp.status_code in (200, 204):
                        cls._log(
                            f"Resultado do item {numero_item} atualizado "
                            f"via PUT (seq={seq_r})."
                        )
                        return {"status_code": put_resp.status_code, "method": "PUT"}

                # Se PUT não funcionou, log e continua para _handle_error
                logger.warning(
                    "[PNCP] PUT também falhou para item %s. Resposta original: %s",
                    numero_item, resp_text[:500]
                )

        cls._handle_error(resp)

    # ------------------------------------------------------------------ #
    # CONSULTAR RESULTADOS EXISTENTES DE UM ITEM                         #
    # ------------------------------------------------------------------ #

    @classmethod
    def consultar_resultados_item(
        cls,
        *,
        cnpj_orgao: str,
        ano_compra: int,
        sequencial_compra: int,
        numero_item: int,
    ) -> list:
        """
        Consulta os resultados já cadastrados de um item no PNCP.
        Tenta primeiro no endpoint de escrita (BASE_URL) e depois no de consulta.
        Retorna lista de resultados (cada um com sequencialResultado).
        """
        token = cls._get_token()

        # Tentar nos dois endpoints possíveis
        base_urls = [cls.BASE_URL]
        # Adicionar endpoint de consulta como fallback
        consulta_url = cls.BASE_URL.replace("/api/pncp/", "/api/consulta/")
        if consulta_url != cls.BASE_URL:
            base_urls.append(consulta_url)

        for base in base_urls:
            url = (
                f"{base}/orgaos/{cnpj_orgao}/compras/"
                f"{int(ano_compra)}/{int(sequencial_compra)}/itens/"
                f"{int(numero_item)}/resultados"
            )

            headers = {
                "Authorization": f"Bearer {token}",
                "accept": "application/json",
            }

            try:
                resp = requests.get(
                    url,
                    headers=headers,
                    verify=cls.VERIFY_SSL,
                    timeout=cls.DEFAULT_TIMEOUT,
                )
            except requests.exceptions.RequestException as exc:
                logger.warning("[PNCP] Falha ao consultar resultados item %s em %s: %s",
                               numero_item, base, exc)
                continue

            logger.warning("[PNCP] GET resultados item %s -> %s: %s",
                           numero_item, resp.status_code, (resp.text or "")[:1000])

            if resp.status_code == 200:
                try:
                    body = resp.json()
                    if isinstance(body, list):
                        return body
                    if isinstance(body, dict):
                        return body.get("resultados", body.get("data", [body]))
                except ValueError:
                    pass

        return []

    # ------------------------------------------------------------------ #
    # DELETAR RESULTADO DE UM ITEM                                       #
    # ------------------------------------------------------------------ #

    @classmethod
    def deletar_resultado_item(
        cls,
        *,
        cnpj_orgao: str,
        ano_compra: int,
        sequencial_compra: int,
        numero_item: int,
        sequencial_resultado: int,
    ) -> bool:
        """
        Remove um resultado específico de um item no PNCP.
        Endpoint:
          DELETE /orgaos/{cnpj}/compras/{ano}/{seq}/itens/{numeroItem}/resultados/{seqResultado}
        """
        token = cls._get_token()

        url = (
            f"{cls.BASE_URL}/orgaos/{cnpj_orgao}/compras/"
            f"{int(ano_compra)}/{int(sequencial_compra)}/itens/"
            f"{int(numero_item)}/resultados/{int(sequencial_resultado)}"
        )

        headers = {
            "Authorization": f"Bearer {token}",
            "accept": "application/json",
        }

        cls._log(f"Deletando resultado {sequencial_resultado} do item {numero_item}: {url}")

        try:
            resp = requests.delete(
                url,
                headers=headers,
                verify=cls.VERIFY_SSL,
                timeout=cls.DEFAULT_TIMEOUT,
            )
        except requests.exceptions.RequestException as exc:
            logger.warning("[PNCP] Falha ao deletar resultado %s do item %s: %s",
                           sequencial_resultado, numero_item, exc)
            return False

        if resp.status_code in (200, 204):
            cls._log(f"Resultado {sequencial_resultado} do item {numero_item} deletado.")
            return True

        logger.warning("[PNCP] DELETE resultado %s item %s retornou %s: %s",
                       sequencial_resultado, numero_item,
                       resp.status_code, (resp.text or "")[:500])
        return False

    # ------------------------------------------------------------------ #
    # ATUALIZAR ITEM DE CONTRATAÇÃO (PATCH parcial)                      #
    # ------------------------------------------------------------------ #

    @classmethod
    def atualizar_item_compra(
        cls,
        *,
        cnpj_orgao: str,
        ano_compra: int,
        sequencial_compra: int,
        numero_item: int,
        item_payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Atualiza parcialmente um item da contratação no PNCP.
        Endpoint PNCP:
          PATCH /orgaos/{cnpj}/compras/{ano}/{seq}/itens/{numeroItem}
        """
        token = cls._get_token()

        url = (
            f"{cls.BASE_URL}/orgaos/{cnpj_orgao}/compras/"
            f"{int(ano_compra)}/{int(sequencial_compra)}/itens/{int(numero_item)}"
        )

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "accept": "application/json",
        }

        cls._log(f"Atualizando item {numero_item} no PNCP: {url}")

        try:
            resp = requests.patch(
                url,
                headers=headers,
                json=item_payload,
                verify=cls.VERIFY_SSL,
                timeout=cls.DEFAULT_TIMEOUT,
            )
        except requests.exceptions.RequestException as exc:
            msg = f"Falha de comunicação com PNCP (atualizar item {numero_item}): {exc}"
            cls._log(msg, "error")
            raise ValueError(msg) from exc

        if resp.status_code in (200, 204):
            cls._log(f"Item {numero_item} atualizado com sucesso no PNCP.")
            return {"status_code": resp.status_code}

        cls._handle_error(resp)

    # ------------------------------------------------------------------ #
    # SINCRONIZAR RESULTADOS (enviar fornecedores vencedores dos itens)  #
    # ------------------------------------------------------------------ #

    @classmethod
    def sincronizar_resultados(
        cls,
        processo,
    ) -> Dict[str, Any]:
        """
        Sincroniza os resultados dos itens no PNCP:
        - Para cada item com fornecedor vencedor (ItemFornecedor.vencedor=True),
          envia o resultado (fornecedor, valores homologados).
        - Atualiza a situação dos itens para 'Homologado' (2).

        Requer que a compra já esteja publicada (pncp_ano_compra e
        pncp_sequencial_compra preenchidos).
        """
        if not processo.pncp_ano_compra or not processo.pncp_sequencial_compra:
            raise ValueError(
                "Processo não publicado no PNCP. Publique primeiro antes de "
                "sincronizar resultados."
            )

        cnpj_orgao = re.sub(r"\D", "", (processo.entidade.cnpj or ""))
        if len(cnpj_orgao) != 14:
            raise ValueError("CNPJ da entidade inválido.")

        ano = int(processo.pncp_ano_compra)
        seq = int(processo.pncp_sequencial_compra)

        # Mapeamento de porte do fornecedor para ID PNCP
        # 1=ME, 2=EPP, 3=Demais, 4=Cooperativa, 5=MEI
        PORTE_MAP = {
            "ME": "1", "EPP": "2", "MEI": "5",
            "DEMAIS": "3", "COOPERATIVA": "4",
            "MICRO EMPRESA": "1", "EMPRESA DE PEQUENO PORTE": "2",
        }

        resultados_ok = []
        erros = []

        itens = processo.itens.select_related("fornecedor").prefetch_related(
            "propostas__fornecedor"
        ).order_by("ordem")

        for item in itens:
            numero_item = item.ordem or item.pncp_numero_item

            if not numero_item:
                erros.append(f"Item '{item.descricao}' sem número de ordem.")
                continue

            # Buscar proposta vencedora
            proposta_vencedora = item.propostas.filter(
                vencedor=True
            ).select_related("fornecedor").first()

            # Fallback: fornecedor direto do item
            if not proposta_vencedora and item.fornecedor:
                fornecedor = item.fornecedor
                valor_unit = float(item.valor_estimado or 0)
                qtd = float(item.quantidade or 1)
            elif proposta_vencedora:
                fornecedor = proposta_vencedora.fornecedor
                valor_unit = float(proposta_vencedora.valor_proposto or 0)
                qtd = float(item.quantidade or 1)
            else:
                logger.info("[PNCP] Item %s '%s' sem fornecedor vencedor, pulando.",
                            numero_item, item.descricao)
                continue

            ni_fornecedor = re.sub(r"\D", "", (fornecedor.cnpj or ""))
            if not ni_fornecedor:
                erros.append(
                    f"Item {numero_item}: Fornecedor '{fornecedor.razao_social}' sem CNPJ."
                )
                continue

            tipo_pessoa = "PJ" if len(ni_fornecedor) == 14 else (
                "PF" if len(ni_fornecedor) == 11 else "PJ"
            )

            porte_raw = (fornecedor.porte or "").strip().upper()
            porte_id = PORTE_MAP.get(porte_raw, "3")

            from datetime import date as date_cls
            data_resultado = date_cls.today().isoformat()

            resultado_payload = {
                "quantidadeHomologada": qtd,
                "valorUnitarioHomologado": valor_unit,
                "valorTotalHomologado": round(valor_unit * qtd, 2),
                "percentualDesconto": 0,
                "aplicacaoMargemPreferencia": False,
                "aplicacaoBeneficioMeEpp": porte_id in ("1", "2", "5"),
                "aplicacaoCriterioDesempate": False,
                "tipoPessoaId": tipo_pessoa,
                "niFornecedor": ni_fornecedor,
                "nomeRazaoSocialFornecedor": (fornecedor.razao_social or "")[:255],
                "porteFornecedorId": porte_id,
                "codigoPais": "BRA",
                "indicadorSubcontratacao": False,
                "ordemClassificacaoSrp": 1,
                "dataResultado": data_resultado,
            }

            try:
                # ---- LIMPAR resultados anteriores do item ----
                # Evita duplicação quando o fornecedor muda e sincroniza de novo
                resultados_existentes = cls.consultar_resultados_item(
                    cnpj_orgao=cnpj_orgao,
                    ano_compra=ano,
                    sequencial_compra=seq,
                    numero_item=numero_item,
                )

                deletados = 0
                if resultados_existentes:
                    for res_antigo in resultados_existentes:
                        seq_resultado = (
                            res_antigo.get("sequencialResultado")
                            or res_antigo.get("sequencial")
                        )
                        if seq_resultado is not None:
                            ok = cls.deletar_resultado_item(
                                cnpj_orgao=cnpj_orgao,
                                ano_compra=ano,
                                sequencial_compra=seq,
                                numero_item=numero_item,
                                sequencial_resultado=int(seq_resultado),
                            )
                            if ok:
                                deletados += 1
                            time.sleep(0.3)

                # Se a consulta não retornou nada, tentar deletar por
                # força bruta os sequenciais 1..5
                if not resultados_existentes:
                    for seq_r in range(1, 6):
                        ok = cls.deletar_resultado_item(
                            cnpj_orgao=cnpj_orgao,
                            ano_compra=ano,
                            sequencial_compra=seq,
                            numero_item=numero_item,
                            sequencial_resultado=seq_r,
                        )
                        if ok:
                            deletados += 1
                            time.sleep(0.3)

                logger.info("[PNCP] Item %s: %d resultados antigos deletados.",
                            numero_item, deletados)

                if deletados > 0:
                    time.sleep(0.5)

                # ---- Inserir novo resultado ----
                try:
                    result = cls.inserir_resultado_item(
                        cnpj_orgao=cnpj_orgao,
                        ano_compra=ano,
                        sequencial_compra=seq,
                        numero_item=numero_item,
                        resultado_payload=resultado_payload,
                    )
                except ValueError as ve:
                    ve_str = str(ve)
                    # Se 404 "Item não cadastrado", inserir o item no PNCP primeiro
                    if "404" in ve_str and ("não cadastrado" in ve_str.lower()
                                            or "not found" in ve_str.lower()):
                        logger.warning(
                            "[PNCP] Item %s não existe no PNCP. Inserindo...",
                            numero_item
                        )
                        # Determinar material/serviço
                        service_cats = {2, 3, 4, 5, 6, 8}
                        cat_id_raw = item.categoria_item
                        cat_id_val = int(cat_id_raw) if cat_id_raw else None
                        tipo_ms = "S" if (cat_id_val and cat_id_val in service_cats) else "M"

                        crit_id = int(processo.criterio_julgamento or 1)

                        item_pncp_payload = [{
                            "numeroItem": numero_item,
                            "materialOuServico": tipo_ms,
                            "tipoBeneficioId": int(item.tipo_beneficio or 1),
                            "incentivoProdutivoBasico": False,
                            "orcamentoSigiloso": False,
                            "aplicabilidadeMargemPreferenciaNormal": False,
                            "aplicabilidadeMargemPreferenciaAdicional": False,
                            "descricao": (item.descricao or "Item")[:255],
                            "quantidade": qtd,
                            "unidadeMedida": (item.unidade or "UN")[:20],
                            "valorUnitarioEstimado": valor_unit,
                            "valorTotal": round(valor_unit * qtd, 4),
                            "criterioJulgamentoId": crit_id,
                        }]

                        cls.inserir_itens_compra(
                            cnpj_orgao=cnpj_orgao,
                            ano_compra=ano,
                            sequencial_compra=seq,
                            itens_payload=item_pncp_payload,
                        )
                        time.sleep(1)

                        # Tentar inserir resultado de novo
                        result = cls.inserir_resultado_item(
                            cnpj_orgao=cnpj_orgao,
                            ano_compra=ano,
                            sequencial_compra=seq,
                            numero_item=numero_item,
                            resultado_payload=resultado_payload,
                        )
                    else:
                        raise

                resultados_ok.append({
                    "item": numero_item,
                    "fornecedor": fornecedor.razao_social,
                    "status": "OK",
                })

                # Atualizar situação do item para Homologado (2)
                try:
                    cls.atualizar_item_compra(
                        cnpj_orgao=cnpj_orgao,
                        ano_compra=ano,
                        sequencial_compra=seq,
                        numero_item=numero_item,
                        item_payload={"situacaoCompraItemId": "2"},
                    )
                except Exception as e:
                    logger.warning(
                        "[PNCP] Erro ao atualizar situação do item %s: %s",
                        numero_item, str(e)
                    )

            except Exception as e:
                erros.append(f"Item {numero_item}: {str(e)}")
                logger.error("[PNCP] Erro ao inserir resultado item %s: %s",
                             numero_item, str(e))

            time.sleep(0.5)

        return {
            "total_itens": itens.count(),
            "resultados_enviados": len(resultados_ok),
            "erros": len(erros),
            "detalhes": resultados_ok,
            "erros_detalhes": erros,
        }

     # ------------------------------------------------------------------ #
    # 6.4.1 – Inserir Ata de Registro de Preço                          #
    # ------------------------------------------------------------------ #

    @classmethod
    def inserir_ata_registro_preco(
        cls,
        *,
        cnpj_orgao: str,
        ano_compra: int,
        sequencial_compra: int,
        numero_ata_registro_preco: str,
        ano_ata: int,
        data_assinatura: str,
        data_vigencia_inicio: str,
        data_vigencia_fim: str,
    ) -> Dict[str, Any]:
        """
        6.4.1 – Inserir Ata de Registro de Preço
        Endpoint:
        /orgaos/{cnpj}/compras/{anoCompra}/{sequencialCompra}/atas  (POST)
        """
        token = cls._get_token()

        url = (
            f"{cls.BASE_URL}/orgaos/{cnpj_orgao}/compras/"
            f"{int(ano_compra)}/{int(sequencial_compra)}/atas"
        )

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "accept": "application/json",
        }

        payload = {
            "numeroAtaRegistroPreco": (numero_ata_registro_preco or "").strip(),
            "anoAta": int(ano_ata),
            "dataAssinatura": data_assinatura,       # yyyy-MM-dd
            "dataVigenciaInicio": data_vigencia_inicio,
            "dataVigenciaFim": data_vigencia_fim,
        }

        cls._log(f"Inserindo Ata de RP no PNCP: {url}")

        try:
            resp = requests.post(
                url,
                headers=headers,
                json=payload,
                verify=cls.VERIFY_SSL,
                timeout=cls.DEFAULT_TIMEOUT,
            )
        except requests.exceptions.RequestException as exc:
            msg = f"Falha de comunicação com PNCP (inserir ata): {exc}"
            cls._log(msg, "error")
            raise ValueError(msg) from exc

        if resp.status_code in (200, 201):
            # a API retorna location no header e, em alguns ambientes, um JSON
            result: Dict[str, Any] = {
                "status_code": resp.status_code,
                "location": resp.headers.get("location") or resp.headers.get("Location"),
            }
            try:
                body = resp.json()
                if isinstance(body, dict):
                    result.update(body)
            except ValueError:
                result["raw_response"] = resp.text
            cls._log(f"Ata inserida com sucesso. Location: {result.get('location')}")
            return result

        cls._handle_error(resp)

    # ------------------------------------------------------------------ #
    # 6.4.3 – Excluir Ata de Registro de Preço                          #
    # ------------------------------------------------------------------ #

    @classmethod
    def excluir_ata_registro_preco(
        cls,
        *,
        cnpj_orgao: str,
        ano_compra: int,
        sequencial_compra: int,
        sequencial_ata: int,
        justificativa: str,
    ) -> bool:
        """
        Exclui/Remove uma Ata de Registro de Preços no PNCP.
        Endpoint:
          /orgaos/{cnpj}/compras/{anoCompra}/{sequencialCompra}/atas/{sequencialAta} (DELETE)
        """
        token = cls._get_token()

        url = (
            f"{cls.BASE_URL}/orgaos/{cnpj_orgao}/compras/"
            f"{int(ano_compra)}/{int(sequencial_compra)}/atas/{int(sequencial_ata)}"
        )

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "accept": "*/*",
        }

        payload = {
            "justificativa": (justificativa or "")[:255],
        }

        cls._log(f"Excluindo Ata de Registro de Preços no PNCP: {url}")

        try:
            resp = requests.delete(
                url,
                headers=headers,
                json=payload,
                verify=cls.VERIFY_SSL,
                timeout=cls.DEFAULT_TIMEOUT,
            )
        except requests.exceptions.RequestException as exc:
            msg = f"Falha de comunicação com PNCP (excluir Ata): {exc}"
            cls._log(msg, "error")
            raise ValueError(msg) from exc

        if resp.status_code in (200, 204):
            cls._log("Ata excluída com sucesso do PNCP.")
            return True

        cls._handle_error(resp)
    @classmethod
    def anexar_documento_ata(
        cls,
        *,
        cnpj_orgao: str,
        ano_compra: int,
        sequencial_compra: int,
        sequencial_ata: int,
        arquivo: IO[bytes],
        titulo_documento: str,
        tipo_documento_id: int,
        content_type: str = "application/pdf",
    ) -> Dict[str, Any]:
        """
        6.4.6 – Inserir Documento de uma Ata
        Endpoint:
        /orgaos/{cnpj}/compras/{anoCompra}/{sequencialCompra}/atas/{sequencialAta}/arquivos  (POST)
        """
        token = cls._get_token()

        if hasattr(arquivo, "seek"):
            arquivo.seek(0)

        url = (
            f"{cls.BASE_URL}/orgaos/{cnpj_orgao}/compras/"
            f"{int(ano_compra)}/{int(sequencial_compra)}/atas/{int(sequencial_ata)}/arquivos"
        )

        headers = {
            "Authorization": f"Bearer {token}",
            "Titulo-Documento": (titulo_documento or "Documento")[:50],
            "Tipo-Documento": str(int(tipo_documento_id)),
            "accept": "*/*",
        }

        files = {
            "arquivo": (
                getattr(arquivo, "name", "documento.pdf"),
                arquivo,
                content_type,
            )
        }

        cls._log(f"Anexando documento à Ata no PNCP: {url}")

        try:
            resp = requests.post(
                url,
                headers=headers,
                files=files,
                verify=cls.VERIFY_SSL,
                timeout=90,
            )
        except requests.exceptions.RequestException as exc:
            msg = f"Falha de comunicação com PNCP (anexar documento à ata): {exc}"
            cls._log(msg, "error")
            raise ValueError(msg) from exc

        if resp.status_code in (200, 201):
            location = resp.headers.get("location") or resp.headers.get("Location")
            result: Dict[str, Any] = {
                "location": location,
                "status_code": resp.status_code,
            }
            try:
                body = resp.json()
                if isinstance(body, dict):
                    result.update(body)
            except ValueError:
                result["raw_response"] = resp.text

            cls._log(f"Documento de Ata anexado com sucesso. Location: {location}")
            return result

        cls._handle_error(resp)

    @classmethod
    def excluir_documento_ata(
        cls,
        *,
        cnpj_orgao: str,
        ano_compra: int,
        sequencial_compra: int,
        sequencial_ata: int,
        sequencial_documento: int,
        justificativa: str,
    ) -> bool:
        """
        6.4.7 – Excluir Documento de uma Ata
        Endpoint:
        /orgaos/{cnpj}/compras/{anoCompra}/{sequencialCompra}/atas/{sequencialAta}/arquivos/{sequencialDocumento} (DELETE)
        """
        token = cls._get_token()

        url = (
            f"{cls.BASE_URL}/orgaos/{cnpj_orgao}/compras/"
            f"{int(ano_compra)}/{int(sequencial_compra)}/atas/{int(sequencial_ata)}/arquivos/{int(sequencial_documento)}"
        )

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "accept": "*/*",
        }

        payload = {
            "justificativa": (justificativa or "")[:255],
        }

        cls._log(
            f"Excluindo documento {sequencial_documento} da Ata {sequencial_ata} no PNCP: {url}"
        )

        try:
            resp = requests.delete(
                url,
                headers=headers,
                json=payload,
                verify=cls.VERIFY_SSL,
                timeout=cls.DEFAULT_TIMEOUT,
            )
        except requests.exceptions.RequestException as exc:
            msg = f"Falha de comunicação com PNCP (excluir documento de ata): {exc}"
            cls._log(msg, "error")
            raise ValueError(msg) from exc

        if resp.status_code in (200, 204):
            cls._log("Documento de Ata excluído com sucesso no PNCP.")
            return True

        cls._handle_error(resp)

    @classmethod
    def listar_documentos_ata(
        cls,
        *,
        cnpj_orgao: str,
        ano_compra: int,
        sequencial_compra: int,
        sequencial_ata: int,
    ) -> List[Dict[str, Any]]:
        """
        6.4.8 – Consultar Todos os Documentos de uma Ata
        Endpoint:
        /orgaos/{cnpj}/compras/{anoCompra}/{sequencialCompra}/atas/{sequencialAta}/arquivos (GET)
        """
        token = cls._get_token()

        url = (
            f"{cls.BASE_URL}/orgaos/{cnpj_orgao}/compras/"
            f"{int(ano_compra)}/{int(sequencial_compra)}/atas/{int(sequencial_ata)}/arquivos"
        )

        headers = {
            "Authorization": f"Bearer {token}",
            "accept": "*/*",
        }

        cls._log(f"Listando documentos da Ata {sequencial_ata} no PNCP: {url}")

        try:
            resp = requests.get(
                url,
                headers=headers,
                verify=cls.VERIFY_SSL,
                timeout=cls.DEFAULT_TIMEOUT,
            )
        except requests.exceptions.RequestException as exc:
            msg = f"Falha de comunicação com PNCP (listar documentos de ata): {exc}"
            cls._log(msg, "error")
            raise ValueError(msg) from exc

        if resp.status_code == 200:
            try:
                data = resp.json()
            except ValueError:
                return [{"raw_response": resp.text}]

            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                docs = data.get("documentos") or data.get("Documentos")
                if isinstance(docs, list):
                    return docs
            return [data]

        cls._handle_error(resp)



# ====================================================================== #
# IMPORTAÇÃO DE PLANILHA XLSX                                            #
# ====================================================================== #


class ImportacaoService:
    """
    Serviço utilitário para importação de planilha padrão (.xlsx).
    """

    @staticmethod
    def processar_planilha_padrao(arquivo: IO[bytes]) -> Dict[str, Any]:
        """
        Processa uma planilha .xlsx e cria um ProcessoLicitatorio básico.
        """
        # Nome do arquivo (sem caminho)
        nome_arquivo = getattr(arquivo, "name", "Processo Importado")
        nome_base = str(nome_arquivo).rsplit(".", 1)[0]

        # Criação do processo "esqueleto"
        processo = ProcessoLicitatorio.objects.create(
            numero_processo=nome_base,
            numero_certame=None,
            objeto=f"Processo importado do arquivo {nome_arquivo}",
            data_processo=timezone.now().date(),
        )

        return {
            "processo": processo,
            "lotes_criados": 0,
            "itens_importados": 0,
            "fornecedores_vinculados": 0,
        }