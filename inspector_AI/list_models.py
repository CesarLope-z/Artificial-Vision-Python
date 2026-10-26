"""Muestra modelos disponibles para la clave configurada en .env."""

from google import genai

import config


def main() -> int:
    if not config.GEMINI_API_KEY:
        print("Error: falta GEMINI_API_KEY en el archivo .env")
        return 1
    client = genai.Client(api_key=config.GEMINI_API_KEY)
    print("=== MODELOS DISPONIBLES ===")
    for model in client.models.list():
        name = getattr(model, "name", "")
        if name:
            print(f"- {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

