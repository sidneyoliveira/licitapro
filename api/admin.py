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
    list_display = ('numero', 'modalidade', 'status', 'orgao', 'data_abertura')
    search_fields = ('numero', 'objeto', 'orgao__nome')
    list_filter = ('modalidade', 'status', 'orgao__entidade')
    inlines = [LoteInline]


@admin.register(Lote)
class LoteAdmin(admin.ModelAdmin):
    list_display = ('numero', 'processo', 'descricao')
    search_fields = ('processo__numero', 'descricao')
    list_filter = ('processo',)


# ============================================================
# Fornecedores e Participações
# ============================================================

@admin.register(Fornecedor)
class FornecedorAdmin(admin.ModelAdmin):
    list_display = ('nome', 'cnpj', 'email', 'telefone')
    search_fields = ('nome', 'cnpj')
    list_filter = ('criado_em',)


@admin.register(FornecedorProcesso)
class FornecedorProcessoAdmin(admin.ModelAdmin):
    list_display = ('processo', 'fornecedor', 'habilitado', 'data_participacao')
    list_filter = ('habilitado', 'processo')
    search_fields = ('fornecedor__nome', 'processo__numero')


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
    search_fields = ('item__descricao', 'fornecedor__nome')
