from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone

# Estenda o usuário padrão para adicionar campos extras
class CustomUser(AbstractUser):
    cpf = models.CharField(max_length=14, unique=True, null=True, blank=True)
    data_nascimento = models.DateField(null=True, blank=True)
    groups = models.ManyToManyField('auth.Group', related_name='customuser_set', blank=True)
    user_permissions = models.ManyToManyField('auth.Permission', related_name='customuser_set', blank=True)

class Fornecedor(models.Model):
    razao_social = models.CharField(max_length=255)
    cnpj = models.CharField(max_length=18, unique=True)
    email = models.EmailField()
    def __str__(self):
        return self.razao_social

class Entidade(models.Model):

    nome = models.CharField(max_length=200, unique=True)
    cnpj = models.CharField(max_length=18, unique=True, null=True, blank=True)

    def __str__(self):
        return self.nome

class Orgao(models.Model):
    """
    Modelo de Órgão vinculado a uma Entidade.
    """
    nome = models.CharField(max_length=255)
    entidade = models.ForeignKey(Entidade, related_name='orgaos', on_delete=models.CASCADE, null=True, blank=True)

    def __str__(self):
        return f"{self.nome} ({self.entidade.nome})"

class ProcessoLicitatorio(models.Model):
    """ Modelo de Processo Licitatório com os novos campos e organização. """
    
    MODALIDADE_CHOICES = [
        ('Pregão Eletrônico', 'Pregão Eletrônico'),
        ('Concorrência Eletrônica', 'Concorrência Eletrônica'),
        ('Dispensa Eletrônica', 'Dispensa Eletrônica'),
        ('Inexigibilidade Eletrônica', 'Inexigibilidade Eletrônica'),
        ('Adesão a Registro de Preços', 'Adesão a Registro de Preços'),
        ('Credenciamento', 'Credenciamento'),
    ]
    CLASSIFICACAO_CHOICES = [
        ('Compras', 'Compras'),
        ('Serviços Comuns', 'Serviços Comuns'),
        ('Serviços de Engenharia Comuns', 'Serviços de Engenharia Comuns'),
        ('Obras Comuns', 'Obras Comuns'),
    ]
    SITUACAO_CHOICES = [
        ('Aberto', 'Aberto'),
        ('Em Pesquisa', 'Em Pesquisa'),
        ('Aguardando Publicação', 'Aguardando Publicação'),
        ('Publicado', 'Publicado'),
        ('Em Contratação', 'Em Contratação'),
        ('Adjudicado/Homologado', 'Adjudicado/Homologado'),
        ('Revogado/Cancelado', 'Revogado/Cancelado'),
    ]
    ORGANIZACAO_CHOICES = [
        ('Lote', 'Lote'),
        ('Item', 'Item'),
    ]

    # --- CAMPOS OBRIGATÓRIOS ---
    objeto = models.TextField()
    numero_processo = models.CharField(max_length=50, verbose_name="Número")
    numero_certame = models.CharField(max_length=50, verbose_name="Número do Certame")
    modalidade = models.CharField(max_length=50, choices=MODALIDADE_CHOICES)
    classificacao = models.CharField(max_length=50, choices=CLASSIFICACAO_CHOICES)
    data_cadastro = models.DateField(default=timezone.now, verbose_name="Data do Processo")
    orgao = models.ForeignKey(Orgao, on_delete=models.PROTECT, related_name="processos")

    # --- CAMPOS OPCIONAIS ---
    tipo_organizacao = models.CharField(max_length=4, choices=ORGANIZACAO_CHOICES, blank=True, null=True, verbose_name="Tipo de Organização")
    vigencia_meses = models.PositiveIntegerField(blank=True, null=True, verbose_name="Vigência (Meses)")
    situacao = models.CharField(max_length=50, choices=SITUACAO_CHOICES, blank=True, null=True)
    registro_precos = models.BooleanField(default=False)
    data_publicacao = models.DateField(null=True, blank=True, verbose_name="Data da Publicação")
    data_abertura = models.DateTimeField(null=True, blank=True, verbose_name="Abertura da Contratação")
    valor_referencia = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, verbose_name="Valor de Referência")

    def __str__(self):
        return f"{self.numero_processo} - {self.objeto[:50]}"