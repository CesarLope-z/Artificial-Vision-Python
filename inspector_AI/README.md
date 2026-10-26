# Inspector AI con Gemini

Aplicacion general de inspeccion visual con dos paneles. A la izquierda muestra la camara y el rectangulo amarillo; a la derecha permite editar el prompt, configurar contadores, ejecutar el analisis y generar un reporte CSV.

Solo el contenido del rectangulo amarillo se envia a la API de Gemini. El programa no guarda imagenes ni videos, pero la imagen analizada si se transmite a Google para obtener la respuesta.

## Preparar el entorno

Abra PowerShell dentro de `inspector_AI`:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## Configurar la API

Cree o edite el archivo `.env` sin compartirlo ni subirlo a un repositorio:

```text
GEMINI_API_KEY=su_clave_de_Gemini
```

Opcionalmente puede seleccionar otro modelo:

```text
GEMINI_MODEL=gemini-3.5-flash-lite
```

## Ejecutar

```powershell
python main.py
```

1. Modifique el prompt para describir los objetos y fallos que desea inspeccionar.
2. Configure los conteos con `nombre = concepto`. Por ejemplo: `cajas_rotas = caja rota`.
3. Pulse **ACEPTAR CONFIGURACION**.
4. Coloque el objeto dentro del rectangulo amarillo y pulse **ANALIZAR**. La barra espaciadora hace lo mismo.
5. Use **REINICIAR** para poner los conteos en cero, **REPORTE CSV** para guardar el resumen y **SALIR** o `Q` para cerrar.

Los contadores generales disponibles son:

- `@analisis`: solicitudes terminadas correctamente.
- `@objetos`: suma de elementos detectados.
- `@alertas`: cantidad de alertas devueltas.
- `@aprobados`: resultados con estado aprobado.
- `@inciertos`: resultados que Gemini no pudo decidir con seguridad.

## Cambiar de camara

Edite `CAMERA_INDEX` en `config.py`. Normalmente `0` corresponde a la camara integrada; pruebe `1` o `2` para otra camara.

## Recomendaciones y limitaciones

Use una camara fija, fondo uniforme e iluminacion constante. Escriba criterios concretos y visualmente comprobables. Para mejorar los conteos, use en el prompt exactamente los mismos nombres escritos a la derecha del signo `=`.

Cada pulsacion de **ANALIZAR** realiza una solicitud a Gemini y puede consumir cuota o generar costo segun la cuenta. Un mismo objeto puede contarse varias veces si se analiza repetidamente. La respuesta de un modelo generativo puede variar o equivocarse; no debe considerarse una certificacion industrial sin pruebas con imagenes reales, reglas adicionales y validacion humana.

