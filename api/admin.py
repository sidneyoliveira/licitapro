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

# --- REGISTO DO NOVO MODELO DE CATÁLOGO ---
# Esta linha torna o seu catálogo de itens visível e gerível na área de administração
@admin.register(ItemCatalogo)
class ItemCatalogoAdmin(admin.ModelAdmin):
    list_display = ('descricao', 'unidade', 'especificacao')
    search_fields = ('descricao', 'especificacao')

class ItemProcessoAdmin(admin.ModelAdmin):
    list_display = ('id', 'processo', 'item_catalogo', 'quantidade', 'ordem')
    list_filter = ('processo',)
    search_fields = ('item_catalogo__descricao',)

    def save_model(self, request, obj, form, change):
        """
        Sobrescrevemos o método de salvar do admin.
        Esta função é chamada sempre que um ItemProcesso é salvo através da interface de admin.
        """
        # Se for um objeto novo (não uma edição), calculamos a ordem.
        if not obj.pk:
            # Encontra a ordem mais alta para os itens deste processo e adiciona 1.
            try:
                ordem_max = ItemProcesso.objects.filter(processo=obj.processo).latest('ordem').ordem
                obj.ordem = ordem_max + 1
            except ItemProcesso.DoesNotExist:
                # Se for o primeiro item do processo, a ordem é 1.
                obj.ordem = 1
        
        # Continua com o processo normal de salvar o objeto.
        super().save_model(request, obj, form, change)