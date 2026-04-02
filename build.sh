#!/usr/bin/env bash
# exit on error
set -o errexit

# Limpa __pycache__ stale para evitar conflitos de import
find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

# Comandos para instalar dependências e preparar o banco de dados
pip install -r requirements.txt
python manage.py collectstatic --no-input
python manage.py migrate

# echo "Creating superuser..."
# # O comando vai ler as variáveis de ambiente DJANGO_SUPERUSER_* automaticamente
# python manage.py createsuperuser --no-input
# echo "Superuser created."