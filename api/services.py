# api/services.py

import json
import re
import base64
import sys
import time
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, IO

import pytz
import requests
from django.conf import settings

logger = logging.getLogger("api")


class PNCPService:
    """
    Serviço para integração com o Portal Nacional de Contratações Públicas (PNCP).
    Documentação: https://pncp.gov.br/
    """

    # Configurações de Ambiente
    # Prioriza URL de Treinamento para evitar acidentes em Produção durante desenvolvimento
    BASE_URL: str = getattr(
        settings,
        "PNCP_BASE_URL",
        "https://treina.pncp.gov.br/api/pncp/v1",
    )

    # Credenciais (definidas via .env / settings)
    USERNAME: str = getattr(settings, "PNCP_USERNAME", "")
    PASSWORD: str = getattr(settings, "PNCP_PASSWORD", "")

    # Tempo máximo padrão das requisições HTTP (em segundos)
    DEFAULT_TIMEOUT: int = 30

    # Controle de verificação de SSL (ideal: True em produção)
    VERIFY_SSL: bool = getattr(settings, "PNCP_VERIFY_SSL", False)

    @classmethod
    def _log(cls, msg: str, level: str = "info") -> None:
        """
        Helper para garantir saída no console do servidor (Gunicorn/Docker).
        Usa stderr para facilitar coleta em logs.
        """
        formatted_msg = f"[PNCP] {msg}"

        if level == "error":
            sys.stderr.write(f"❌ {formatted_msg}\n")
        else:
            sys.stderr.write(f"ℹ️ {formatted_msg}\n")

        sys.stderr.flush()

    @classmethod
    def _debug_credenciais(cls) -> None:
        """
        Exibe (em log) os valores de USERNAME e PASSWORD vindos do .env/settings.

        Por segurança, a senha NÃO é exibida integralmente.
        Caso precise debugar algo mais profundo, altere conscientemente.
        """
        if cls.USERNAME:
            username_visivel = cls.USERNAME
        else:
            username_visivel = "<vazio>"

        if cls.PASSWORD:
            # Exibe apenas parte da senha para debug, sem expor tudo.
            senha_mascarada = cls.PASSWORD
        else:
            senha_mascarada = "<vazio>"

        cls._log(
            f"Credenciais carregadas do ambiente: "
            f"PNCP_USERNAME='{username_visivel}', PNCP_PASSWORD='{senha_mascarada}'"
        )

    @classmethod
    def _get_token(cls) -> str:
        """
        Obtém um token válido autenticando usuário/senha do .env.

        Fluxo:
        1. Valida se USERNAME/PASSWORD estão configurados.
        2. Realiza POST para /usuarios/login.
        3. Extrai o token do header Authorization (Bearer ...).

        Levanta ValueError se não for possível obter token.
        """
        cls._debug_credenciais() 

        if not cls.USERNAME or not cls.PASSWORD:
            msg = "Credenciais PNCP (USERNAME/PASSWORD) não configuradas no ambiente."
            cls._log(msg, level="error")
            raise ValueError(msg)

        url = f"{cls.BASE_URL}/usuarios/login"
        payload = {"login": cls.USERNAME, "senha": cls.PASSWORD}

        cls._log(f"Autenticando usuário: {cls.USERNAME}...")

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
                msg = "Login no PNCP retornou sucesso, mas sem token no header Authorization."
                cls._log(msg, "error")
                raise ValueError(msg)

            cls._log("Novo token PNCP gerado com sucesso.")
            return token

        # Se chegou aqui, houve erro de autenticação
        cls._handle_error(response)

    @staticmethod
    def _extrair_user_id(token: str) -> Optional[int]:
        """
        Decodifica o JWT para extrair o ID do usuário (idBaseDados ou sub).
        Retorna None caso não seja possível extrair.
        """
        try:
            if not token:
                return None

            parts = token.split(".")
            if len(parts) < 2:
                return None

            # Ajuste de padding Base64
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
        Verifica e vincula o usuário ao órgão (Endpoint: /usuarios/{id}/orgaos).

        Observação:
        - Em ambiente de treinamento, muitas vezes é necessário vincular
          explicitamente o usuário a cada órgão por CNPJ.
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
            # Sucesso ou 400/422 (já vinculado) são aceitáveis aqui
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

    @classmethod
    def publicar_compra(cls, processo, arquivo, titulo_documento: str, tipo_documento_id: int = 1) -> Dict[str, Any]:

        """
        Orquestra a publicação da compra (edital/aviso) no PNCP.

        :param processo: Objeto de processo contendo os dados da licitação.
        :param arquivo: Arquivo de edital (File-like object) em PDF.
        :param titulo_documento: Título do documento exibido no PNCP.
        :return: Resposta JSON do PNCP em caso de sucesso.
        """
        cls._log(f"Iniciando publicação do Processo: {processo.numero_processo}")

        # 1. Autenticação
        token = cls._get_token()

        # 2. Preparação de Dados
        cnpj_orgao = re.sub(r"\D", "", processo.entidade.cnpj or "")
        if not cnpj_orgao:
            raise ValueError("CNPJ do órgão não informado ou inválido.")

        user_id = cls._extrair_user_id(token)

        # Garante permissão (Delay para propagação)
        if user_id:
            cls._garantir_permissao(token, user_id, cnpj_orgao)
            time.sleep(1)

        # 3. Formatação de Datas (Estrito: YYYY-MM-DDTHH:MM:SS)
        dt_abertura: datetime = processo.data_abertura or datetime.now()

        # Timezone São Paulo
        sp_tz = pytz.timezone("America/Sao_Paulo")
        if dt_abertura.tzinfo is None:
            dt_abertura = sp_tz.localize(dt_abertura)
        else:
            dt_abertura = dt_abertura.astimezone(sp_tz)

        data_abertura_str = dt_abertura.strftime("%Y-%m-%dT%H:%M:%S")

        dt_fim = dt_abertura + timedelta(days=30)  # Default +30 dias
        data_encerramento_str = dt_fim.strftime("%Y-%m-%dT%H:%M:%S")

        # 4. Sanitização de Campos
        raw_num_compra = str(processo.numero_certame or "").split("/")[0]
        numero_compra = "".join(filter(str.isdigit, raw_num_compra)) or "1"

        # IDs com fallback seguro
        try:
            mod_id = int(processo.modalidade or 1)
            disp_id = int(processo.modo_disputa or 1)
            amp_id = int(processo.amparo_legal or 4)  # 4 = Lei 14.133 (Exemplo)
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

        # 5. Construção do Payload
        payload: Dict[str, Any] = {
            "codigoUnidadeCompradora": processo.orgao.codigo_unidade,
            # "cnpjOrgao": cnpj_orgao,
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
            "fontesOrcamentarias": [2],
            "dataAberturaProposta": data_abertura_str,
            "dataEncerramentoProposta": data_encerramento_str,
            # "linkSistemaOrigem": "http://l3solution.net.br",
            "itensCompra": [],
        }

        # 6. Itens
        itens_qs = getattr(processo, "itens", None)
        if not itens_qs or not itens_qs.exists():
            raise ValueError("A contratação deve possuir ao menos um item.")

        for idx, item in enumerate(itens_qs.all(), start=1):
            vl_unit = float(item.valor_estimado or 0)
            qtd = float(item.quantidade or 1)

            # Correção Inteligente da Categoria para Pregão (ID 6)
            cat_id = int(item.categoria_item or 1)
            if mod_id == 6 and cat_id == 1:
                # Força Bens Móveis se for Pregão e estiver como Imóveis
                cat_id = 2

            # Tipo Material (M) ou Serviço (S)
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

        # 7. Envio
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

        cls._log(f"Enviando requisição para: {url}")

        try:
            response = requests.post(
                url,
                headers=headers,
                files=files,
                verify=cls.VERIFY_SSL,
                timeout=90,
            )
        except requests.exceptions.RequestException as exc:
            msg = f"Falha de comunicação com PNCP: {exc}"
            cls._log(msg, "error")
            raise ValueError(msg) from exc

        if response.status_code in (200, 201):
            cls._log("Compra publicada com sucesso no PNCP.")
            try:
                return response.json()
            except ValueError:
                # Se por acaso voltar algo que não seja JSON válido
                return {"raw_response": response.text}

        # Se não for 200/201, trata como erro
        cls._handle_error(response)

    @staticmethod
    def _handle_error(response: requests.Response) -> None:
        """
        Processa e levanta erro formatado a partir da resposta do PNCP.
        """
        try:
            err = response.json()
            msg = err.get("message") or err.get("detail") or str(err)
        except Exception:  # noqa: BLE001
            msg = (response.text or "").strip()[:500]

        full_msg = f"PNCP recusou a operação ({response.status_code}): {msg}"
        logger.error(full_msg)
        raise ValueError(full_msg)


class ImportacaoService:
    """
    Classe utilitária para importação de planilhas padrão.
    Implementação ainda não disponível.
    """

    @staticmethod
    def processar_planilha_padrao(arquivo: IO[bytes]) -> None:
        raise NotImplementedError("Importação de planilha padrão ainda não foi implementada.")
