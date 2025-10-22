from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone


# ============================================================
# USUÁRIO PERSONALIZADO
# ============================================================

class CustomUser(AbstractUser):
    cpf = models.CharField(max_length=14, unique=True, null=True, blank=True)
    data_nascimento = models.DateField(null=True, blank=True)
    groups = models.ManyToManyField('auth.Group', related_name='customuser_set', blank=True)
    user_permissions = models.ManyToManyField('auth.Permission', related_name='customuser_set', blank=True)

    def __str__(self):
        return self.get_full_name() or self.username


# ============================================================
# ENTIDADE / ÓRGÃO
# ============================================================

class Entidade(models.Model):
    nome = models.CharField(max_length=200, unique=True)
    cnpj = models.CharField(max_length=18, unique=True, null=True, blank=True)
    ano = models.IntegerField(default=timezone.now().year, verbose_name="Ano de Exercício")

    def __str__(self):
        return f"{self.nome} ({self.ano})"


class Orgao(models.Model):
    nome = models.CharField(max_length=255)
    entidade = models.ForeignKey(Entidade, related_name='orgaos', on_delete=models.CASCADE)

    def __str__(self):
        return f"{self.nome} - {self.entidade.nome}"


# ============================================================
# PROCESSO LICITATÓRIO
# ============================================================

class ProcessoLicitatorio(models.Model):
    class Modalidade(models.TextChoices):
        PREGAO_ELETRONICO = 'Pregão Eletrônico'
        CONCORRENCIA_ELETRONICA = 'Concorrência Eletrônica'
        DISPENSA_ELETRONICA = 'Dispensa Eletrônica'
        INEXIGIBILIDADE_ELETRONICA = 'Inexigibilidade Eletrônica'
        ADESAO_ARP = 'Adesão a Registro de Preços'
        CREDENCIAMENTO = 'Credenciamento'

    class Situacao(models.TextChoices):
        ABERTO = 'Aberto'
        EM_PESQUISA = 'Em Pesquisa'
        AGUARDANDO_PUBLICACAO = 'Aguardando Publicação'
        PUBLICADO = 'Publicado'
        EM_CONTRATACAO = 'Em Contratação'
        ADJUDICADO_HOMOLOGADO = 'Adjudicado/Homologado'
        REVOGADO_CANCELADO = 'Revogado/Cancelado'

    numero = models.CharField(max_length=50, unique=True)
    objeto = models.TextField()
    modalidade = models.CharField(max_length=100, choices=Modalidade.choices)
    data_abertura = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=50, choices=Situacao.choices, default=Situacao.EM_PESQUISA)
    valor_referencia = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    orgao = models.ForeignKey(Orgao, related_name='processos', on_delete=models.PROTECT)

    data_criacao_sistema = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-data_abertura']

    def __str__(self):
        return f"{self.numero}"


# ============================================================
# LOTE
# ============================================================

class Lote(models.Model):
    processo = models.ForeignKey(ProcessoLicitatorio, on_delete=models.CASCADE, related_name='lotes')
    numero = models.PositiveIntegerField()
    descricao = models.TextField(blank=True, null=True)

    class Meta:
        unique_together = ('processo', 'numero')

    def __str__(self):
        return f"Lote {self.numero} - {self.processo.numero}"


# ============================================================
# FORNECEDOR
# ============================================================

class Fornecedor(models.Model):
    nome = models.CharField(max_length=255)
    cnpj = models.CharField(max_length=18, unique=True)
    telefone = models.CharField(max_length=30, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    endereco = models.CharField(max_length=255, blank=True, null=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['nome']

    def __str__(self):
        return self.nome


# ============================================================
# ITEM (dentro de um processo e opcionalmente dentro de um lote)
# ============================================================

class Item(models.Model):
    processo = models.ForeignKey(ProcessoLicitatorio, related_name='itens', on_delete=models.CASCADE)
    lote = models.ForeignKey(Lote, related_name='itens', on_delete=models.SET_NULL, null=True, blank=True)
    fornecedor = models.ForeignKey(Fornecedor, related_name='itens', on_delete=models.SET_NULL, null=True, blank=True)
    descricao = models.CharField(max_length=255)
    unidade = models.CharField(max_length=20)
    quantidade = models.DecimalField(max_digits=12, decimal_places=2)
    valor_estimado = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    ordem = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ['ordem']
        unique_together = ('processo', 'ordem')

    def __str__(self):
        return f"{self.descricao} ({self.processo.numero})"


# ============================================================
# FORNECEDOR ↔ PROCESSO (participantes)
# ============================================================

class FornecedorProcesso(models.Model):
    processo = models.ForeignKey(ProcessoLicitatorio, on_delete=models.CASCADE, related_name='fornecedores')
    fornecedor = models.ForeignKey(Fornecedor, on_delete=models.CASCADE, related_name='processos')
    data_participacao = models.DateField(auto_now_add=True)
    habilitado = models.BooleanField(default=True)

    class Meta:
        unique_together = ('processo', 'fornecedor')

    def __str__(self):
        return f"{self.fornecedor.nome} - {self.processo.numero}"


# ============================================================
# ITEM ↔ FORNECEDOR (propostas e vencedor)
# ============================================================

class ItemFornecedor(models.Model):
    item = models.ForeignKey(Item, related_name='propostas', on_delete=models.CASCADE)
    fornecedor = models.ForeignKey(Fornecedor, related_name='propostas', on_delete=models.CASCADE)
    valor_proposto = models.DecimalField(max_digits=14, decimal_places=2)
    vencedor = models.BooleanField(default=False)

    class Meta:
        unique_together = ('item', 'fornecedor')

    def __str__(self):
        return f"{self.item.descricao} - {self.fornecedor.nome}"
