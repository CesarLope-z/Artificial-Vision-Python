"""Cliente de Gemini para inspeccion visual general y respuesta estructurada."""

from __future__ import annotations

from dataclasses import dataclass
import json
import time
from typing import Any

import cv2
import numpy as np
from PIL import Image

import config


@dataclass(frozen=True)
class InspectionItem:
    name: str
    kind: str
    detected: bool
    count: int
    description: str


@dataclass(frozen=True)
class DetectionBox:
    label: str
    box_2d: tuple[int, int, int, int]


@dataclass(frozen=True)
class InspectionResult:
    status: str
    summary: str
    items: tuple[InspectionItem, ...]
    alerts: tuple[str, ...]
    boxes: tuple[DetectionBox, ...]
    latency: float
    analyzed_at: float


RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "status": {
            "type": "string",
            "enum": ["APROBADO", "ALERTA", "INCIERTO"],
            "description": "Resultado general segun el prompt del usuario.",
        },
        "summary": {"type": "string"},
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "kind": {
                        "type": "string",
                        "enum": ["OBJETO", "FALLO", "CONDICION"],
                    },
                    "detected": {"type": "boolean"},
                    "count": {"type": "integer", "minimum": 0},
                    "description": {"type": "string"},
                },
                "required": ["name", "kind", "detected", "count", "description"],
            },
        },
        "alerts": {"type": "array", "items": {"type": "string"}},
        "boxes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "label": {"type": "string"},
                    "box_2d": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "minItems": 4,
                        "maxItems": 4,
                        "description": "[ymin, xmin, ymax, xmax] normalizado de 0 a 1000.",
                    },
                },
                "required": ["label", "box_2d"],
            },
        },
    },
    "required": ["status", "summary", "items", "alerts", "boxes"],
}


class VisionInspector:
    """Envia un recorte en memoria a Gemini; nunca guarda la imagen en disco."""

    def __init__(self) -> None:
        if not config.GEMINI_API_KEY:
            raise ValueError("Falta GEMINI_API_KEY en el archivo .env")
        try:
            from google import genai
        except ImportError as exc:
            raise RuntimeError(
                "Falta el paquete google-genai. Instale requirements.txt."
            ) from exc
        self._genai = genai
        self.client = genai.Client(api_key=config.GEMINI_API_KEY)

    @staticmethod
    def _full_prompt(user_prompt: str, counter_targets: list[str]) -> str:
        targets = [target for target in counter_targets if not target.startswith("@")]
        target_text = ", ".join(f'"{target}"' for target in targets) or "ninguno"
        return f"""{user_prompt.strip()}

INSTRUCCIONES DE RESPUESTA DEL SISTEMA:
- Analiza exclusivamente lo visible en la imagen adjunta.
- Devuelve el estado APROBADO, ALERTA o INCIERTO segun las reglas del usuario.
- En items incluye los objetos, fallos o condiciones relevantes.
- Los siguientes conceptos alimentan contadores. Incluye un item para cada uno y
  copia su nombre exactamente, aunque no aparezca: {target_text}.
- Para un concepto ausente usa detected=false y count=0.
- Una alerta debe describir solamente un incumplimiento visible.
- En boxes incluye cajas de objetos o fallos localizables. box_2d debe ser
  [ymin, xmin, ymax, xmax] con coordenadas enteras normalizadas entre 0 y 1000.
- No escribas Markdown ni informacion fuera del JSON solicitado.
"""

    @staticmethod
    def _parse_response(data: Any, latency: float, analyzed_at: float) -> InspectionResult:
        if not isinstance(data, dict):
            raise ValueError("Gemini devolvio una respuesta JSON inesperada.")
        status = str(data.get("status", "INCIERTO")).strip().upper()
        if status not in {"APROBADO", "ALERTA", "INCIERTO"}:
            status = "INCIERTO"

        items: list[InspectionItem] = []
        for raw in data.get("items", []):
            if not isinstance(raw, dict):
                continue
            detected = bool(raw.get("detected", False))
            try:
                count = max(0, int(raw.get("count", 0)))
            except (TypeError, ValueError):
                count = int(detected)
            items.append(
                InspectionItem(
                    name=str(raw.get("name", "sin nombre")).strip(),
                    kind=str(raw.get("kind", "CONDICION")).strip().upper(),
                    detected=detected,
                    count=count if detected else 0,
                    description=str(raw.get("description", "")).strip(),
                )
            )

        alerts = tuple(
            str(value).strip()
            for value in data.get("alerts", [])
            if str(value).strip()
        )
        boxes: list[DetectionBox] = []
        for raw in data.get("boxes", []):
            if not isinstance(raw, dict):
                continue
            coordinates = raw.get("box_2d")
            if not isinstance(coordinates, list) or len(coordinates) != 4:
                continue
            try:
                ymin, xmin, ymax, xmax = (
                    max(0, min(1000, int(value))) for value in coordinates
                )
            except (TypeError, ValueError):
                continue
            if ymax <= ymin or xmax <= xmin:
                continue
            boxes.append(
                DetectionBox(
                    label=str(raw.get("label", "elemento")).strip(),
                    box_2d=(ymin, xmin, ymax, xmax),
                )
            )

        return InspectionResult(
            status=status,
            summary=str(data.get("summary", "Sin resumen.")).strip(),
            items=tuple(items),
            alerts=alerts,
            boxes=tuple(boxes),
            latency=latency,
            analyzed_at=analyzed_at,
        )

    def analyze_frame(
        self, frame: np.ndarray, user_prompt: str, counter_targets: list[str]
    ) -> InspectionResult:
        if frame is None or frame.size == 0:
            raise ValueError("El area amarilla no contiene una imagen valida.")

        image = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        prompt = self._full_prompt(user_prompt, counter_targets)
        started = time.perf_counter()
        analyzed_at = time.time()
        try:
            from google.genai import types

            response = self.client.models.generate_content(
                model=config.GEMINI_MODEL,
                contents=[image, prompt],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_json_schema=RESPONSE_SCHEMA,
                    temperature=0.1,
                ),
            )
            response_text = response.text
            if not response_text:
                raise ValueError("Gemini no devolvio contenido.")
            data = json.loads(response_text)
        except Exception as exc:
            raise RuntimeError(f"No se pudo completar el analisis con Gemini: {exc}") from exc
        return self._parse_response(data, time.perf_counter() - started, analyzed_at)

