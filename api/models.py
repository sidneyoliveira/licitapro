# backend/api/models.py

from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone
from django.db.models import Max
from django.core.exceptions import ValidationError

class CustomUser(AbstractUser):
    cpf = models.CharField(max_length=14, unique=True, null=True, blank=True)
    data_nascimento = models.DateField(null=True, blank=True)
    groups = models.ManyToManyField('auth.Group', related_name='customuser_set', blank=True)
    user_permissions = models.ManyToManyField('auth.Permission', related_name='customuser_set', blank=True)

    def __str__(self):
        return self.get_full_name() or self.username


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


class ProcessoLicitatorio(models.Model):
    class Modalidade(models.TextChoices):
        PREGAO_ELETRONICO = 'Pregão Eletrônico'
        CONCORRENCIA_ELETRONICA = 'Concorrência Eletrônica'
        DISPENSA_ELETRONICA = 'Dispensa Eletrônica'
        INEXIGIBILIDADE_ELETRONICA = 'Inexigibilidade Eletrônica'
        ADESAO_ARP = 'Adesão a Registro de Preços'
        CREDENCIAMENTO = 'Credenciamento'

    class Classificacao(models.TextChoices):
        COMPRAS = 'Compras'
        SERVICOS_COMUNS = 'Serviços Comuns'
        SERVICOS_ENGENHARIA = 'Serviços de Engenharia Comuns'
        OBRAS_COMUNS = 'Obras Comuns'

    class Situacao(models.TextChoices):
        ABERTO = 'Aberto'
        EM_PESQUISA = 'Em Pesquisa'
        AGUARDANDO_PUBLICACAO = 'Aguardando Publicação'
        PUBLICADO = 'Publicado'
        EM_CONTRATACAO = 'Em Contratação'
        ADJUDICADO_HOMOLOGADO = 'Adjudicado/Homologado'
        REVOGADO_CANCELADO = 'Revogado/Cancelado'

    class Organizacao(models.TextChoices):
        LOTE = 'Lote'
        ITEM = 'Item'

    objeto = models.TextField()
    numero_processo = models.CharField(max_length=50)
    data_processo = models.DateField()
    modalidade = models.CharField(max_length=50, choices=Modalidade.choices)
    classificacao = models.CharField(max_length=50, choices=Classificacao.choices)
    orgao = models.ForeignKey(Orgao, on_delete=models.PROTECT, related_name="processos")
    tipo_organizacao = models.CharField(max_length=10, choices=Organizacao.choices)
    registro_precos = models.BooleanField(default=False)
    situacao = models.CharField(max_length=50, choices=Situacao.choices, default=Situacao.EM_PESQUISA)
    data_criacao_sistema = models.DateTimeField(auto_now_add=True)
    valor_referencia = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    numero_certame = models.CharField(max_length=50, blank=True, null=True)
    data_abertura = models.DateTimeField(null=True, blank=True)
    vigencia_meses = models.PositiveIntegerField(blank=True, null=True)

    class Meta:
        ordering = ['-data_processo']

    def __str__(self):
        return f"{self.numero_processo}"


class ItemProcesso(models.Model):
    processo = models.ForeignKey('ProcessoLicitatorio', related_name='itens', on_delete=models.CASCADE)
    descricao = models.CharField(max_length=255)
    especificacao = models.TextField(blank=True, null=True)
    unidade = models.CharField(max_length=20)
    quantidade = models.DecimalField(max_digits=12, decimal_places=4)
    ordem = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ['ordem']
        unique_together = (('processo', 'ordem'),)

    def __str__(self):
        return f"Item {self.ordem} - {self.descricao}"

    @staticmethod
    def reorder_items(processo_id, item_id, nova_ordem):

        itens = list(ItemProcesso.objects.filter(processo_id=processo_id).order_by('ordem'))
        item = next((i for i in itens if i.id == item_id), None)
        if not item:
            return

        itens.remove(item)
        # Insere o item na nova posição (lista é 0-based)
        itens.insert(nova_ordem - 1, item)

        # Atualiza todas as ordens
        for idx, i in enumerate(itens, start=1):
            ItemProcesso.objects.filter(id=i.id).update(ordem=idx)
    
    
class Fornecedor(models.Model):
    razao_social = models.CharField(max_length=255)
    cnpj = models.CharField(max_length=18)
    email = models.EmailField(blank=True, null=True)
    telefone = models.CharField(max_length=30, blank=True, null=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['razao_social']
        unique_together = (('razao_social', 'cnpj'),)

    def __str__(self):
        return self.razao_social


class ItemFornecedor(models.Model):
    item = models.ForeignKey(ItemProcesso, related_name='fornecedores_vinculados', on_delete=models.CASCADE)
    fornecedor = models.ForeignKey(Fornecedor, related_name='itens_cotados', on_delete=models.CASCADE)
    preco_unitario = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    observacao = models.TextField(blank=True, null=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = (('item', 'fornecedor'),)
        ordering = ['-criado_em']

    def __str__(self):
        return f"{self.fornecedor} -> {self.item}"
