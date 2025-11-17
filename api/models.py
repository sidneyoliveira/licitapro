from django.db import models, transaction
from django.contrib.auth.models import AbstractUser
from django.utils import timezone
from django.core.exceptions import ValidationError

# ============================================================
# 👤 USUÁRIO PERSONALIZADO
# ============================================================

class CustomUser(AbstractUser):
    cpf = models.CharField(max_length=14, unique=True, null=True, blank=True)
    data_nascimento = models.DateField(null=True, blank=True)
    phone = models.CharField(max_length=20, null=True, blank=True)
    profile_image = models.ImageField(upload_to='profile_pics/', null=True, blank=True)

    # Corrige conflitos de related_name duplicados no admin
    groups = models.ManyToManyField('auth.Group', related_name='customuser_groups', blank=True)
    user_permissions = models.ManyToManyField('auth.Permission', related_name='customuser_permissions', blank=True)

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

    # Código da Unidade Compradora (genérico, atende PNCP e outros)
    codigo_unidade = models.CharField(
        max_length=32,
        blank=True,
        null=True,
        help_text='Código da Unidade Compradora (ex.: 1010)'
    )

    # 🔹 Agora pode ficar em branco inclusive no banco (null=True)
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
    # -------------------------------
    # Identificação / objetos
    # -------------------------------
    numero_processo = models.CharField(max_length=50, blank=True, null=True)
    numero_certame = models.CharField(max_length=50, blank=True, null=True)
    objeto = models.TextField(blank=True, null=True)

    # -------------------------------
    # Classificadores principais
    # -------------------------------
    modalidade = models.CharField(
        max_length=50,
        blank=True,
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
        blank=True,
        choices=[
            ('Compras', 'Compras'),
            ('Serviços Comuns', 'Serviços Comuns'),
            ('Serviços de Engenharia Comuns', 'Serviços de Engenharia Comuns'),
            ('Obras Comuns', 'Obras Comuns'),
        ],
    )
    tipo_organizacao = models.CharField(
        max_length=10,
        blank=True,
        choices=[('Lote', 'Lote'), ('Item', 'Item')],
    )

    situacao = models.CharField(
        max_length=50,
        blank=True,
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

    # -------------------------------
    # Datas e valores
    # -------------------------------
    data_processo = models.DateField(blank=True, null=True)
    data_abertura = models.DateTimeField(blank=True, null=True)

    valor_referencia = models.DecimalField(max_digits=14, decimal_places=2, blank=True, null=True)
    vigencia_meses = models.PositiveIntegerField(blank=True, null=True)

    # SRP (Registro de Preço) – alias compatível com o front (registro_precos)
    registro_preco = models.BooleanField(default=False, blank=True, verbose_name="Registro de Preço")

    # -------------------------------
    # Relações
    # -------------------------------
    # 🔹 Agora podem ser nulos na importação
    entidade = models.ForeignKey(
        'Entidade',
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name='processos'
    )
    orgao = models.ForeignKey(
        'Orgao',
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name='processos'
    )

    data_criacao_sistema = models.DateTimeField(auto_now_add=True, blank=True)

    # -------------------------------
    # Domínios (IDs oficiais PNCP) – continuam aqui para publicação
    # -------------------------------
    instrumento_convocatorio_id = models.PositiveIntegerField(blank=True, null=True)
    modalidade_id = models.PositiveIntegerField(blank=True, null=True)
    modo_disputa_id = models.PositiveIntegerField(blank=True, null=True)
    criterio_julgamento_id = models.PositiveIntegerField(blank=True, null=True)
    amparo_legal_id = models.PositiveIntegerField(blank=True, null=True)
    situacao_contratacao_id = models.PositiveIntegerField(blank=True, null=True)

    # -------------------------------
    # Campos textuais selecionados no sistema (o front envia estes)
    # Mantemos ambos: texto para UX/auditoria e *_id para PNCP
    # -------------------------------
    fundamentacao = models.CharField(
        max_length=16,
        choices=[
            ("lei_14133", "Lei 14.133/21"),
            ("lei_8666",  "Lei 8.666/93"),
            ("lei_10520", "Lei 10.520/02"),
        ],
        blank=True,
        null=True,
    )
    amparo_legal = models.CharField(max_length=64, blank=True, null=True)
    modo_disputa = models.CharField(max_length=24, blank=True, null=True)
    criterio_julgamento = models.CharField(max_length=32, blank=True, null=True)

    # -------------------------------
    # Identificação da compra
    # -------------------------------
    numero_compra = models.CharField(max_length=32, blank=True, null=True)
    ano_compra = models.PositiveIntegerField(blank=True, null=True)

    # -------------------------------
    # Janela de propostas
    # -------------------------------
    abertura_propostas = models.DateTimeField(blank=True, null=True)
    encerramento_propostas = models.DateTimeField(blank=True, null=True)

    # -------------------------------
    # Links
    # -------------------------------
    link_sistema_origem = models.URLField(blank=True, null=True)
    link_processo_eletronico = models.URLField(blank=True, null=True)

    # -------------------------------
    # Controle/retornos da publicação
    # -------------------------------
    sequencial_publicacao = models.PositiveIntegerField(blank=True, null=True)
    id_controle_publicacao = models.CharField(max_length=64, blank=True, null=True)
    ultima_atualizacao_publicacao = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ['-data_processo']
        verbose_name = "Processo Licitatório"
        verbose_name_plural = "Processos Licitatórios"

    def __str__(self):
        return f"{self.numero_certame}"

    # -------------------------------
    # Alias compatível com o front (registro_precos)
    # -------------------------------
    @property
    def registro_precos(self):
        return self.registro_preco

    @registro_precos.setter
    def registro_precos(self, value):
        self.registro_preco = bool(value)

    # -------------------------------
    # Helpers de Lotes
    # -------------------------------
    def next_lote_numero(self) -> int:
        ultimo = self.lotes.order_by('-numero').first()
        return (ultimo.numero + 1) if ultimo else 1

    @transaction.atomic
    def criar_lotes(self, quantidade: int = None, descricao_prefixo: str = "Lote ",
                    *, lotes: list = None, numero: int = None, descricao: str = ""):
        created = []

        if isinstance(lotes, list) and lotes:
            for item in lotes:
                n = item.get('numero') or self.next_lote_numero()
                d = item.get('descricao') or ""
                obj = Lote.objects.create(processo=self, numero=n, descricao=d)
                created.append(obj)
            return created

        if numero is not None or descricao:
            n = numero or self.next_lote_numero()
            obj = Lote.objects.create(processo=self, numero=n, descricao=descricao or "")
            created.append(obj)
            return created

        if quantidade and quantidade > 0:
            start = self.next_lote_numero()
            for i in range(quantidade):
                n = start + i
                d = f"{descricao_prefixo}{n}"
                obj = Lote.objects.create(processo=self, numero=n, descricao=d)
                created.append(obj)
            return created

        raise ValidationError("Parâmetros inválidos para criação de lotes.")

    @transaction.atomic
    def organizar_lotes(self, ordem_ids: list[int] = None, normalizar: bool = False,
                        inicio: int = 1, mapa: list[dict] = None):
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

        if normalizar:
            numero = inicio or 1
            for obj in self.lotes.order_by('numero', 'id'):
                if obj.numero != numero:
                    obj.numero = numero
                    obj.save(update_fields=['numero'])
                numero += 1
            return self.lotes.order_by('numero')

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

        raise ValidationError("Parâmetros inválidos para organização de lotes.")


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

    # Ordem sequencial no processo (pode ser usado como número do item no envio)
    ordem = models.PositiveIntegerField(default=1)

    # ================================================
    # COMPLEMENTOS GENÉRICOS PARA PUBLICAÇÃO
    # ================================================
    natureza = models.CharField(
        max_length=1,
        choices=(('M', 'Material'), ('S', 'Serviço')),
        blank=True,
        null=True,
        help_text='M = Material, S = Serviço'
    )
    tipo_beneficio_id = models.PositiveIntegerField(blank=True, null=True)
    criterio_julgamento_id = models.PositiveIntegerField(blank=True, null=True)

    catalogo_id = models.PositiveIntegerField(blank=True, null=True)
    categoria_item_catalogo_id = models.PositiveIntegerField(blank=True, null=True)
    catalogo_codigo_item = models.CharField(max_length=64, blank=True, null=True)

    class Meta:
        ordering = ['ordem']
        constraints = [
            models.UniqueConstraint(fields=['processo', 'ordem'], name='uniq_item_processo_ordem'),
        ]

    def __str__(self):
        return f"{self.descricao} ({self.processo.numero_processo})"

    def clean(self):
        # se tem lote, ele precisa pertencer ao mesmo processo
        if self.lote and self.lote.processo_id != self.processo_id:
            raise ValidationError("O lote selecionado pertence a outro processo.")

    def save(self, *args, **kwargs):
        # atribui próxima ordem automaticamente se não vier definida (apenas na criação)
        if getattr(self, "_state", None) and self._state.adding and (self.ordem is None or self.ordem <= 0):
            last = Item.objects.filter(processo=self.processo).order_by('-ordem').first()
            self.ordem = (last.ordem + 1) if last else 1
        super().save(*args, **kwargs)


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
        return f"{self.fornecedor.razao_social or self.fornecedor.cnpj} - {self.processo.numero_processo}"


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


# ============================================================
# 📑 CONTRATO / EMPENHO (GENÉRICO PARA PUBLICAÇÃO)
# ============================================================

class ContratoEmpenho(models.Model):
    processo = models.ForeignKey(ProcessoLicitatorio, related_name='contratos', on_delete=models.PROTECT)

    tipo_contrato_id = models.PositiveIntegerField()
    numero_contrato_empenho = models.CharField(max_length=64)
    ano_contrato = models.PositiveIntegerField()
    processo_ref = models.CharField(max_length=64, blank=True, null=True)  # Nº do processo administrativo
    categoria_processo_id = models.PositiveIntegerField(blank=True, null=True)
    receita = models.BooleanField(default=False)

    # Unidade compradora
    unidade_codigo = models.CharField(max_length=32, blank=True, null=True)

    # Fornecedor
    ni_fornecedor = models.CharField(max_length=14, blank=True, null=True)  # CNPJ/CPF sem formatação
    tipo_pessoa_fornecedor = models.CharField(
        max_length=2,
        choices=(('PJ', 'Pessoa Jurídica'), ('PF', 'Pessoa Física')),
        blank=True,
        null=True
    )

    # Controle de publicação (genérico)
    sequencial_publicacao = models.PositiveIntegerField(blank=True, null=True)

    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-criado_em']

    def __str__(self):
        return f"Contrato/Empenho {self.numero_contrato_empenho}/{self.ano_contrato}"
