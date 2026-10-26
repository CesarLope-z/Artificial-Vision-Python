import google.generativeai as genai
import os
from dotenv import load_dotenv

# Cargar la API key desde tu archivo .env
load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    print("Error: No se encontró GEMINI_API_KEY en el archivo .env")
    exit()

genai.configure(api_key=api_key)

print("=== MODELOS DISPONIBLES PARA GENERAR CONTENIDO ===")
for m in genai.list_models():
    # Filtramos para mostrar solo los que sirven para generar texto/analizar imágenes
    if 'generateContent' in m.supported_generation_methods:
        print(f"- {m.name}")