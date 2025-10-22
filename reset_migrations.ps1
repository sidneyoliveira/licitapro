Write-Host "🔄 Resetando migrações Django com segurança..."

# Apaga todos os arquivos de migração, menos o __init__.py
Get-ChildItem -Recurse -Include *.py -Path .\backend\api\migrations\ | 
    Where-Object { $_.Name -ne "__init__.py" } | Remove-Item -Force

# Apaga arquivos compilados
Get-ChildItem -Recurse -Include *.pyc -Path .\backend\api\migrations\ | Remove-Item -Force

# Recria as migrações
python manage.py makemigrations
python manage.py migrate --fake-initial

Write-Host "✅ Migrações recriadas com sucesso!"