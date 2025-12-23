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
            "informacaoComplementar": "Integrado via API Licitapro",
            "fontesOrcamentarias": [2],
            "dataAberturaProposta": data_abertura_str,
            "dataEncerramentoProposta": data_encerramento_str,
            "itensCompra": [],
        }

        itens_qs = getattr(processo, "itens", None)
        if not itens_qs or not itens_qs.exists():
            raise ValueError("A contratação deve possuir ao menos um item para ser publicada no PNCP.")

        for idx, item in enumerate(itens_qs.all(), start=1):
            vl_unit = float(item.valor_estimado or 0)
            qtd = float(item.quantidade or 1)

            # Categoria do item (ajuste simples para pregão, se necessário)
            cat_id = int(item.categoria_item or 1)
            if mod_id == 6 and cat_id == 1:
                cat_id = 2

            # Material (M) ou Serviço (S) – regra simplificada
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
                    "itemCategoriaId": cat_id,
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