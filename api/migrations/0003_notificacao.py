from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0002_anotacoes_compartilhamento_e_preferencias'),
    ]

    operations = [
        migrations.CreateModel(
            name='Notificacao',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('tipo_acao', models.CharField(choices=[('create', 'Criação'), ('update', 'Edição'), ('delete', 'Exclusão'), ('check', 'Marcação')], max_length=16)),
                ('titulo', models.CharField(max_length=180)),
                ('mensagem', models.TextField(blank=True, null=True)),
                ('lida', models.BooleanField(default=False)),
                ('criado_em', models.DateTimeField(auto_now_add=True)),
                ('anotacao', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='notificacoes', to='api.anotacao')),
                ('ator', models.ForeignKey(blank=True, help_text='Usuário que realizou a ação', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='notificacoes_emitidas', to='api.customuser')),
                ('processo', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='notificacoes', to='api.processolicitatorio')),
                ('usuario', models.ForeignKey(help_text='Usuário que recebe a notificação', on_delete=django.db.models.deletion.CASCADE, related_name='notificacoes', to='api.customuser')),
            ],
            options={
                'verbose_name': 'Notificação',
                'verbose_name_plural': 'Notificações',
                'ordering': ['-criado_em'],
            },
        ),
    ]
