"""Validacion y conteos configurables para los resultados de Gemini."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
import re

from api_client import InspectionResult


SPECIAL_RULES = {
    "@analisis",
    "@objetos",
    "@alertas",
    "@aprobados",
    "@inciertos",
}


def normalize(value: str) -> str:
    return " ".join(value.casefold().strip().split())


def validate_prompt(text: str) -> str:
    prompt = text.strip()
    if len(prompt) < 15:
        raise ValueError("El prompt debe explicar con mas detalle que se desea inspeccionar.")
    if len(prompt) > 8000:
        raise ValueError("El prompt es demasiado largo; use menos de 8000 caracteres.")
    return prompt


def parse_counter_definitions(text: str) -> OrderedDict[str, str]:
    """Lee reglas con formato 'nombre = concepto visual'."""
    definitions: OrderedDict[str, str] = OrderedDict()
    normalized_names: set[str] = set()
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError(
                f"Linea {line_number}: use el formato nombre = concepto."
            )
        raw_name, raw_target = line.split("=", 1)
        name = raw_name.strip()
        target = raw_target.strip()
        if not name or not target:
            raise ValueError(f"Linea {line_number}: el contador esta incompleto.")
        if not re.fullmatch(r"[\w áéíóúñÁÉÍÓÚÑ-]+", name):
            raise ValueError(f"Linea {line_number}: el nombre contiene simbolos no validos.")
        normalized_name = normalize(name)
        if normalized_name in normalized_names:
            raise ValueError(f"El contador '{name}' esta repetido.")
        if target.startswith("@") and normalize(target) not in SPECIAL_RULES:
            valid = ", ".join(sorted(SPECIAL_RULES))
            raise ValueError(f"Regla especial desconocida '{target}'. Use: {valid}.")
        normalized_names.add(normalized_name)
        definitions[name] = target
    if not definitions:
        raise ValueError("Configure al menos un contador.")
    return definitions


@dataclass(frozen=True)
class CountSnapshot:
    current: dict[str, int]
    totals: dict[str, int]


class ConfigurableCounters:
    """Acumula objetos o fallos elegidos por el usuario."""

    def __init__(self, definitions: OrderedDict[str, str]) -> None:
        self.definitions = definitions.copy()
        self.totals = {name: 0 for name in self.definitions}
        self.last = {name: 0 for name in self.definitions}

    def update(self, result: InspectionResult) -> CountSnapshot:
        current: dict[str, int] = {}
        for name, target in self.definitions.items():
            normalized_target = normalize(target)
            if normalized_target == "@analisis":
                value = 1
            elif normalized_target == "@objetos":
                value = sum(max(0, item.count) for item in result.items if item.detected)
            elif normalized_target == "@alertas":
                value = len(result.alerts)
            elif normalized_target == "@aprobados":
                value = int(result.status == "APROBADO")
            elif normalized_target == "@inciertos":
                value = int(result.status == "INCIERTO")
            else:
                value = sum(
                    max(0, item.count)
                    for item in result.items
                    if item.detected and normalize(item.name) == normalized_target
                )
            current[name] = value
            self.totals[name] += value
        self.last = current
        return CountSnapshot(current=current.copy(), totals=self.totals.copy())

    def reset(self) -> None:
        for name in self.definitions:
            self.last[name] = 0
            self.totals[name] = 0

