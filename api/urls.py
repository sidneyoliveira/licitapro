from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from django.conf.urls.static import static
from django.conf import settings

from .views import (
    EntidadeViewSet,
    OrgaoViewSet,
    ProcessoLicitatorioViewSet,
    LoteViewSet,
    ItemViewSet,
    FornecedorViewSet,
    FornecedorProcessoViewSet,
    ItemFornecedorViewSet,
    ContratoEmpenhoViewSet,
    ReorderItensView,
    CreateUserView,
    ManageUserView,
    DashboardStatsView,
    GoogleLoginView,
    UsuarioViewSet,
    ConstantesSistemaView,
    SystemConfigView,
    AnotacaoViewSet,
    NotificacaoViewSet,
    UsuarioLookupView,
    ArquivoUserViewSet,
    DocumentoPNCPViewSet,
    AtaRegistroPrecosViewSet,
    DocumentoAtaRegistroPrecosViewSet,
)

# ============================================================
# 🔗 ROTAS REGISTRADAS AUTOMATICAMENTE
# ============================================================

router = DefaultRouter()

# ENTIDADES / ÓRGÃOS
router.register(r'entidades', EntidadeViewSet, basename='entidade')
router.register(r'orgaos', OrgaoViewSet, basename='orgao')

# PROCESSO LICITATÓRIO
router.register(r'processos', ProcessoLicitatorioViewSet, basename='processo')

# LOTES / ITENS
router.register(r'lotes', LoteViewSet, basename='lote')
router.register(r'itens', ItemViewSet, basename='item')

# FORNECEDORES E RELACIONAMENTOS
router.register(r'fornecedores', FornecedorViewSet, basename='fornecedor')
router.register(r'fornecedores-processo', FornecedorProcessoViewSet, basename='fornecedor-processo')
router.register(r'itens-fornecedor', ItemFornecedorViewSet, basename='item-fornecedor')

# CONTRATOS
router.register(r'contratos', ContratoEmpenhoViewSet, basename='contrato')

# USUÁRIOS
router.register(r'usuarios', UsuarioViewSet, basename='usuario')

# ANOTAÇÕES
router.register(r'anotacoes', AnotacaoViewSet, basename='anotacao')
router.register(r'notificacoes', NotificacaoViewSet, basename='notificacao')

# ARQUIVOS DO USUÁRIO
router.register(r'arquivos-user', ArquivoUserViewSet, basename='arquivos-user')

# DOCUMENTOS PNCP (IMPORTANTE: definir basename)
router.register(r'documentos-pncp', DocumentoPNCPViewSet, basename='documento-pncp')
router.register(r'atas-registro-precos', AtaRegistroPrecosViewSet, basename='atas-registro-precos')
router.register(r'documentos-atas', DocumentoAtaRegistroPrecosViewSet, basename='documento-ata')

# ============================================================
# 🛣️ URLPATTERNS COMPLETO
# ============================================================

urlpatterns = [
    # Endpoints REST padrão (registrados via router)
    path('', include(router.urls)),

    # Ações customizadas
    path('reorder-itens/', ReorderItensView.as_view(), name='reorder-itens'),
    path('dashboard-stats/', DashboardStatsView.as_view(), name='dashboard-stats'),

    # Autenticação e gerenciamento de usuários
    path('register/', CreateUserView.as_view(), name='register'),
    path('me/', ManageUserView.as_view(), name="user-manage"),
    path('usuarios-lookup/', UsuarioLookupView.as_view(), name='usuarios-lookup'),

    # JWT Auth endpoints
    path('token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),

    # Login Google
    path('google/', GoogleLoginView.as_view(), name='google-login'),

    # Constantes / Config
    path('constantes/sistema/', ConstantesSistemaView.as_view(), name='constantes-sistema'),
    path('system/config/', SystemConfigView.as_view(), name='system-config'),
]

# Servir MEDIA em ambiente de desenvolvimento
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
