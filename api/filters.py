# api/filters.py
from django_filters import rest_framework as filters
from .models import ProcessoLicitatorio

class ProcessoFilter(filters.FilterSet):
    # Filtro para buscar no campo 'objeto' ou 'numero_processo' (case-insensitive)
    search = filters.CharFilter(method='filter_by_search', label='Search')

    class Meta:
        model = ProcessoLicitatorio
        fields = ['modalidade', 'situacao', 'orgao', 'classificacao',  'registro_precos']

    def filter_by_search(self, queryset, name, value):
        # Q objects permitem buscas complexas com OR
        from django.db.models import Q
        return queryset.filter(
            Q(objeto__icontains=value) | Q(numero_processo__icontains=value)
        )