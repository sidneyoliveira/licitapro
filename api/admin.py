# backend/api/admin.py
from django.contrib import admin
from .models import (
    CustomUser,
    Entidade,
    Orgao,
    ProcessoLicitatorio,
    ItemProcesso,
    Fornecedor,
    ItemFornecedor
)


@admin.register(ItemProcesso)
class ItemProcessoAdmin(admin.ModelAdmin):
    list_display = ('id', 'descricao', 'unidade', 'quantidade', 'processo', 'ordem')
    list_filter = ('processo',)
    search_fields = ('descricao', 'especificacao')


@admin.register(Fornecedor)
class FornecedorAdmin(admin.ModelAdmin):
    list_display = ('id', 'razao_social', 'cnpj', 'email', 'telefone')
    search_fields = ('razao_social', 'cnpj')


@admin.register(ProcessoLicitatorio)
class ProcessoAdmin(admin.ModelAdmin):
    list_display = ('id', 'numero_processo', 'objeto', 'data_processo', 'situacao', 'orgao')
    search_fields = ('numero_processo', 'objeto')
    list_filter = ('situacao', 'modalidade', 'classificacao')


admin.site.register(CustomUser)
admin.site.register(Entidade)
admin.site.register(Orgao)
admin.site.register(ItemFornecedor)