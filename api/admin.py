# backend/api/admin.py
from django.contrib import admin
from .models import CustomUser, Entidade, Orgao, ProcessoLicitatorio, ItemProcesso, FornecedorProcesso

@admin.register(ItemProcesso)
class ItemProcessoAdmin(admin.ModelAdmin):
    list_display = ('id', 'descricao', 'unidade', 'quantidade', 'processo', 'ordem')
    list_filter = ('processo',)
    search_fields = ('descricao',)
    
admin.site.register(CustomUser)
admin.site.register(Entidade)
admin.site.register(Orgao)
admin.site.register(ProcessoLicitatorio)
admin.site.register(FornecedorProcesso)