# backend/api/models.py

from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone

class CustomUser(AbstractUser):
    cpf = models.CharField(max_length=14, unique=True, null=True, blank=True)
    data_nascimento = models.DateField(null=True, blank=True)
    groups = models.ManyToManyField('auth.Group', related_name='customuser_set', blank=True)
    user_permissions = models.ManyToManyField('auth.Permission', related_name='customuser_set', blank=True)

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
        return f"{self.nome} ({self.entidade.nome})"

class Fornecedor(models.Model):
    razao_social = models.CharField(max_length=255)
    cnpj = models.CharField(max_length=18, unique=True)
    email = models.EmailField(blank=True, null=True)
    telefone = models.CharField(max_length=20, blank=True, null=True)
    def __str__(self):
        return self.razao_social

class ItemCatalogo(models.Model):

    descricao = models.CharField(max_length=255, unique=True)
    especificacao = models.TextField(blank=True, null=True)
    unidade = models.CharField(max_length=20)

    class Meta:
        ordering = ['descricao']

    def __str__(self):
        return self.descricao
    
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

    # --- CAMPOS OBRIGATÓRIOS ---
    objeto = models.TextField()
    numero_processo = models.CharField(max_length=50)
    data_processo = models.DateField(verbose_name="Data do Processo") # A única data obrigatória
    modalidade = models.CharField(max_length=50, choices=Modalidade.choices)
    classificacao = models.CharField(max_length=50, choices=Classificacao.choices)
    orgao = models.ForeignKey(Orgao, on_delete=models.PROTECT, related_name="processos")
    tipo_organizacao = models.CharField(max_length=10, choices=Organizacao.choices)
    registro_precos = models.BooleanField(default=False)

    # --- CAMPO AUTOMÁTICO (para referência interna) ---
    data_criacao_sistema = models.DateTimeField(auto_now_add=True)
    
    # --- CAMPOS OPCIONAIS ---
    numero_certame = models.CharField(max_length=50, blank=True, null=True)
    data_abertura = models.DateTimeField(null=True, blank=True)
    valor_referencia = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    vigencia_meses = models.PositiveIntegerField(blank=True, null=True)
    situacao = models.CharField(max_length=50, choices=Situacao.choices, blank=True, null=True)
    fornecedores_participantes = models.ManyToManyField(Fornecedor, related_name='processos_participados', blank=True)

    def __str__(self):
        return self.numero_processo
    
    class Meta:
        ordering = ['-data_processo']

class ItemProcesso(models.Model):
 
    processo = models.ForeignKey(ProcessoLicitatorio, related_name='itens_do_processo', on_delete=models.CASCADE)
    item_catalogo = models.ForeignKey(ItemCatalogo, related_name='nos_processos', on_delete=models.PROTECT)
    quantidade = models.DecimalField(max_digits=10, decimal_places=2)
    ordem = models.PositiveIntegerField(default=0)

    class Meta:
        # Garante que não podemos adicionar o mesmo item do catálogo duas vezes no mesmo processo
        unique_together = ('processo', 'item_catalogo')
        ordering = ['id']

    def __str__(self):
        return f"{self.item_catalogo.descricao} no processo {self.processo.numero_processo}"