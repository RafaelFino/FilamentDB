#!/usr/bin/env python3
"""
install-creality-profiles.py

Script para descobrir automaticamente o caminho do Creality Print e copiar
os perfis exportados para a instalação local.
"""

import os
import shutil
import platform
from pathlib import Path


def find_creality_print_path():
    """Descobre o caminho de instalação do Creality Print baseado no sistema operacional."""
    system = platform.system()
    home = Path.home()
    
    possible_paths = []
    
    if system == "Linux":
        # Linux: ~/.config/Creality/Creality Print/7.0/
        possible_paths = [
            home / ".config" / "Creality" / "Creality Print" / "7.0",
            home / ".config" / "Creality" / "Creality Print",
        ]
    elif system == "Darwin":  # macOS
        # macOS: ~/Library/Application Support/Creality/Creality Print/7.0/
        possible_paths = [
            home / "Library" / "Application Support" / "Creality" / "Creality Print" / "7.0",
            home / "Library" / "Application Support" / "Creality" / "Creality Print",
        ]
    elif system == "Windows":
        # Windows: %APPDATA%\Creality\Creality Print\7.0\
        appdata = os.environ.get("APPDATA", "")
        if appdata:
            possible_paths = [
                Path(appdata) / "Creality" / "Creality Print" / "7.0",
                Path(appdata) / "Creality" / "Creality Print",
            ]
    
    # Verificar qual caminho existe
    for path in possible_paths:
        if path.exists():
            print(f"✓ Creality Print encontrado em: {path}")
            return path
    
    print("✗ Creality Print não encontrado nos caminhos padrão.")
    print("Caminhos verificados:")
    for path in possible_paths:
        print(f"  - {path}")
    
    return None


def get_user_id(creality_path):
    """Descobre o ID do usuário do Creality Print."""
    user_path = creality_path / "user"
    
    if not user_path.exists():
        print(f"✗ Pasta user não encontrada em: {user_path}")
        return None
    
    # Listar subdiretórios na pasta user
    user_dirs = [d for d in user_path.iterdir() if d.is_dir() and d.name != "Temp" and d.name != "default"]
    
    if not user_dirs:
        print("✗ Nenhum diretório de usuário encontrado.")
        return None
    
    if len(user_dirs) == 1:
        user_id = user_dirs[0].name
        print(f"✓ ID do usuário encontrado: {user_id}")
        return user_id
    
    # Se houver múltiplos, usar o mais recente
    print(f"✓ Múltiplos usuários encontrados: {[d.name for d in user_dirs]}")
    print(f"✓ Usando o mais recente: {user_dirs[-1].name}")
    return user_dirs[-1].name


def copy_filament_profiles(source_dir, target_dir, user_id):
    """Copia os perfis de filamento para a pasta do Creality Print."""
    filament_dir = target_dir / "user" / user_id / "filament"
    
    if not filament_dir.exists():
        print(f"✗ Pasta filament não encontrada em: {filament_dir}")
        print(f"  Criando pasta...")
        filament_dir.mkdir(parents=True, exist_ok=True)
    
    source_files = list(Path(source_dir).glob("*.json"))
    
    if not source_files:
        print(f"✗ Nenhum arquivo .json encontrado em: {source_dir}")
        return False
    
    copied = 0
    for json_file in source_files:
        info_file = json_file.with_suffix('.info')
        
        # Copiar arquivo JSON
        shutil.copy2(json_file, filament_dir / json_file.name)
        
        # Copiar arquivo INFO se existir
        if info_file.exists():
            shutil.copy2(info_file, filament_dir / info_file.name)
        
        copied += 1
        print(f"✓ Copiado: {json_file.name}")
    
    print(f"✓ Total de perfis de filamento copiados: {copied}")
    return True


def copy_process_profiles(source_dir, target_dir, user_id):
    """Copia os perfis de processo para a pasta do Creality Print."""
    process_dir = target_dir / "user" / user_id / "process"
    
    if not process_dir.exists():
        print(f"✗ Pasta process não encontrada em: {process_dir}")
        print(f"  Criando pasta...")
        process_dir.mkdir(parents=True, exist_ok=True)
    
    source_files = list(Path(source_dir).glob("*.json"))
    
    if not source_files:
        print(f"✗ Nenhum arquivo .json encontrado em: {source_dir}")
        return False
    
    copied = 0
    for json_file in source_files:
        info_file = json_file.with_suffix('.info')
        
        # Copiar arquivo JSON
        shutil.copy2(json_file, process_dir / json_file.name)
        
        # Copiar arquivo INFO se existir
        if info_file.exists():
            shutil.copy2(info_file, process_dir / info_file.name)
        
        copied += 1
        print(f"✓ Copiado: {json_file.name}")
    
    print(f"✓ Total de perfis de processo copiados: {copied}")
    return True


def main():
    print("=" * 60)
    print("Instalador de Perfis - Creality Print")
    print("=" * 60)
    print()
    
    # Descobrir caminho do Creality Print
    creality_path = find_creality_print_path()
    
    if not creality_path:
        print("\nPor favor, especifique manualmente o caminho do Creality Print:")
        custom_path = input("Caminho: ").strip()
        if custom_path:
            creality_path = Path(custom_path)
            if not creality_path.exists():
                print(f"✗ Caminho inválido: {custom_path}")
                return
        else:
            return
    
    print()
    
    # Descobrir ID do usuário
    user_id = get_user_id(creality_path)
    if not user_id:
        print("\nNão foi possível identificar o ID do usuário.")
        print("Por favor, verifique a instalação do Creality Print.")
        return
    
    print()
    
    # Diretórios de origem (dentro do projeto)
    project_root = Path(__file__).parent
    filament_source = project_root / "creality-print"
    process_source = project_root / "creality-print-process"
    
    # Copiar perfis de filamento
    print("-" * 60)
    print("Copiando perfis de filamento...")
    print("-" * 60)
    if filament_source.exists():
        copy_filament_profiles(filament_source, creality_path, user_id)
    else:
        print(f"✗ Diretório de origem não encontrado: {filament_source}")
        print("  Execute 'python export-creality-print.py' primeiro.")
    
    print()
    
    # Copiar perfis de processo
    print("-" * 60)
    print("Copiando perfis de processo...")
    print("-" * 60)
    if process_source.exists():
        copy_process_profiles(process_source, creality_path, user_id)
    else:
        print(f"✗ Diretório de origem não encontrado: {process_source}")
        print("  Execute 'python export-process.py' primeiro.")
    
    print()
    print("=" * 60)
    print("Instalação concluída!")
    print("=" * 60)
    print()
    print("Abra o Creality Print para verificar os novos perfis.")


if __name__ == "__main__":
    main()
