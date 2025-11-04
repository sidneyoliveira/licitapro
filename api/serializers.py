from rest_framework import serializers
from django.db.models import Max
from .models import (
    CustomUser,
    Entidade,
    Orgao,
    ProcessoLicitatorio,
    Lote,
    Item,
    Fornecedor,
    FornecedorProcesso,
    ItemFornecedor
)

# ============================================================
# 1️⃣ USUÁRIO
# ============================================================

class UserSerializer(serializers.ModelSerializer):
    profile_image = serializers.ImageField(required=False, allow_null=True)

    class Meta:
        model = CustomUser
        fields = [
            'id',
            'username',
            'email',
            'first_name',
            'last_name',
            'cpf',
            'phone',
            'data_nascimento',
            'password',
            'profile_image',
        ]
        read_only_fields = ['id', 'username']
        extra_kwargs = {
            'password': {'write_only': True, 'required': False}
        }

    def get_profile_image(self, obj):
        request = self.context.get('request')
        if request and obj.profile_image and hasattr(obj.profile_image, 'url'):
            return request.build_absolute_uri(obj.profile_image.url)
        return None

    def update(self, instance, validated_data):
        password = validated_data.pop('password', None)
        user = super().update(instance, validated_data)
        if password:
            user.set_password(password)
            user.save()
        return user


# ============================================================
# 2️⃣ ENTIDADE / ÓRGÃO
# ============================================================

class EntidadeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Entidade
        fields = '__all__'
        read_only_fields = ['id']


class OrgaoSerializer(serializers.ModelSerializer):
    entidade_nome = serializers.CharField(source='entidade.nome', read_only=True)

    class Meta:
        model = Orgao
        fields = '__all__'
        read_only_fields = ['id', 'entidade_nome']


# ============================================================
# 3️⃣ FORNECEDOR
# ============================================================

class FornecedorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Fornecedor
        fields = [
            'id', 'cnpj', 'razao_social', 'nome_fantasia', 'porte',
            'telefone', 'email', 'cep', 'logradouro', 'numero',
            'bairro', 'complemento', 'uf', 'municipio', 'criado_em'
        ]
        read_only_fields = ['id', 'criado_em']


# ============================================================
# 4️⃣ LOTE
# ============================================================

class LoteSerializer(serializers.ModelSerializer):
    processo_numero = serializers.CharField(source='processo.numero_processo', read_only=True)

    class Meta:
        model = Lote
        fields = ['id', 'processo', 'processo_numero', 'numero', 'descricao']
        read_only_fields = ['id', 'processo_numero']

    def validate(self, attrs):
        """
        Evita conflito de (processo, numero) duplicados quando informado manualmente.
        """
        processo = attrs.get('processo') or getattr(self.instance, 'processo', None)
        numero = attrs.get('numero') or getattr(self.instance, 'numero', None)
        if processo and numero:
            qs = Lote.objects.filter(processo=processo, numero=numero)
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError("Já existe um lote com esse número para este processo.")
        return attrs


# ============================================================
# 5️⃣ ITEM
# ============================================================

class ItemSerializer(serializers.ModelSerializer):
    processo_numero = serializers.CharField(source='processo.numero_processo', read_only=True)
    lote_numero = serializers.IntegerField(source='lote.numero', read_only=True)
    fornecedor_nome = serializers.CharField(source='fornecedor.razao_social', read_only=True)

    class Meta:
        model = Item
        fields = [
            'id',
            'processo',
            'processo_numero',
            'descricao',
            'unidade',
            'quantidade',
            'valor_estimado',
            'lote',
            'lote_numero',
            'fornecedor',
            'fornecedor_nome',
            'ordem',
        ]
        read_only_fields = ['id', 'processo_numero', 'lote_numero', 'fornecedor_nome', 'ordem']

    def create(self, validated_data):
        """
        Define ordem incremental por processo (Max('ordem') + 1).
        """
        processo = validated_data.get('processo')
        if processo:
            last_ord = Item.objects.filter(processo=processo).aggregate(m=Max('ordem'))['m'] or 0
            validated_data['ordem'] = last_ord + 1
        return super().create(validated_data)

    def validate(self, attrs):
        """
        Garante que, se houver lote, ele pertença ao mesmo processo.
        """
        processo = attrs.get('processo') or getattr(self.instance, 'processo', None)
        lote = attrs.get('lote') or getattr(self.instance, 'lote', None)
        if lote and processo and lote.processo_id != processo.id:
            raise serializers.ValidationError("O lote selecionado pertence a outro processo.")
        return attrs


# ============================================================
# 6️⃣ PROCESSO LICITATÓRIO
# ============================================================

class ProcessoLicitatorioSerializer(serializers.ModelSerializer):
    entidade_nome = serializers.CharField(source='entidade.nome', read_only=True)
    orgao_nome = serializers.CharField(source='orgao.nome', read_only=True)

    # compatibilidade: expõe o campo do banco e um alias amigável ao front
    registro_preco_display = serializers.SerializerMethodField()
    registro_precos = serializers.BooleanField(source='registro_precos', required=False)  # alias (property no model)

    class Meta:
        model = ProcessoLicitatorio
        fields = [
            'id',
            'objeto',
            'modalidade',
            'data_abertura',
            'situacao',
            'entidade',
            'entidade_nome',
            'orgao',
            'orgao_nome',
            'valor_referencia',
            'vigencia_meses',
            'classificacao',
            'tipo_organizacao',
            'registro_preco',           # campo real do banco
            'registro_precos',          # alias (front)
            'registro_preco_display',   # "Sim"/"Não"
            'data_processo',
            'numero_processo',
            'numero_certame',
        ]

    def get_registro_preco_display(self, obj):
        return "Sim" if obj.registro_preco else "Não"


# ============================================================
# 7️⃣ FORNECEDOR ↔ PROCESSO (participantes)
# ============================================================

class FornecedorProcessoSerializer(serializers.ModelSerializer):
    fornecedor_nome = serializers.CharField(source='fornecedor.razao_social', read_only=True)
    processo_numero = serializers.CharField(source='processo.numero_processo', read_only=True)

    class Meta:
        model = FornecedorProcesso
        fields = [
            'id',
            'processo',
            'processo_numero',
            'fornecedor',
            'fornecedor_nome',
            'data_participacao',
            'habilitado'
        ]
        read_only_fields = ['id', 'data_participacao', 'fornecedor_nome', 'processo_numero']


# ============================================================
# 8️⃣ ITEM ↔ FORNECEDOR (propostas e vencedores)
# ============================================================

class ItemFornecedorSerializer(serializers.ModelSerializer):
    item_descricao = serializers.CharField(source='item.descricao', read_only=True)
    fornecedor_nome = serializers.CharField(source='fornecedor.razao_social', read_only=True)

    class Meta:
        model = ItemFornecedor
        fields = [
            'id',
            'item',
            'item_descricao',
            'fornecedor',
            'fornecedor_nome',
            'valor_proposto',
            'vencedor'
        ]
        read_only_fields = ['id', 'item_descricao', 'fornecedor_nome']
