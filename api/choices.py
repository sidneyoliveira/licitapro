# api/choices.py

NATUREZAS_DESPESA = [
    ("33901100", "33901100 - Vencimentos e vantagens fixas - pessoal civil"),
    ("33901200", "33901200 - Vencimentos e vantagens fixas - pessoal militar"),
    ("33901400", "33901400 - Diárias"),
    ("33901500", "33901500 - Auxílio alimentação"),
    ("33901600", "33901600 - Despesas de locomoção, transporte e hospedagem"),
    ("33901800", "33901800 - Auxílio financeiro a estudante"),
    ("33902000", "33902000 - Auxílio transporte"),
    ("33902300", "33902300 - Obrigações patronais"),
    ("33903000", "33903000 - Material de consumo"),
    ("33903200", "33903200 - Material, bem ou serviço para distribuição gratuita"),
    ("33903300", "33903300 - Passagens e despesas com locomoção"),
    ("33903400", "33903400 - Outros serviços de terceiro - pessoa física"),
    ("33903500", "33903500 - Serviços de consultoria"),
    ("33903600", "33903600 - Serviços de terceiros – pessoa física"),
    ("33903700", "33903700 - Serviços de terceiros – pessoa jurídica"),
    ("33903800", "33903800 - Serviços de limpeza e conservação"),
    ("33903900", "33903900 - Serviços jurídicos"),
    ("33904000", "33904000 - Serviços de tecnologia da informação"),
    ("33904100", "33904100 - Contribuições"),
    ("33904200", "33904200 - Assistência médica e odontológica"),
    ("33904300", "33904300 - Seguro de vida"),
    ("33904400", "33904400 - Indenizações e restituições"),
    ("33904500", "33904500 - Serviços de energia elétrica"),
    ("33904600", "33904600 - Outros serviços de terceiros"),
    ("33904700", "33904700 - Serviços de comunicação"),
    ("33904800", "33904800 - Serviços de água e esgoto"),
    ("33904900", "33904900 - Serviços de vigilância"),
    ("33905000", "33905000 - Serviços gráficos"),
    ("33905100", "33905100 - Publicidade legal"),
    ("33905200", "33905200 - Serviços de transporte"),
    ("33905300", "33905300 - Manutenção de equipamentos"),
    ("33905400", "33905400 - Locação de imóveis"),
    ("33905500", "33905500 - Locação de veículos"),
    ("33905600", "33905600 - Serviços de telefonia móvel"),
    ("33905700", "33905700 - Serviços de internet"),
    ("33905800", "33905800 - Serviços de capacitação"),
    ("33905900", "33905900 - Serviços de apoio administrativo"),
    ("44905100", "44905100 - Obras e instalações"),
    ("44905200", "44905200 - Material permanente"),
    ("44906100", "44906100 - Aquisição de equipamentos e material permanente"),
    ("44907100", "44907100 - Aquisição de imóveis"),
    ("44907200", "44907200 - Aquisição de veículos"),
    ("44907300", "44907300 - Aquisição de mobiliário"),
    ("44907400", "44907400 - Aquisição de equipamentos de informática"),
    ("44907500", "44907500 - Aquisição de equipamentos hospitalares"),
    ("44909000", "44909000 - Outras despesas de capital"),
]

MODO_DISPUTA_CHOICES = (
    ("aberto", "Aberto"),
    ("fechado", "Fechado"),
    ("aberto_e_fechado", "Aberto e Fechado"),
)

CRITERIO_JULGAMENTO_CHOICES = (
    ("menor_preco", "Menor Preço"),
    ("maior_desconto", "Maior Desconto"),
)

AMPARO_LEGAL_CHOICES = (
    ("art_23", "Art. 23 (Lei 8.666/93)"),
    ("art_24", "Art. 24 (Lei 8.666/93)"),
    ("art_25", "Art. 25 (Lei 8.666/93)"),
    ("art_4", "Art. 4º (Lei 10.520/02)"),
    ("art_5", "Art. 5º (Lei 10.520/02)"),
    ("art_28_i", "Art. 28, inciso I (Lei 14.133/21)"),
    ("art_28_ii", "Art. 28, inciso II (Lei 14.133/21)"),
    ("art_75_par7", "Art. 75, § 7º (Lei 14.133/21)"),
    ("art_75_i", "Art. 75, inciso I (Lei 14.133/21)"),
    ("art_75_ii", "Art. 75, inciso II (Lei 14.133/21)"),
    ("art_75_iii_a", "Art. 75, inciso III, a"),
    ("art_75_iii_b", "Art. 75, inciso III, b"),
    ("art_75_iii_c", "Art. 75, inciso III, c"),
    ("art_75_iii_d", "Art. 75, inciso III, d"),
    ("art_75_iii_e", "Art. 75, inciso III, e"),
    ("art_75_iii_f", "Art. 75, inciso III, f"),
    ("art_75_iv_a", "Art. 75, inciso IV, a"),
    ("art_75_iv_b", "Art. 75, inciso IV, b"),
    ("art_75_iv_c", "Art. 75, inciso IV, c"),
    ("art_75_iv_d", "Art. 75, inciso IV, d"),
    ("art_75_iv_e", "Art. 75, inciso IV, e"),
    ("art_75_iv_f", "Art. 75, inciso IV, f"),
    ("art_75_iv_j", "Art. 75, inciso IV, j"),
    ("art_75_iv_k", "Art. 75, inciso IV, k"),
    ("art_75_iv_m", "Art. 75, inciso IV, m"),
    ("art_75_ix", "Art. 75, inciso IX"),
    ("art_75_viii", "Art. 75, inciso VIII"),
    ("art_75_xv", "Art. 75, inciso XV"),
    ("lei_11947_art14_1", "Lei 11.947/2009, Art. 14, § 1º"),
    ("art_79_i", "Art. 79, inciso I (Credenciamento)"),
    ("art_79_ii", "Art. 79, inciso II (Credenciamento)"),
    ("art_79_iii", "Art. 79, inciso III (Credenciamento)"),
    ("art_74_caput", "Art. 74, caput (Inexigibilidade)"),
    ("art_74_i", "Art. 74, I"),
    ("art_74_ii", "Art. 74, II"),
    ("art_74_iii_a", "Art. 74, III, a"),
    ("art_74_iii_b", "Art. 74, III, b"),
    ("art_74_iii_c", "Art. 74, III, c"),
    ("art_74_iii_d", "Art. 74, III, d"),
    ("art_74_iii_e", "Art. 74, III, e"),
    ("art_74_iii_f", "Art. 74, III, f"),
    ("art_74_iii_g", "Art. 74, III, g"),
    ("art_74_iii_h", "Art. 74, III, h"),
    ("art_74_iv", "Art. 74, IV"),
    ("art_74_v", "Art. 74, V"),
    ("art_86_2", "Art. 86, § 2º (Adesão SRP)"),
)

MODALIDADE_CHOICES = (
    ('Pregão Eletrônico', 'Pregão Eletrônico'),
    ('Concorrência Eletrônica', 'Concorrência Eletrônica'),
    ('Dispensa Eletrônica', 'Dispensa Eletrônica'),
    ('Inexigibilidade Eletrônica', 'Inexigibilidade Eletrônica'),
    ('Adesão a Registro de Preços', 'Adesão a Registro de Preços'),
    ('Credenciamento', 'Credenciamento'),
)

CLASSIFICACAO_CHOICES = (
    ('Compras', 'Compras'),
    ('Serviços Comuns', 'Serviços Comuns'),
    ('Serviços de Engenharia Comuns', 'Serviços de Engenharia Comuns'),
    ('Obras Comuns', 'Obras Comuns'),
)

TIPO_ORGANIZACAO_CHOICES = (
    ('Lote', 'Lote'), 
    ('Item', 'Item')
)

SITUACAO_CHOICES = (
    ('Aberto', 'Aberto'),
    ('Em Pesquisa', 'Em Pesquisa'),
    ('Aguardando Publicação', 'Aguardando Publicação'),
    ('Publicado', 'Publicado'),
    ('Em Contratação', 'Em Contratação'),
    ('Adjudicado/Homologado', 'Adjudicado/Homologado'),
    ('Revogado/Cancelado', 'Revogado/Cancelado'),
)

FUNDAMENTACAO_CHOICES = (
    ("lei_14133", "Lei 14.133/21"),
    ("lei_8666",  "Lei 8.666/93"),
    ("lei_10520", "Lei 10.520/02"),
)

TIPO_PESSOA_CHOICES = (
    ('PJ', 'Pessoa Jurídica'), 
    ('PF', 'Pessoa Física')
)