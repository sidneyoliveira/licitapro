# api/models.py

from django.db import models, transaction
from django.contrib.auth.models import AbstractUser
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.db.models import Q

# Importação das escolhas (Choices) atualizadas (agora baseadas em IDs inteiros)
from .choices import (
    NATUREZAS_DESPESA_CHOICES,
    MODO_DISPUTA_CHOICES,
    CRITERIO_JULGAMENTO_CHOICES,
    AMPARO_LEGAL_CHOICES,
    MODALIDADE_CHOICES,
    SITUACAO_CHOICES,          # String
    TIPO_ORGANIZACAO_CHOICES,  # String
    INSTRUMENTO_CONVOCATORIO_CHOICES,
    SITUACAO_ITEM_CHOICES,     # Novo
    TIPO_BENEFICIO_CHOICES,    # Novo
    CATEGORIA_ITEM_CHOICES     # Novo
)

# ============================================================
# 👤 USUÁRIO PERSONALIZADO
# ============================================================

class CustomUser(AbstractUser):
    cpf = models.CharField(max_length=14, unique=True, null=True, blank=True)
    data_nascimento = models.DateField(null=True, blank=True)
    phone = models.CharField(max_length=20, null=True, blank=True)
    profile_image = models.ImageField(upload_to='profile_pics/', null=True, blank=True)

    # Ajustes para compatibilidade com o admin do Django
    groups = models.ManyToManyField(
        'auth.Group', 
        related_name='customuser_groups', 
        blank=True
    )
    user_permissions = models.ManyToManyField(
        'auth.Permission', 
        related_name='customuser_permissions', 
        blank=True
    )

    def __str__(self):
        return self.get_full_name() or self.username


# ============================================================
# 🏛️ ENTIDADE / ÓRGÃO
# ============================================================

class Entidade(models.Model):
    nome = models.CharField(max_length=200, unique=True)
    cnpj = models.CharField(max_length=18, unique=True, null=True, blank=True)
    ano = models.IntegerField(default=timezone.now().year, verbose_name="Ano de Exercício")

    class Meta:
        ordering = ['nome']

    def __str__(self):
        return f"{self.nome} ({self.ano})"


class Orgao(models.Model):
    nome = models.CharField(max_length=255)
    
    # Código genérico (atende PNCP e outros sistemas)
    codigo_unidade = models.CharField(
        max_length=32,
        blank=True,
        null=True,
        help_text='Código da Unidade Compradora (ex.: 1010)'
    )

    entidade = models.ForeignKey(
        Entidade,
        related_name='orgaos',
        blank=True,
        null=True,
        on_delete=models.CASCADE
    )

    class Meta:
        ordering = ['nome']

    def __str__(self):
        return f"{self.nome} - {self.entidade.nome if self.entidade else 'Sem Entidade'}"


# ============================================================
# 📄 PROCESSO LICITATÓRIO
# ============================================================

class ProcessoLicitatorio(models.Model):
    # --- Identificação ---
    numero_processo = models.CharField(max_length=50, blank=True, null=True)
    numero_certame = models.CharField(max_length=50, blank=True, null=True)
    objeto = models.TextField(blank=True, null=True)

    # --- Classificadores ---
    # Agora Modalidade é Inteiro (ID do PNCP)
    modalidade = models.IntegerField(choices=MODALIDADE_CHOICES, blank=True, null=True, verbose_name="Modalidade (ID)")
    
    # Classificação ainda pode ser string se for controle interno, ou ajustar se houver tabela PNCP
    classificacao = models.CharField(max_length=50, blank=True, null=True) 
    
    tipo_organizacao = models.CharField(max_length=10, blank=True, choices=TIPO_ORGANIZACAO_CHOICES)
    
    situacao = models.CharField(
        max_length=50, 
        blank=True, 
        choices=SITUACAO_CHOICES,
        default='em_pesquisa'
    )

    # --- Datas e Valores ---
    data_processo = models.DateField(blank=True, null=True)
    data_abertura = models.DateTimeField(blank=True, null=True)
    valor_referencia = models.DecimalField(max_digits=14, decimal_places=2, blank=True, null=True)
    vigencia_meses = models.PositiveIntegerField(blank=True, null=True)

    # SRP (Registro de Preço)
    registro_preco = models.BooleanField(default=False, blank=True, verbose_name="Registro de Preço")

    # --- Relações ---
    entidade = models.ForeignKey(
        Entidade, 
        on_delete=models.PROTECT, 
        blank=True, 
        null=True, 
        related_name='processos'
    )
    orgao = models.ForeignKey(
        Orgao, 
        on_delete=models.PROTECT, 
        blank=True, 
        null=True, 
        related_name='processos'
    )

    data_criacao_sistema = models.DateTimeField(auto_now_add=True, blank=True)

    # --- Detalhes Jurídicos/PNCP (Agora IDs Inteiros) ---
    instrumento_convocatorio = models.IntegerField(choices=INSTRUMENTO_CONVOCATORIO_CHOICES, blank=True, null=True, verbose_name="Instrumento Convocatório (ID)")
    amparo_legal = models.IntegerField(choices=AMPARO_LEGAL_CHOICES, blank=True, null=True, verbose_name="Amparo Legal (ID)")
    modo_disputa = models.IntegerField(choices=MODO_DISPUTA_CHOICES, blank=True, null=True, verbose_name="Modo de Disputa (ID)")
    criterio_julgamento = models.IntegerField(choices=CRITERIO_JULGAMENTO_CHOICES, blank=True, null=True, verbose_name="Critério de Julgamento (ID)")

    # Mantido campo legado para não quebrar migrations antigas imediatamente, se desejar remover depois
    fundamentacao = models.CharField(max_length=50, blank=True, null=True, help_text="Campo legado. Use instrumento_convocatorio.")
    pncp_publicado_em = models.DateTimeField(blank=True, null=True)
    pncp_ano_compra = models.PositiveIntegerField(blank=True, null=True)
    pncp_sequencial_compra = models.PositiveIntegerField(blank=True, null=True)

    pncp_link = models.URLField(blank=True, null=True)
    pncp_ultimo_retorno = models.JSONField(blank=True, null=True)
    class Meta:
        ordering = ['-data_processo']
        verbose_name = "Processo Licitatório"
        verbose_name_plural = "Processos Licitatórios"

    def __str__(self):
        return f"{self.numero_certame or self.numero_processo}"

    # --- Alias para Frontend (React espera 'registro_precos') ---
    @property
    def registro_precos(self):
        return self.registro_preco

    @registro_precos.setter
    def registro_precos(self, value):
        self.registro_preco = bool(value)

    # --- Lógica de Negócio (Fat Model) ---

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



class DocumentoPNCP(models.Model):
    STATUS = (
        ("rascunho", "Rascunho (local)"),
        ("enviado", "Enviado ao PNCP"),
        ("erro", "Erro no envio"),
        ("removido", "Removido"),
    )

    processo = models.ForeignKey(
        ProcessoLicitatorio,
        related_name="docs_pncp",
        on_delete=models.CASCADE
    )

    tipo_documento_id = models.PositiveIntegerField()
    titulo = models.CharField(max_length=255, default="Documento")
    observacao = models.TextField(blank=True, null=True)

    # Recomendo manter obrigatório (bom para integridade)
    arquivo = models.FileField(upload_to="documentos_pncp/")
    arquivo_nome = models.CharField(max_length=255, blank=True, null=True)
    arquivo_hash = models.CharField(max_length=80, blank=True, null=True)

    status = models.CharField(max_length=20, choices=STATUS, default="rascunho")

    pncp_sequencial_documento = models.PositiveIntegerField(blank=True, null=True)
    pncp_publicado_em = models.DateTimeField(blank=True, null=True)

    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["processo", "tipo_documento_id"],
                condition=Q(ativo=True) & ~Q(status="removido"),
                name="uniq_docpncp_processo_tipo_ativo"
            )
        ]

    def __str__(self):
        return f"{self.processo_id} - tipo {self.tipo_documento_id} - {self.status}"
# ============================================================
# 📦 LOTE
# ============================================================

class Lote(models.Model):
    processo = models.ForeignKey(ProcessoLicitatorio, related_name='lotes', on_delete=models.CASCADE)
    numero = models.PositiveIntegerField()
    descricao = models.TextField(blank=True, null=True)

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
    cnpj = models.CharField(max_length=18, unique=True)
    razao_social = models.CharField(max_length=255)
    nome_fantasia = models.CharField(max_length=255, blank=True, null=True)
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
        return self.razao_social or self.cnpj


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
    fornecedor = models.ForeignKey(
        Fornecedor, 
        related_name='itens', 
        on_delete=models.SET_NULL, 
        blank=True, 
        null=True
    )

    descricao = models.CharField(max_length=255)
    especificacao = models.TextField(
        blank=True, 
        null=True, 
        help_text="Especificação detalhada do item (vindo da planilha)."
    )
    
    unidade = models.CharField(max_length=20)
    quantidade = models.DecimalField(max_digits=12, decimal_places=4) # Aumentei decimais para precisão
    valor_estimado = models.DecimalField(max_digits=14, decimal_places=2, blank=True, null=True)
    
    ordem = models.PositiveIntegerField(default=1)
    
    # Classificadores (Atualizados para PNCP)
    natureza = models.CharField(max_length=8, choices=NATUREZAS_DESPESA_CHOICES, blank=True, null=True)
    
    # Novos campos com IDs Inteiros
    situacao_item = models.IntegerField(choices=SITUACAO_ITEM_CHOICES, default=1, verbose_name="Situação do Item (ID)")
    tipo_beneficio = models.IntegerField(choices=TIPO_BENEFICIO_CHOICES, blank=True, null=True, verbose_name="Tipo de Benefício (ID)")
    categoria_item = models.IntegerField(choices=CATEGORIA_ITEM_CHOICES, blank=True, null=True, verbose_name="Categoria do Item (ID)")

    pncp_numero_item = models.PositiveIntegerField(blank=True, null=True)
    pncp_ultima_atualizacao = models.DateTimeField(blank=True, null=True)
    class Meta:
        ordering = ['ordem']
        constraints = [
            models.UniqueConstraint(fields=['processo', 'ordem'], name='uniq_item_processo_ordem'),
        ]

    def __str__(self):
        return f"{self.descricao} ({self.processo.numero_processo})"

    def clean(self):
        """Validação de integridade: Item não pode estar em Lote de outro Processo."""
        if self.lote and self.lote.processo_id != self.processo_id:
            raise ValidationError("O lote selecionado pertence a outro processo.")

    def save(self, *args, **kwargs):
        """Auto-numeração do campo 'ordem' se não fornecido."""
        if self._state.adding and (self.ordem is None or self.ordem <= 0):
            last = Item.objects.filter(processo=self.processo).order_by('-ordem').first()
            self.ordem = (last.ordem + 1) if last else 1
        super().save(*args, **kwargs)


# ============================================================
# 🔗 FORNECEDOR ↔ PROCESSO (Participantes)
# ============================================================

class FornecedorProcesso(models.Model):
    processo = models.ForeignKey(
        ProcessoLicitatorio, 
        on_delete=models.CASCADE, 
        related_name='fornecedores_processo'
    )
    fornecedor = models.ForeignKey(
        Fornecedor, 
        on_delete=models.CASCADE, 
        related_name='processos'
    )
    data_participacao = models.DateField(auto_now_add=True)
    habilitado = models.BooleanField(default=True)

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
    
    # Ajuste: se Tipo de Pessoa tiver um Choices definido, use aqui
    tipo_pessoa_fornecedor = models.CharField(
        max_length=2,
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

# ============================================================
# 📝 ANOTAÇÕES
# ============================================================

class Anotacao(models.Model):
    usuario = models.ForeignKey(
        CustomUser, 
        on_delete=models.CASCADE, 
        related_name='anotacoes'
    )
    texto = models.TextField()
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-criado_em'] # Mais recentes primeiro
        verbose_name = "Anotação"
        verbose_name_plural = "Anotações"

    def __str__(self):
        return f"Nota de {self.usuario.username} em {self.criado_em.strftime('%d/%m/%Y')}"
    

# ============================================================
# 📝 ARQUIVOS DO USUARIO
# ============================================================

class ArquivoUser(models.Model):
    usuario = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='arquivos'
    )
    arquivo = models.FileField(upload_to='arquivos-user/')
    descricao = models.CharField(max_length=255, blank=True, null=True)
    enviado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-enviado_em']
        verbose_name = "Arquivo do Usuário"
        verbose_name_plural = "Arquivos dos Usuários"

    def __str__(self):
        return f"Arquivo de {self.usuario.username} - {self.descricao or self.arquivo.name}"

# ============================================================
# 📜 ATA DE REGISTRO DE PREÇOS
# ============================================================

class AtaRegistroPrecos(models.Model):
    STATUS_CHOICES = (
        ("rascunho", "Rascunho (local)"),
        ("publicada", "Publicada no PNCP"),
        ("cancelada", "Cancelada"),
    )

    processo = models.ForeignKey(
        ProcessoLicitatorio,
        related_name="atas_registro",
        on_delete=models.CASCADE,
    )

    numero_ata = models.CharField(max_length=50)
    ano_ata = models.PositiveIntegerField()

    data_assinatura = models.DateField(blank=True, null=True)

    # alinhado com o PNCP (dataInicioVigencia / dataFimVigencia)
    data_vigencia_inicio = models.DateField(blank=True, null=True)
    data_vigencia_fim = models.DateField(blank=True, null=True)

    observacao = models.TextField(blank=True, null=True)

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="rascunho",
    )

    # PNCP
    pncp_sequencial_ata = models.PositiveIntegerField(blank=True, null=True)
    numero_controle_pncp = models.CharField(max_length=100, blank=True, null=True)
    pncp_publicada_em = models.DateTimeField(blank=True, null=True)

    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-criado_em"]
        verbose_name = "Ata de Registro de Preços"
        verbose_name_plural = "Atas de Registro de Preços"

    def __str__(self):
        return f"Ata {self.numero_ata}/{self.ano_ata} - {self.processo}"


class DocumentoAtaRegistroPrecos(models.Model):
    STATUS = (
        ("rascunho", "Rascunho (local)"),
        ("enviado", "Enviado ao PNCP"),
        ("erro", "Erro no envio"),
        ("removido", "Removido"),
    )

    ata = models.ForeignKey(
        AtaRegistroPrecos,
        related_name="documentos",
        on_delete=models.CASCADE,
    )

    tipo_documento_id = models.PositiveIntegerField()
    titulo = models.CharField(max_length=255, default="Documento da Ata")
    observacao = models.TextField(blank=True, null=True)

    arquivo = models.FileField(upload_to="atas_registro_pncp/")
    arquivo_nome = models.CharField(max_length=255, blank=True, null=True)
    arquivo_hash = models.CharField(max_length=80, blank=True, null=True)

    status = models.CharField(
        max_length=20,
        choices=STATUS,
        default="rascunho",
    )

    pncp_sequencial_documento = models.PositiveIntegerField(blank=True, null=True)
    pncp_publicado_em = models.DateTimeField(blank=True, null=True)

    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-criado_em"]

    def __str__(self):
        return f"Doc Ata {self.titulo} ({self.ata})"
