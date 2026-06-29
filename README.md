# FilamentDB

FilamentDB é um sistema centralizado baseado em SQLite para gerenciamento, estruturação e exportação de perfis de materiais para impressão 3D.

O projeto elimina a fragmentação de configurações de filamentos presentes em fatiadores. Ele centraliza as variáveis em um banco de dados relacional e gera perfis prontos para importação, com foco inicial no Creality Print 7.0.

## Problema e Solução

### Cenário Atual
* Configurações espalhadas por múltiplos presets nos fatiadores.
* Inconsistência de parâmetros entre marcas do mesmo material.
* Ajustes manuais repetitivos por impressora e bico.
* Dificuldade de migração e controle de versão de perfis.

### Solução do FilamentDB
* Banco de dados SQLite como única fonte de verdade.
* Vinculação direta entre material, impressora, bico e perfil.
* Geração automatizada de arquivos de configuração prontos para o fatiador.

## Arquitetura do Sistema

```text
SQLite Database
│
├── Marcas (Manufacturers)
├── Materiais (Materials)
├── Impressoras (Printers)
├── Bicos (Nozzles)
└── Perfis de Filamento (Filament Profiles)
│
▼
Mecanismo de Exportação (Exporter Engine)
│
▼
Perfis Creality Print 7.0 (.json + .info)
```

## Conceitos Estruturais

* **Marcas**: Cadastro de fabricantes de filamentos (ex: Creality, Sunlu, Bambu Lab).
* **Materiais**: Taxonomia de polímeros (PLA, PETG, ABS, TPU, ASA) e suas variações (Plus, Silk, Matte).
* **Impressoras**: Abstração do hardware físico (foco inicial na Creality K2 Combo).
* **Bicos**: Definição de diâmetros de saída do hardware (0.4mm, 0.6mm, 0.8mm).
* **Perfis de Filamento**: Parâmetros finais calculados (temperaturas, fluxo, velocidade volumétrica e regras de compatibilidade).

## Recursos Principais

* Banco de dados SQLite centralizado para todos os perfis.
* Taxonomia estruturada por marca, linha e material.
* Geração de perfis ciente das limitações da impressora e do bico.
* Exportação direta para o formato nativo do Creality Print 7.0.
* Reprodutibilidade total sem necessidade de ajustes manuais na interface do fatiador.

## Estrutura do Repositório

```text
FilamentDB/
├── creality-print/
|   ├── MaterialX_BrandA_NameW.yaml
|   ...
|   └── MaterialY_BrandN_NameZ.yaml
├── data/
|   ├── brandA.yaml
|   ├── brandB.yaml
|   ...
|   └── brandN.yaml
├── .gitignore
├── LICENSE
├── README.md
├── create_db.py
├── export-creality-print.py
├── filament.db
└── seed.py
```

## Instruções de Uso

### 1. Inicializar e popular o banco de dados
```bash
python create_db.py
python seed.py
```

### 2. Exportar os perfis
```bash
python export-creality-print.py
```

### 3. Importar no Creality Print 7.0
Copie os arquivos gerados para a pasta de usuário do seu fatiador:
```text
~/.config/Creality/Creality Print/7.0/user/<USER_ID>/filament
```

## Diretrizes de Design

* **Fonte Única de Verdade**: Sem duplicidade de dados ou presets órfãos.
* **Foco no Hardware**: Perfis dependem do conjunto impressora + bico, não apenas do filamento isolado.
* **Reprodutibilidade**: Qualquer perfil pode ser reconstruído do zero através do banco de dados.

## Escopo e Suporte do Projeto

### Suporte Atual
* Fatiador: Creality Print 7.0
* Impressora principal: Creality K2 Combo
* Materiais: PLA, PETG, ABS, ASA, TPU

### Planejamento de Recursos Futuros
* Exportação multiplataforma (OrcaSlicer, PrusaSlicer).
* Compatibilidade com novas impressoras (Série K1, Ender, Bambu Lab).
* Interface web para gerenciamento visual dos perfis.
* Sistema de versionamento de perfis de filamento.
* Motor de recomendação automática com base em histórico de calibração.

## Licença

Este projeto está sob a licença Apache-2.0.
