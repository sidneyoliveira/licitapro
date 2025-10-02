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