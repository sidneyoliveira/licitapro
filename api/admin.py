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

    def save_model(self, request, obj, form, change):
        """
        Sobrescrevemos o método de salvar do admin.
        Esta função é chamada sempre que um ItemProcesso é salvo através da interface de admin.
        """
        # Se for um objeto novo (não uma edição)
        if not obj.pk and obj.processo:
            # Encontra a ordem mais alta para os itens deste processo e adiciona 1.
            try:
                ordem_max = ItemProcesso.objects.filter(processo=obj.processo).latest('ordem').ordem
                obj.ordem = ordem_max + 1
            except ItemProcesso.DoesNotExist:
                # Se for o primeiro item do processo, a ordem é 1.
                obj.ordem = 1
        
        # Continua com o processo normal de salvar o objeto.
        super().save_model(request, obj, form, change)

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
