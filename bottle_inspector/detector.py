"""Deteccion generica de objetos con Grounding DINO ejecutado localmente."""

from __future__ import annotations

from dataclasses import dataclass
import inspect
import time
from typing import Any

import cv2
import numpy as np

import config


@dataclass(frozen=True)
class ObjectDetection:
    """Objeto localizado dentro del rectangulo amarillo."""

    label: str
    confidence: float
    bounding_box: tuple[int, int, int, int]


@dataclass(frozen=True)
class InspectionResult:
    """Resultado de una ejecucion del modelo."""

    detections: tuple[ObjectDetection, ...]
    latency: float
    analyzed_at: float


def inspection_region(frame_shape: tuple[int, ...]) -> tuple[int, int, int, int]:
    """Calcula el rectangulo amarillo en pixeles."""
    frame_h, frame_w = frame_shape[:2]
    x1 = max(0, min(int(config.INSPECTION_REGION[0] * frame_w), frame_w - 1))
    y1 = max(0, min(int(config.INSPECTION_REGION[1] * frame_h), frame_h - 1))
    x2 = max(x1 + 1, min(int(config.INSPECTION_REGION[2] * frame_w), frame_w))
    y2 = max(y1 + 1, min(int(config.INSPECTION_REGION[3] * frame_h), frame_h))
    return x1, y1, x2 - x1, y2 - y1


class GroundingDinoDetector:
    """Carga el modelo una vez y analiza imagenes sin una API remota."""

    def __init__(self) -> None:
        self._processor: Any = None
        self._model: Any = None
        self._torch: Any = None
        self.device = "cpu"

    @property
    def loaded(self) -> bool:
        return self._model is not None

    def _load_model(self) -> None:
        if self.loaded:
            return
        try:
            import torch
            from transformers import AutoModelForZeroShotObjectDetection, AutoProcessor
        except ImportError as exc:
            raise RuntimeError(
                "Faltan dependencias. Active el entorno e instale requirements.txt."
            ) from exc

        self._torch = torch
        if config.LOCAL_DEVICE == "cuda":
            if not torch.cuda.is_available():
                raise RuntimeError("Se solicito CUDA, pero no esta disponible.")
            self.device = "cuda"
        elif config.LOCAL_DEVICE == "cpu":
            self.device = "cpu"
        else:
            self.device = "cuda" if torch.cuda.is_available() else "cpu"

        if self.device == "cpu":
            torch.set_num_threads(max(1, int(config.LOCAL_CPU_THREADS)))

        self._processor = AutoProcessor.from_pretrained(config.LOCAL_MODEL_ID)
        self._model = AutoModelForZeroShotObjectDetection.from_pretrained(
            config.LOCAL_MODEL_ID
        ).to(self.device)
        self._model.eval()

    @staticmethod
    def _clean_box(
        box: list[float], image_shape: tuple[int, ...]
    ) -> tuple[int, int, int, int] | None:
        height, width = image_shape[:2]
        x1, y1, x2, y2 = (float(value) for value in box)
        left = max(0, min(int(round(x1)), width - 1))
        top = max(0, min(int(round(y1)), height - 1))
        right = max(left + 1, min(int(round(x2)), width))
        bottom = max(top + 1, min(int(round(y2)), height))
        if right <= left or bottom <= top:
            return None
        return left, top, right - left, bottom - top

    def analyze(self, image_bgr: np.ndarray, labels: list[str]) -> InspectionResult:
        """Analiza solamente la imagen recibida; el llamador entrega el recorte."""
        if image_bgr is None or image_bgr.size == 0:
            raise ValueError("El area de inspeccion esta vacia.")
        if not labels:
            raise ValueError("Debe indicar al menos una categoria para analizar.")

        self._load_model()
        assert self._processor is not None and self._model is not None
        assert self._torch is not None

        from PIL import Image

        started = time.perf_counter()
        image = Image.fromarray(cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB))
        inputs = self._processor(
            images=image, text=[labels], return_tensors="pt"
        ).to(self.device)
        with self._torch.inference_mode():
            outputs = self._model(**inputs)
        # Transformers cambio los nombres de estos argumentos entre versiones.
        # La inspeccion de la firma mantiene compatibilidad con las ramas 4.x y 5.x.
        post_process = self._processor.post_process_grounded_object_detection
        parameters = inspect.signature(post_process).parameters
        post_kwargs = {
            "text_threshold": config.LOCAL_TEXT_THRESHOLD,
            "target_sizes": [image.size[::-1]],
        }
        if "threshold" in parameters:
            post_kwargs["threshold"] = config.LOCAL_BOX_THRESHOLD
        else:
            post_kwargs["box_threshold"] = config.LOCAL_BOX_THRESHOLD
        if "input_ids" in parameters:
            processed = post_process(outputs, inputs.input_ids, **post_kwargs)[0]
        else:
            processed = post_process(outputs, **post_kwargs)[0]

        boxes = processed["boxes"].detach().cpu().tolist()
        scores = processed["scores"].detach().cpu().tolist()
        raw_labels = processed.get("text_labels", processed.get("labels", []))
        detections: list[ObjectDetection] = []
        for box, score, raw_label in zip(boxes, scores, raw_labels):
            if hasattr(raw_label, "item"):
                raw_label = raw_label.item()
            if isinstance(raw_label, int) and 0 <= raw_label < len(labels):
                label = labels[raw_label]
            else:
                label = str(raw_label).strip()
            clean_box = self._clean_box(box, image_bgr.shape)
            if clean_box is not None:
                detections.append(
                    ObjectDetection(
                        label=label,
                        confidence=float(score),
                        bounding_box=clean_box,
                    )
                )

        detections.sort(key=lambda item: item.confidence, reverse=True)
        return InspectionResult(
            detections=tuple(detections),
            latency=time.perf_counter() - started,
            analyzed_at=time.time(),
        )

