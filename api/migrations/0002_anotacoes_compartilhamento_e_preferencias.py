from django.db import migrations


class Migration(migrations.Migration):
    """
    Migration de ponte para restaurar a cadeia de migrações do app `api`.

    Contexto:
    - O repositório ficou sem o arquivo 0002, mas a 0003 depende dele.
    - Sem este arquivo, `manage.py migrate` quebra com inconsistência de migração.

    Esta migration não altera schema por si só; ela apenas recompõe a sequência
    esperada para que as próximas migrações (ex.: 0003_notificacao) sejam aplicadas.
    """

    dependencies = [
        ("api", "0001_initial"),
    ]

    operations = []
