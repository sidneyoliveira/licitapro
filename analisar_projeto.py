import os

# --- CONFIGURAÇÕES ---
# O diretório do seu projeto que você quer analisar
project_directory = '.'  # '.' significa o diretório atual onde o script está

# O nome do arquivo de saída que será gerado
output_filename = 'codigo_completo.txt'

# Pastas que você quer ignorar (muito importante para não incluir coisas desnecessárias)
exclude_dirs = {
    'node_modules',
    'venv',
    '.git',
    '__pycache__',
    '.vscode',
    'dist',
    'build',
    # Adicione outras pastas que não são relevantes, como 'docs', 'tests', etc. se quiser
}

# Extensões de arquivo que você quer ignorar
exclude_extensions = {
    '.pyc',
    '.log',
    '.tmp',
    '.DS_Store',
    '.zip',
    '.tar.gz',
    '.jpg',
    '.png',
    '.svg',
    # Adicione outras extensões de arquivos de mídia, binários, etc.
}
# ---------------------

def should_exclude(path, is_dir):
    """Verifica se um arquivo ou diretório deve ser excluído."""
    parts = set(path.split(os.sep))
    if parts.intersection(exclude_dirs):
        return True
    if not is_dir:
        _, ext = os.path.splitext(path)
        if ext in exclude_extensions:
            return True
    return False

def analyze_project(directory, output_file):
    """Percorre o projeto e escreve o conteúdo dos arquivos no arquivo de saída."""
    for root, dirs, files in os.walk(directory, topdown=True):
        # Filtra os diretórios a serem ignorados
        dirs[:] = [d for d in dirs if not should_exclude(os.path.join(root, d), True)]
        
        for file_name in files:
            file_path = os.path.join(root, file_name)
            relative_path = os.path.relpath(file_path, directory)

            if should_exclude(relative_path, False):
                continue
            
            # Escreve um cabeçalho para cada arquivo
            output_file.write('=' * 80 + '\n')
            output_file.write(f'ARQUIVO: {relative_path}\n')
            output_file.write('=' * 80 + '\n\n')
            
            # Tenta ler e escrever o conteúdo do arquivo
            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    output_file.write(f.read())
                output_file.write('\n\n')
            except Exception as e:
                output_file.write(f'!!! Erro ao ler o arquivo: {e} !!!\n\n')

# --- EXECUÇÃO ---
try:
    with open(output_filename, 'w', encoding='utf-8') as f_out:
        print(f"Analisando o projeto em '{os.path.abspath(project_directory)}'...")
        analyze_project(project_directory, f_out)
        print(f"\nSucesso! Todo o código foi consolidado em '{output_filename}'.")
        print("Agora, por favor, abra este arquivo, copie todo o seu conteúdo e cole-o aqui no chat.")
except Exception as e:
    print(f"Ocorreu um erro: {e}")