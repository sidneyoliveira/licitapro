# api/services.py

import json
import re
import base64
import sys
import time
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, IO, List

import pytz
import requests
from django.conf import settings

logger = logging.getLogger("api")


class PNCPService:
    """
    Serviço para integração com o Portal Nacional de Contratações Públicas (PNCP).
    Documentação: Manual de Integração PNCP v2.3.8.
    """

    # Configurações de Ambiente
    BASE_URL: str = getattr(
        settings,
        "PNCP_BASE_URL",
        "https://treina.pncp.gov.br/api/pncp/v1",
    )

    # Credenciais
    USERNAME: str = getattr(settings, "PNCP_USERNAME", "")
    PASSWORD: str = getattr(settings, "PNCP_PASSWORD", "")

    # Tempo máximo padrão das requisições HTTP (em segundos)
    DEFAULT_TIMEOUT: int = 30

    # Verificação de SSL
    VERIFY_SSL: bool = getattr(settings, "PNCP_VERIFY_SSL", False)

    # ------------------------------------------------------------------ #
    # HELPERS INTERNOS                                                   #
    # ------------------------------------------------------------------ #

    @classmethod
    def _log(cls, msg: str, level: str = "info") -> None:
        """
        Helper para logar em stderr (útil em Docker / Gunicorn).
        """
        formatted = f"[PNCP] {msg}\n"
        if level == "error":
            sys.stderr.write("❌ " + formatted)
        else:
            sys.stderr.write("ℹ️ " + formatted)
        sys.stderr.flush()

    @classmethod
    def _debug_credenciais(cls) -> None:
        """
        Log mínimo das credenciais (sem expor senha completa).
        """
        username_visivel = cls.USERNAME or "<vazio>"
        if cls.PASSWORD:
            senha_mascarada = cls.PASSWORD[:2] + "***"
        else:
            senha_mascarada = "<vazio>"

        cls._log(
            f"Credenciais carregadas do ambiente: "
            f"PNCP_USERNAME='{username_visivel}', PNCP_PASSWORD='{senha_mascarada}'"
        )

    @classmethod
    def _get_token(cls) -> str:
        """
        Obtém token Bearer no endpoint /usuarios/login.
        Levanta ValueError em caso de erro.
        """
        cls._debug_credenciais()

        if not cls.USERNAME or not cls.PASSWORD:
            msg = "Credenciais PNCP (USERNAME/PASSWORD) não configuradas no ambiente."
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
                msg = "Login no PNCP retornou 200, mas sem token no header Authorization."
                cls._log(msg, "error")
                raise ValueError(msg)

            cls._log("Token PNCP obtido com sucesso.")
            return token

        cls._handle_error(response)

    @staticmethod
    def _extrair_user_id(token: str) -> Optional[int]:
        """
        Decodifica o JWT e tenta extrair 'idBaseDados' ou 'sub' como user_id.
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
        Não bloqueante em caso de falha.
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
        Processa erro vindo do PNCP e levanta ValueError com mensagem amigável.
        """
        try:
            err = response.json()
            msg = err.get("message") or err.get("detail") or str(err)
        except Exception:  # noqa: BLE001
            msg = (response.text or "").strip()[:500]

        full_msg = f"PNCP recusou a operação ({response.status_code}): {msg}"
        logger.error(full_msg)
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
        Endpoint: /v1/orgaos/{cnpj}/compras/{ano}/{sequencial} (GET)
        """
        token = cls._get_token()

        url = f"{cls.BASE_URL}/orgaos/{cnpj_orgao}/compras/{int(ano_compra)}/{int(sequencial_compra)}"
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
        Endpoint: /v1/orgaos/{cnpj}/compras/{ano}/{sequencial}/arquivos (GET)
        """
        token = cls._get_token()

        url = f"{cls.BASE_URL}/orgaos/{cnpj_orgao}/compras/{int(ano_compra)}/{int(sequencial_compra)}/arquivos"
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
                # Caso PNCP mude o retorno, devolvemos bruto
                return [{"raw_response": resp.text}]

            # Manual sugere um objeto com chave "documentos" ou similar.
            # Caso o PNCP já retorne uma lista, tratamos também.
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
        Endpoint: /v1/orgaos/{cnpj}/compras/{ano}/{sequencial}/arquivos (POST)

        Retorna:
            {
              "location": "<url do recurso>",
              "status_code": 201,
              "raw_response": "...",  # quando houver
            }
        """
        token = cls._get_token()

        if hasattr(arquivo, "seek"):
            arquivo.seek(0)

        url = f"{cls.BASE_URL}/orgaos/{cnpj_orgao}/compras/{int(ano_compra)}/{int(sequencial_compra)}/arquivos"

        headers = {
            "Authorization": f"Bearer {token}",
            "Titulo-Documento": (titulo_documento or "Documento")[:255],
            "Tipo-Documento-Id": str(int(tipo_documento_id)),
            "accept": "*/*",
        }

        files = {
            "arquivo": (
                getattr(arquivo, "name", "documento"),
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
            # Em alguns ambientes pode vir um corpo vazio; tentamos parsear:
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
        Endpoint: /v1/orgaos/{cnpj}/compras/{ano}/{sequencial}/arquivos/{sequencialDocumento} (DELETE)

        Envia JSON no corpo:
            { "justificativa": "..." }
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
            "justificativa": justificativa[:255],
        }

        cls._log(f"Excluindo documento {sequencial_arquivo} da contratação: {url}")

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
    # Atualização de Metadados de Documento (título / tipo)             #
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
        Endpoint (Swagger): /v1/orgaos/{cnpj}/compras/{ano}/{sequencial}/arquivos/{sequencialArquivo} (PUT)
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
        Helper para substituir um arquivo:
          1. Exclui o documento anterior com justificativa.
          2. Anexa o novo documento.

        Não é transação atômica no PNCP, mas concentra o fluxo.
        """
        cls._log(
            f"Iniciando substituição do documento {sequencial_arquivo_antigo} "
            f"da compra {ano_compra}/{sequencial_compra}..."
        )

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
                f"Aviso: falha ao excluir documento antigo durante substituição: {exc}",
                "error",
            )
            # Dependendo da regra de negócio, você pode optar por abortar aqui:
            # raise

        # Anexa o novo
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
    # Publicação da COMPRA (já existia)                                  #
    # ------------------------------------------------------------------ #

    @classmethod
    def publicar_compra(
        cls,
        processo,
        arquivo,
        titulo_documento: str,
        tipo_documento_id: int = 1,
    ) -> Dict[str, Any]:
        """
        Orquestra a publicação da compra (edital/aviso) no PNCP.
        OBS.: Este método dispara a criação da contratação no PNCP
        (/orgaos/{cnpj}/compras) e já envia um documento junto.

        O retorno normalmente contém dados como:
            - numeroControlePNCP
            - anoCompra
            - sequencialCompra
        que devem ser gravados no modelo Processo para uso posterior
        (consultar_compra, anexar_documento_compra, etc.).
        """
        cls._log(f"Iniciando publicação do Processo: {processo.numero_processo}")

        token = cls._get_token()

        # CNPJ do órgão originário (entidade do processo)
        cnpj_orgao = re.sub(r"\D", "", (processo.entidade.cnpj or "")) if processo.entidade else ""
        if len(cnpj_orgao) != 14:
            raise ValueError("CNPJ da entidade inválido/ausente.")

        if not processo.orgao or not processo.orgao.codigo_unidade:
            raise ValueError("Código da unidade compradora (orgao.codigo_unidade) inválido/ausente.")

        user_id = cls._extrair_user_id(token)

        if user_id:
            cls._garantir_permissao(token, user_id, cnpj_orgao)
            time.sleep(1)

        # Datas (fuso São Paulo)
        dt_abertura: datetime = processo.data_abertura or datetime.now()
        sp_tz = pytz.timezone("America/Sao_Paulo")
        if dt_abertura.tzinfo is None:
            dt_abertura = sp_tz.localize(dt_abertura)
        else:
            dt_abertura = dt_abertura.astimezone(sp_tz)

        data_abertura_str = dt_abertura.strftime("%Y-%m-%dT%H:%M:%S")

        dt_fim = dt_abertura + timedelta(days=30)
        data_encerramento_str = dt_fim.strftime("%Y-%m-%dT%H:%M:%S")

        # Número da compra (sequencial do sistema de origem)
        raw_num_compra = str(processo.numero_certame or "").split("/")[0]
        numero_compra = "".join(filter(str.isdigit, raw_num_compra)) or "1"

        try:
            mod_id = int(processo.modalidade or 1)
            disp_id = int(processo.modo_disputa or 1)
            amp_id = int(processo.amparo_legal or 4)
            inst_id = int(processo.instrumento_convocatorio or 1)
            crit_id = int(processo.criterio_julgamento or 1)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "IDs de domínio (Modalidade, Amparo, etc.) devem ser números inteiros."
            ) from exc

        ano_compra = (
            int(processo.data_processo.year)
            if getattr(processo, "data_processo", None)
            else datetime.now().year
        )

        payload: Dict[str, Any] = {
            "codigoUnidadeCompradora": processo.orgao.codigo_unidade,
            "anoCompra": ano_compra,
            "numeroCompra": numero_compra,
            "numeroProcesso": str(processo.numero_processo),
            "tipoInstrumentoConvocatorioId": inst_id,
            "modalidadeId": mod_id,
            "modoDisputaId": disp_id,
            "amparoLegalId": amp_id,
            "srp": bool(getattr(processo, "registro_preco", False)),
            "objetoCompra": (processo.objeto or "Objeto não informado")[:5000],
            "informacaoComplementar": "Integrado via API Licitapro",
            "fontesOrcamentarias": [2],  # ajustar conforme tabela de domínio, se necessário
            "dataAberturaProposta": data_abertura_str,
            "dataEncerramentoProposta": data_encerramento_str,
            "itensCompra": [],
        }

        itens_qs = getattr(processo, "itens", None)
        if not itens_qs or not itens_qs.exists():
            raise ValueError("A contratação deve possuir ao menos um item.")

        for idx, item in enumerate(itens_qs.all(), start=1):
            vl_unit = float(item.valor_estimado or 0)
            qtd = float(item.quantidade or 1)

            cat_id = int(item.categoria_item or 1)
            if mod_id == 6 and cat_id == 1:
                cat_id = 2  # correção de categoria em pregão

            tipo_ms = "S" if cat_id in [2, 4, 8, 9] else "M"

            payload["itensCompra"].append(
                {
                    "numeroItem": item.ordem or idx,
                    "materialOuServico": tipo_ms,
                    "tipoBeneficioId": int(item.tipo_beneficio or 1),
                    "incentivoProdutivoBasico": False,
                    "orcamentoSigiloso": False,
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
                    "itemCategoriaId": 3,
                    "catalogoId": 2,
                }
            )

        if hasattr(arquivo, "seek"):
            arquivo.seek(0)

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

        try:
            response = requests.post(
                url,
                headers=headers,
                files=files,
                verify=cls.VERIFY_SSL,
                timeout=90,
            )
        except requests.exceptions.RequestException as exc:
            msg = f"Falha de comunicação com PNCP (publicar compra): {exc}"
            cls._log(msg, "error")
            raise ValueError(msg) from exc

        if response.status_code in (200, 201):
            cls._log("Compra publicada com sucesso no PNCP.")
            try:
                return response.json()
            except ValueError:
                return {"raw_response": response.text}

        cls._handle_error(response)


class ImportacaoService:
    """
    Classe utilitária para importação de planilhas padrão.
    Implementação ainda não disponível.
    """

    @staticmethod
    def processar_planilha_padrao(arquivo: IO[bytes]) -> None:
        raise NotImplementedError("Importação de planilha padrão ainda não foi implementada.")
