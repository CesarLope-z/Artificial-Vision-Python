"""Validacion del prompt y contadores configurables del inspector."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
import re

from detector import ObjectDetection


SPECIAL_ANALYSES = "@analisis"
SPECIAL_EMPTY = "@sin_detecciones"


def normalize(value: str) -> str:
    """Normaliza textos para comparar categorias sin depender de mayusculas."""
    return " ".join(value.casefold().strip().split())


def parse_prompt(text: str) -> list[str]:
    """Convierte el editor en una lista unica de categorias."""
    labels: list[str] = []
    seen: set[str] = set()
    for raw_line in text.splitlines():
        line = raw_line.strip().lstrip("-•").strip()
        if not line or line.startswith("#"):
            continue
        key = normalize(line)
        if key not in seen:
            seen.add(key)
            labels.append(line)
    if not labels:
        raise ValueError("Escriba al menos una categoria, una por linea.")
    return labels


def parse_counter_definitions(text: str, labels: list[str]) -> OrderedDict[str, str]:
    """Lee lineas 'nombre = categoria' y comprueba que sean validas."""
    available = {normalize(label): label for label in labels}
    counters: OrderedDict[str, str] = OrderedDict()
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError(
                f"Linea {line_number}: use el formato nombre = categoria."
            )
        raw_name, raw_target = line.split("=", 1)
        name = raw_name.strip()
        target = normalize(raw_target)
        if not name or not target:
            raise ValueError(f"Linea {line_number}: el contador esta incompleto.")
        if not re.fullmatch(r"[\w áéíóúñÁÉÍÓÚÑ-]+", name):
            raise ValueError(f"Linea {line_number}: el nombre contiene simbolos no validos.")
        if name in counters:
            raise ValueError(f"El contador '{name}' esta repetido.")
        if target not in (SPECIAL_ANALYSES, SPECIAL_EMPTY) and target not in available:
            raise ValueError(
                f"El contador '{name}' usa una categoria que no aparece en el prompt."
            )
        counters[name] = target if target.startswith("@") else available[target]
    if not counters:
        raise ValueError("Configure al menos un contador.")
    return counters


@dataclass(frozen=True)
class CountSnapshot:
    current: dict[str, int]
    totals: dict[str, int]


class ConfigurableCounters:
    """Cuenta detecciones segun reglas que el usuario puede editar."""

    def __init__(self, definitions: OrderedDict[str, str]) -> None:
        self.definitions = definitions.copy()
        self.totals = {name: 0 for name in self.definitions}
        self.last = {name: 0 for name in self.definitions}

    def update(self, detections: tuple[ObjectDetection, ...]) -> CountSnapshot:
        detected = [normalize(item.label) for item in detections]
        current: dict[str, int] = {}
        for name, target in self.definitions.items():
            normalized_target = normalize(target)
            if normalized_target == SPECIAL_ANALYSES:
                value = 1
            elif normalized_target == SPECIAL_EMPTY:
                value = int(not detections)
            else:
                value = sum(
                    1
                    for label in detected
                    if label == normalized_target
                    or normalized_target in label
                    or label in normalized_target
                )
            current[name] = value
            self.totals[name] += value
        self.last = current
        return CountSnapshot(current=current.copy(), totals=self.totals.copy())

    def reset(self) -> None:
        for name in self.totals:
            self.totals[name] = 0
            self.last[name] = 0

