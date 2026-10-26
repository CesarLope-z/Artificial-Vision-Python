"""Configuracion del inspector visual general conectado a Gemini."""

import os

from dotenv import load_dotenv


load_dotenv()

# Camara e interfaz
CAMERA_INDEX = 0
FRAME_WIDTH = 1280
FRAME_HEIGHT = 720
WINDOW_TITLE = "Inspector AI - Gemini"
WINDOW_GEOMETRY = "1440x840"

# Solamente este rectangulo amarillo se envia a Gemini.
# Formato relativo: (x inicial, y inicial, x final, y final).
INSPECTION_REGION = (0.25, 0.06, 0.75, 0.94)

# La clave se mantiene en .env y nunca se escribe en el codigo ni en reportes.
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite").strip()

# Este texto aparece completo en el editor y puede cambiarse sin modificar codigo.
DEFAULT_PROMPT = """Actua como inspector visual del contenido del cuadro amarillo.

Identifica los objetos principales visibles y cuenta cada tipo.
Busca tambien fallos claramente observables, por ejemplo productos rotos,
empaques abiertos, piezas faltantes o elementos fuera de posicion.

Marca ALERTA solamente cuando exista evidencia visual suficiente.
Si la imagen no permite decidir, utiliza INCIERTO y explica brevemente por que.
No supongas caracteristicas que no pueden verse en la imagen."""

# Formato: nombre mostrado = concepto que Gemini debe contar.
# Los valores que empiezan con @ son contadores generales del sistema.
DEFAULT_COUNTERS = """analisis_realizados = @analisis
objetos_detectados = @objetos
alertas_detectadas = @alertas
aprobados = @aprobados
resultados_inciertos = @inciertos"""

# Colores BGR para el video.
COLOR_REGION = (0, 215, 255)
COLOR_OK = (60, 210, 80)
COLOR_ALERT = (40, 50, 235)
COLOR_UNCERTAIN = (0, 180, 255)
COLOR_TEXT = (255, 255, 255)

