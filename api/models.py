from django.db import models, transaction
from django.conf import settings
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model

# Importação das escolhas (Choices) padronizadas para o PNCP
# Certifique-se de que o arquivo api/choices.py esteja criado conforme o passo anterior
from .choices import (
    MODALIDADE_CHOICES,
    MODO_DISPUTA_CHOICES,
    AMPARO_LEGAL_CHOICES,
    SITUACAO_CHOICES,
    CRITERIO_JULGAMENTO_CHOICES,
    TIPO_INSTRUMENTO_CONVOCATORIO_CHOICES,
    NATUREZAS_DESPESA,
    TIPO_ORGANIZACAO_CHOICES,
    TIPO_PESSOA_CHOICES,
    CLASSIFICACAO_CHOICES,
    FUNDAMENTACAO_CHOICES
)

# ============================================================
# 🏛️ ENTIDADE / ÓRGÃO
# ============================================================

class Entidade(models.Model):
    """
    Representa a entidade pública (Prefeitura, Câmara, Autarquia).
    Dados essenciais para o cabeçalho do PNCP.
    """
    nome = models.CharField(max_length=255)
    cnpj = models.CharField(max_length=18, unique=True)
    endereco = models.TextField(blank=True, null=True)
    logo = models.ImageField(upload_to='entidades/', blank=True, null=True)
    ano = models.IntegerField(default=2025, verbose_name="Ano de Exercício")
    
    # Configurações de integração
    pncp_token = models.CharField(max_length=500, blank=True, null=True, help_text="Token de acesso ao PNCP")

    class Meta:
        ordering = ['nome']

    def __str__(self):
        return f"{self.nome} ({self.cnpj})"

class Orgao(models.Model):
    """
    Unidade Orçamentária ou Administrativa vinculada à Entidade.
    O PNCP exige o 'codigoUnidadeCompradora'.
    """
    entidade = models.ForeignKey(Entidade, on_delete=models.CASCADE, related_name='orgaos')
    nome = models.CharField(max_length=255)
    codigo_unidade = models.CharField(
        max_length=20, 
        default="000000",
        help_text="Código da Unidade Compradora no sistema do Governo (ex: UASG ou código próprio cadastrado no PNCP)"
    )
    
    class Meta:
        ordering = ['nome']

    def __str__(self):
        return f"{self.nome} - {self.codigo_unidade}"

# ============================================================
# 📄 PROCESSO LICITATÓRIO
# ============================================================

class ProcessoLicitatorio(models.Model):
    """
    Entidade principal. Armazena os dados do processo/licitação.
    Combina a lógica de negócio (Fat Model) com os campos do PNCP.
    """
    # --- Identificação ---
    entidade = models.ForeignKey(Entidade, on_delete=models.CASCADE)
    orgao = models.ForeignKey(Orgao, on_delete=models.SET_NULL, null=True, blank=True)
    
    numero_processo = models.CharField(max_length=50, help_text="Número administrativo interno")
    numero_certame = models.CharField(max_length=50, help_text="Número do edital/licitação para o público")
    ano = models.IntegerField(default=2025)
    objeto = models.TextField(help_text="Descrição sucinta do objeto da licitação")

    # --- Classificadores e Domínios Controlados ---
    modalidade = models.CharField(
        max_length=100, 
        choices=MODALIDADE_CHOICES
    )
    
    modo_disputa = models.CharField(
        max_length=50, 
        choices=MODO_DISPUTA_CHOICES,
        blank=True, null=True
    )
    
    amparo_legal = models.CharField(
        max_length=255, 
        choices=AMPARO_LEGAL_CHOICES
    )
    
    criterio_julgamento = models.CharField(
        max_length=50,
        choices=CRITERIO_JULGAMENTO_CHOICES,
        default="MENOR PRECO",
        help_text="Critério principal de julgamento do certame"
    )

    tipo_instrumento = models.IntegerField(
        choices=TIPO_INSTRUMENTO_CONVOCATORIO_CHOICES,
        default=1, # Edital
        help_text="Tipo de documento convocatório (Edital, Aviso, etc)"
    )

    classificacao = models.CharField(max_length=50, blank=True, choices=CLASSIFICACAO_CHOICES)
    tipo_organizacao = models.CharField(max_length=10, blank=True, choices=TIPO_ORGANIZACAO_CHOICES, default='ITEM')
    
    situacao = models.CharField(max_length=50, choices=SITUACAO_CHOICES, default='EM PESQUISA')
    fundamentacao = models.CharField(max_length=50, choices=FUNDAMENTACAO_CHOICES, blank=True, null=True)

    # --- Datas e Valores ---
    data_processo = models.DateField(help_text="Data de autuação do processo")
    data_abertura = models.DateTimeField(help_text="Data/Hora de abertura da sessão pública")
    data_publicacao = models.DateTimeField(null=True, blank=True, auto_now_add=True)
    
    valor_estimado_total = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    valor_referencia = models.DecimalField(max_digits=15, decimal_places=2, blank=True, null=True) # Mantido para compatibilidade
    vigencia_meses = models.PositiveIntegerField(blank=True, null=True)

    # SRP (Registro de Preço)
    registro_preco = models.BooleanField(default=False, verbose_name="Registro de Preço (SRP)")
    lei_14133 = models.BooleanField(default=True, verbose_name="Regido pela Lei 14.133/21")
    
    # --- Controle de Integração ---
    pncp_sequencial = models.CharField(max_length=50, blank=True, null=True, help_text="Sequencial gerado pelo PNCP após publicação")
    pncp_url = models.URLField(blank=True, null=True, help_text="Link para a compra no PNCP")
    
    usuario_criacao = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('entidade', 'numero_certame', 'ano', 'modalidade')
        ordering = ['-ano', '-data_abertura']
        verbose_name = "Processo Licitatório"
        verbose_name_plural = "Processos Licitatórios"

    def __str__(self):
        return f"{self.numero_certame}/{self.ano} - {self.get_modalidade_display()}"

    def save(self, *args, **kwargs):
        # Normalização básica automática
        if self.modalidade: 
            self.modalidade = self.modalidade.upper().strip()
        if self.modo_disputa:
            self.modo_disputa = self.modo_disputa.upper().strip()
        super().save(*args, **kwargs)

    # --- Alias para Frontend (React espera 'registro_precos' em alguns componentes legados) ---
    @property
    def registro_precos(self):
        return self.registro_preco

    @registro_precos.setter
    def registro_precos(self, value):
        self.registro_preco = bool(value)

    # ============================================================
    # LÓGICA DE NEGÓCIO (MÉTODOS DE LOTE)
    # ============================================================

    def next_lote_numero(self) -> int:
        """Calcula o próximo número de lote disponível."""
        ultimo = self.lotes.order_by('-numero').first()
        return (ultimo.numero + 1) if ultimo else 1

    @transaction.atomic
    def criar_lotes(self, quantidade: int = None, descricao_prefixo: str = "Lote ",
                    *, lotes: list = None, numero: int = None, descricao: str = ""):
        """
        Cria lotes de forma flexível: em massa (quantidade), lista explícita ou individual.
        """
        created = []

        # 1. Criação via lista de objetos/dicts
        if isinstance(lotes, list) and lotes:
            for item in lotes:
                n = item.get('numero') or self.next_lote_numero()
                d = item.get('descricao') or ""
                obj = Lote.objects.create(processo=self, numero=n, descricao=d)
                created.append(obj)
            return created

        # 2. Criação individual
        if numero is not None or descricao:
            n = numero or self.next_lote_numero()
            obj = Lote.objects.create(processo=self, numero=n, descricao=descricao or "")
            created.append(obj)
            return created

        # 3. Criação em massa (ex: criar 10 lotes de uma vez)
        if quantidade and quantidade > 0:
            start = self.next_lote_numero()
            for i in range(quantidade):
                n = start + i
                d = f"{descricao_prefixo}{n}"
                obj = Lote.objects.create(processo=self, numero=n, descricao=d)
                created.append(obj)
            return created

        raise ValidationError("Parâmetros insuficientes para criação de lotes.")

    @transaction.atomic
    def organizar_lotes(self, ordem_ids: list = None, normalizar: bool = False,
                        inicio: int = 1, mapa: list = None):
        """
        Reordena ou renomeia os números dos lotes.
        """
        # Caso 1: Reordenar baseado em lista de IDs
        if isinstance(ordem_ids, list) and ordem_ids:
            qs = list(self.lotes.filter(id__in=ordem_ids))
            id2obj = {o.id: o for o in qs}
            numero = inicio or 1
            for _id in ordem_ids:
                obj = id2obj.get(_id)
                if obj:
                    obj.numero = numero
                    obj.save(update_fields=['numero'])
                    numero += 1
            return self.lotes.order_by('numero')

        # Caso 2: Normalizar sequência (1, 2, 3...)
        if normalizar:
            numero = inicio or 1
            for obj in self.lotes.order_by('numero', 'id'):
                if obj.numero != numero:
                    obj.numero = numero
                    obj.save(update_fields=['numero'])
                numero += 1
            return self.lotes.order_by('numero')

        # Caso 3: Mapa explícito (ID -> Novo Número)
        if isinstance(mapa, list) and mapa:
            ids = [m.get('id') for m in mapa if m.get('id') is not None]
            qs = self.lotes.filter(id__in=ids)
            id2obj = {o.id: o for o in qs}
            for m in mapa:
                _id = m.get('id')
                num = m.get('numero')
                if _id in id2obj and isinstance(num, int) and num > 0:
                    obj = id2obj[_id]
                    obj.numero = num
                    obj.save(update_fields=['numero'])
            return self.lotes.order_by('numero')

        raise ValidationError("Parâmetros insuficientes para organização de lotes.")


# ============================================================
# 📦 LOTE
# ============================================================

class Lote(models.Model):
    processo = models.ForeignKey(ProcessoLicitatorio, related_name='lotes', on_delete=models.CASCADE)
    numero = models.PositiveIntegerField()
    descricao = models.TextField(blank=True, null=True)
    valor_total = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)

    class Meta:
        ordering = ['numero']
        constraints = [
            models.UniqueConstraint(fields=['processo', 'numero'], name='uniq_lote_processo_numero'),
        ]

    def __str__(self):
        return f"Lote {self.numero} ({self.processo.numero_processo})"


# ============================================================
# 🏭 FORNECEDOR
# ============================================================

class Fornecedor(models.Model):
    cnpj_cpf = models.CharField(max_length=18, unique=True, verbose_name="CNPJ/CPF")
    nome = models.CharField(max_length=255) # Alias para razao_social para compatibilidade
    razao_social = models.CharField(max_length=255)
    nome_fantasia = models.CharField(max_length=255, blank=True, null=True)
    tipo_pessoa = models.CharField(max_length=2, choices=TIPO_PESSOA_CHOICES, default='PJ')
    porte = models.CharField(max_length=100, blank=True, null=True)
    
    # Contato
    telefone = models.CharField(max_length=20, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    
    # Endereço
    cep = models.CharField(max_length=20, blank=True, null=True)
    logradouro = models.CharField(max_length=255, blank=True, null=True)
    numero = models.CharField(max_length=50, blank=True, null=True)
    bairro = models.CharField(max_length=100, blank=True, null=True)
    complemento = models.CharField(max_length=255, blank=True, null=True)
    uf = models.CharField(max_length=2, blank=True, null=True)
    municipio = models.CharField(max_length=100, blank=True, null=True)
    
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['razao_social']

    def __str__(self):
        return self.nome or self.razao_social or self.cnpj_cpf
    
    def save(self, *args, **kwargs):
        if not self.nome and self.razao_social:
            self.nome = self.razao_social
        elif not self.razao_social and self.nome:
            self.razao_social = self.nome
        super().save(*args, **kwargs)


# ============================================================
# 📋 ITEM
# ============================================================

class Item(models.Model):
    processo = models.ForeignKey(
        ProcessoLicitatorio, 
        related_name='itens', 
        on_delete=models.CASCADE
    )
    lote = models.ForeignKey(
        Lote, 
        related_name='itens', 
        on_delete=models.SET_NULL, 
        blank=True, 
        null=True
    )
    # Vencedor do item (atalho)
    fornecedor = models.ForeignKey(
        Fornecedor, 
        related_name='itens_vencidos', 
        on_delete=models.SET_NULL, 
        blank=True, 
        null=True
    )

    numero = models.IntegerField(default=1) # Campo 'ordem' renomeado para 'numero' para padronização
    descricao = models.CharField(max_length=255)
    especificacao = models.TextField(
        blank=True, 
        null=True, 
        help_text="Especificação detalhada do item."
    )
    codigo_catmat = models.CharField(max_length=20, blank=True, null=True, verbose_name="Código CATMAT/CATSER")
    
    unidade = models.CharField(max_length=50)
    quantidade = models.DecimalField(max_digits=12, decimal_places=4)
    valor_estimado = models.DecimalField(max_digits=15, decimal_places=4)
    valor_total = models.DecimalField(max_digits=15, decimal_places=2, editable=False)
    
    natureza_despesa = models.CharField(max_length=10, choices=NATUREZAS_DESPESA, blank=True, null=True)
    tipo_organizacao = models.CharField(max_length=10, choices=TIPO_ORGANIZACAO_CHOICES, default='ITEM')

    class Meta:
        ordering = ['numero']
        constraints = [
            models.UniqueConstraint(fields=['processo', 'numero'], name='uniq_item_processo_numero'),
        ]

    def __str__(self):
        return f"Item {self.numero} - {self.descricao[:30]} ({self.processo.numero_processo})"

    def clean(self):
        """Validação de integridade."""
        if self.lote and self.lote.processo_id != self.processo_id:
            raise ValidationError("O lote selecionado pertence a outro processo.")

    def save(self, *args, **kwargs):
        """Cálculo de total e auto-numeração."""
        if self.quantidade and self.valor_estimado:
            self.valor_total = self.quantidade * self.valor_estimado
        else:
            self.valor_total = 0
            
        if self._state.adding and (self.numero is None or self.numero <= 0):
            last = Item.objects.filter(processo=self.processo).order_by('-numero').first()
            self.numero = (last.numero + 1) if last else 1
        super().save(*args, **kwargs)


# ============================================================
# 🔗 FORNECEDOR ↔ PROCESSO (Participantes)
# ============================================================

class FornecedorProcesso(models.Model):
    processo = models.ForeignKey(
        ProcessoLicitatorio, 
        on_delete=models.CASCADE, 
        related_name='participantes'
    )
    fornecedor = models.ForeignKey(
        Fornecedor, 
        on_delete=models.CASCADE, 
        related_name='processos_participados'
    )
    data_participacao = models.DateField(auto_now_add=True)
    habilitado = models.BooleanField(default=True)
    vencedor = models.BooleanField(default=False)
    valor_adjudicado = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)

    class Meta:
        unique_together = (('processo', 'fornecedor'),)
        verbose_name = "Fornecedor do Processo"
        verbose_name_plural = "Fornecedores do Processo"

    def __str__(self):
        return f"{self.fornecedor} - {self.processo.numero_processo}"


# ============================================================
# 💰 ITEM ↔ FORNECEDOR (Propostas)
# ============================================================

class ItemFornecedor(models.Model):
    item = models.ForeignKey(Item, related_name='propostas', on_delete=models.CASCADE)
    fornecedor = models.ForeignKey(Fornecedor, related_name='propostas', on_delete=models.CASCADE)
    valor_proposto = models.DecimalField(max_digits=14, decimal_places=2)
    vencedor = models.BooleanField(default=False)

    class Meta:
        unique_together = (('item', 'fornecedor'),)
        verbose_name = "Proposta de Fornecedor"
        verbose_name_plural = "Propostas de Fornecedores"

    def __str__(self):
        return f"{self.item.descricao} - {self.fornecedor}"


# ============================================================
# 📑 CONTRATO / EMPENHO
# ============================================================

class ContratoEmpenho(models.Model):
    processo = models.ForeignKey(
        ProcessoLicitatorio, 
        related_name='contratos', 
        on_delete=models.PROTECT
    )

    tipo_contrato_id = models.PositiveIntegerField()
    numero_contrato_empenho = models.CharField(max_length=64)
    ano_contrato = models.PositiveIntegerField()
    processo_ref = models.CharField(max_length=64, blank=True, null=True)
    categoria_processo_id = models.PositiveIntegerField(blank=True, null=True)
    receita = models.BooleanField(default=False)

    unidade_codigo = models.CharField(max_length=32, blank=True, null=True)
    ni_fornecedor = models.CharField(max_length=14, blank=True, null=True)
    
    tipo_pessoa_fornecedor = models.CharField(
        max_length=2,
        choices=TIPO_PESSOA_CHOICES,
        blank=True,
        null=True
    )

    sequencial_publicacao = models.PositiveIntegerField(blank=True, null=True)
    
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-criado_em']

    def __str__(self):
        return f"Contrato/Empenho {self.numero_contrato_empenho}/{self.ano_contrato}"