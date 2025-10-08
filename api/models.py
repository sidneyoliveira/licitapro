# backend/api/models.py

from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone

class CustomUser(AbstractUser):
    cpf = models.CharField(max_length=14, unique=True, null=True, blank=True)
    data_nascimento = models.DateField(null=True, blank=True)
    # Mantém os relacionamentos padrão de grupos/perms sem conflito
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
    # enums
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

    # Campos
    objeto = models.TextField()
    numero_processo = models.CharField(max_length=50)
    data_processo = models.DateField()
    modalidade = models.CharField(max_length=50, choices=Modalidade.choices)
    classificacao = models.CharField(max_length=50, choices=Classificacao.choices)
    orgao = models.ForeignKey(Orgao, on_delete=models.PROTECT, related_name="processos")
    tipo_organizacao = models.CharField(max_length=10, choices=Organizacao.choices)
    registro_precos = models.BooleanField(default=False)
    situacao = models.CharField(max_length=50, choices=Situacao.choices, default=Situacao.EM_PESQUISA)

    # automáticos / opcionais
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
    """
    Item diretamente associado a um Processo.
    Não há catálogo: cada item pertence a um processo.
    """
    processo = models.ForeignKey(ProcessoLicitatorio, related_name='itens', on_delete=models.CASCADE)
    descricao = models.CharField(max_length=255)
    especificacao = models.TextField(blank=True, null=True)
    unidade = models.CharField(max_length=20)
    quantidade = models.DecimalField(max_digits=12, decimal_places=4)
    ordem = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ['ordem']
        unique_together = (('processo', 'ordem'),)  # mantém a regra de unicidade

    def __str__(self):
        return f"Item {self.id} - {self.descricao}"

    @staticmethod
    def reorder_items(processo_id, new_order_ids):
        """
        Reordena itens de um processo sem causar conflito de unique_together.
        new_order_ids: lista de IDs de ItemProcesso na ordem desejada
        """
        # Busca todos os itens do processo
        itens = ItemProcesso.objects.filter(processo_id=processo_id)
        # Atribui valores temporários para evitar conflito
        for idx, item_id in enumerate(new_order_ids, start=1):
            ItemProcesso.objects.filter(id=item_id).update(ordem=idx + 1000)
        # Atualiza para valores finais
        for idx, item_id in enumerate(new_order_ids, start=1):
            ItemProcesso.objects.filter(id=item_id).update(ordem=idx)


class Fornecedor(models.Model):
    """
    Cadastro de fornecedores no sistema (catálogo de fornecedores).
    Fornecedor pode ser vinculado a processos posteriormente.
    """
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
    """
    Tabela de ligação entre ItemProcesso e Fornecedor.
    Prepara o sistema para quando você quiser associar cada item a um fornecedor (ou vários),
    preços por fornecedor, lotes, etc. Não é obrigatório para cadastrar itens, mas já existe.
    """
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