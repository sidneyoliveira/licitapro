from django.contrib import admin
from .models import (
    CustomUser,
    Entidade,
    Orgao,
    ProcessoLicitatorio,
    Lote,
    Fornecedor,
    FornecedorProcesso,
    Item,
    ItemFornecedor,
    Anotacao,
    ArquivoUser,
    DocumentoPNCP
)

# ============================================================
# CustomUser
# ============================================================

@admin.register(CustomUser)
class CustomUserAdmin(admin.ModelAdmin):
    list_display = ('username', 'email', 'cpf', 'is_staff', 'is_superuser')
    search_fields = ('username', 'email', 'cpf')
    list_filter = ('is_staff', 'is_superuser', 'is_active')


# ============================================================
# Entidade e Órgão
# ============================================================

@admin.register(Entidade)
class EntidadeAdmin(admin.ModelAdmin):
    list_display = ('nome', 'cnpj', 'ano')
    search_fields = ('nome', 'cnpj')


@admin.register(Orgao)
class OrgaoAdmin(admin.ModelAdmin):
    list_display = ('nome', 'entidade')
    search_fields = ('nome', 'entidade__nome')
    list_filter = ('entidade',)


# ============================================================
# Processo Licitatório e Lote
# ============================================================

class LoteInline(admin.TabularInline):
    model = Lote
    extra = 1


@admin.register(ProcessoLicitatorio)
class ProcessoLicitatorioAdmin(admin.ModelAdmin):
    list_display = ('id', 'situacao', 'modalidade', 'data_abertura')
    search_fields = ('objeto', 'orgao__nome')
    list_filter = ('modalidade', 'situacao')
    inlines = [LoteInline]


@admin.register(Lote)
class LoteAdmin(admin.ModelAdmin):
    list_display = ('numero', 'processo', 'descricao')
    search_fields = ('numero', 'descricao')
    list_filter = ('processo',)


# ============================================================
# Fornecedores e Participações
# ============================================================

@admin.register(Fornecedor)
class FornecedorAdmin(admin.ModelAdmin):
    list_display = (
        'razao_social',
        'nome_fantasia',
        'cnpj',
        'porte',
        'telefone',
        'email',
        'cep',
        'logradouro',
        'numero',
        'bairro',
        'complemento',
        'uf',
        'municipio',
        'criado_em',
    )

    search_fields = (
        'razao_social',
        'nome_fantasia',
        'cnpj',
        'email',
        'telefone',
        'municipio',
        'uf',
    )

    list_filter = (
        'porte',
        'uf',
        'municipio',
        'criado_em',
    )

    ordering = ('razao_social',)


@admin.register(FornecedorProcesso)
class FornecedorProcessoAdmin(admin.ModelAdmin):
    list_display = ('processo', 'fornecedor', 'habilitado', 'data_participacao')
    list_filter = ('habilitado', 'processo')
    search_fields = ('fornecedor__razaosocial', 'processo__numero')


# ============================================================
# Itens e Propostas
# ============================================================

class ItemFornecedorInline(admin.TabularInline):
    model = ItemFornecedor
    extra = 1


@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
    list_display = ('descricao', 'processo', 'lote', 'quantidade', 'unidade', 'ordem')
    search_fields = ('descricao', 'processo__numero')
    list_filter = ('processo', 'lote')
    inlines = [ItemFornecedorInline]


@admin.register(ItemFornecedor)
class ItemFornecedorAdmin(admin.ModelAdmin):
    list_display = ('item', 'fornecedor', 'valor_proposto', 'vencedor')
    list_filter = ('vencedor', 'fornecedor')
    search_fields = ('item__descricao', 'fornecedor__razaosocial')


@admin.register(Anotacao)
class AnotacaoAdmin(admin.ModelAdmin):
    list_display = ('id', 'usuario', 'texto',)


@admin.register(ArquivoUser)
class ArquivoUserAdmin(admin.ModelAdmin):
    list_display = ('id', 'usuario', 'arquivo', 'descricao', 'enviado_em')
    search_fields = ('usuario', 'descricao')

@admin.register(DocumentoPNCP)
class DocumentoPNCPAdmin(admin.ModelAdmin):
    list_display = ('id', 'processo', 'tipo_documento', 'titulo', 'arquivo_nome', 'criado_em')
    search_fields = ('processo__numero', 'titulo', 'arquivo_nome')
    list_filter = ('tipo_documento', 'criado_em')
                         