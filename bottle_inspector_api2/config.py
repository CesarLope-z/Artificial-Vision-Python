# config.py
import os
from dotenv import load_dotenv

# Cargar variables de entorno desde el archivo .env
load_dotenv()

# Configuración del sistema
CAMERA_INDEX = 0
RESOLUTION = (640, 480)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Interfaz y zona de inspeccion (valores relativos al fotograma).
WINDOW_TITLE = "Inspector visual de botellas"
INSPECTION_REGION = (0.25, 0.08, 0.75, 0.92)
UI_REFRESH_MS = 20
# Dentro de config.py, reemplaza INSPECTION_PROMPT por esto:

INSPECTION_PROMPT = """
Eres un inspector de calidad de envasado. Tu tarea es analizar la botella en la imagen y devolver un JSON estricto.

Revisa los siguientes puntos:
1. ¿Hay una botella visible?
2. ¿La tapa está presente y parece correctamente alineada?
3. ¿La botella presenta abolladuras o deformaciones visibles?
4. ¿La etiqueta está presente, derecha y centrada?
5. ¿El nivel de llenado de líquido es correcto, está casi vacío, o está rebalsando?

Debes devolver ÚNICAMENTE un objeto JSON con esta estructura exacta:
{
  "botella_detectada": true o false,
  "tapa_estado": "CORRECTA", "AUSENTE" o "DESALINEADA",
  "etiqueta_estado": "CORRECTA", "AUSENTE", "INCLINADA" o "DESPLAZADA",
  "deformacion_detectada": true o false,
  "nivel_llenado": "CORRECTO", "INSUFICIENTE" o "EXCESIVO",
  "alertas": ["lista", "de", "problemas", "encontrados", "vacío si todo está bien"]
}
"""
