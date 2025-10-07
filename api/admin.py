# backend/api/admin.py

from django.contrib import admin
from .models import CustomUser, Entidade, Orgao, Fornecedor, ProcessoLicitatorio, ItemProcesso, ItemCatalogo

# Register your models here.

# Para permitir a gestão básica dos seus modelos na área de administração
admin.site.register(CustomUser)
admin.site.register(Entidade)
admin.site.register(Orgao)
admin.site.register(Fornecedor)
admin.site.register(ProcessoLicitatorio)
admin.site.register(ItemProcesso)

@admin.register(ItemProcesso)
class ItemProcessoAdmin(admin.ModelAdmin):
    list_display = ('id', 'processo', 'item_catalogo', 'quantidade', 'ordem')
    list_filter = ('processo',)
    search_fields = ('item_catalogo__descricao',)
    
    def save_model(self, request, obj, form, change):
        """
        Sobrescreve o método de salvar do admin para calcular a ordem.
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