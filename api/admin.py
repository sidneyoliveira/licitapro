# api/admin.py
from django.contrib import admin
from .models import CustomUser, ProcessoLicitatorio, Orgao, Fornecedor

# Linha principal: registra o modelo de usuário para que ele apareça na área de admin
admin.site.register(CustomUser)

# Bônus: registre seus outros modelos para gerenciá-los facilmente
admin.site.register(ProcessoLicitatorio)
admin.site.register(Orgao)
admin.site.register(Fornecedor)