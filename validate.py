#!/usr/bin/env python3
"""validate.py — Validador de invariantes dos perfis de processo do FilamentDB.

Este módulo é **read-only e determinístico**: valida os perfis de processo
GERADOS EM MEMÓRIA por ``build.generate_process_profile`` (antes do export),
sem escrever nenhum arquivo, perfil ou banco. Ele é a guarda automática contra
a classe de bug que motivou a spec ``profile-audit-consistency`` — em especial o
``initial_layer_print_height`` não-múltiplo do ``layer_height`` (o bug do Safe).

As invariantes são funções puras (uma por regra), cada uma recebendo o contexto
necessário e devolvendo ``list[Violation]`` (lista vazia = OK). Nenhuma função
pura chama ``build.error()`` nem ``sys.exit()``: a decisão de falhar o build
(severidade "high") ou apenas avisar ("medium"/"low") mora na integração em
``build.seed_processes()``.

Filosofia inegociável (steering ``.kiro/steering/filamentdb-rules.md``): o MVS é
responsabilidade **exclusiva do filamento** — nenhuma invariante aqui lê ou
valida ``max_volumetric_speed``. O cap de velocidade/aceleração é responsabilidade
**exclusiva do device** (``device["limits"]``).

Estrutura do item de entrada (``GeneratedProfile``):
  - ``profile``: dict do perfil gerado em memória (valores de velocidade/aceleração
    como string, ex. ``"300.0"``; ``layer_height`` e ``initial_layer_print_height``
    como string, ex. ``"0.20"``).
  - ``profile_type``: id do profile type (ex. ``"standard"``, ``"safe"``).
  - ``layer_height``: string original do layer height (ex. ``"0.20"``).
  - ``material``: nome do material de processo (ex. ``"PLA"``).
  - ``device``: dict do device já carregado por ``build.load_device`` (contém
    ``id``, ``display_name``, ``limits``, ``slicers``).

``run_all(profiles, devices, source_defs)`` roda todas as invariantes sobre a
lista de ``GeneratedProfile`` e concatena o resultado.

``import build`` no topo é seguro: ``build`` NÃO importa ``validate`` no topo —
ele faz um **import tardio** de ``validate`` dentro de ``seed_processes()``, o
que quebra o ciclo (quando ``validate`` roda ``import build``, o módulo ``build``
já está totalmente carregado em ``sys.modules``).
"""

import json
from dataclasses import dataclass
from typing import Any

import build

# Tolerância para razões de layer height (múltiplo inteiro).
EPS = 1e-6
# Tolerância relativa para a matemática de multiplicadores (strings "300.0" vs
# recomputação em float).
REL_TOL = 1e-3
# Largura mínima da prime tower (steering: >= 35mm para reduzir desperdício).
PRIME_TOWER_MIN_WIDTH = 35

# Faixa absoluta sã para distâncias de suporte (mm). Simplificação deliberada:
# em vez de comparar com a escala do layer height vizinho (que exigiria conhecer
# todos os perfis vizinhos), usamos uma faixa absoluta plausível. O achado de
# monotonicidade/vizinhança da auditoria já foi corrigido na process-base (2.2);
# aqui garantimos apenas que os valores ficam dentro de limites sãos.
SUPPORT_INTERFACE_SPACING_RANGE = (0.2, 2.0)
SUPPORT_OBJECT_XY_RANGE = (0.2, 1.5)


@dataclass
class Violation:
    """Uma violação de invariante encontrada sobre um perfil gerado.

    severity ∈ {"high", "medium", "low"}. "high" falha o build; "medium"/"low"
    viram aviso. A mensagem (``__str__``) é renderizada em pt-BR e cita o
    arquivo-fonte em ``process-base/``, a invariante, o valor obtido e o esperado.
    """

    severity: str
    source_path: str
    invariant: str
    detail: str
    got: Any
    expected: Any

    def __str__(self) -> str:
        sev = {"high": "ALTA", "medium": "MÉDIA", "low": "BAIXA"}.get(
            self.severity, self.severity.upper()
        )
        return (
            f"[{sev}] {self.invariant} em {self.source_path}: {self.detail} "
            f"(obtido={self.got!r}, esperado={self.expected!r})"
        )


@dataclass
class GeneratedProfile:
    """Perfil de processo gerado + metadados de origem para citar a fonte."""

    profile: dict
    profile_type: str
    layer_height: str
    material: str
    device: dict


# =============================================================================
# Helpers internos (puros)
# =============================================================================

def _to_float(value):
    """Converte um valor (possivelmente string "300.0") para float; None se falhar."""
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _load_material_base(material: str) -> dict:
    """Carrega as velocidades base do material de process-base/materials/<MAT>.json.

    Leitura read-only. Retorna {} se o arquivo não existir (não é papel desta
    invariante falhar por arquivo ausente — check_combinations cobre estrutura).
    """
    path = build.PROCESS_BASE_DIR / "materials" / f"{material}.json"
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_profile_type_raw(profile_type: str) -> dict:
    """Carrega o JSON bruto do profile type (read-only). {} se ausente."""
    path = build.PROCESS_BASE_DIR / "profile_types" / f"{profile_type}.json"
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def expected_profile_count(source_defs: dict) -> int:
    """Deriva a contagem esperada de perfis expandindo combinations.json.

    Σ len(layer_heights) × len(materials) × len(devices_da_combo). Zero hardcode:
    o contrato de contagem (atualmente 51) resulta diretamente da matriz, então o
    validador acompanha qualquer mudança futura sem edição.
    """
    default_devices = source_defs.get("default_devices", ["k2"])
    total = 0
    for combo in source_defs.get("combinations", []):
        devices = combo.get("devices", default_devices)
        total += len(combo.get("layer_heights", [])) * len(
            combo.get("materials", [])
        ) * len(devices)
    return total


# =============================================================================
# Invariantes (funções puras)
# =============================================================================

def check_layer_multiple(item: GeneratedProfile) -> list[Violation]:
    """Coerência entre initial_layer_print_height e layer_height.

    INVARIANTE CRÍTICA. Causa raiz verificada empiricamente no Creality Print:
    quando a PRIME TOWER está ligada (nosso caso em 100% dos perfis), o slicer
    deixa de reconhecer o multifilamento/CFS se a primeira camada difere da
    altura de camada. Observado: 0.16 Detail (initial 0.16 == layer) reconhece
    multicor; 0.12 Detail (initial 0.24 != layer 0.12) NÃO reconhece, apesar de
    0.24/0.12=2 ser múltiplo inteiro. Logo "múltiplo inteiro" é fraco demais —
    com prime tower a condição segura é ``initial == layer``.

    Regra:
      - prime tower ligada  → exige initial == layer_height (HIGH se diferir).
      - prime tower desligada → piso mínimo: initial deve ser múltiplo inteiro
        de layer_height (classe do bug do Safe / warning de altura de camada).

    Valida o perfil GERADO (pós ADHESION_OVERRIDE_FIELDS). Fonte citada: se o
    valor gerado coincide com o override do profile_type, cita o profile_type;
    senão o layer_heights/<layer>.json.
    """
    profile = item.profile
    lh = _to_float(item.layer_height)
    initial = _to_float(profile.get("initial_layer_print_height"))
    violations: list[Violation] = []
    if lh is None or initial is None or lh <= 0:
        return violations

    # Fonte do desalinhamento (profile_type override vs layer_height).
    pt_raw = _load_profile_type_raw(item.profile_type)
    pt_initial = _to_float(pt_raw.get("initial_layer_print_height"))
    if pt_initial is not None and abs(pt_initial - initial) <= EPS:
        source = f"process-base/profile_types/{item.profile_type}.json"
    else:
        source = f"process-base/layer_heights/{item.layer_height}.json"

    # Prime tower ligada? (string "1"/"true" ou número). Nosso default é ligada.
    pt_flag = str(profile.get("enable_prime_tower", "")).strip().lower()
    prime_tower_on = pt_flag in ("1", "true", "yes", "on")

    if prime_tower_on:
        if abs(initial - lh) > EPS:
            violations.append(
                Violation(
                    severity="high",
                    source_path=source,
                    invariant="check_layer_multiple",
                    detail=(
                        f"Com a prime tower ligada, initial_layer_print_height "
                        f"({initial}) deve ser IGUAL a layer_height ({lh}). "
                        f"Diferença faz o Creality Print perder o reconhecimento "
                        f"de multifilamento/CFS no perfil "
                        f"{profile.get('name', item.profile_type)} (verificado: "
                        f"0.12 Detail com initial 0.24 quebra; 0.16 com initial "
                        f"igual ao layer funciona)."
                    ),
                    got=initial,
                    expected=f"== layer_height ({lh})",
                )
            )
    else:
        ratio = initial / lh
        if abs(ratio - round(ratio)) > EPS:
            violations.append(
                Violation(
                    severity="high",
                    source_path=source,
                    invariant="check_layer_multiple",
                    detail=(
                        f"initial_layer_print_height ({initial}) não é múltiplo "
                        f"inteiro de layer_height ({lh}); razão = {ratio:.4f}. "
                        f"Perfil {profile.get('name', item.profile_type)} "
                        f"dispararia o warning de altura de camada."
                    ),
                    got=initial,
                    expected=f"múltiplo inteiro de {lh}",
                )
            )
    return violations


def check_device_caps(item: GeneratedProfile) -> list[Violation]:
    """Nenhuma velocidade/aceleração gerada pode ultrapassar os caps do device.

    Caps vêm exclusivamente de ``device["limits"]`` (k2=600/800/20000,
    cc2=500/500/20000). As velocidades/acelerações no perfil gerado vêm como
    STRING (ex. "300.0") — convertidas para float. travel_speed usa o cap de
    travel; os demais SPEED_FIELDS usam o cap de extrusão; ACCEL_FIELDS usam o
    cap de aceleração.
    """
    profile = item.profile
    limits = item.device["limits"]
    extrusion_cap = float(limits["max_extrusion_speed"])
    travel_cap = float(limits["max_travel_speed"])
    accel_cap = float(limits["max_acceleration"])
    source = f"process-base/devices/{item.device['id']}.json"
    violations: list[Violation] = []

    for field in build.SPEED_FIELDS:
        val = _to_float(profile.get(field))
        if val is None:
            continue
        cap = travel_cap if field == "travel_speed" else extrusion_cap
        kind = "travel" if field == "travel_speed" else "extrusão"
        if val > cap + EPS:
            violations.append(
                Violation(
                    severity="high",
                    source_path=source,
                    invariant="check_device_caps",
                    detail=(
                        f"{field} ({val}) ultrapassa o cap de {kind} do device "
                        f"'{item.device['id']}' no perfil "
                        f"{profile.get('name', item.profile_type)}."
                    ),
                    got=val,
                    expected=f"<= {cap}",
                )
            )

    for field in build.ACCEL_FIELDS:
        val = _to_float(profile.get(field))
        if val is None:
            continue
        if val > accel_cap + EPS:
            violations.append(
                Violation(
                    severity="high",
                    source_path=source,
                    invariant="check_device_caps",
                    detail=(
                        f"{field} ({val}) ultrapassa o cap de aceleração do device "
                        f"'{item.device['id']}' no perfil "
                        f"{profile.get('name', item.profile_type)}."
                    ),
                    got=val,
                    expected=f"<= {accel_cap}",
                )
            )
    return violations


def check_multiplier_math(item: GeneratedProfile) -> list[Violation]:
    """valor_gerado ≈ base_material × multiplicador (do profile type) × speed_scale.

    Para cada SPEED_FIELD presente no material: o multiplicador é ``quality_speed``
    se o campo ∈ QUALITY_SPEED_FIELDS e o profile type declara ``quality_speed``;
    senão ``speed``. Para ACCEL_FIELDS usa ``accel``. Também multiplica pelos
    multiplicadores de material (speed_multiplier / acceleration_multiplier) —
    que a filosofia manda serem 1.0.

    REDUÇÃO POR ALTURA DE CAMADA (``speed_scale`` do layer_heights/<lh>.json):
    ``generate_process_profile`` aplica ``speed_scale`` a TODOS os SPEED_FIELDS
    exceto ``travel_speed`` ANTES dos caps (0.24=0.85, 0.28=0.75, ≤0.20=1.0). O
    esperado incorpora esse fator para não gerar falso-positivo HIGH em 0.24/0.28.
    A fonte da redução é a ALTURA DE CAMADA, nunca o MVS do material.

    Decisão quando gerado < esperado: se o gerado bate exatamente num cap aplicável
    (device ou cap de layer_height), é capamento legítimo → OK. Caso contrário:
      - se o multiplicador de material != 1.0 → dupla penalização (MÉDIA);
      - senão → discrepância real inexplicada (ALTA).
    """
    profile = item.profile
    material_base = _load_material_base(item.material)
    if not material_base:
        return []
    mult = build.PROFILE_MULTIPLIERS.get(item.profile_type, {"speed": 1.0, "accel": 1.0})
    material_speed_mult = material_base.get("speed_multiplier", 1.0)
    material_accel_mult = material_base.get("acceleration_multiplier", 1.0)

    limits = item.device["limits"]
    extrusion_cap = float(limits["max_extrusion_speed"])
    travel_cap = float(limits["max_travel_speed"])
    accel_cap = float(limits["max_acceleration"])

    # Caps de layer_height (ex. initial_layer_speed reduzido) e speed_scale: lidos
    # read-only de layer_heights/<lh>.json.
    layer_path = build.PROCESS_BASE_DIR / "layer_heights" / f"{item.layer_height}.json"
    layer_data = {}
    if layer_path.exists():
        with open(layer_path, "r", encoding="utf-8") as f:
            layer_data = json.load(f)
    speed_scale = _to_float(layer_data.get("speed_scale", 1.0)) or 1.0

    source = f"process-base/materials/{item.material}.json"
    violations: list[Violation] = []

    def _check(field, base_val, multiplier, material_mult, caps, scale):
        gerado = _to_float(profile.get(field))
        if gerado is None or base_val is None:
            return
        esperado = base_val * multiplier * material_mult * scale
        denom = max(abs(esperado), EPS)
        if abs(gerado - esperado) / denom <= REL_TOL:
            return
        # Gerado abaixo do esperado pode ser capamento legítimo.
        if gerado < esperado:
            for cap in caps:
                if cap is not None and abs(gerado - cap) <= max(abs(cap), EPS) * REL_TOL:
                    return  # capado — OK
        if material_mult != 1.0:
            violations.append(
                Violation(
                    severity="medium",
                    source_path=source,
                    invariant="check_multiplier_math",
                    detail=(
                        f"{field}: possível dupla penalização — o material aplica "
                        f"multiplicador {material_mult} (deveria ser 1.0, o cap mora "
                        f"no filamento). Perfil {profile.get('name', item.profile_type)}."
                    ),
                    got=gerado,
                    expected=esperado,
                )
            )
        else:
            violations.append(
                Violation(
                    severity="high",
                    source_path=source,
                    invariant="check_multiplier_math",
                    detail=(
                        f"{field}: valor gerado não bate com base × multiplicador × "
                        f"speed_scale ({base_val} × {multiplier} × {scale}). Perfil "
                        f"{profile.get('name', item.profile_type)}."
                    ),
                    got=gerado,
                    expected=esperado,
                )
            )

    for field in build.SPEED_FIELDS:
        if field not in material_base:
            continue
        base_val = _to_float(material_base.get(field))
        if field in mult.get("field_multipliers", {}):
            multiplier = mult["field_multipliers"][field]
        elif field in build.QUALITY_SPEED_FIELDS and "quality_speed" in mult:
            multiplier = mult["quality_speed"]
        else:
            multiplier = mult["speed"]
        cap = travel_cap if field == "travel_speed" else extrusion_cap
        layer_cap = _to_float(layer_data.get(field))
        # travel_speed NÃO recebe speed_scale (movimento sem extrusão).
        field_scale = 1.0 if field == "travel_speed" else speed_scale
        _check(field, base_val, multiplier, material_speed_mult, [cap, layer_cap], field_scale)

    for field in build.ACCEL_FIELDS:
        if field not in material_base:
            continue
        base_val = _to_float(material_base.get(field))
        # Aceleração não é escalada por speed_scale.
        _check(field, base_val, mult["accel"], material_accel_mult, [accel_cap], 1.0)

    return violations


def check_shell_thickness(item: GeneratedProfile) -> list[Violation]:
    """top/bottom_shell_thickness ≈ top/bottom_shell_layers × layer_height.

    Severidade MÉDIA: o stock faz o mesmo acoplamento solto (o slicer resolve por
    max(layers, ceil(thickness/lh))). É previsibilidade, não erro. Tolera campos
    ausentes. NUNCA quebra o build.
    """
    profile = item.profile
    lh = _to_float(item.layer_height)
    if lh is None or lh <= 0:
        return []
    source = f"process-base/layer_heights/{item.layer_height}.json"
    violations: list[Violation] = []

    for layers_field, thickness_field, nome in (
        ("top_shell_layers", "top_shell_thickness", "top"),
        ("bottom_shell_layers", "bottom_shell_thickness", "bottom"),
    ):
        layers = _to_float(profile.get(layers_field))
        thickness = _to_float(profile.get(thickness_field))
        if layers is None or thickness is None:
            continue
        esperado = layers * lh
        denom = max(abs(esperado), EPS)
        if abs(thickness - esperado) / denom > REL_TOL:
            violations.append(
                Violation(
                    severity="medium",
                    source_path=source,
                    invariant="check_shell_thickness",
                    detail=(
                        f"{thickness_field} ({thickness}) != {layers_field} ({int(layers)}) "
                        f"× layer_height ({lh}) = {esperado:.3f}. Acoplamento solto "
                        f"shell_layers (profile_type) vs shell_thickness (layer_height); "
                        f"o slicer resolve por max(layers, ceil(thickness/lh))."
                    ),
                    got=thickness,
                    expected=esperado,
                )
            )
    return violations


def check_support_distances(item: GeneratedProfile) -> list[Violation]:
    """support_top_z_distance >= layer_height; spacing/xy dentro de faixa sã.

    Severidade MÉDIA. SIMPLIFICAÇÃO deliberada: em vez de comparar com a escala
    do layer height vizinho (exigiria todos os perfis vizinhos), usamos uma faixa
    absoluta sã (SUPPORT_*_RANGE) — a monotonicidade entre vizinhos já foi
    restaurada na process-base (correção 2.2). Tolera campos ausentes.
    """
    profile = item.profile
    lh = _to_float(item.layer_height)
    source = f"process-base/layer_heights/{item.layer_height}.json"
    violations: list[Violation] = []

    z = _to_float(profile.get("support_top_z_distance"))
    if z is not None and lh is not None and z + EPS < lh:
        violations.append(
            Violation(
                severity="medium",
                source_path=source,
                invariant="check_support_distances",
                detail=(
                    f"support_top_z_distance ({z}) menor que layer_height ({lh}): o gap "
                    f"de topo fica abaixo de uma camada e o suporte funde na peça "
                    f"(contraria a filosofia PETG de remoção fácil)."
                ),
                got=z,
                expected=f">= {lh}",
            )
        )

    spacing = _to_float(profile.get("support_interface_spacing"))
    if spacing is not None and not (
        SUPPORT_INTERFACE_SPACING_RANGE[0] <= spacing <= SUPPORT_INTERFACE_SPACING_RANGE[1]
    ):
        violations.append(
            Violation(
                severity="medium",
                source_path=source,
                invariant="check_support_distances",
                detail=(
                    f"support_interface_spacing ({spacing}) fora da faixa sã "
                    f"{SUPPORT_INTERFACE_SPACING_RANGE}."
                ),
                got=spacing,
                expected=f"dentro de {SUPPORT_INTERFACE_SPACING_RANGE}",
            )
        )

    xy = _to_float(profile.get("support_object_xy_distance"))
    if xy is not None and not (
        SUPPORT_OBJECT_XY_RANGE[0] <= xy <= SUPPORT_OBJECT_XY_RANGE[1]
    ):
        violations.append(
            Violation(
                severity="medium",
                source_path=source,
                invariant="check_support_distances",
                detail=(
                    f"support_object_xy_distance ({xy}) fora da faixa sã "
                    f"{SUPPORT_OBJECT_XY_RANGE}."
                ),
                got=xy,
                expected=f"dentro de {SUPPORT_OBJECT_XY_RANGE}",
            )
        )
    return violations


def check_prime_tower(item: GeneratedProfile) -> list[Violation]:
    """prime_tower_width >= 35; flush_into_objects DEVE ser 0; flags coerentes.

    ``flush_into_objects = 1`` contamina a peça em troca de cor (ALTA). Também
    confere coerência de flush_multiplier/flags com a base.json (divergência
    inesperada → MÉDIA). base.json é lido read-only.
    """
    profile = item.profile
    source = "process-base/base.json"
    violations: list[Violation] = []

    width = _to_float(profile.get("prime_tower_width"))
    if width is not None and width + EPS < PRIME_TOWER_MIN_WIDTH:
        violations.append(
            Violation(
                severity="high",
                source_path=source,
                invariant="check_prime_tower",
                detail=(
                    f"prime_tower_width ({width}) abaixo do mínimo "
                    f"{PRIME_TOWER_MIN_WIDTH}mm (steering: >= 35 para reduzir desperdício)."
                ),
                got=width,
                expected=f">= {PRIME_TOWER_MIN_WIDTH}",
            )
        )

    flush_obj = profile.get("flush_into_objects")
    if flush_obj is not None:
        flush_obj_int = int(str(flush_obj).strip().lower() in {"1", "true", "yes"})
        if flush_obj_int != 0:
            violations.append(
                Violation(
                    severity="high",
                    source_path=source,
                    invariant="check_prime_tower",
                    detail=(
                        "flush_into_objects deve ser 0 — com 1, material purgado "
                        "(cor errada) é despejado dentro do corpo das peças em trocas "
                        "de cor, contaminando a superfície/volume do objeto."
                    ),
                    got=flush_obj,
                    expected="0",
                )
            )

    # Coerência com base.json: flush_multiplier e as flags de flush devem bater
    # com a fonte de verdade (divergência inesperada no merge = aviso).
    base_path = build.PROCESS_BASE_DIR / "base.json"
    if base_path.exists():
        with open(base_path, "r", encoding="utf-8") as f:
            base_data = json.load(f)
        for field in ("flush_multiplier", "flush_into_infill", "flush_into_support"):
            if field not in base_data or field not in profile:
                continue
            base_val = _to_float(base_data[field])
            gen_val = _to_float(profile[field])
            if base_val is None or gen_val is None:
                continue
            denom = max(abs(base_val), EPS)
            if abs(gen_val - base_val) / denom > REL_TOL:
                violations.append(
                    Violation(
                        severity="medium",
                        source_path=source,
                        invariant="check_prime_tower",
                        detail=(
                            f"{field} ({gen_val}) divergente da base.json ({base_val}) — "
                            f"um profile_type ou layer_height sobrescreveu inesperadamente."
                        ),
                        got=gen_val,
                        expected=base_val,
                    )
                )
    return violations


def check_inherits_resolve(item: GeneratedProfile) -> list[Violation]:
    """Todo inherits resolvido do slicer é string não-vazia e plausível.

    Para o K2 (Creality Print + Orca), resolve a cadeia via build.resolve_inherits
    e confere que o resultado é string não-vazia e bate com o template esperado
    (contém o display_name do device). Para a CC2 (pai Elegoo ausente nesta
    máquina) degrada para severidade BAIXA/skip com nota — NUNCA falha o build
    (missing-cc2-source é WARNING/LOW por decisão de projeto).
    """
    device = item.device
    source = f"process-base/devices/{device['id']}.json"
    violations: list[Violation] = []

    for slicer in ("creality_print", "orca"):
        cfg = device["slicers"].get(slicer, {})
        if not cfg.get("enabled"):
            continue
        chain = cfg.get("process_inherits_by_layer") or []
        if not chain:
            continue
        resolved = build.resolve_inherits(
            chain, item.layer_height,
            display_name=device["display_name"],
            profile_type=item.profile_type,
        )
        if not isinstance(resolved, str) or not resolved.strip():
            violations.append(
                Violation(
                    severity="high",
                    source_path=source,
                    invariant="check_inherits_resolve",
                    detail=(
                        f"inherits do slicer '{slicer}' não resolveu para uma string "
                        f"não-vazia no layer {item.layer_height}."
                    ),
                    got=resolved,
                    expected="string não-vazia",
                )
            )
            continue
        # CC2: o perfil-pai Elegoo não existe nesta máquina — não há como
        # confirmar a existência do pai. Degrada para BAIXA (nota informativa),
        # nunca hard-fail.
        if device["id"] == "cc2":
            violations.append(
                Violation(
                    severity="low",
                    source_path=source,
                    invariant="check_inherits_resolve",
                    detail=(
                        f"inherits '{resolved}' (slicer {slicer}) aponta para um perfil-pai "
                        f"Elegoo que não existe nesta máquina — existência não verificável; "
                        f"confirmar o nome exato na instalação do OrcaSlicer alvo."
                    ),
                    got=resolved,
                    expected="pai confirmado na instalação alvo",
                )
            )
        elif device.get("display_name") and device["display_name"] not in resolved:
            # K2: o template inclui o display_name; se não aparecer, o nome é
            # implausível (provável erro de template).
            violations.append(
                Violation(
                    severity="high",
                    source_path=source,
                    invariant="check_inherits_resolve",
                    detail=(
                        f"inherits '{resolved}' (slicer {slicer}) não contém o display_name "
                        f"'{device['display_name']}' do device — template implausível."
                    ),
                    got=resolved,
                    expected=f"nome contendo '{device['display_name']}'",
                )
            )
    return violations


def check_combinations(
    profiles: list[GeneratedProfile], source_defs: dict
) -> list[Violation]:
    """Todo device em combinations.json tem arquivo; contagem = total DERIVADO.

    ``source_defs`` é o conteúdo de combinations.json. Confere (a) que todo device
    referenciado tem arquivo em process-base/devices/ e (b) que a contagem total
    de perfis gerados bate com o total DERIVADO expandindo combinations.json
    (Σ len(layer_heights) × len(materials) × len(devices)). **Zero hardcode** de
    51/86 — resistente a mudanças futuras da matriz. Divergência → ALTA.
    """
    source = "process-base/combinations.json"
    violations: list[Violation] = []

    default_devices = source_defs.get("default_devices", ["k2"])
    referenced = set(default_devices)
    for combo in source_defs.get("combinations", []):
        referenced.update(combo.get("devices", []))
    for dev_id in sorted(referenced):
        path = build.DEVICES_DIR / f"{dev_id}.json"
        if not path.exists():
            violations.append(
                Violation(
                    severity="high",
                    source_path=source,
                    invariant="check_combinations",
                    detail=(
                        f"device '{dev_id}' referenciado em combinations.json sem arquivo "
                        f"em process-base/devices/."
                    ),
                    got=dev_id,
                    expected="arquivo de device existente",
                )
            )

    expected_total = expected_profile_count(source_defs)
    total = len(profiles)
    if total != expected_total:
        violations.append(
            Violation(
                severity="high",
                source_path=source,
                invariant="check_combinations",
                detail=(
                    f"contagem de perfis de processo gerados ({total}) difere do "
                    f"total derivado de combinations.json ({expected_total}). "
                    f"Conferir combinations.json."
                ),
                got=total,
                expected=expected_total,
            )
        )
    return violations


# =============================================================================
# Orquestração
# =============================================================================

def run_all(
    profiles: list[GeneratedProfile],
    devices: dict,
    source_defs: dict,
) -> list[Violation]:
    """Roda todas as invariantes sobre os perfis gerados e concatena o resultado.

    Parâmetros:
      - ``profiles``: lista de ``GeneratedProfile`` (ver docstring do módulo para a
        estrutura do item). Cada item carrega o perfil gerado + metadados de
        origem (profile_type, layer_height, material, device).
      - ``devices``: dict ``{device_id: device_dict}`` dos devices carregados por
        ``build.load_device``. Mantido para extensões futuras; as invariantes por
        item já acessam o device via ``item.device``.
      - ``source_defs``: conteúdo de ``combinations.json`` (usado por
        ``check_combinations``).

    Retorna a lista concatenada de ``Violation`` (vazia = tudo OK). NÃO decide
    falhar o build — isso é responsabilidade da integração em build.py.
    """
    per_item_checks = (
        check_layer_multiple,
        check_device_caps,
        check_multiplier_math,
        check_shell_thickness,
        check_support_distances,
        check_prime_tower,
        check_inherits_resolve,
    )
    violations: list[Violation] = []
    for item in profiles:
        for check in per_item_checks:
            violations.extend(check(item))
    violations.extend(check_combinations(profiles, source_defs))
    return violations
