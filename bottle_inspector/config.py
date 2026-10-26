"""Configuracion del inspector visual generico con IA local."""

# Camara y ventana
CAMERA_INDEX = 0
FRAME_WIDTH = 1280
FRAME_HEIGHT = 720
WINDOW_TITLE = "Inspector AI - Vision artificial local"
WINDOW_GEOMETRY = "1420x820"

# Unicamente el contenido de este rectangulo amarillo se envia al modelo.
# Formato: (x inicial, y inicial, x final, y final), relativo al fotograma.
INSPECTION_REGION = (0.25, 0.06, 0.75, 0.94)

# Modelo local. La primera ejecucion descarga sus archivos publicos; despues se
# reutilizan desde la cache y no se necesita cuenta, token ni servicio en la nube.
LOCAL_MODEL_ID = "IDEA-Research/grounding-dino-tiny"
LOCAL_DEVICE = "auto"  # "auto", "cpu" o "cuda"
LOCAL_BOX_THRESHOLD = 0.25
LOCAL_TEXT_THRESHOLD = 0.22
LOCAL_CPU_THREADS = 4

# El modelo suele reconocer mejor las categorias escritas en ingles. Se permite
# una categoria por linea y el usuario puede cambiarlas desde la interfaz.
DEFAULT_PROMPT = """person
cardboard box
safety helmet
damaged product"""

# Contadores editables: nombre visible = categoria del prompt.
# Hay dos valores especiales: @analisis y @sin_detecciones.
DEFAULT_COUNTERS = """analisis_realizados = @analisis
personas = person
cajas = cardboard box
cascos = safety helmet
posibles_fallos = damaged product
sin_detecciones = @sin_detecciones"""

# Colores BGR usados sobre el video de OpenCV.
COLOR_REGION = (0, 215, 255)
COLOR_DETECTION = (60, 210, 80)
COLOR_TEXT = (255, 255, 255)

