from django.db import models


# ============================================================
# 1️⃣ PROCESSO LICITATÓRIO
# ============================================================

class ProcessoLicitatorio(models.Model):
    numero = models.CharField(max_length=50, unique=True)
    objeto = models.TextField()
    modalidade = models.CharField(
        max_length=100,
        choices=[
            ('PREGÃO', 'Pregão'),
            ('CONVITE', 'Convite'),
            ('TOMADA', 'Tomada de Preços'),
            ('CONCORRÊNCIA', 'Concorrência'),
            ('DISPENSA', 'Dispensa de Licitação'),
            ('INEXIGIBILIDADE', 'Inexigibilidade'),
        ]
    )
    data_abertura = models.DateField()
    status = models.CharField(max_length=50, default='Em andamento')

    def __str__(self):
        return f"{self.numero} - {self.modalidade}"


# ============================================================
# 2️⃣ FORNECEDOR
# ============================================================

class Fornecedor(models.Model):
    nome = models.CharField(max_length=255)
    cnpj = models.CharField(max_length=18, unique=True)
    telefone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    endereco = models.TextField(blank=True)

    def __str__(self):
        return f"{self.nome} ({self.cnpj})"


# ============================================================
# 3️⃣ LOTE
# ============================================================

class Lote(models.Model):
    processo = models.ForeignKey(
        ProcessoLicitatorio,
        on_delete=models.CASCADE,
        related_name='lotes'
    )
    numero = models.PositiveIntegerField()
    descricao = models.TextField(blank=True)

    class Meta:
        unique_together = ('processo', 'numero')
        ordering = ['processo', 'numero']

    def __str__(self):
        return f"Lote {self.numero} - {self.processo.numero}"


# ============================================================
# 4️⃣ ITEM
# ============================================================

class Item(models.Model):
    processo = models.ForeignKey(
        ProcessoLicitatorio,
        on_delete=models.CASCADE,
        related_name='itens'
    )
    descricao = models.TextField()
    unidade = models.CharField(max_length=50)
    quantidade = models.DecimalField(max_digits=10, decimal_places=2)
    valor_estimado = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    lote = models.ForeignKey(
        Lote,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='itens'
    )
    fornecedor = models.ForeignKey(
        'Fornecedor',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='itens'
    )

    class Meta:
        ordering = ['processo', 'id']

    def __str__(self):
        return f"{self.descricao[:50]}"


# ============================================================
# 5️⃣ FORNECEDOR-PROCESSO (participantes)
# ============================================================

class FornecedorProcesso(models.Model):
    processo = models.ForeignKey(
        ProcessoLicitatorio,
        on_delete=models.CASCADE,
        related_name='fornecedores_participantes'
    )
    fornecedor = models.ForeignKey(Fornecedor, on_delete=models.CASCADE)
    data_participacao = models.DateField(auto_now_add=True)
    habilitado = models.BooleanField(default=False)

    class Meta:
        unique_together = ('processo', 'fornecedor')
        ordering = ['processo', 'fornecedor']

    def __str__(self):
        return f"{self.fornecedor.nome} no {self.processo.numero}"


# ============================================================
# 6️⃣ ITEM-FORNECEDOR (propostas)
# ============================================================

class ItemFornecedor(models.Model):
    item = models.ForeignKey(
        Item,
        on_delete=models.CASCADE,
        related_name='propostas'
    )
    fornecedor = models.ForeignKey(Fornecedor, on_delete=models.CASCADE)
    valor_proposto = models.DecimalField(max_digits=12, decimal_places=2)
    vencedor = models.BooleanField(default=False)

    class Meta:
        unique_together = ('item', 'fornecedor')
        ordering = ['item', 'valor_proposto']

    def __str__(self):
        return f"{self.item.descricao[:30]} - {self.fornecedor.nome}"
