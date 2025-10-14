# backend/api/urls.py

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .views import (
    ProcessoViewSet,
    EntidadeViewSet,
    OrgaoViewSet,
    ItemProcessoViewSet,
    FornecedorViewSet,
    ReorderItemView,
    CreateUserView,
    ManageUserView,
    DashboardStatsView,
)

router = DefaultRouter()
router.register(r'processos', ProcessoViewSet, basename='processo')
router.register(r'entidades', EntidadeViewSet, basename='entidade')
router.register(r'orgaos', OrgaoViewSet, basename='orgao')
router.register(r'itens', ItemProcessoViewSet, basename='item')
router.register(r'fornecedores', FornecedorViewSet, basename='fornecedor')

urlpatterns = [
    path('', include(router.urls)),
    path('itens/reordenar/', ReorderItemView.as_view(), name='reorder_item'),
    path('dashboard-stats/', DashboardStatsView.as_view(), name='dashboard_stats'),
    path('register/', CreateUserView.as_view(), name='register'),
    path('me/', ManageUserView.as_view(), name='me'),
    path('token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
]