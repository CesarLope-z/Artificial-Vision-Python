# api_client.py
import cv2
import json
import google.generativeai as genai
import config

class VisionInspector:
    def __init__(self):
        if not config.GEMINI_API_KEY:
            raise ValueError("Falta GEMINI_API_KEY en el archivo .env")

        genai.configure(api_key=config.GEMINI_API_KEY)
        # Usamos gemini-1.5-flash por su rapidez en inferencia visual
        self.model = genai.GenerativeModel(
            model_name="gemini-3.5-flash-lite",
            generation_config={"response_mime_type": "application/json"}
        )

    def analyze_frame(self, frame):
        """Convierte el frame de OpenCV a imagen, lo envía a la API y retorna un diccionario."""
        try:
            # Codificar el frame a formato JPEG en memoria
            _, buffer = cv2.imencode('.jpg', frame)
            image_bytes = buffer.tobytes()

            # Preparar el objeto de imagen para Gemini
            image_parts = [
                {
                    "mime_type": "image/jpeg",
                    "data": image_bytes
                }
            ]

            # Enviar solicitud a la API
            response = self.model.generate_content([config.INSPECTION_PROMPT, image_parts[0]])

            # Parsear la respuesta JSON
            resultado = json.loads(response.text)
            return resultado

        except Exception as e:
            print(f"Error al comunicar con la API: {e}")
            return {
                "botella_detectada": False,
                "tapa_estado": "ERROR",
                "etiqueta_estado": "ERROR",
                "deformacion_detectada": False,
                "alertas": ["Error de conexión con la API"]
            }
