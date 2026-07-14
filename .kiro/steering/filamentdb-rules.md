# FilamentDB — Regras de Projeto

## Impressora e Setup

- Impressora: Creality K2 (CoreXY, Direct Drive)
- Nozzle: 0.4mm
- Filamentos premium: Voolt3D Velvet, Sunlu High Speed (principal uso)

## Hierarquia de Perfis de Processo

Do mais rápido ao mais caprichado:

```
Draft → Fast → Balanced → Refined → Extreme → Strong
```

- **Draft**: Rápido e econômico, mas funcional (não frágil). Validação de conceito com resistência suficiente para manuseio e encaixes.
- **Fast**: Velocidade máxima com acabamento superior ao Draft (outer/inner, mais top layers).
- **Balanced**: Padrão de uso comum, equilíbrio geral (default).
- **Refined**: Caprichado, um passo acima do Balanced sem chegar no extremo.
- **Extreme**: Máxima qualidade visual, o mais lento e detalhado.
- **Strong**: Resistência mecânica (6 walls, 55% infill).

## Restrições de Materiais Especiais

- **ABS, TPU, PLA-CF, PETG-CF**: Apenas em **0.20mm Balanced**. Não gerar outros layer heights ou profile types para esses materiais.
- **PLA e PETG**: Disponíveis em todos os profile types e layer heights definidos no combinations.json.

## Fabricantes para Exportação

Apenas exportar perfis de filamento dos seguintes fabricantes:

- Voolt3D
- Creality
- Sunlu
- F3D
- Elegoo

Os demais fabricantes ficam no banco (filament-data/) para referência mas não são exportados para Creality-Print/.

## Limites Volumétricos

Todas as velocidades de extrusão devem respeitar o fluxo volumétrico máximo do material:

```
max_speed = (MVS × 0.85) / (layer_height × 0.45)
```

O sistema de cap no build.py garante isso automaticamente. Nunca definir velocidades manuais que excedam esses limites.

## Estrutura de Dados

- `filament-data/*.yaml` — fonte de verdade para filamentos
- `process-base/` — sistema de herança para perfis de processo
- `build.py` — pipeline que gera banco SQLite + exporta para Creality-Print/
- `Creality-Print/` — output final para importar no slicer
