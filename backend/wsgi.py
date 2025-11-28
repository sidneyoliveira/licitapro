import os
import sys
from pathlib import Path
from django.core.wsgi import get_wsgi_application
from dotenv import load_dotenv

# 1. Defina o caminho base explicitamente
BASE_DIR = Path(__file__).resolve().parent.parent

# 2. Carregue o .env ANTES de qualquer outra coisa
# Certifique-se que o arquivo .env está na pasta raiz (junto com manage.py)
env_path = BASE_DIR / '.env'
if env_path.exists():
    load_dotenv(env_path)
else:
    # Fallback caso não ache (opcional, para debug)
    print(f"Aviso: .env não encontrado em {env_path}")

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')

application = get_wsgi_application()