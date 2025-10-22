#!/bin/bash
echo "🔄 Resetando migrações Django com segurança..."
find . -path "*/migrations/*.py" -not -name "__init__.py" -delete
find . -path "*/migrations/*.pyc" -delete
python manage.py makemigrations
python manage.py migrate --fake-initial
echo "✅ Migrações recriadas com sucesso!"
