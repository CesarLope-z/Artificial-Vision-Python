# Inspector AI

Aplicacion general de inspeccion visual con camara y Grounding DINO Tiny ejecutado localmente. No usa Gemini, API remota, token, numero telefonico ni servicios en la nube durante el analisis. No guarda imagenes ni videos.

La interfaz tiene dos paneles: la camara a la izquierda y la configuracion a la derecha. Solamente se envia al modelo el contenido del rectangulo amarillo.

## Crear el entorno virtual

Abra PowerShell dentro de `inspector_AI`:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

## Instalar los requisitos

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

La primera ejecucion descarga el modelo publico `IDEA-Research/grounding-dino-tiny` desde Hugging Face. No requiere cuenta ni token. Despues queda en la cache del equipo y puede reutilizarse sin Internet.

## Ejecutar

```powershell
python main.py
```

1. Escriba en **Categorias del prompt** una categoria visual por linea. Por ejemplo: `person`, `cardboard box` o `damaged product`. El modelo suele funcionar mejor con nombres en ingles.
2. Defina los contadores con el formato `nombre = categoria`. La categoria debe aparecer exactamente en el prompt.
3. Pulse **ACEPTAR CONFIGURACION**.
4. Coloque el objeto dentro del rectangulo amarillo y pulse **ANALIZAR**. Tambien puede usar la barra espaciadora.
5. Pulse **REINICIAR** para poner todos los conteos en cero, **REPORTE CSV** para guardar los resultados o **SALIR**. La tecla `Q` tambien cierra la aplicacion.

Los contadores especiales `@analisis` y `@sin_detecciones` cuentan, respectivamente, cada analisis realizado y cada analisis sin objetos detectados.

## Seleccionar otra camara

Cambie `CAMERA_INDEX` en `config.py`. Normalmente `0` es la camara integrada; pruebe `1` o `2` para otra camara.

## Recomendaciones

Use fondo uniforme, iluminacion estable y camara fija. Coloque completamente el objeto dentro del rectangulo amarillo. Evite reflejos, movimiento excesivo y objetos superpuestos. Para una banda transportadora conviene mantener siempre la misma distancia y posicion de la camara.

## Limitaciones

Grounding DINO interpreta el prompt como una lista de categorias visuales, no como una instruccion de razonamiento libre. Puede buscar `damaged product` o `open box`, pero detectar una ausencia o decidir si un producto cumple una regla compleja requiere agregar logica especifica o entrenar un modelo con ejemplos reales.

Los conteos corresponden a las cajas detectadas cada vez que se pulsa **ANALIZAR**; un mismo objeto puede contarse otra vez si se analiza repetidamente. El modelo no ofrece precision industrial garantizada. En equipos sin GPU la primera carga y cada analisis pueden tardar varios segundos, aunque el video permanece fluido porque el procesamiento se realiza en segundo plano.

