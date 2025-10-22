from django.contrib import admin
from .models import (
    ProcessoLicitatorio,
    Item,
    Lote,
    Fornecedor,
    FornecedorProcesso,
    ItemFornecedor
)

# ---------------------------------------------------
# INLINE: permite cadastrar itens dentro do processo
# ---------------------------------------------------

class ItemInline(admin.TabularInline):
    model = Item
    extra = 1  # quantos campos extras aparecem
    fields = ('descricao', 'unidade', 'quantidade', 'valor_estimado', 'lote', 'fornecedor')
    autocomplete_fields = ('lote', 'fornecedor')
    show_change_link = True  # cria link pra editar item direto


class LoteInline(admin.TabularInline):
    model = Lote
    extra = 1
    fields = ('numero', 'descricao')
    show_change_link = True


class FornecedorProcessoInline(admin.TabularInline):
    model = FornecedorProcesso
    extra = 1
    autocomplete_fields = ('fornecedor',)
    fields = ('fornecedor', 'habilitado', 'data_participacao')


# ---------------------------------------------------
# ADMIN: Processo Licitatório
# ---------------------------------------------------

@admin.register(ProcessoLicitatorio)
class ProcessoLicitatorioAdmin(admin.ModelAdmin):
    list_display = ('numero', 'modalidade', 'data_abertura', 'status')
    list_filter = ('modalidade', 'status')
    search_fields = ('numero', 'objeto')
    date_hierarchy = 'data_abertura'
    inlines = [LoteInline, ItemInline, FornecedorProcessoInline]
    fieldsets = (
        ('Informações Básicas', {
            'fields': ('numero', 'objeto', 'modalidade', 'data_abertura', 'status')
        }),
    )


# ---------------------------------------------------
# ADMIN: Item
# ---------------------------------------------------

@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
    list_display = ('descricao_curta', 'processo', 'lote', 'fornecedor', 'quantidade', 'valor_estimado')
    list_filter = ('processo', 'lote', 'fornecedor')
    search_fields = ('descricao',)
    autocomplete_fields = ('processo', 'lote', 'fornecedor')

    def descricao_curta(self, obj):
        return obj.descricao[:50]
    descricao_curta.short_description = 'Descrição'


# ---------------------------------------------------
# ADMIN: Lote
# ---------------------------------------------------

@admin.register(Lote)
class LoteAdmin(admin.ModelAdmin):
    list_display = ('numero', 'processo', 'descricao_curta')
    list_filter = ('processo',)
    search_fields = ('descricao',)
    autocomplete_fields = ('processo',)

    def descricao_curta(self, obj):
        return obj.descricao[:50]
    descricao_curta.short_description = 'Descrição'


# ---------------------------------------------------
# ADMIN: Fornecedor
# ---------------------------------------------------

@admin.register(Fornecedor)
class FornecedorAdmin(admin.ModelAdmin):
    list_display = ('nome', 'cnpj', 'telefone', 'email')
    search_fields = ('nome', 'cnpj')
    list_filter = ('nome',)
    ordering = ('nome',)


# ---------------------------------------------------
# ADMIN: FornecedorProcesso
# ---------------------------------------------------

@admin.register(FornecedorProcesso)
class FornecedorProcessoAdmin(admin.ModelAdmin):
    list_display = ('fornecedor', 'processo', 'habilitado', 'data_participacao')
    list_filter = ('habilitado', 'processo')
    search_fields = ('fornecedor__nome', 'processo__numero')
    autocomplete_fields = ('fornecedor', 'processo')


# ---------------------------------------------------
# ADMIN: ItemFornecedor (Propostas)
# ---------------------------------------------------

@admin.register(ItemFornecedor)
class ItemFornecedorAdmin(admin.ModelAdmin):
    list_display = ('item', 'fornecedor', 'valor_proposto', 'vencedor')
    list_filter = ('vencedor', 'item__processo')
    search_fields = ('item__descricao', 'fornecedor__nome')
    autocomplete_fields = ('item', 'fornecedor')
