# api/choices.py

# ==============================================================================
# MODALIDADES (Lei 14.133/2021)
# Formato: (ID_PNCP, SLUG, LABEL)
# ==============================================================================
MODALIDADE_CHOICES = (
    (6, "pregao_eletronico", "Pregão - Eletrônico"),
    (7, "pregao_presencial", "Pregão - Presencial"),
    (4, "concorrencia_eletronica", "Concorrência - Eletrônica"),
    (5, "concorrencia_presencial", "Concorrência - Presencial"),
    (8, "dispensa_licitacao", "Dispensa de Licitação"),
    (9, "inexigibilidade", "Inexigibilidade"),
    (11, "pre_qualificacao", "Pré-Qualificação"),
    (12, "credenciamento", "Credenciamento"),
    (13, "leilao_eletronico", "Leilão - Eletrônico"),
    (14, "leilao_presencial", "Leilão - Presencial"),
    (15, "dialogo_competitivo", "Diálogo Competitivo"),
)

# ==============================================================================
# MODO DE DISPUTA
# Formato: (ID_PNCP, SLUG, LABEL)
# ==============================================================================
MODO_DISPUTA_CHOICES = (
    (1, "aberto", "Aberto"),
    (2, "fechado", "Fechado"),
    (3, "aberto_fechado", "Aberto-Fechado"),
    (4, "dispensa_com_disputa", "Dispensa com Disputa"),
    (5, "nao_se_aplica", "Não se aplica"),
    (6, "fechado_aberto", "Fechado-Aberto"),
)

# ==============================================================================
# CRITÉRIO DE JULGAMENTO
# Formato: (ID_PNCP, SLUG, LABEL)
# ==============================================================================
CRITERIO_JULGAMENTO_CHOICES = (
    (1, "menor_preco", "Menor preço"),
    (2, "maior_desconto", "Maior desconto"),
    (3, "melhor_tecnica_conteudo", "Melhor técnica ou conteúdo artístico"),
    (4, "tecnica_e_preco", "Técnica e preço"),
    (5, "maior_lance", "Maior lance"),
    (6, "maior_retorno_economico", "Maior retorno econômico"),
    (7, "nao_se_aplica", "Não se aplica"),
    (8, "melhor_tecnica", "Melhor técnica"),
    (9, "conteudo_artistico", "Conteúdo artístico"),
)

# ==============================================================================
# INSTRUMENTO CONVOCATÓRIO
# Formato: (ID_PNCP, SLUG, LABEL)
# ==============================================================================
INSTRUMENTO_CONVOCATORIO_CHOICES = (
    (1, "edital", "Edital"),
    (2, "aviso_contratacao_direta", "Aviso de Contratação Direta"),
    (3, "ato_autorizacao_contratacao_direta", "Ato que autoriza a Contratação Direta"),
    (4, "edital_chamamento_publico", "Edital de Chamamento Público"),
)

# ==============================================================================
# SITUAÇÃO DA COMPRA (Controle Interno e PNCP)
# Formato: (SLUG, LABEL)
# ==============================================================================
SITUACAO_CHOICES = (
    ('aberto', 'Aberto'),
    ('em_pesquisa', 'Em Pesquisa'),
    ('aguardando_publicacao', 'Aguardando Publicação'),
    ('publicado', 'Publicado'),
    ('em_contratacao', 'Em Contratação'),
    ('adjudicado', 'Adjudicado'),
    ('homologado', 'Homologado'),
    ('revogado', 'Revogado'),
    ('cancelado', 'Cancelado'),
    ('deserto', 'Deserto'),
    ('fracassado', 'Fracassado'),
)

# ==============================================================================
# TIPO DE ORGANIZAÇÃO (Controle Interno)
# Formato: (SLUG, LABEL)
# ==============================================================================
TIPO_ORGANIZACAO_CHOICES = (
    ('lote', 'Lote'),
    ('item', 'Item'),
)

# ==============================================================================
# SITUAÇÃO DO ITEM DA CONTRATAÇÃO (PNCP 5.7)
# Formato: (ID_PNCP, SLUG, LABEL)
# ==============================================================================
SITUACAO_ITEM_CHOICES = (
    (1, "em_andamento", "Em Andamento"),
    (2, "homologado", "Homologado"),
    (3, "anulado_revogado_cancelado", "Anulado/Revogado/Cancelado"),
    (4, "deserto", "Deserto"),
    (5, "fracassado", "Fracassado"),
)

# ==============================================================================
# TIPO DE BENEFÍCIO (ME/EPP)
# Formato: (ID_PNCP, SLUG, LABEL)
# ==============================================================================
TIPO_BENEFICIO_CHOICES = (
    (1, "participacao_exclusiva", "Participação exclusiva para ME/EPP"),
    (2, "subcontratacao", "Subcontratação para ME/EPP"),
    (3, "cota_reservada", "Cota reservada para ME/EPP"),
    (4, "sem_beneficio", "Sem benefício"),
    (5, "nao_se_aplica", "Não se aplica"),
)

# ==============================================================================
# CATEGORIA DO ITEM (Material, Serviço, Obra...)
# Formato: (ID_PNCP, SLUG, LABEL)
# ==============================================================================
CATEGORIA_ITEM_CHOICES = (
    (1, "material", "Material"),
    (2, "servico", "Serviço"),
    (3, "obra", "Obra"),
    (4, "servicos_engenharia", "Serviços de Engenharia"),
    (5, "solucoes_tic", "Soluções de TIC"),
    (6, "locacao_imoveis", "Locação de Imóveis"),
    (7, "alienacao_concessao", "Alienação/Concessão/Permissão"),
    (8, "obras_servicos_engenharia", "Obras e Serviços de Engenharia"),
)

# ==============================================================================
# AMPARO LEGAL (IDs baseados na documentação oficial PNCP)
# Formato: (ID_PNCP, SLUG, LABEL)
# ==============================================================================
AMPARO_LEGAL_CHOICES = (
    # --- Lei 14.133/2021: Art. 28 (Modalidades) ---
    (1, "lei14133_art28_i", "Lei 14.133/2021, Art. 28, I (Pregão)"),
    (2, "lei14133_art28_ii", "Lei 14.133/2021, Art. 28, II (Concorrência)"),
    (3, "lei14133_art28_iii", "Lei 14.133/2021, Art. 28, III (Concurso)"),
    (4, "lei14133_art28_iv", "Lei 14.133/2021, Art. 28, IV (Leilão)"),
    (5, "lei14133_art28_v", "Lei 14.133/2021, Art. 28, V (Diálogo Competitivo)"),

    # --- Lei 14.133/2021: Art. 74 (Inexigibilidade) ---
    (6, "lei14133_art74_i", "Lei 14.133/2021, Art. 74, I (Fornecedor Exclusivo)"),
    (7, "lei14133_art74_ii", "Lei 14.133/2021, Art. 74, II (Artista Consagrado)"),
    (8, "lei14133_art74_iii_a", "Lei 14.133/2021, Art. 74, III, a (Estudos Técnicos)"),
    (9, "lei14133_art74_iii_b", "Lei 14.133/2021, Art. 74, III, b (Pareceres/Perícias)"),
    (10, "lei14133_art74_iii_c", "Lei 14.133/2021, Art. 74, III, c (Assessoria/Consultoria)"),
    (11, "lei14133_art74_iii_d", "Lei 14.133/2021, Art. 74, III, d (Fiscalização/Supervisão)"),
    (12, "lei14133_art74_iii_e", "Lei 14.133/2021, Art. 74, III, e (Patrocínio/Defesa)"),
    (13, "lei14133_art74_iii_f", "Lei 14.133/2021, Art. 74, III, f (Treinamento)"),
    (14, "lei14133_art74_iii_g", "Lei 14.133/2021, Art. 74, III, g (Restauração Histórica)"),
    (15, "lei14133_art74_iii_h", "Lei 14.133/2021, Art. 74, III, h (Controles de Qualidade)"),
    (16, "lei14133_art74_iv", "Lei 14.133/2021, Art. 74, IV (Credenciamento - Inex.)"),
    (17, "lei14133_art74_v", "Lei 14.133/2021, Art. 74, V (Aquisição Imóvel)"),
    (50, "lei14133_art74_caput", "Lei 14.133/2021, Art. 74, caput (Outras Inexigibilidades)"),

    # --- Lei 14.133/2021: Art. 75 (Dispensa) ---
    (18, "lei14133_art75_i", "Lei 14.133/2021, Art. 75, I (Valor < 100k - Engenharia)"),
    (19, "lei14133_art75_ii", "Lei 14.133/2021, Art. 75, II (Valor < 50k - Outros)"),
    (20, "lei14133_art75_iii_a", "Lei 14.133/2021, Art. 75, III, a (Licitação Deserta/Fracassada)"),
    (21, "lei14133_art75_iii_b", "Lei 14.133/2021, Art. 75, III, b (Preços Superiores Mercado)"),
    (22, "lei14133_art75_iv_a", "Lei 14.133/2021, Art. 75, IV, a (Garantia Técnica)"),
    (23, "lei14133_art75_iv_b", "Lei 14.133/2021, Art. 75, IV, b (Acordo Internacional)"),
    (24, "lei14133_art75_iv_c", "Lei 14.133/2021, Art. 75, IV, c (Pesquisa e Desenv.)"),
    (25, "lei14133_art75_iv_d", "Lei 14.133/2021, Art. 75, IV, d (Transferência Tecnologia)"),
    (26, "lei14133_art75_iv_e", "Lei 14.133/2021, Art. 75, IV, e (Hortifrutigranjeiros)"),
    (27, "lei14133_art75_iv_f", "Lei 14.133/2021, Art. 75, IV, f (Alta Tecnologia/Defesa)"),
    (28, "lei14133_art75_iv_g", "Lei 14.133/2021, Art. 75, IV, g (Materiais Forças Armadas)"),
    (29, "lei14133_art75_iv_h", "Lei 14.133/2021, Art. 75, IV, h (Operações de Paz)"),
    (30, "lei14133_art75_iv_i", "Lei 14.133/2021, Art. 75, IV, i (Abastecimento Militar)"),
    (31, "lei14133_art75_iv_j", "Lei 14.133/2021, Art. 75, IV, j (Catadores Resíduos)"),
    (32, "lei14133_art75_iv_k", "Lei 14.133/2021, Art. 75, IV, k (Obras Arte/Históricas)"),
    (33, "lei14133_art75_iv_l", "Lei 14.133/2021, Art. 75, IV, l (Rastreamento/Sigilo)"),
    (34, "lei14133_art75_iv_m", "Lei 14.133/2021, Art. 75, IV, m (Medicamentos Doenças Raras)"),
    (35, "lei14133_art75_v", "Lei 14.133/2021, Art. 75, V (Inovação Tecnológica)"),
    (36, "lei14133_art75_vi", "Lei 14.133/2021, Art. 75, VI (Segurança Nacional)"),
    (37, "lei14133_art75_vii", "Lei 14.133/2021, Art. 75, VII (Guerra/Calamidade)"),
    (38, "lei14133_art75_viii", "Lei 14.133/2021, Art. 75, VIII (Emergência/Calamidade Pública)"),
    (39, "lei14133_art75_ix", "Lei 14.133/2021, Art. 75, IX (Órgão Adm. Pública)"),
    (40, "lei14133_art75_x", "Lei 14.133/2021, Art. 75, X (Intervenção Econômica)"),
    (41, "lei14133_art75_xi", "Lei 14.133/2021, Art. 75, XI (Contrato de Programa)"),
    (42, "lei14133_art75_xii", "Lei 14.133/2021, Art. 75, XII (Prod. Estratégicos SUS)"),
    (43, "lei14133_art75_xiii", "Lei 14.133/2021, Art. 75, XIII (Comissão Avaliação)"),
    (44, "lei14133_art75_xiv", "Lei 14.133/2021, Art. 75, XIV (Assoc. Pessoas Deficiência)"),
    (45, "lei14133_art75_xv", "Lei 14.133/2021, Art. 75, XV (Inst. Pesquisa/Recuperação)"),
    (46, "lei14133_art75_xvi", "Lei 14.133/2021, Art. 75, XVI (Insumos Saúde Fundação)"),
    (60, "lei14133_art75_xvii", "Lei 14.133/2021, Art. 75, XVII (Cisternas/Água)"),
    (77, "lei14133_art75_xviii", "Lei 14.133/2021, Art. 75, XVIII (Cozinha Solidária)"),

    # --- Lei 14.133/2021: Art. 78/79 (Credenciamento/Auxiliares) ---
    (47, "lei14133_art78_i", "Lei 14.133/2021, Art. 78, I (Credenciamento - Geral)"),
    (48, "lei14133_art78_ii", "Lei 14.133/2021, Art. 78, II (Pré-qualificação)"),
    (49, "lei14133_art78_iii", "Lei 14.133/2021, Art. 78, III (Manifestação Interesse)"),
    (140, "lei14133_art79_i", "Lei 14.133/2021, Art. 79, I (Cred. Paralela/Não Excludente)"),
    (141, "lei14133_art79_ii", "Lei 14.133/2021, Art. 79, II (Cred. Seleção Terceiros)"),
    (142, "lei14133_art79_iii", "Lei 14.133/2021, Art. 79, III (Cred. Mercados Fluidos)"),

    # --- Lei 11.947/2009 (Merenda Escolar) ---
    (138, "lei11947_art14", "Lei 11.947/2009, Art. 14 (Agricultura Familiar)"),
    (139, "lei11947_art21", "Lei 11.947/2009, Art. 21 (Emergencial PNAE)"),
)

# ==============================================================================
# NATUREZAS DE DESPESA
# Formato: (CODIGO, DESCRICAO) - Padrão simples Django pois código é string
# ==============================================================================
NATUREZAS_DESPESA_CHOICES = (
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
)

# ==============================================================================
# MAPAS AUXILIARES PARA SERVIÇOS (Busca rápida por Slug)
# ==============================================================================

# Dicionários { "slug": ID_PNCP }
MAP_AMPARO_LEGAL_PNCP = {item[1]: item[0] for item in AMPARO_LEGAL_CHOICES if item[0] is not None}
MAP_MODALIDADE_PNCP = {item[1]: item[0] for item in MODALIDADE_CHOICES}
MAP_MODO_DISPUTA_PNCP = {item[1]: item[0] for item in MODO_DISPUTA_CHOICES}
MAP_INSTRUMENTO_CONVOCATORIO_PNCP = {item[1]: item[0] for item in INSTRUMENTO_CONVOCATORIO_CHOICES}
MAP_SITUACAO_ITEM_PNCP = {item[1]: item[0] for item in SITUACAO_ITEM_CHOICES}
MAP_TIPO_BENEFICIO_PNCP = {item[1]: item[0] for item in TIPO_BENEFICIO_CHOICES}
MAP_CATEGORIA_ITEM_PNCP = {item[1]: item[0] for item in CATEGORIA_ITEM_CHOICES}