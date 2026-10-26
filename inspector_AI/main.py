"""Interfaz de dos paneles para el inspector general mediante Gemini."""

from __future__ import annotations

import csv
from datetime import datetime
import queue
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import cv2
from PIL import Image, ImageTk

import config
from analyzer import ConfigurableCounters, parse_counter_definitions, validate_prompt
from api_client import InspectionResult, VisionInspector


def inspection_region(frame_shape: tuple[int, ...]) -> tuple[int, int, int, int]:
    """Convierte la region relativa configurada a pixeles."""
    frame_h, frame_w = frame_shape[:2]
    x1 = max(0, min(int(config.INSPECTION_REGION[0] * frame_w), frame_w - 1))
    y1 = max(0, min(int(config.INSPECTION_REGION[1] * frame_h), frame_h - 1))
    x2 = max(x1 + 1, min(int(config.INSPECTION_REGION[2] * frame_w), frame_w))
    y2 = max(y1 + 1, min(int(config.INSPECTION_REGION[3] * frame_h), frame_h))
    return x1, y1, x2 - x1, y2 - y1


class InspectorApp:
    """Captura video y ejecuta la llamada a Gemini sin congelar la ventana."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(config.WINDOW_TITLE)
        self.root.geometry(config.WINDOW_GEOMETRY)
        self.root.minsize(1140, 720)
        self.root.configure(bg="#111827")
        self.root.protocol("WM_DELETE_WINDOW", self.close)

        self.capture = cv2.VideoCapture(config.CAMERA_INDEX)
        self.capture.set(cv2.CAP_PROP_FRAME_WIDTH, config.FRAME_WIDTH)
        self.capture.set(cv2.CAP_PROP_FRAME_HEIGHT, config.FRAME_HEIGHT)
        if not self.capture.isOpened():
            self.capture.release()
            raise RuntimeError(
                f"No se pudo abrir la camara {config.CAMERA_INDEX}. "
                "Revise config.py y los permisos de Windows."
            )

        self.inspector: VisionInspector | None = None
        self.prompt = validate_prompt(config.DEFAULT_PROMPT)
        definitions = parse_counter_definitions(config.DEFAULT_COUNTERS)
        self.counters = ConfigurableCounters(definitions)
        self.frame = None
        self.latest_result: InspectionResult | None = None
        self.result_visible_until = 0.0
        self.analysis_busy = False
        self.configuration_version = 0
        self.result_queue: queue.Queue[tuple[int, InspectionResult | Exception]] = queue.Queue()
        self.history: list[dict[str, str]] = []
        self._closed = False
        self._last_frame_time = time.perf_counter()
        self._fps = 0.0

        self.status_text = tk.StringVar(value="Edite el prompt, acepte la configuracion y analice.")
        self.result_text = tk.StringVar(value="SIN ANALISIS")
        self._build_interface()
        self._refresh_counter_panel()
        self.root.bind("<space>", lambda _event: self.start_analysis())
        self.root.bind("<Key-q>", lambda _event: self.close())
        self.root.bind("<Key-Q>", lambda _event: self.close())
        self._update_camera()
        self._poll_results()

    def _build_interface(self) -> None:
        style = ttk.Style()
        style.theme_use("clam")
        style.configure(
            "Primary.TButton",
            font=("Segoe UI", 11, "bold"),
            padding=(14, 10),
            foreground="white",
            background="#2563eb",
        )
        style.map("Primary.TButton", background=[("active", "#1d4ed8")])
        style.configure("Secondary.TButton", font=("Segoe UI", 10), padding=(10, 8))

        header = tk.Frame(self.root, bg="#111827", padx=20, pady=13)
        header.pack(fill="x")
        tk.Label(
            header,
            text="INSPECTOR AI",
            bg="#111827",
            fg="white",
            font=("Segoe UI", 19, "bold"),
        ).pack(side="left")
        tk.Label(
            header,
            text=f"Inspeccion general con Gemini · {config.GEMINI_MODEL}",
            bg="#111827",
            fg="#9ca3af",
            font=("Segoe UI", 10),
        ).pack(side="left", padx=16, pady=(6, 0))

        body = tk.Frame(self.root, bg="#111827")
        body.pack(fill="both", expand=True, padx=18, pady=(0, 18))
        body.grid_columnconfigure(0, weight=3)
        body.grid_columnconfigure(1, weight=2, minsize=445)
        body.grid_rowconfigure(0, weight=1)

        camera_card = tk.Frame(
            body, bg="#030712", highlightthickness=1, highlightbackground="#374151"
        )
        camera_card.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        camera_card.grid_rowconfigure(1, weight=1)
        camera_card.grid_columnconfigure(0, weight=1)
        tk.Label(
            camera_card,
            text="CAMARA EN VIVO  ·  SOLO SE ENVIA EL CUADRO AMARILLO",
            bg="#030712",
            fg="#d1d5db",
            font=("Segoe UI", 10, "bold"),
            anchor="w",
            padx=14,
            pady=10,
        ).grid(row=0, column=0, sticky="ew")
        self.video_label = tk.Label(camera_card, bg="black")
        self.video_label.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))

        right = tk.Frame(body, bg="#e5e7eb", padx=16, pady=14)
        right.grid(row=0, column=1, sticky="nsew")
        right.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(6, weight=1)

        self._section_title(right, "1. PROMPT DE INSPECCION", 0)
        tk.Label(
            right,
            text="Describa libremente que debe revisar Gemini y cuando hay un fallo.",
            bg="#e5e7eb",
            fg="#4b5563",
            font=("Segoe UI", 9),
            anchor="w",
        ).grid(row=1, column=0, sticky="ew", pady=(0, 5))
        self.prompt_editor = tk.Text(
            right,
            height=11,
            wrap="word",
            font=("Segoe UI", 9),
            relief="flat",
            bg="white",
            fg="#111827",
            padx=9,
            pady=7,
            undo=True,
        )
        self.prompt_editor.grid(row=2, column=0, sticky="ew")
        self.prompt_editor.insert("1.0", config.DEFAULT_PROMPT)

        self._section_title(right, "2. CONTADORES MODIFICABLES", 3)
        tk.Label(
            right,
            text="Formato: nombre = concepto. Ejemplo: cajas_rotas = caja rota",
            bg="#e5e7eb",
            fg="#4b5563",
            font=("Segoe UI", 9),
            anchor="w",
        ).grid(row=4, column=0, sticky="ew", pady=(0, 5))
        self.counter_editor = tk.Text(
            right,
            height=6,
            wrap="none",
            font=("Consolas", 9),
            relief="flat",
            bg="white",
            fg="#111827",
            padx=8,
            pady=7,
            undo=True,
        )
        self.counter_editor.grid(row=5, column=0, sticky="ew")
        self.counter_editor.insert("1.0", config.DEFAULT_COUNTERS)

        middle = tk.Frame(right, bg="#e5e7eb")
        middle.grid(row=6, column=0, sticky="nsew", pady=(12, 8))
        middle.grid_columnconfigure(0, weight=1)
        middle.grid_rowconfigure(2, weight=1)

        action_buttons = tk.Frame(middle, bg="#e5e7eb")
        action_buttons.grid(row=0, column=0, sticky="ew")
        action_buttons.grid_columnconfigure(0, weight=1)
        action_buttons.grid_columnconfigure(1, weight=1)
        self.apply_button = ttk.Button(
            action_buttons,
            text="ACEPTAR CONFIGURACION",
            command=self.apply_configuration,
            style="Secondary.TButton",
        )
        self.apply_button.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        self.analyze_button = ttk.Button(
            action_buttons,
            text="ANALIZAR",
            command=self.start_analysis,
            style="Primary.TButton",
        )
        self.analyze_button.grid(row=0, column=1, sticky="ew", padx=(5, 0))

        self.result_label = tk.Label(
            middle,
            textvariable=self.result_text,
            bg="#d1d5db",
            fg="#111827",
            font=("Segoe UI", 10, "bold"),
            anchor="w",
            justify="left",
            wraplength=400,
            padx=10,
            pady=8,
        )
        self.result_label.grid(row=1, column=0, sticky="ew", pady=(9, 7))

        self.counter_panel = tk.Frame(middle, bg="#f3f4f6", padx=10, pady=8)
        self.counter_panel.grid(row=2, column=0, sticky="nsew")

        bottom_buttons = tk.Frame(right, bg="#e5e7eb")
        bottom_buttons.grid(row=7, column=0, sticky="ew")
        for column in range(3):
            bottom_buttons.grid_columnconfigure(column, weight=1)
        ttk.Button(
            bottom_buttons,
            text="REINICIAR",
            command=self.reset_counters,
            style="Secondary.TButton",
        ).grid(row=0, column=0, sticky="ew", padx=(0, 4))
        ttk.Button(
            bottom_buttons,
            text="REPORTE CSV",
            command=self.generate_report,
            style="Secondary.TButton",
        ).grid(row=0, column=1, sticky="ew", padx=4)
        ttk.Button(
            bottom_buttons,
            text="SALIR",
            command=self.close,
            style="Secondary.TButton",
        ).grid(row=0, column=2, sticky="ew", padx=(4, 0))

        tk.Label(
            right,
            textvariable=self.status_text,
            bg="#e5e7eb",
            fg="#374151",
            font=("Segoe UI", 9),
            anchor="w",
            justify="left",
            wraplength=415,
        ).grid(row=8, column=0, sticky="ew", pady=(9, 0))

    @staticmethod
    def _section_title(parent: tk.Widget, text: str, row: int) -> None:
        tk.Label(
            parent,
            text=text,
            bg="#e5e7eb",
            fg="#111827",
            font=("Segoe UI", 11, "bold"),
            anchor="w",
        ).grid(row=row, column=0, sticky="ew", pady=(2 if row == 0 else 11, 3))

    def apply_configuration(self) -> None:
        try:
            prompt = validate_prompt(self.prompt_editor.get("1.0", "end"))
            definitions = parse_counter_definitions(
                self.counter_editor.get("1.0", "end")
            )
        except ValueError as exc:
            messagebox.showerror("Configuracion no valida", str(exc), parent=self.root)
            return

        new_counters = ConfigurableCounters(definitions)
        for name, target in definitions.items():
            if name in self.counters.definitions and self.counters.definitions[name] == target:
                new_counters.totals[name] = self.counters.totals[name]
                new_counters.last[name] = self.counters.last[name]
        self.prompt = prompt
        self.counters = new_counters
        self.configuration_version += 1
        self.latest_result = None
        self.result_text.set("CONFIGURACION APLICADA")
        self.result_label.configure(bg="#d1d5db", fg="#111827")
        self.status_text.set(
            f"Prompt actualizado y {len(definitions)} contadores activos. Pulse ANALIZAR."
        )
        self._refresh_counter_panel()

    def start_analysis(self) -> None:
        if self.analysis_busy:
            self.status_text.set("Ya existe un analisis en curso. Espere la respuesta.")
            return
        if self.frame is None:
            self.status_text.set("Aun no hay imagen disponible de la camara.")
            return

        x, y, width, height = inspection_region(self.frame.shape)
        crop = self.frame[y : y + height, x : x + width].copy()
        prompt = self.prompt
        targets = list(self.counters.definitions.values())
        version = self.configuration_version
        self.analysis_busy = True
        self.analyze_button.state(["disabled"])
        self.result_text.set("ANALIZANDO CON GEMINI...")
        self.result_label.configure(bg="#fde68a", fg="#92400e")
        self.status_text.set("Enviando exclusivamente el contenido del cuadro amarillo.")

        def worker() -> None:
            try:
                if self.inspector is None:
                    self.inspector = VisionInspector()
                payload: InspectionResult | Exception = self.inspector.analyze_frame(
                    crop, prompt, targets
                )
            except Exception as exc:
                payload = exc
            self.result_queue.put((version, payload))

        threading.Thread(target=worker, daemon=True, name="gemini-inspector").start()

    def _poll_results(self) -> None:
        if self._closed:
            return
        try:
            while True:
                version, payload = self.result_queue.get_nowait()
                self.analysis_busy = False
                self.analyze_button.state(["!disabled"])
                if version != self.configuration_version:
                    self.status_text.set("Resultado descartado porque cambio la configuracion.")
                    continue
                if isinstance(payload, Exception):
                    self.latest_result = None
                    self.result_text.set("ERROR DE ANALISIS")
                    self.result_label.configure(bg="#fecaca", fg="#991b1b")
                    self.status_text.set(str(payload))
                    continue
                self._accept_result(payload)
        except queue.Empty:
            pass
        self.root.after(100, self._poll_results)

    def _accept_result(self, result: InspectionResult) -> None:
        self.latest_result = result
        self.result_visible_until = time.monotonic() + 6.0
        snapshot = self.counters.update(result)
        self._refresh_counter_panel()
        colors = {
            "APROBADO": ("#bbf7d0", "#166534"),
            "ALERTA": ("#fecaca", "#991b1b"),
            "INCIERTO": ("#fde68a", "#92400e"),
        }
        background, foreground = colors[result.status]
        self.result_label.configure(bg=background, fg=foreground)
        details = result.summary
        if result.alerts:
            details += "\nAlertas: " + " · ".join(result.alerts[:3])
        self.result_text.set(f"{result.status}: {details}")
        self.status_text.set(
            f"Respuesta recibida en {result.latency:.2f} s · {len(result.boxes)} regiones localizadas."
        )
        self.history.append(
            {
                "fecha": datetime.fromtimestamp(result.analyzed_at).isoformat(timespec="seconds"),
                "estado": result.status,
                "resumen": result.summary,
                "alertas": "; ".join(result.alerts),
                "items": "; ".join(
                    f"{item.name}:{item.count}" for item in result.items if item.detected
                ),
                "conteo_actual": "; ".join(
                    f"{name}:{value}" for name, value in snapshot.current.items()
                ),
            }
        )

    def _refresh_counter_panel(self) -> None:
        for child in self.counter_panel.winfo_children():
            child.destroy()
        self.counter_panel.grid_columnconfigure(0, weight=1)
        headers = (("CONTADOR", 0), ("ULTIMO", 1), ("TOTAL", 2))
        for text, column in headers:
            tk.Label(
                self.counter_panel,
                text=text,
                bg="#f3f4f6",
                fg="#6b7280",
                font=("Segoe UI", 8, "bold"),
                anchor="w" if column == 0 else "center",
            ).grid(row=0, column=column, sticky="ew", padx=(0 if column == 0 else 8, 0))
        for row, name in enumerate(self.counters.definitions, start=1):
            tk.Label(
                self.counter_panel,
                text=name.replace("_", " ").upper(),
                bg="#f3f4f6",
                fg="#1f2937",
                font=("Segoe UI", 9),
                anchor="w",
            ).grid(row=row, column=0, sticky="ew", pady=2)
            tk.Label(
                self.counter_panel,
                text=str(self.counters.last[name]),
                bg="#f3f4f6",
                fg="#2563eb",
                font=("Segoe UI", 10, "bold"),
                width=6,
            ).grid(row=row, column=1, padx=8)
            tk.Label(
                self.counter_panel,
                text=str(self.counters.totals[name]),
                bg="#f3f4f6",
                fg="#111827",
                font=("Segoe UI", 11, "bold"),
                width=6,
            ).grid(row=row, column=2, padx=(8, 0))

    def reset_counters(self) -> None:
        self.counters.reset()
        self.history.clear()
        self._refresh_counter_panel()
        self.result_text.set("CONTEOS REINICIADOS")
        self.result_label.configure(bg="#d1d5db", fg="#111827")
        self.status_text.set("Los conteos y el historial temporal quedaron en cero.")

    def generate_report(self) -> None:
        path = filedialog.asksaveasfilename(
            parent=self.root,
            title="Guardar reporte de inspeccion",
            defaultextension=".csv",
            filetypes=[("Archivo CSV", "*.csv")],
            initialfile=f"reporte_inspector_{datetime.now():%Y%m%d_%H%M%S}.csv",
        )
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as handle:
                writer = csv.writer(handle)
                writer.writerow(["REPORTE INSPECTOR AI CON GEMINI"])
                writer.writerow(["Generado", datetime.now().isoformat(timespec="seconds")])
                writer.writerow(["Modelo", config.GEMINI_MODEL])
                writer.writerow(["Prompt", self.prompt])
                writer.writerow([])
                writer.writerow(["CONTADORES", "Concepto/regla", "Total"])
                for name, target in self.counters.definitions.items():
                    writer.writerow([name, target, self.counters.totals[name]])
                writer.writerow([])
                writer.writerow(["HISTORIAL"])
                writer.writerow(
                    ["Fecha", "Estado", "Resumen", "Alertas", "Items", "Conteo del analisis"]
                )
                for item in self.history:
                    writer.writerow(
                        [
                            item["fecha"],
                            item["estado"],
                            item["resumen"],
                            item["alertas"],
                            item["items"],
                            item["conteo_actual"],
                        ]
                    )
        except OSError as exc:
            messagebox.showerror("No se pudo guardar", str(exc), parent=self.root)
            return
        self.status_text.set(f"Reporte guardado: {path}")

    @staticmethod
    def _draw_text(frame, text: str, position: tuple[int, int], color) -> None:
        cv2.putText(
            frame, text, position, cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 4, cv2.LINE_AA
        )
        cv2.putText(
            frame, text, position, cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2, cv2.LINE_AA
        )

    def _draw_overlay(self, frame) -> None:
        x, y, width, height = inspection_region(frame.shape)
        cv2.rectangle(frame, (x, y), (x + width, y + height), config.COLOR_REGION, 3)
        self._draw_text(frame, "AREA ENVIADA A GEMINI", (x + 9, y + 25), config.COLOR_REGION)
        self._draw_text(frame, f"FPS {self._fps:.1f}", (14, 28), config.COLOR_TEXT)
        if self.analysis_busy:
            self._draw_text(frame, "ANALIZANDO...", (14, 56), config.COLOR_REGION)
        if self.latest_result is None or time.monotonic() > self.result_visible_until:
            return
        result_color = {
            "APROBADO": config.COLOR_OK,
            "ALERTA": config.COLOR_ALERT,
            "INCIERTO": config.COLOR_UNCERTAIN,
        }[self.latest_result.status]
        for detected_box in self.latest_result.boxes:
            ymin, xmin, ymax, xmax = detected_box.box_2d
            left = x + int(xmin / 1000 * width)
            top = y + int(ymin / 1000 * height)
            right = x + int(xmax / 1000 * width)
            bottom = y + int(ymax / 1000 * height)
            cv2.rectangle(frame, (left, top), (right, bottom), result_color, 2)
            self._draw_text(
                frame,
                detected_box.label,
                (left, max(y + 22, top - 7)),
                result_color,
            )

    def _update_camera(self) -> None:
        if self._closed:
            return
        ok, frame = self.capture.read()
        if ok and frame is not None:
            self.frame = frame.copy()
            now = time.perf_counter()
            instant = 1.0 / max(now - self._last_frame_time, 1e-6)
            self._last_frame_time = now
            self._fps = instant if self._fps == 0.0 else self._fps * 0.9 + instant * 0.1
            display = frame.copy()
            self._draw_overlay(display)
            image = Image.fromarray(cv2.cvtColor(display, cv2.COLOR_BGR2RGB))
            available_w = max(640, self.video_label.winfo_width() - 4)
            available_h = max(480, self.video_label.winfo_height() - 4)
            image.thumbnail((available_w, available_h), Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(image=image)
            self.video_label.configure(image=photo)
            self.video_label.image = photo
        else:
            self.status_text.set("No se pudo leer la camara. Compruebe la conexion.")
        self.root.after(15, self._update_camera)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self.capture.isOpened():
            self.capture.release()
        self.root.destroy()


def run() -> int:
    root = tk.Tk()
    try:
        InspectorApp(root)
    except (RuntimeError, ValueError) as exc:
        messagebox.showerror("Inspector AI", str(exc), parent=root)
        root.destroy()
        return 1
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(run())

