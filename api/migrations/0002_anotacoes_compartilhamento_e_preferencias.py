from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='customuser',
            name='receber_anotacoes_compartilhadas',
            field=models.BooleanField(
                default=True,
                help_text='Permite que outros usuários compartilhem anotações com este usuário.',
                verbose_name='Receber anotações compartilhadas',
            ),
        ),
        migrations.AddField(
            model_name='customuser',
            name='usuarios_bloqueados',
            field=models.ManyToManyField(
                blank=True,
                help_text='Usuários bloqueados não podem compartilhar anotações com este usuário.',
                related_name='bloqueado_por',
                symmetrical=False,
                to='api.customuser',
                verbose_name='Usuários bloqueados',
            ),
        ),
        migrations.AddField(
            model_name='anotacao',
            name='concluida',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='anotacao',
            name='titulo',
            field=models.CharField(blank=True, max_length=160, null=True),
        ),
        migrations.AddField(
            model_name='anotacao',
            name='processo',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='anotacoes',
                to='api.processolicitatorio',
            ),
        ),
        migrations.AddField(
            model_name='anotacao',
            name='compartilhada_com',
            field=models.ManyToManyField(blank=True, related_name='anotacoes_compartilhadas', to='api.customuser'),
        ),
    ]
