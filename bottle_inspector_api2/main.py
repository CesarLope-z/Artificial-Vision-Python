"""Interfaz de escritorio para la inspeccion visual de botellas."""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from queue import Empty, Queue
from threading import Thread
import tkinter as tk
from tkinter import messagebox

import cv2
from PIL import Image, ImageTk

from api_client import VisionInspector
import config


BG_WINDOW = "#15191f"
BG_CAMERA = "#090b0e"
BG_PANEL = "#343a43"
BG_CARD = "#414852"
TEXT_PRIMARY = "#f4f7fa"
TEXT_SECONDARY = "#b9c1ca"
GREEN = "#3ac47d"
RED = "#ef5350"
YELLOW = "#ffca28"
BLUE = "#4299e1"


class BottleInspectorApp:
    """Mantiene la camara fluida mientras la IA analiza en segundo plano."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(config.WINDOW_TITLE)
        self.root.configure(bg=BG_WINDOW)
        self.root.minsize(1080, 650)
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.bind("<space>", lambda _event: self.start_inspection())
        self.root.bind("<Key-q>", lambda _event: self.close())
        self.root.bind("<Key-Q>", lambda _event: self.close())

        self.inspector = VisionInspector()
        self.capture = cv2.VideoCapture(config.CAMERA_INDEX)
        if not self.capture.isOpened():
            raise RuntimeError("No se pudo abrir la camara configurada.")
        self.capture.set(cv2.CAP_PROP_FRAME_WIDTH, config.RESOLUTION[0])
        self.capture.set(cv2.CAP_PROP_FRAME_HEIGHT, config.RESOLUTION[1])

        self.running = True
        self.inspecting = False
        self.current_frame = None
        self.last_results: dict | None = None
        self.result_queue: Queue[dict] = Queue()
        self.session_started = datetime.now()
        self.history: list[dict[str, object]] = []
        self.counters = {
            "total": 0,
            "aprobadas": 0,
            "sin_tapa": 0,
            "mala_etiqueta": 0,
            "deformacion": 0,
            "mal_llenado": 0,
        }
        self.counter_vars = {
            key: tk.StringVar(value="0") for key in self.counters
        }
        self.state_var = tk.StringVar(value="LISTO PARA INSPECCIONAR")
        self.status_var = tk.StringVar(value="Coloque la botella dentro de la guia amarilla.")

        self._build_interface()
        self._update_camera()

    def _build_interface(self) -> None:
        """Construye los dos cuadros principales de la ventana."""
        container = tk.Frame(self.root, bg=BG_WINDOW)
        container.pack(fill="both", expand=True, padx=18, pady=18)
        container.grid_columnconfigure(0, weight=3)
        container.grid_columnconfigure(1, weight=2)
        container.grid_rowconfigure(0, weight=1)

        left = tk.Frame(
            container,
            bg=BG_CAMERA,
            highlightbackground="#59616b",
            highlightthickness=1,
        )
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        tk.Label(
            left,
            text="CAMARA DE INSPECCION",
            bg=BG_CAMERA,
            fg=TEXT_PRIMARY,
            font=("Segoe UI Semibold", 15),
            anchor="w",
        ).pack(fill="x", padx=18, pady=(14, 8))
        self.video_label = tk.Label(left, bg=BG_CAMERA, bd=0)
        self.video_label.pack(expand=True, padx=16, pady=(0, 10))
        tk.Label(
            left,
            text="La IA analiza solamente el interior de la guia amarilla  |  ESPACIO: analizar  |  Q: salir",
            bg=BG_CAMERA,
            fg=TEXT_SECONDARY,
            font=("Segoe UI", 9),
        ).pack(fill="x", padx=18, pady=(0, 14))

        right = tk.Frame(
            container,
            bg=BG_PANEL,
            highlightbackground="#59616b",
            highlightthickness=1,
            width=380,
        )
        right.grid(row=0, column=1, sticky="nsew")
        right.grid_propagate(False)

        tk.Label(
            right,
            text="RESUMEN DE INSPECCION",
            bg=BG_PANEL,
            fg=TEXT_PRIMARY,
            font=("Segoe UI Semibold", 16),
            anchor="w",
        ).pack(fill="x", padx=20, pady=(16, 5))
        self.state_label = tk.Label(
            right,
            textvariable=self.state_var,
            bg=BG_PANEL,
            fg=YELLOW,
            font=("Segoe UI Bold", 13),
            anchor="w",
        )
        self.state_label.pack(fill="x", padx=20, pady=(0, 12))

        counters_grid = tk.Frame(right, bg=BG_PANEL)
        counters_grid.pack(fill="x", padx=16)
        cards = (
            ("total", "TOTAL", TEXT_PRIMARY),
            ("aprobadas", "APROBADAS", GREEN),
            ("sin_tapa", "SIN TAPA", RED),
            ("mala_etiqueta", "ETIQUETA MALA", RED),
            ("deformacion", "DEFORMADAS", RED),
            ("mal_llenado", "MAL LLENADO", RED),
        )
        for index, (key, title, color) in enumerate(cards):
            self._create_counter_card(
                counters_grid,
                row=index // 2,
                column=index % 2,
                title=title,
                variable=self.counter_vars[key],
                color=color,
            )

        tk.Label(
            right,
            text="ULTIMO RESULTADO",
            bg=BG_PANEL,
            fg=TEXT_SECONDARY,
            font=("Segoe UI Semibold", 10),
            anchor="w",
        ).pack(fill="x", padx=20, pady=(16, 6))
        self.alerts_text = tk.Text(
            right,
            height=6,
            bg="#292e35",
            fg=TEXT_PRIMARY,
            insertbackground=TEXT_PRIMARY,
            relief="flat",
            font=("Segoe UI", 10),
            padx=10,
            pady=8,
            wrap="word",
            state="disabled",
        )
        self.alerts_text.pack(fill="x", padx=16)
        self._set_alert_text("Todavia no hay una inspeccion.")

        actions = tk.Frame(right, bg=BG_PANEL)
        actions.pack(fill="x", side="bottom", padx=16, pady=16)
        self.analyze_button = self._button(
            actions, "ANALIZAR BOTELLA", self.start_inspection, BLUE
        )
        self.analyze_button.pack(fill="x", pady=(0, 8))

        report_row = tk.Frame(actions, bg=BG_PANEL)
        report_row.pack(fill="x")
        self._button(report_row, "REPORTE CSV", self.generate_csv, "#59636f").pack(
            side="left", fill="x", expand=True, padx=(0, 4)
        )
        self._button(report_row, "RESUMEN TXT", self.generate_txt, "#59636f").pack(
            side="left", fill="x", expand=True, padx=(4, 0)
        )
        self._button(actions, "SALIR", self.close, "#7b3434").pack(
            fill="x", pady=(8, 0)
        )
        tk.Label(
            actions,
            textvariable=self.status_var,
            bg=BG_PANEL,
            fg=TEXT_SECONDARY,
            font=("Segoe UI", 9),
            wraplength=340,
            justify="left",
            anchor="w",
        ).pack(fill="x", pady=(10, 0))

    @staticmethod
    def _button(parent, text: str, command, background: str) -> tk.Button:
        return tk.Button(
            parent,
            text=text,
            command=command,
            bg=background,
            fg="white",
            activebackground=background,
            activeforeground="white",
            relief="flat",
            cursor="hand2",
            font=("Segoe UI Semibold", 10),
            padx=10,
            pady=9,
        )

    @staticmethod
    def _create_counter_card(parent, row, column, title, variable, color) -> None:
        parent.grid_columnconfigure(column, weight=1)
        card = tk.Frame(parent, bg=BG_CARD, padx=12, pady=8)
        card.grid(row=row, column=column, sticky="nsew", padx=4, pady=4)
        tk.Label(
            card,
            text=title,
            bg=BG_CARD,
            fg=TEXT_SECONDARY,
            font=("Segoe UI Semibold", 9),
        ).pack(anchor="w")
        tk.Label(
            card,
            textvariable=variable,
            bg=BG_CARD,
            fg=color,
            font=("Segoe UI Bold", 22),
        ).pack(anchor="w")

    @staticmethod
    def _inspection_box(frame) -> tuple[int, int, int, int]:
        height, width = frame.shape[:2]
        x1 = int(config.INSPECTION_REGION[0] * width)
        y1 = int(config.INSPECTION_REGION[1] * height)
        x2 = int(config.INSPECTION_REGION[2] * width)
        y2 = int(config.INSPECTION_REGION[3] * height)
        return x1, y1, x2, y2

    def _draw_camera_overlay(self, frame):
        display = frame.copy()
        x1, y1, x2, y2 = self._inspection_box(display)
        cv2.rectangle(display, (x1, y1), (x2, y2), (0, 215, 255), 3)
        cv2.putText(
            display,
            "COLOQUE LA BOTELLA AQUI",
            (x1 + 8, y1 + 25),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (0, 0, 0),
            4,
            cv2.LINE_AA,
        )
        cv2.putText(
            display,
            "COLOQUE LA BOTELLA AQUI",
            (x1 + 8, y1 + 25),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (0, 215, 255),
            2,
            cv2.LINE_AA,
        )
        if self.inspecting:
            cv2.rectangle(display, (0, 0), (display.shape[1], 42), (0, 0, 0), -1)
            cv2.putText(
                display,
                "ANALIZANDO CON IA...",
                (18, 29),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.70,
                (0, 215, 255),
                2,
                cv2.LINE_AA,
            )
        return display

    def _update_camera(self) -> None:
        if not self.running:
            return
        ok, frame = self.capture.read()
        if ok and frame is not None:
            frame = cv2.flip(frame, 1)
            self.current_frame = frame.copy()
            display = self._draw_camera_overlay(frame)
            rgb = cv2.cvtColor(display, cv2.COLOR_BGR2RGB)
            photo = ImageTk.PhotoImage(Image.fromarray(rgb))
            self.video_label.configure(image=photo)
            self.video_label.image = photo
        self._poll_result()
        self.root.after(config.UI_REFRESH_MS, self._update_camera)

    def start_inspection(self) -> None:
        if self.inspecting:
            self.status_var.set("Ya existe un analisis en curso.")
            return
        if self.current_frame is None:
            self.status_var.set("La camara todavia no tiene un fotograma disponible.")
            return
        frame = self.current_frame.copy()
        x1, y1, x2, y2 = self._inspection_box(frame)
        inspection_crop = frame[y1:y2, x1:x2].copy()
        self.inspecting = True
        self.analyze_button.configure(state="disabled", bg="#586573")
        self.state_var.set("ANALIZANDO...")
        self.state_label.configure(fg=YELLOW)
        self.status_var.set("La IA esta revisando la botella.")

        def analyze() -> None:
            result = self.inspector.analyze_frame(inspection_crop)
            self.result_queue.put(result)

        Thread(target=analyze, name="vision-inspection", daemon=True).start()

    def _poll_result(self) -> None:
        try:
            result = self.result_queue.get_nowait()
        except Empty:
            return
        self.inspecting = False
        self.analyze_button.configure(state="normal", bg=BLUE)
        self.last_results = result
        self._process_result(result)

    def _process_result(self, result: dict) -> None:
        detected = bool(result.get("botella_detectada"))
        alerts = [str(item) for item in result.get("alertas", [])]
        if not detected:
            self.state_var.set("NO SE DETECTA BOTELLA")
            self.state_label.configure(fg=YELLOW)
            self._set_alert_text("No se encontro una botella dentro de la guia amarilla.")
            self.status_var.set("Ajuste la posicion y vuelva a analizar.")
            return

        cap_bad = str(result.get("tapa_estado", "")).upper() == "AUSENTE"
        label_bad = str(result.get("etiqueta_estado", "")).upper() in {
            "AUSENTE",
            "INCLINADA",
            "DESPLAZADA",
        }
        deformed = bool(result.get("deformacion_detectada"))
        fill_bad = str(result.get("nivel_llenado", "")).upper() in {
            "INSUFICIENTE",
            "EXCESIVO",
        }
        approved = not (cap_bad or label_bad or deformed or fill_bad or alerts)
        self.counters["total"] += 1
        self.counters["sin_tapa"] += int(cap_bad)
        self.counters["mala_etiqueta"] += int(label_bad)
        self.counters["deformacion"] += int(deformed)
        self.counters["mal_llenado"] += int(fill_bad)
        self.counters["aprobadas"] += int(approved)
        for key, value in self.counters.items():
            self.counter_vars[key].set(str(value))

        state = "APROBADA" if approved else "RECHAZADA"
        self.state_var.set(state)
        self.state_label.configure(fg=GREEN if approved else RED)
        self._set_alert_text(
            "Sin alertas. La botella parece correcta."
            if approved
            else "\n".join(f"• {alert}" for alert in alerts)
            or "Se detecto una posible anomalía."
        )
        self.status_var.set("Inspeccion terminada. Puede colocar la siguiente botella.")
        self.history.append(
            {
                "fecha_hora": datetime.now().isoformat(timespec="seconds"),
                "resultado": state,
                "tapa": result.get("tapa_estado", "SIN DATO"),
                "etiqueta": result.get("etiqueta_estado", "SIN DATO"),
                "deformacion": "SI" if deformed else "NO",
                "nivel_llenado": result.get("nivel_llenado", "SIN DATO"),
                "alertas": " | ".join(alerts) if alerts else "NINGUNA",
            }
        )

    def _set_alert_text(self, text: str) -> None:
        self.alerts_text.configure(state="normal")
        self.alerts_text.delete("1.0", "end")
        self.alerts_text.insert("1.0", text)
        self.alerts_text.configure(state="disabled")

    def _reports_directory(self) -> Path:
        directory = Path(__file__).resolve().parent / "reportes"
        directory.mkdir(exist_ok=True)
        return directory

    def generate_csv(self) -> None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = self._reports_directory() / f"reporte_botellas_{timestamp}.csv"
        with path.open("w", newline="", encoding="utf-8-sig") as file:
            writer = csv.writer(file)
            writer.writerow(["REPORTE DE INSPECCION DE BOTELLAS"])
            writer.writerow(["Inicio de sesion", self.session_started.isoformat(timespec="seconds")])
            writer.writerow(["Generado", datetime.now().isoformat(timespec="seconds")])
            writer.writerow([])
            writer.writerow(["RESUMEN", "CANTIDAD"])
            for key, value in self.counters.items():
                writer.writerow([key.replace("_", " ").upper(), value])
            writer.writerow([])
            writer.writerow(
                [
                    "FECHA_HORA",
                    "RESULTADO",
                    "TAPA",
                    "ETIQUETA",
                    "DEFORMACION",
                    "NIVEL_LLENADO",
                    "ALERTAS",
                ]
            )
            for item in self.history:
                writer.writerow(
                    [
                        item["fecha_hora"],
                        item["resultado"],
                        item["tapa"],
                        item["etiqueta"],
                        item["deformacion"],
                        item["nivel_llenado"],
                        item["alertas"],
                    ]
                )
        self.status_var.set(f"Reporte CSV guardado: {path.name}")
        messagebox.showinfo("Reporte generado", f"Se guardo el reporte en:\n{path}")

    def generate_txt(self) -> None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = self._reports_directory() / f"resumen_botellas_{timestamp}.txt"
        lines = [
            "RESUMEN DE INSPECCION DE BOTELLAS",
            "=" * 38,
            f"Inicio de sesion: {self.session_started.isoformat(timespec='seconds')}",
            f"Generado: {datetime.now().isoformat(timespec='seconds')}",
            "",
            f"Total: {self.counters['total']}",
            f"Aprobadas: {self.counters['aprobadas']}",
            f"Sin tapa: {self.counters['sin_tapa']}",
            f"Etiqueta mala: {self.counters['mala_etiqueta']}",
            f"Posible deformacion: {self.counters['deformacion']}",
            f"Mal llenado: {self.counters['mal_llenado']}",
        ]
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        self.status_var.set(f"Resumen TXT guardado: {path.name}")
        messagebox.showinfo("Resumen generado", f"Se guardo el resumen en:\n{path}")

    def close(self) -> None:
        if not self.running:
            return
        self.running = False
        self.capture.release()
        self.root.destroy()


def main() -> int:
    root = tk.Tk()
    try:
        BottleInspectorApp(root)
    except (ValueError, RuntimeError) as error:
        messagebox.showerror("No se pudo iniciar", str(error), parent=root)
        root.destroy()
        return 1
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
