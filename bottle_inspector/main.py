"""Interfaz de escritorio del inspector visual generico."""

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
from analyzer import ConfigurableCounters, parse_counter_definitions, parse_prompt
from detector import GroundingDinoDetector, InspectionResult, inspection_region


class InspectorApp:
    """Mantiene la camara fluida y ejecuta cada analisis en segundo plano."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(config.WINDOW_TITLE)
        self.root.geometry(config.WINDOW_GEOMETRY)
        self.root.minsize(1120, 700)
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

        self.detector = GroundingDinoDetector()
        self.labels = parse_prompt(config.DEFAULT_PROMPT)
        definitions = parse_counter_definitions(config.DEFAULT_COUNTERS, self.labels)
        self.counters = ConfigurableCounters(definitions)
        self.frame = None
        self.latest_result: InspectionResult | None = None
        self.analysis_busy = False
        self.configuration_version = 0
        self.result_queue: queue.Queue[tuple[int, InspectionResult | Exception]] = queue.Queue()
        self.history: list[dict[str, str]] = []
        self._closed = False
        self._last_frame_time = time.perf_counter()
        self._fps = 0.0

        self.status_text = tk.StringVar(value="Listo. Ajuste las categorias y pulse ANALIZAR.")
        self.result_text = tk.StringVar(value="Sin analisis")
        self._counter_widgets: dict[str, tuple[tk.Label, tk.Label]] = {}
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
            text="Deteccion visual local y configurable",
            bg="#111827",
            fg="#9ca3af",
            font=("Segoe UI", 10),
        ).pack(side="left", padx=16, pady=(6, 0))

        body = tk.Frame(self.root, bg="#111827")
        body.pack(fill="both", expand=True, padx=18, pady=(0, 18))
        body.grid_columnconfigure(0, weight=3)
        body.grid_columnconfigure(1, weight=2, minsize=430)
        body.grid_rowconfigure(0, weight=1)

        camera_card = tk.Frame(body, bg="#030712", highlightthickness=1, highlightbackground="#374151")
        camera_card.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        camera_card.grid_rowconfigure(1, weight=1)
        camera_card.grid_columnconfigure(0, weight=1)
        tk.Label(
            camera_card,
            text="CAMARA EN VIVO  ·  SOLO SE ANALIZA EL CUADRO AMARILLO",
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

        self._section_title(right, "1. CATEGORIAS DEL PROMPT", 0)
        tk.Label(
            right,
            text="Una categoria visual por linea. En ingles suele detectar mejor.",
            bg="#e5e7eb",
            fg="#4b5563",
            font=("Segoe UI", 9),
            anchor="w",
        ).grid(row=1, column=0, sticky="ew", pady=(0, 5))
        self.prompt_editor = tk.Text(
            right,
            height=6,
            wrap="word",
            font=("Consolas", 10),
            relief="flat",
            bg="white",
            fg="#111827",
            padx=8,
            pady=7,
            undo=True,
        )
        self.prompt_editor.grid(row=2, column=0, sticky="ew")
        self.prompt_editor.insert("1.0", config.DEFAULT_PROMPT)

        self._section_title(right, "2. CONTADORES MODIFICABLES", 3)
        tk.Label(
            right,
            text="Formato: nombre = categoria. Especiales: @analisis, @sin_detecciones",
            bg="#e5e7eb",
            fg="#4b5563",
            font=("Segoe UI", 9),
            anchor="w",
        ).grid(row=4, column=0, sticky="ew", pady=(0, 5))
        self.counter_editor = tk.Text(
            right,
            height=7,
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
        middle.grid(row=6, column=0, sticky="nsew", pady=(13, 8))
        middle.grid_columnconfigure(0, weight=1)
        middle.grid_rowconfigure(2, weight=1)

        buttons = tk.Frame(middle, bg="#e5e7eb")
        buttons.grid(row=0, column=0, sticky="ew")
        buttons.grid_columnconfigure((0, 1), weight=1)
        self.apply_button = ttk.Button(
            buttons,
            text="ACEPTAR CONFIGURACION",
            command=self.apply_configuration,
            style="Secondary.TButton",
        )
        self.apply_button.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        self.analyze_button = ttk.Button(
            buttons,
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
            padx=10,
            pady=8,
        )
        self.result_label.grid(row=1, column=0, sticky="ew", pady=(10, 8))

        self.counter_panel = tk.Frame(middle, bg="#f3f4f6", padx=10, pady=8)
        self.counter_panel.grid(row=2, column=0, sticky="nsew")

        bottom_buttons = tk.Frame(right, bg="#e5e7eb")
        bottom_buttons.grid(row=7, column=0, sticky="ew")
        bottom_buttons.grid_columnconfigure((0, 1, 2), weight=1)
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
            wraplength=410,
        ).grid(row=8, column=0, sticky="ew", pady=(10, 0))

    @staticmethod
    def _section_title(parent: tk.Widget, text: str, row: int) -> None:
        tk.Label(
            parent,
            text=text,
            bg="#e5e7eb",
            fg="#111827",
            font=("Segoe UI", 11, "bold"),
            anchor="w",
        ).grid(row=row, column=0, sticky="ew", pady=(2 if row == 0 else 12, 3))

    def apply_configuration(self) -> None:
        """Valida y activa el texto visible sin modificar el codigo."""
        try:
            labels = parse_prompt(self.prompt_editor.get("1.0", "end"))
            definitions = parse_counter_definitions(
                self.counter_editor.get("1.0", "end"), labels
            )
        except ValueError as exc:
            messagebox.showerror("Configuracion no valida", str(exc), parent=self.root)
            return

        new_counters = ConfigurableCounters(definitions)
        for name, target in definitions.items():
            if name in self.counters.definitions and self.counters.definitions[name] == target:
                new_counters.totals[name] = self.counters.totals[name]
                new_counters.last[name] = self.counters.last[name]
        self.labels = labels
        self.counters = new_counters
        self.configuration_version += 1
        self.latest_result = None
        self.result_text.set("Configuracion aplicada; pulse ANALIZAR.")
        self.status_text.set(
            f"Activas: {len(labels)} categorias y {len(definitions)} contadores."
        )
        self._refresh_counter_panel()

    def start_analysis(self) -> None:
        """Copia el rectangulo amarillo y lo envia al modelo en otro hilo."""
        if self.analysis_busy:
            self.status_text.set("El modelo ya esta analizando. Espere el resultado.")
            return
        if self.frame is None:
            self.status_text.set("Aun no hay imagen disponible de la camara.")
            return

        x, y, width, height = inspection_region(self.frame.shape)
        crop = self.frame[y : y + height, x : x + width].copy()
        labels = list(self.labels)
        version = self.configuration_version
        self.analysis_busy = True
        self.analyze_button.state(["disabled"])
        self.status_text.set(
            "Cargando el modelo local..." if not self.detector.loaded else "Analizando el cuadro amarillo..."
        )
        self.result_text.set("ANALIZANDO...")

        def worker() -> None:
            try:
                result: InspectionResult | Exception = self.detector.analyze(crop, labels)
            except Exception as exc:  # El error se muestra en el hilo de la interfaz.
                result = exc
            self.result_queue.put((version, result))

        threading.Thread(target=worker, daemon=True, name="inspector-ai").start()

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
                    self.status_text.set(str(payload))
                    continue
                self._accept_result(payload)
        except queue.Empty:
            pass
        self.root.after(100, self._poll_results)

    def _accept_result(self, result: InspectionResult) -> None:
        self.latest_result = result
        snapshot = self.counters.update(result.detections)
        self._refresh_counter_panel()
        if result.detections:
            summary = ", ".join(
                f"{item.label} ({item.confidence:.0%})" for item in result.detections[:4]
            )
            if len(result.detections) > 4:
                summary += f" y {len(result.detections) - 4} mas"
            self.result_text.set(f"DETECTADO: {summary}")
        else:
            self.result_text.set("SIN DETECCIONES")
        self.status_text.set(
            f"Analisis terminado en {result.latency:.2f} s usando {self.detector.device.upper()}."
        )
        self.history.append(
            {
                "fecha": datetime.fromtimestamp(result.analyzed_at).isoformat(timespec="seconds"),
                "detecciones": "; ".join(
                    f"{item.label}:{item.confidence:.3f}" for item in result.detections
                ),
                "conteo_actual": "; ".join(
                    f"{name}:{value}" for name, value in snapshot.current.items()
                ),
            }
        )

    def _refresh_counter_panel(self) -> None:
        for child in self.counter_panel.winfo_children():
            child.destroy()
        self._counter_widgets.clear()
        tk.Label(
            self.counter_panel,
            text="CONTADOR",
            bg="#f3f4f6",
            fg="#6b7280",
            font=("Segoe UI", 8, "bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="ew")
        tk.Label(
            self.counter_panel,
            text="ULTIMO",
            bg="#f3f4f6",
            fg="#6b7280",
            font=("Segoe UI", 8, "bold"),
        ).grid(row=0, column=1, padx=8)
        tk.Label(
            self.counter_panel,
            text="TOTAL",
            bg="#f3f4f6",
            fg="#6b7280",
            font=("Segoe UI", 8, "bold"),
        ).grid(row=0, column=2, padx=(8, 0))
        self.counter_panel.grid_columnconfigure(0, weight=1)
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
        self.result_text.set("Conteos reiniciados")
        self.status_text.set("Los contadores y el historial del reporte quedaron en cero.")

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
                writer.writerow(["REPORTE INSPECTOR AI"])
                writer.writerow(["Generado", datetime.now().isoformat(timespec="seconds")])
                writer.writerow(["Categorias", " | ".join(self.labels)])
                writer.writerow([])
                writer.writerow(["CONTADORES", "Categoria/regla", "Total"])
                for name, target in self.counters.definitions.items():
                    writer.writerow([name, target, self.counters.totals[name]])
                writer.writerow([])
                writer.writerow(["HISTORIAL"])
                writer.writerow(["Fecha", "Detecciones", "Conteo de este analisis"])
                for item in self.history:
                    writer.writerow(
                        [item["fecha"], item["detecciones"], item["conteo_actual"]]
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
        cv2.rectangle(
            frame, (x, y), (x + width, y + height), config.COLOR_REGION, 3
        )
        self._draw_text(
            frame,
            "AREA ANALIZADA",
            (x + 9, y + 25),
            config.COLOR_REGION,
        )
        self._draw_text(frame, f"FPS {self._fps:.1f}", (14, 28), config.COLOR_TEXT)
        if self.analysis_busy:
            self._draw_text(frame, "ANALIZANDO...", (14, 56), config.COLOR_REGION)
        if self.latest_result is None:
            return
        for item in self.latest_result.detections:
            local_x, local_y, box_w, box_h = item.bounding_box
            left, top = x + local_x, y + local_y
            cv2.rectangle(
                frame,
                (left, top),
                (left + box_w, top + box_h),
                config.COLOR_DETECTION,
                2,
            )
            self._draw_text(
                frame,
                f"{item.label} {item.confidence:.0%}",
                (left, max(y + 22, top - 7)),
                config.COLOR_DETECTION,
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
            rgb = cv2.cvtColor(display, cv2.COLOR_BGR2RGB)
            image = Image.fromarray(rgb)
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
    except RuntimeError as exc:
        messagebox.showerror("Inspector AI", str(exc), parent=root)
        root.destroy()
        return 1
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(run())

