from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone


# ============================================================
# 👤 USUÁRIO PERSONALIZADO
# ============================================================

class CustomUser(AbstractUser):
    cpf = models.CharField(max_length=14, unique=True, null=True, blank=True)
    data_nascimento = models.DateField(null=True, blank=True)

    # Corrige conflitos de related_name duplicados no admin
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
    entidade = models.ForeignKey(Entidade, related_name='orgaos', on_delete=models.CASCADE)

    class Meta:
        ordering = ['nome']

    def __str__(self):
        return f"{self.nome} - {self.entidade.nome}"


# ============================================================
# 📄 PROCESSO LICITATÓRIO
# ============================================================

class ProcessoLicitatorio(models.Model):
    numero = models.CharField(max_length=50, unique=True, blank=True)
    numero_processo = models.CharField(max_length=50, blank=True, null=True)
    numero_certame = models.CharField(max_length=50, blank=True, null=True)
    objeto = models.TextField()

    modalidade = models.CharField(
        max_length=50,
        choices=[
            ('Pregão Eletrônico', 'Pregão Eletrônico'),
            ('Concorrência Eletrônica', 'Concorrência Eletrônica'),
            ('Dispensa Eletrônica', 'Dispensa Eletrônica'),
            ('Inexigibilidade Eletrônica', 'Inexigibilidade Eletrônica'),
            ('Adesão a Registro de Preços', 'Adesão a Registro de Preços'),
            ('Credenciamento', 'Credenciamento'),
        ],
    )

    classificacao = models.CharField(
        max_length=50,
        choices=[
            ('Compras', 'Compras'),
            ('Serviços Comuns', 'Serviços Comuns'),
            ('Serviços de Engenharia Comuns', 'Serviços de Engenharia Comuns'),
            ('Obras Comuns', 'Obras Comuns'),
        ],
    )

    tipo_organizacao = models.CharField(
        max_length=10,
        choices=[('Lote', 'Lote'), ('Item', 'Item')],
    )

    situacao = models.CharField(
        max_length=50,
        choices=[
            ('Aberto', 'Aberto'),
            ('Em Pesquisa', 'Em Pesquisa'),
            ('Aguardando Publicação', 'Aguardando Publicação'),
            ('Publicado', 'Publicado'),
            ('Em Contratação', 'Em Contratação'),
            ('Adjudicado/Homologado', 'Adjudicado/Homologado'),
            ('Revogado/Cancelado', 'Revogado/Cancelado'),
        ],
        default='Em Pesquisa',
    )

    data_processo = models.DateField(blank=True, null=True)
    data_abertura = models.DateTimeField(blank=True, null=True)
    valor_referencia = models.DecimalField(max_digits=14, decimal_places=2, blank=True, null=True)
    vigencia_meses = models.PositiveIntegerField(blank=True, null=True)
    registro_preco = models.BooleanField(default=False, verbose_name="Registro de Preço")

    entidade = models.ForeignKey('Entidade', on_delete=models.PROTECT, related_name='processos')
    orgao = models.ForeignKey('Orgao', on_delete=models.PROTECT, related_name='processos')

    data_criacao_sistema = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-data_processo']
        verbose_name = "Processo Licitatório"
        verbose_name_plural = "Processos Licitatórios"

    def __str__(self):
        return f"{self.numero_certame or self.numero}"


# ============================================================
# 📦 LOTE
# ============================================================

class Lote(models.Model):
    processo = models.ForeignKey(ProcessoLicitatorio, related_name='lotes', on_delete=models.CASCADE)
    numero = models.PositiveIntegerField()
    descricao = models.TextField(blank=True, null=True)

    class Meta:
        unique_together = (('processo', 'numero'),)
        ordering = ['numero']

    def __str__(self):
        return f"Lote {self.numero} ({self.processo.numero})"


# ============================================================
# 🏭 FORNECEDOR
# ============================================================

class Fornecedor(models.Model):
    cnpj = models.CharField(max_length=18, unique=True)
    razao_social = models.CharField(max_length=255)
    nome_fantasia = models.CharField(max_length=255, blank=True, null=True)
    porte = models.CharField(max_length=100, blank=True, null=True)
    telefone = models.CharField(max_length=20, blank=True, null=True) 
    email = models.EmailField(blank=True, null=True)
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
        managed = True

    def __str__(self):
        return self.razao_social or self.cnpj


# ============================================================
# 📋 ITEM
# ============================================================

class Item(models.Model):
    processo = models.ForeignKey(ProcessoLicitatorio, related_name='itens', on_delete=models.CASCADE)
    descricao = models.CharField(max_length=255)
    unidade = models.CharField(max_length=20)
    quantidade = models.DecimalField(max_digits=12, decimal_places=2)
    valor_estimado = models.DecimalField(max_digits=14, decimal_places=2, blank=True, null=True)

    lote = models.ForeignKey(Lote, related_name='itens', on_delete=models.SET_NULL, blank=True, null=True)
    fornecedor = models.ForeignKey('Fornecedor', related_name='itens', on_delete=models.SET_NULL, blank=True, null=True)

    ordem = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ['ordem']
        unique_together = (('processo', 'ordem'),)

    def __str__(self):
        return f"{self.descricao} ({self.processo.numero})"


# ============================================================
# 🔗 FORNECEDOR ↔ PROCESSO
# ============================================================

class FornecedorProcesso(models.Model):
    processo = models.ForeignKey('ProcessoLicitatorio', on_delete=models.CASCADE, related_name='fornecedores_processo')
    fornecedor = models.ForeignKey('Fornecedor', on_delete=models.CASCADE, related_name='processos')
    data_participacao = models.DateField(auto_now_add=True)
    habilitado = models.BooleanField(default=True)

    class Meta:
        unique_together = (('processo', 'fornecedor'),)
        verbose_name = "Fornecedor do Processo"
        verbose_name_plural = "Fornecedores do Processo"

    def __str__(self):
        return f"{self.fornecedor.razao_social or self.fornecedor.cnpj} - {self.processo.numero}"


# ============================================================
# 💰 ITEM ↔ FORNECEDOR (propostas)
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
        return f"{self.item.descricao} - {self.fornecedor.razao_social or self.fornecedor.cnpj}"
