# api/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .views import (
    ProcessoViewSet, 
    OrgaoViewSet, 
    FornecedorViewSet, 
    MunicipioViewSet,  
    CreateUserView,
    ManageUserView,
    DashboardStatsView
)

router = DefaultRouter()
router.register(r'processos', ProcessoViewSet)
router.register(r'orgaos', OrgaoViewSet)
router.register(r'fornecedores', FornecedorViewSet)
router.register(r'municipios', MunicipioViewSet, basename='municipio')

urlpatterns = [
    path('', include(router.urls)),
    # Rotas de Autenticação JWT
    path('token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('register/', CreateUserView.as_view(), name='register'),
    path('dashboard-stats/', DashboardStatsView.as_view(), name='dashboard_stats'),
    path('me/', ManageUserView.as_view(), name='me'),
]