#!/usr/bin/env bash
# exit on error
set -o errexit

# Comandos para instalar dependências e preparar o banco de dados
pip install -r requirements.txt
python manage.py collectstatic --no-input
python manage.py migrate

# --- SCRIPT DE CRIAÇÃO DO SUPERUSUÁRIO (CORRIGIDO) ---
if [[ "$CREATE_SUPERUSER" == "true" ]]; then
  echo "Creating superuser..."
  # O comando vai ler as variáveis de ambiente DJANGO_SUPERUSER_* automaticamente
  python manage.py createsuperuser --no-input
  echo "Superuser created."
fi