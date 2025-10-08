# backend/api/admin.py

from django.contrib import admin
from django import forms
from django.db.models import Max

from .models import (
    CustomUser,
    Entidade,
    Orgao,
    ProcessoLicitatorio,
    ItemProcesso,
    Fornecedor,
    ItemFornecedor
)


class ItemProcessoForm(forms.ModelForm):
    class Meta:
        model = ItemProcesso
        fields = '__all__'

    def clean(self):
        cleaned = super().clean()
        # Se for criação (instance ainda não tem pk), computa a próxima ordem
        if not self.instance.pk:
            processo = cleaned.get('processo')
            if processo:
                ordem_max = ItemProcesso.objects.filter(processo=processo).aggregate(Max('ordem'))['ordem__max']
                next_ordem = (ordem_max or 0) + 1
                cleaned['ordem'] = next_ordem
                # garante que a instância também receba o valor antes de validate_unique
                self.instance.ordem = next_ordem
        return cleaned


@admin.register(ItemProcesso)
class ItemProcessoAdmin(admin.ModelAdmin):
    form = ItemProcessoForm
    list_display = ('id', 'descricao', 'unidade', 'quantidade', 'processo', 'ordem')
    list_filter = ('processo',)
    search_fields = ('descricao', 'especificacao')

    def get_readonly_fields(self, request, obj=None):
        # Ao editar, não deixar alterar a ordem manualmente (opcional)
        if obj:
            return ('ordem',)
        return ()

    def save_model(self, request, obj, form, change):
        """
        Backup: se por algum motivo a ordem não tiver sido definida no form,
        tenta definir aqui antes de salvar.
        """
        if not change and not getattr(obj, 'ordem', None) and obj.processo:
            ordem_max = ItemProcesso.objects.filter(processo=obj.processo).aggregate(Max('ordem'))['ordem__max']
            obj.ordem = (ordem_max or 0) + 1

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
