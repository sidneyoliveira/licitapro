# ==============================================================================
# FONTE DA VERDADE (MASTER DATA)
# Estrutura: (ID_PNCP, CHAVE_INTERNA, LABEL_EXIBICAO)
# ==============================================================================

# --- 1. MODALIDADES (Conforme sua seleção) ---
_MODALIDADE_DATA = [
    (4, "CONCORRENCIA - ELETRONICA", "Concorrência Eletrônica"),
    (5, "CONCORRENCIA - PRESENCIAL", "Concorrência Presencial"),
    (6, "PREGAO - ELETRONICO", "Pregão Eletrônico"),
    (7, "PREGAO - PRESENCIAL", "Pregão Presencial"),
    (8, "DISPENSA", "Dispensa de Licitação"),
    (9, "INEXIGIBILIDADE", "Inexigibilidade"),
    (11, "PRE-QUALIFICACAO", "Pré-qualificação"),
    (12, "CREDENCIAMENTO", "Credenciamento"),
    # Adesão a Ata não tem ID próprio na tabela base 1-14 do PNCP. 
    # Mantido como opção interna.
    (None, "ADESAO SRP", "Adesão a Registro de Preços (Carona)"),
]

# --- 2. MODO DE DISPUTA (Atualizado conforme JSON PNCP) ---
_MODO_DISPUTA_DATA = [
    (1, "ABERTO", "Aberto"),
    (2, "FECHADO", "Fechado"),
    (3, "ABERTO-FECHADO", "Aberto-Fechado"),
    (4, "DISPENSA COM DISPUTA", "Dispensa Com Disputa"),
    (5, "NAO SE APLICA", "Não se aplica"),
    (6, "FECHADO-ABERTO", "Fechado-Aberto"),
]

# --- 3. CRITÉRIO DE JULGAMENTO (Atualizado conforme JSON PNCP) ---
_CRITERIO_JULGAMENTO_DATA = [
    (1, "MENOR PRECO", "Menor preço"),
    (2, "MAIOR DESCONTO", "Maior desconto"),
    # Item 3 (Melhor técnica ou conteúdo artístico) está inativo no PNCP (statusAtivo: false).
    (4, "TECNICA E PRECO", "Técnica e preço"),
    (5, "MAIOR LANCE", "Maior lance"),
    (6, "MAIOR RETORNO ECONOMICO", "Maior retorno econômico"),
    (7, "NAO SE APLICA", "Não se aplica"),
    (8, "MELHOR TECNICA", "Melhor técnica"),
    (9, "CONTEUDO ARTISTICO", "Conteúdo artístico"),
]

# --- 4. ORIGEM DO RECURSO (Novo - Conforme JSON PNCP) ---
_ORIGEM_RECURSO_DATA = [
    (1, "NAO SE APLICA", "Não se aplica"),
    (2, "MUNICIPAL", "Municipal"),
    (3, "ESTADUAL", "Estadual"),
    (4, "FEDERAL", "Federal"),
    (5, "ORGANISMO INTERNACIONAL", "Organismo Internacional"),
]

# --- 5. TIPO DE INSTRUMENTO CONVOCATÓRIO (Novo - Conforme JSON PNCP) ---
_TIPO_INSTRUMENTO_CONVOCATORIO_DATA = [
    (1, "EDITAL", "Edital"), 
    # Usado em: Leilão, Diálogo Competitivo, Concurso, Concorrência, Pregão.
    
    (2, "AVISO DE CONTRATACAO DIRETA", "Aviso de Contratação Direta"), 
    # Usado em: Dispensa com Disputa.
    
    (3, "ATO QUE AUTORIZA A CONTRATACAO DIRETA", "Ato que autoriza a Contratação Direta"), 
    # Usado em: Dispensa sem Disputa ou Inexigibilidade.
    
    (4, "EDITAL DE CHAMAMENTO PUBLICO", "Edital de Chamamento Público"), 
    # Usado em: Manifestação de Interesse, Pré-qualificação, Credenciamento.
]

# --- 6. AMPAROS LEGAIS (Apenas modalidades solicitadas) ---
_AMPARO_LEGAL_DATA = [
    # === PREGÃO (Lei 14.133 e correlatas) ===
    (1, "LEI 14.133/2021, ART. 28, I", "Lei 14.133/21 - Art. 28, I (Pregão)"),
    (113, "LEI 13.303/2016, ART. 32, IV", "Lei 13.303/16 - Art. 32, IV (Pregão - Estatais)"),
    (169, "MEDIDA PROVISORIA 1.309/2025, ART. 12, IV (PREGAO)", "MP 1.309/25 - Art. 12, IV (Pregão)"),

    # === CONCORRÊNCIA ===
    (2, "LEI 14.133/2021, ART. 28, II", "Lei 14.133/21 - Art. 28, II (Concorrência)"),
    (170, "MEDIDA PROVISORIA 1.309/2025, ART. 12, IV (CONCORRENCIA)", "MP 1.309/25 - Art. 12, IV (Concorrência)"),

    # === DISPENSA DE LICITAÇÃO (Art. 75 - Lei 14.133) ===
    # Valores
    (18, "LEI 14.133/2021, ART. 75, I", "Lei 14.133/21 - Art. 75, I (Engenharia/Manutenção < 100k)"),
    (19, "LEI 14.133/2021, ART. 75, II", "Lei 14.133/21 - Art. 75, II (Compras/Serviços < 50k)"),
    # Fracassada/Deserta
    (20, "LEI 14.133/2021, ART. 75, III, A", "Lei 14.133/21 - Art. 75, III, a (Licitação Deserta)"),
    (21, "LEI 14.133/2021, ART. 75, III, B", "Lei 14.133/21 - Art. 75, III, b (Licitação Fracassada)"),
    # Inciso IV (Diversos)
    (22, "LEI 14.133/2021, ART. 75, IV, A", "Lei 14.133/21 - Art. 75, IV, a"),
    (23, "LEI 14.133/2021, ART. 75, IV, B", "Lei 14.133/21 - Art. 75, IV, b"),
    (24, "LEI 14.133/2021, ART. 75, IV, C", "Lei 14.133/21 - Art. 75, IV, c (Pesquisa/Desenvolvimento)"),
    (25, "LEI 14.133/2021, ART. 75, IV, D", "Lei 14.133/21 - Art. 75, IV, d"),
    (26, "LEI 14.133/2021, ART. 75, IV, E", "Lei 14.133/21 - Art. 75, IV, e (Hortifrutigranjeiros/Perecíveis)"),
    (27, "LEI 14.133/2021, ART. 75, IV, F", "Lei 14.133/21 - Art. 75, IV, f"),
    (28, "LEI 14.133/2021, ART. 75, IV, G", "Lei 14.133/21 - Art. 75, IV, g"),
    (29, "LEI 14.133/2021, ART. 75, IV, H", "Lei 14.133/21 - Art. 75, IV, h"),
    (30, "LEI 14.133/2021, ART. 75, IV, I", "Lei 14.133/21 - Art. 75, IV, i"),
    (31, "LEI 14.133/2021, ART. 75, IV, J", "Lei 14.133/21 - Art. 75, IV, j (Coleta Seletiva/Catadores)"),
    (32, "LEI 14.133/2021, ART. 75, IV, K", "Lei 14.133/21 - Art. 75, IV, k"),
    (33, "LEI 14.133/2021, ART. 75, IV, L", "Lei 14.133/21 - Art. 75, IV, l"),
    (34, "LEI 14.133/2021, ART. 75, IV, M", "Lei 14.133/21 - Art. 75, IV, m (Medicamentos Doenças Raras)"),
    # Outros Incisos Art 75
    (35, "LEI 14.133/2021, ART. 75, V", "Lei 14.133/21 - Art. 75, V"),
    (36, "LEI 14.133/2021, ART. 75, VI", "Lei 14.133/21 - Art. 75, VI"),
    (37, "LEI 14.133/2021, ART. 75, VII", "Lei 14.133/21 - Art. 75, VII (Guerra/Grave Perturbação)"),
    (38, "LEI 14.133/2021, ART. 75, VIII", "Lei 14.133/21 - Art. 75, VIII (Emergência/Calamidade)"),
    (39, "LEI 14.133/2021, ART. 75, IX", "Lei 14.133/21 - Art. 75, IX"),
    (40, "LEI 14.133/2021, ART. 75, X", "Lei 14.133/21 - Art. 75, X"),
    (41, "LEI 14.133/2021, ART. 75, XI", "Lei 14.133/21 - Art. 75, XI"),
    (42, "LEI 14.133/2021, ART. 75, XII", "Lei 14.133/21 - Art. 75, XII"),
    (43, "LEI 14.133/2021, ART. 75, XIII", "Lei 14.133/21 - Art. 75, XIII"),
    (44, "LEI 14.133/2021, ART. 75, XIV", "Lei 14.133/21 - Art. 75, XIV"),
    (45, "LEI 14.133/2021, ART. 75, XV", "Lei 14.133/21 - Art. 75, XV"),
    (46, "LEI 14.133/2021, ART. 75, XVI", "Lei 14.133/21 - Art. 75, XVI"),
    (60, "LEI 14.133/2021, ART. 75, XVII", "Lei 14.133/21 - Art. 75, XVII"),
    (77, "LEI 14.133/2021, ART. 75, XVIII", "Lei 14.133/21 - Art. 75, XVIII (Cozinha Solidária)"),

    # === DISPENSA (Alienação/Outros - Art. 76) ===
    (61, "LEI 14.133/2021, ART. 76, I, A", "Lei 14.133/21 - Art. 76, I, a (Dação em Pagamento)"),
    (62, "LEI 14.133/2021, ART. 76, I, B", "Lei 14.133/21 - Art. 76, I, b (Doação)"),
    (63, "LEI 14.133/2021, ART. 76, I, C", "Lei 14.133/21 - Art. 76, I, c (Permuta)"),
    (64, "LEI 14.133/2021, ART. 76, I, D", "Lei 14.133/21 - Art. 76, I, d (Investidura)"),
    (65, "LEI 14.133/2021, ART. 76, I, E", "Lei 14.133/21 - Art. 76, I, e (Venda a outro órgão)"),
    (71, "LEI 14.133/2021, ART. 76, II, A", "Lei 14.133/21 - Art. 76, II, a (Doação Bens Móveis)"),
    (72, "LEI 14.133/2021, ART. 76, II, B", "Lei 14.133/21 - Art. 76, II, b (Permuta Bens Móveis)"),

    # === DISPENSA (Outras Leis/Calamidade) ===
    (51, "LEI 14.284/2021, ART. 29, CAPUT", "Lei 14.284/21 - Art. 29 (Auxílio Emergencial)"),
    (137, "LEI 13.979/2020, ART. 4, 1", "Lei 13.979/20 - Art. 4, §1 (Emergência Saúde)"),
    (149, "MP 1.221/2024, ART. 2, I (CALAMIDADE PUBLICA)", "MP 1.221/24 - Art. 2, I (Calamidade Pública)"),
    (151, "MP 1.221/2024, ART. 2, II (CALAMIDADE PUBLICA)", "MP 1.221/24 - Art. 2, II (Calamidade Pública)"),
    (161, "LEI 14.981/2024, ART. 21 (CALAMIDADE PUBLICA)", "Lei 14.981/24 - Art. 21 (Calamidade)"),
    (84, "LEI 13.303/2016, ART. 29, I", "Lei 13.303/16 - Art. 29, I (Estatais - Engenharia < 100k)"),
    (85, "LEI 13.303/2016, ART. 29, II", "Lei 13.303/16 - Art. 29, II (Estatais - Compras < 50k)"),

    # === INEXIGIBILIDADE (Art. 74 - Lei 14.133) ===
    (6, "LEI 14.133/2021, ART. 74, I", "Lei 14.133/21 - Art. 74, I (Fornecedor Exclusivo)"),
    (7, "LEI 14.133/2021, ART. 74, II", "Lei 14.133/21 - Art. 74, II (Artista Consagrado)"),
    # Serviços Técnicos Especializados (Art 74 III)
    (8, "LEI 14.133/2021, ART. 74, III, A", "Lei 14.133/21 - Art. 74, III, a (Estudos Técnicos)"),
    (9, "LEI 14.133/2021, ART. 74, III, B", "Lei 14.133/21 - Art. 74, III, b (Pareceres/Perícias)"),
    (10, "LEI 14.133/2021, ART. 74, III, C", "Lei 14.133/21 - Art. 74, III, c (Assessorias/Consultorias)"),
    (11, "LEI 14.133/2021, ART. 74, III, D", "Lei 14.133/21 - Art. 74, III, d (Fiscalização/Supervisão)"),
    (12, "LEI 14.133/2021, ART. 74, III, E", "Lei 14.133/21 - Art. 74, III, e (Patrocínio/Defesa Judicial)"),
    (13, "LEI 14.133/2021, ART. 74, III, F", "Lei 14.133/21 - Art. 74, III, f (Treinamento/Pessoal)"),
    (14, "LEI 14.133/2021, ART. 74, III, G", "Lei 14.133/21 - Art. 74, III, g (Restauração Histórica)"),
    (15, "LEI 14.133/2021, ART. 74, III, H", "Lei 14.133/21 - Art. 74, III, h (Controles de Qualidade)"),
    (16, "LEI 14.133/2021, ART. 74, IV", "Lei 14.133/21 - Art. 74, IV (Credenciamento - Inexigibilidade)"),
    (17, "LEI 14.133/2021, ART. 74, V", "Lei 14.133/21 - Art. 74, V (Aquisição/Locação Imóvel)"),
    (50, "LEI 14.133/2021, ART. 74, CAPUT", "Lei 14.133/21 - Art. 74, caput (Inexigibilidade Geral)"),
    # Inexigibilidade Estatais
    (102, "LEI 13.303/2016, ART. 30, CAPUT - INEXIGIBILIDADE", "Lei 13.303/16 - Art. 30 (Inexigibilidade)"),
    (104, "LEI 13.303/2016, ART. 30, I", "Lei 13.303/16 - Art. 30, I (Fornecedor Exclusivo)"),

    # === CREDENCIAMENTO ===
    (47, "LEI 14.133/2021, ART. 78, I", "Lei 14.133/21 - Art. 78, I (Credenciamento - Proc. Auxiliar)"),
    (140, "LEI 14.133/2021, ART. 79, I", "Lei 14.133/21 - Art. 79, I (Credenciamento Paralelo)"),
    (141, "LEI 14.133/2021, ART. 79, II", "Lei 14.133/21 - Art. 79, II (Credenciamento c/ Seleção)"),
    (142, "LEI 14.133/2021, ART. 79, III", "Lei 14.133/21 - Art. 79, III (Credenciamento Mercados Fluidos)"),
    (103, "LEI 13.303/2016, ART. 30, CAPUT - CREDENCIAMENTO", "Lei 13.303/16 - Credenciamento"),
    (125, "REGULAMENTO INTERNO DE LICITACOES E CONTRATOS ESTATAIS - CREDENCIAMENTO", "Regulamento Interno - Credenciamento"),

    # === PRÉ-QUALIFICAÇÃO ===
    (48, "LEI 14.133/2021, ART. 78, II", "Lei 14.133/21 - Art. 78, II (Pré-qualificação)"),
    (122, "LEI 13.303/2016, ART. 63, I", "Lei 13.303/16 - Art. 63, I (Pré-qualificação Permanente)"),

    # === ADESÃO A ATA (Carona) ===
    # O PNCP V1 não tem ID específico no range 1-199 para "Art 86 Carona" como amparo primário.
    # Geralmente utiliza-se a fundamentação de dispensa ou processo próprio. 
    # Mapeamos aqui para seleção no sistema, mas o envio ao PNCP pode requerer ajuste no service.py.
    # Usaremos um ID placeholder (ex: None) ou mapearemos para um genérico se necessário.
    (None, "LEI 14.133/2021, ART. 86, 2", "Lei 14.133/21 - Art. 86, § 2º (Adesão a Ata/Carona)"),
]


# ==============================================================================
# GERAÇÃO AUTOMÁTICA DE CHOICES E MAPAS
# ==============================================================================

# Choices para o Django (chave, label)
MODALIDADE_CHOICES = [(item[1], item[2]) for item in _MODALIDADE_DATA]
MODO_DISPUTA_CHOICES = [(item[1], item[2]) for item in _MODO_DISPUTA_DATA]
AMPARO_LEGAL_CHOICES = [(item[1], item[2]) for item in _AMPARO_LEGAL_DATA]
CRITERIO_JULGAMENTO_CHOICES = [(item[1], item[2]) for item in _CRITERIO_JULGAMENTO_DATA]
ORIGEM_RECURSO_CHOICES = [(item[1], item[2]) for item in _ORIGEM_RECURSO_DATA]
TIPO_INSTRUMENTO_CONVOCATORIO_CHOICES = [(item[1], item[2]) for item in _TIPO_INSTRUMENTO_CONVOCATORIO_DATA]

# Mapas para o Service/API (chave -> id_pncp)
# Filtra apenas itens que têm ID válido (diferente de None)
MAP_MODALIDADE_PNCP = {item[1]: item[0] for item in _MODALIDADE_DATA if item[0] is not None}
MAP_MODO_DISPUTA_PNCP = {item[1]: item[0] for item in _MODO_DISPUTA_DATA if item[0] is not None}
MAP_AMPARO_LEGAL_PNCP = {item[1]: item[0] for item in _AMPARO_LEGAL_DATA if item[0] is not None}
MAP_CRITERIO_JULGAMENTO_PNCP = {item[1]: item[0] for item in _CRITERIO_JULGAMENTO_DATA if item[0] is not None}
MAP_ORIGEM_RECURSO_PNCP = {item[1]: item[0] for item in _ORIGEM_RECURSO_DATA if item[0] is not None}
MAP_TIPO_INSTRUMENTO_CONVOCATORIO_PNCP = {item[1]: item[0] for item in _TIPO_INSTRUMENTO_CONVOCATORIO_DATA if item[0] is not None}


# ==============================================================================
# OUTROS CHOICES (Estáticos)
# ==============================================================================

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

CLASSIFICACAO_CHOICES = (
    ('COMPRAS', 'Compras'),
    ('SERVICOS COMUNS', 'Serviços Comuns'),
    ('SERVICOS DE ENGENHARIA COMUNS', 'Serviços de Engenharia Comuns'),
    ('OBRAS COMUNS', 'Obras Comuns'),
)

TIPO_ORGANIZACAO_CHOICES = (
    ('LOTE', 'Lote'), 
    ('ITEM', 'Item')
)

SITUACAO_CHOICES = (
    ('ABERTO', 'Aberto'),
    ('EM PESQUISA', 'Em Pesquisa'),
    ('AGUARDANDO PUBLICACAO', 'Aguardando Publicação'),
    ('PUBLICADO', 'Publicado'),
    ('EM CONTRATACAO', 'Em Contratação'),
    ('ADJUDICADO/HOMOLOGADO', 'Adjudicado/Homologado'),
    ('REVOGADO/CANCELADO', 'Revogado/Cancelado'),
)

TIPO_PESSOA_CHOICES = (
    ('PJ', 'Pessoa Jurídica'), 
    ('PF', 'Pessoa Física')
)