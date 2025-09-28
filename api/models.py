# backend/api/models.py

from django.db import models
from django.contrib.auth.models import AbstractUser

# --- MODELO DE UTILIZADOR (sem alterações) ---
class CustomUser(AbstractUser):
    cpf = models.CharField(max_length=14, unique=True, null=True, blank=True)
    data_nascimento = models.DateField(null=True, blank=True)
    groups = models.ManyToManyField('auth.Group', related_name='customuser_set', blank=True)
    user_permissions = models.ManyToManyField('auth.Permission', related_name='customuser_set', blank=True)

# --- MODELOS DE SUPORTE (aperfeiçoados) ---
class Fornecedor(models.Model):
    razao_social = models.CharField(max_length=255)
    # Campo CNPJ mantido, mas sem o validador customizado
    cnpj = models.CharField(max_length=18, unique=True)
    email = models.EmailField()
    
    def __str__(self):
        return self.razao_social

class Entidade(models.Model):
    nome = models.CharField(max_length=200, unique=True)
    # Campo CNPJ mantido, mas sem o validador customizado
    cnpj = models.CharField(max_length=18, unique=True, null=True, blank=True)

    def __str__(self):
        return self.nome
    
    class Meta:
        verbose_name = "Entidade"
        verbose_name_plural = "Entidades"

class Orgao(models.Model):
    nome = models.CharField(max_length=255)
    entidade = models.ForeignKey(Entidade, related_name='orgaos', on_delete=models.CASCADE, null=True, blank=True)

    def __str__(self):
        if self.entidade:
            return f"{self.nome} ({self.entidade.nome})"
        return self.nome
    
    class Meta:
        verbose_name = "Órgão"
        verbose_name_plural = "Órgãos"

# --- MODELO PRINCIPAL (aperfeiçoado) ---
class ProcessoLicitatorio(models.Model):
    """ 
    Modelo de Processo Licitatório aperfeiçoado com TextChoices para melhor
    manutenção e índices de base de dados para melhor performance.
    """
    
    class Modalidade(models.TextChoices):
        PREGAO_ELETRONICO = 'Pregão Eletrônico'
        CONCORRENCIA = 'Concorrência Eletrônica'
        DISPENSA = 'Dispensa Eletrônica'
        INEXIGIBILIDADE = 'Inexigibilidade Eletrônica'
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
        HOMOLOGADO = 'Adjudicado/Homologado'
        CANCELADO = 'Revogado/Cancelado'

    class Organizacao(models.TextChoices):
        LOTE = 'Lote'
        ITEM = 'Item'

    # --- CAMPOS OBRIGATÓRIOS ---
    objeto = models.TextField()
    numero_processo = models.CharField(max_length=50, verbose_name="Número", db_index=True)
    numero_certame = models.CharField(max_length=50, verbose_name="Número do Certame", db_index=True)
    modalidade = models.CharField(max_length=50, choices=Modalidade.choices)
    classificacao = models.CharField(max_length=50, choices=Classificacao.choices)
    data_cadastro = models.DateField(auto_now_add=True, verbose_name="Data de Cadastro")
    orgao = models.ForeignKey(Orgao, on_delete=models.PROTECT, related_name="processos")

    # --- CAMPOS OPCIONAIS ---
    tipo_organizacao = models.CharField(max_length=10, choices=Organizacao.choices, blank=True, null=True, verbose_name="Tipo de Organização")
    vigencia_meses = models.PositiveIntegerField(blank=True, null=True, verbose_name="Vigência (Meses)")
    situacao = models.CharField(max_length=50, choices=Situacao.choices, blank=True, null=True, db_index=True)
    registro_precos = models.BooleanField(default=False)
    data_publicacao = models.DateField(null=True, blank=True, verbose_name="Data do Processo")
    data_abertura = models.DateTimeField(null=True, blank=True, verbose_name="Abertura da Contratação")
    valor_referencia = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, verbose_name="Valor de Referência")
    
    def __str__(self):
        return f"{self.numero_processo} - {self.objeto[:50]}"
    
    class Meta:
        verbose_name = "Processo Licitatório"
        verbose_name_plural = "Processos Licitatórios"
        ordering = ['-data_cadastro']