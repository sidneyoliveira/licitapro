# backend/api/admin.py

from django.contrib import admin

from .models import CustomUser, Entidade, Orgao, Fornecedor, ProcessoLicitatorio, ItemProcesso, ItemCatalogo

admin.site.register(CustomUser)
admin.site.register(Entidade)
admin.site.register(Orgao)
admin.site.register(Fornecedor) 
admin.site.register(ProcessoLicitatorio)
admin.site.register(ItemCatalogo)

@admin.register(ItemProcesso)
class ItemProcessoAdmin(admin.ModelAdmin):
    list_display = ('id', 'processo', 'item_catalogo', 'quantidade', 'ordem')
    list_filter = ('processo',)
    search_fields = ('item_catalogo__descricao',)

    def save_model(self, request, obj, form, change):
        """
        Sobrescreve o método de salvar do admin para calcular a ordem.
        """
        if not obj.pk and obj.processo:
            try:
                ordem_max = ItemProcesso.objects.filter(processo=obj.processo).latest('ordem').ordem
                obj.ordem = ordem_max + 1
            except ItemProcesso.DoesNotExist:
                obj.ordem = 1
        
        super().save_model(request, obj, form, change)