# backend/api/urls.py

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView

from .views import *

router = DefaultRouter()
router.register(r'processos', ProcessoViewSet, basename='processo')
router.register(r'entidades', EntidadeViewSet, basename='entidade')
router.register(r'orgaos', OrgaoViewSet, basename='orgao')
router.register(r'itens', ItemProcessoViewSet, basename='item')
router.register(r'fornecedores', FornecedorProcessoViewSet, basename='fornecedor')


urlpatterns = [
    path('', include(router.urls)),
    path('reorder-itens/', ReorderItensView.as_view(), name='reorder-itens'),
    path('dashboard-stats/', DashboardStatsView.as_view(), name='dashboard_stats'),
    path('register/', CreateUserView.as_view(), name='register'),
    path('me/', ManageUserView.as_view(), name='me'),
    path('token/', MyTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
]