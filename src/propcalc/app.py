from __future__ import annotations

import ctypes
import json
import math
import os
import sqlite3
import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any

from .appdata import export_database, prepare_working_database
from .calculator import CalculationInputs, CalculationResult, PropellerCalculator
from .config import APP_NAME, APP_VERSION, AUTHOR
from .repository import Repository
from .runtime_import import RuntimeImportService
from .units import from_si, to_si, unit_label
from .widgets import ScrollFrame, Tooltip


TEXT = {
    "uk": {
        "calculator": "Калькулятор", "database": "База", "builds": "Збірки", "compare": "Порівняння",
        "frame": "Рама", "testing": "Тестування", "help": "Методика", "about": "Про програму",
        "language": "Мова", "units": "Одиниці", "tooltips": "Підказки", "calculate": "Розрахувати",
        "search": "Пошук", "import": "Імпорт", "export_db": "Експорт propellers.db", "advanced": "Додаткові параметри",
        "basic": "Основні параметри", "results": "Результати", "efficiency": "Ефективність",
        "current": "Поточна точка", "optimum": "Максимальна ефективність", "warnings": "Попередження",
        "simplified": "Оцінка за спрощеною моделлю", "save": "Зберегти збірку", "update": "Оновити збірку",
        "save_as": "Зберегти як нову", "delete": "Видалити", "duplicate": "Дублювати",
        "add_compare": "Додати до порівняння", "refresh": "Оновити", "recommend": "Рекомендації",
    },
    "en": {
        "calculator": "Calculator", "database": "Database", "builds": "Builds", "compare": "Compare",
        "frame": "Frame", "testing": "Testing", "help": "Methodology", "about": "About",
        "language": "Language", "units": "Units", "tooltips": "Tooltips", "calculate": "Calculate",
        "search": "Search", "import": "Import", "export_db": "Export propellers.db", "advanced": "Advanced parameters",
        "basic": "Basic parameters", "results": "Results", "efficiency": "Efficiency",
        "current": "Current point", "optimum": "Maximum efficiency", "warnings": "Warnings",
        "simplified": "Simplified-model estimate", "save": "Save build", "update": "Update build",
        "save_as": "Save as new", "delete": "Delete", "duplicate": "Duplicate",
        "add_compare": "Add to comparison", "refresh": "Refresh", "recommend": "Recommendations",
    },
}


HELP_UK = """PROPeller Calculator Professional UA v3 - методика

Джерела та достовірність
• UIUC: фізичні статичні та аеродинамічні випробування у вітровій трубі. Найвища базова достовірність.
• ENOLA: окремо позначені experiment, CFD (RANS/URANS/MRF/DES) і BEMT. Метод ніколи не змішується з експериментом.
• APC PERFILES: прогноз виробника; це не стендове вимірювання.
• APC Product Data: каталог розмірів, SKU і маси; це не характеристика тяги.
• APC RPM Rev 5: структурне обмеження RPM = коефіцієнт / діаметр у дюймах.

Основні формули (усі внутрішні величини SI)
n = RPM / 60 [об/с]
J = V / (n·D)
T = Ct·ρ·n²·D⁴
P = Cp·ρ·n³·D⁵
Q = P / (2πn)
ηprop = Ct·J/Cp для динаміки; у статиці показується FOM = Ct^(3/2)/(√2·Cp).
Kt = 60/(2π·KV). За наявності Rm та I0 робоча RPM знаходиться балансом моменту мотора й пропелера.

Інтерполяція
Спочатку виконується лінійна інтерполяція по J у двох сусідніх RPM-серіях, потім по RPM. За межами таблиці береться найближчий край і явно знижується достовірність.

Ефективність зв’язки
Аеродинамічна шкала показує ηprop або статичний FOM. Шкала системи множить її на оцінену ефективність мотора та ESC. Без Rm/I0 результат прямо позначається як спрощена оцінка.

Де брати параметри
KV, Rm, I0, максимальний струм і потужність - із паспорта/моторної карти або стенду; C-рейтинг і ємність - із батареї; ESC limit - з паспорта ESC; маса - зважування готового апарата; швидкість - польотний режим; густина - 1.225 кг/м³ для стандартного повітря.

Ручний приклад
Для D=0.254 м, RPM=6000, Ct=0.10, ρ=1.225: n=100 об/с; T=0.10·1.225·100²·0.254⁴≈5.10 Н. Формулу та фактичні проміжні значення поточного розрахунку видно на вкладці «Тестування».

Обмеження
Модель не замінює стенд, перевірку температури, вібрацій, міцності кріплення, кавітації у воді або рекомендації виробника. Екстраполяція, невідома геометрія і спрощена моторна модель знижують достовірність."""

HELP_EN = """Propeller Calculator Professional UA v3 - methodology

Sources and confidence
• UIUC: physical static and wind-tunnel experiments; highest base confidence.
• ENOLA: experiment, CFD (RANS/URANS/MRF/DES), and BEMT remain explicitly separated.
• APC PERFILES: manufacturer prediction, not a bench measurement.
• APC Product Data: dimensions/SKU/mass catalog, not thrust performance.
• APC RPM Rev 5: structural RPM = coefficient / propeller diameter in inches.

Core formulas (internal SI)
n = RPM/60; J = V/(n·D); T = Ct·ρ·n²·D⁴; P = Cp·ρ·n³·D⁵; Q = P/(2πn).
Dynamic ηprop = Ct·J/Cp; static display uses FOM = Ct^(3/2)/(√2·Cp).
Kt = 60/(2π·KV). With Rm and I0, operating RPM is solved from motor/propeller torque balance.

Interpolation and extrapolation
The engine linearly interpolates in J within neighboring RPM curves, then in RPM. Outside a table it clamps to the nearest edge, marks extrapolation, and reduces confidence.

Powertrain efficiency
The aerodynamic gauge is ηprop or static FOM. The system gauge combines it with estimated motor and ESC efficiency. Missing Rm/I0 is always labeled as a simplified-model estimate.

Where inputs come from
Use the motor datasheet/map or bench for KV, Rm, I0, max current/power; the battery label for capacity/C rating; ESC datasheet for its limit; measured ready-to-fly mass; intended airspeed; 1.225 kg/m³ for standard air.

Manual example
For D=0.254 m, RPM=6000, Ct=0.10, ρ=1.225: n=100 rev/s and T=0.10·1.225·100²·0.254⁴≈5.10 N. The Testing tab exposes the live calculation trace.

Limitations
This does not replace bench testing, temperature/vibration/fastener validation, water cavitation analysis, or manufacturer limits. Extrapolation, unknown geometry, and simplified motor parameters reduce confidence."""


TOOLTIPS = {
    "model": ("Модель пропелера з нормалізованої бази. Шукайте маркування на лопаті/упаковці. Більший діаметр зазвичай підвищує тягу і навантаження; більший крок - швидкість і струм. Критичність: висока.",
              "Normalized propeller model. Find the marking on the blade/package. More diameter usually raises thrust and load; more pitch raises speed/current. Criticality: high."),
    "voltage": ("Робоча напруга під навантаженням, V. Беріть із телеметрії або S×3.7 V. Зростання підвищує RPM/струм; зменшення - тягу. Типово 7.4-44.4 V. Критичність: висока.",
                "Loaded operating voltage in V, from telemetry or S×3.7 V. Increasing raises RPM/current; decreasing reduces thrust. Typical 7.4-44.4 V. Criticality: high."),
    "throttle": ("Газ 0-100%. Еквівалентна напруга ≈ U×газ. Зростання різко підвищує потужність (приблизно з RPM³). Критичність: висока.",
                 "Throttle 0-100%. Effective voltage ≈ V×throttle. Power rises steeply (roughly RPM³). Criticality: high."),
    "kv": ("KV мотора, RPM/V без навантаження. З паспорта мотора. Більше KV - більше RPM і струм; менше KV - більше придатне для великих пропелерів. Типово 100-3000 KV. Критичність: висока.",
           "Motor KV in no-load RPM/V, from the datasheet. Higher KV raises RPM/current; lower KV suits larger props. Typical 100-3000 KV. Criticality: high."),
    "speed": ("Швидкість потоку відносно пропелера. Формула J=V/(nD). Зростання змінює робочу точку й може зменшити тягу; 0 = статичний режим. Критичність: висока для польоту.",
              "Flow speed relative to the propeller. J=V/(nD). Increasing shifts the operating point and may reduce thrust; 0 is static. Criticality: high in flight."),
    "mass": ("Повна маса апарата з батареєю і корисним навантаженням. Виміряти вагами. Більша маса зменшує T/W і час. Типово 0.1-25 kg. Критичність: висока.",
             "All-up mass with battery/payload, measured on a scale. More mass lowers T/W and endurance. Typical 0.1-25 kg. Criticality: high."),
    "rm": ("Опір обмотки Rm, Ω, бажано з моторної карти. Менший Rm зменшує I²R-втрати. Без нього використовується спрощена модель. Типово 0.01-0.5 Ω. Критичність: середня/висока.",
           "Winding resistance Rm in Ω, preferably from a motor map. Lower Rm reduces I²R loss. Missing Rm triggers the simplified model. Typical 0.01-0.5 Ω."),
    "i0": ("Струм холостого ходу I0, A. З паспорта/стенду. Більший I0 означає більші втрати. Без нього оцінка спрощена. Типово 0.2-5 A. Критичність: середня.",
           "No-load current I0 in A from datasheet/bench. Higher I0 means more loss. Missing I0 triggers simplified estimation. Typical 0.2-5 A."),
}


class PropellerApp(tk.Tk):
    def __init__(self):
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            pass
        super().__init__()
        self.database_path, self.paths = prepare_working_database()
        self.repository = Repository(self.database_path)
        self.calculator = PropellerCalculator(self.repository)
        self.title(f"{APP_NAME} - {AUTHOR}")
        self.minsize(1040, 680)
        width = min(1500, max(1120, self.winfo_screenwidth() - 80))
        height = min(920, max(700, self.winfo_screenheight() - 90))
        self.geometry(f"{width}x{height}+20+20")
        self.language = tk.StringVar(value=self._setting("language", "uk"))
        self.unit_system = tk.StringVar(value=self._setting("units", "SI"))
        self.tooltips_enabled = tk.BooleanVar(value=self._setting("tooltips", "1") == "1")
        Tooltip.enabled = self.tooltips_enabled.get()
        self.last_unit_system = self.unit_system.get()
        self.current_result: CalculationResult | None = None
        self.current_inputs: CalculationInputs | None = None
        self.current_build_id: int | None = None
        self.compare_items: list[dict[str, Any]] = []
        self.model_lookup: dict[str, str] = {}
        self._init_vars()
        self._style()
        self._build_shell()
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def _setting(self, key: str, default: str) -> str:
        row = self.repository.connection.execute("SELECT value FROM app_settings WHERE key=?", (key,)).fetchone()
        return row[0] if row else default

    def _save_setting(self, key: str, value: str) -> None:
        self.repository.connection.execute(
            "INSERT INTO app_settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value)
        )
        self.repository.connection.commit()

    def t(self, key: str) -> str:
        return TEXT[self.language.get()].get(key, key)

    def _init_vars(self) -> None:
        self.vars = {name: tk.StringVar(value=value) for name, value in {
            "model_search": "", "model": "", "medium": "air", "voltage": "14.8", "battery_s": "4",
            "throttle": "100", "kv": "900", "speed": "0", "mass": "1.5", "motors": "1",
            "capacity": "5.0", "c_rating": "30", "esc": "40", "rm": "", "i0": "",
            "motor_max_current": "", "motor_max_power": "", "density": "1.225",
            "build_name": "My build", "build_description": "", "build_note": "",
            "compare_criterion": "maximum efficiency", "frame_diagonal": "0.45", "frame_geometry": "X",
            "frame_motors": "4", "arm_width": "0.02", "arm_thickness": "0.004", "frame_material": "Carbon fiber",
            "frame_mass": "0.8", "payload": "0.3",
        }.items()}
        self.result_vars = {key: tk.StringVar(value="-") for key in (
            "thrust", "current", "power", "rpm", "tw", "runtime", "esc_margin", "motor_margin",
            "battery_margin", "structural", "confidence", "aero", "system", "optimum",
        )}

    def _style(self) -> None:
        style = ttk.Style(self)
        if "vista" in style.theme_names():
            style.theme_use("vista")
        style.configure("TFrame", background="#F3F6F8")
        style.configure("TLabel", background="#F3F6F8", foreground="#13242E", font=("Segoe UI", 9))
        style.configure("Title.TLabel", font=("Segoe UI Semibold", 16), foreground="#0B3B4B")
        style.configure("Section.TLabel", font=("Segoe UI Semibold", 11), foreground="#0C5B67")
        style.configure("Card.TFrame", background="#FFFFFF", relief="solid", borderwidth=1)
        style.configure("CardTitle.TLabel", background="#FFFFFF", foreground="#53717A", font=("Segoe UI", 8))
        style.configure("CardValue.TLabel", background="#FFFFFF", foreground="#063E4C", font=("Segoe UI Semibold", 13))
        style.configure("Accent.TButton", font=("Segoe UI Semibold", 10))
        style.configure("Treeview", rowheight=25, font=("Segoe UI", 9))
        style.configure("Treeview.Heading", font=("Segoe UI Semibold", 9))
        style.configure("TNotebook.Tab", padding=(12, 7), font=("Segoe UI", 9))

    def _build_shell(self) -> None:
        for child in self.winfo_children():
            child.destroy()
        top = ttk.Frame(self, padding=(12, 8))
        top.pack(fill="x")
        ttk.Label(top, text=APP_NAME, style="Title.TLabel").pack(side="left")
        ttk.Label(top, text=f"  {AUTHOR}", foreground="#607880").pack(side="left")
        controls = ttk.Frame(top)
        controls.pack(side="right")
        ttk.Label(controls, text=self.t("language") + ":").pack(side="left", padx=(0, 4))
        language = ttk.Combobox(controls, width=8, state="readonly", values=("uk", "en"), textvariable=self.language)
        language.pack(side="left", padx=(0, 10)); language.bind("<<ComboboxSelected>>", self._language_changed)
        ttk.Label(controls, text=self.t("units") + ":").pack(side="left", padx=(0, 4))
        units = ttk.Combobox(controls, width=9, state="readonly", values=("SI", "Imperial"), textvariable=self.unit_system)
        units.pack(side="left", padx=(0, 10)); units.bind("<<ComboboxSelected>>", self._units_changed)
        ttk.Checkbutton(controls, text=self.t("tooltips"), variable=self.tooltips_enabled, command=self._toggle_tooltips).pack(side="left")
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        builders = [
            ("calculator", self._build_calculator_tab), ("database", self._build_database_tab),
            ("builds", self._build_builds_tab), ("compare", self._build_compare_tab),
            ("frame", self._build_frame_tab), ("testing", self._build_testing_tab),
            ("help", self._build_help_tab), ("about", self._build_about_tab),
        ]
        for key, builder in builders:
            tab = ttk.Frame(self.notebook)
            self.notebook.add(tab, text=self.t(key))
            builder(tab)

    def _language_changed(self, _event=None) -> None:
        self._save_setting("language", self.language.get())
        self._build_shell()

    def _units_changed(self, _event=None) -> None:
        old, new = self.last_unit_system, self.unit_system.get()
        for name, quantity in (("speed", "speed"), ("mass", "mass_kg"), ("frame_diagonal", "length_m"),
                               ("arm_width", "length_m"), ("arm_thickness", "length_m"),
                               ("frame_mass", "mass_kg"), ("payload", "mass_kg")):
            try:
                si = to_si(float(self.vars[name].get()), quantity, old)
                self.vars[name].set(f"{from_si(si, quantity, new):.6g}")
            except ValueError:
                pass
        self.last_unit_system = new
        self._save_setting("units", new)
        self._build_shell()
        if self.current_result:
            self._display_result(self.current_result, self.current_inputs)

    def _toggle_tooltips(self) -> None:
        Tooltip.enabled = self.tooltips_enabled.get()
        self._save_setting("tooltips", "1" if Tooltip.enabled else "0")

    def _tooltip(self, key: str) -> str:
        pair = TOOLTIPS.get(key, ("Engineering input. See Methodology.", "Engineering input. See Methodology."))
        return pair[0 if self.language.get() == "uk" else 1]

    def on_close(self) -> None:
        self.repository.close()
        self.destroy()

    def _field(self, parent, row: int, label: str, variable: tk.StringVar, unit: str = "", tooltip: str | None = None,
               width: int = 13) -> ttk.Entry:
        lab = ttk.Label(parent, text=label)
        lab.grid(row=row, column=0, sticky="w", padx=(0, 8), pady=3)
        entry = ttk.Entry(parent, textvariable=variable, width=width)
        entry.grid(row=row, column=1, sticky="ew", pady=3)
        ttk.Label(parent, text=unit, foreground="#607880").grid(row=row, column=2, sticky="w", padx=(6, 0), pady=3)
        if tooltip:
            Tooltip(lab, lambda key=tooltip: self._tooltip(key))
            Tooltip(entry, lambda key=tooltip: self._tooltip(key))
        parent.columnconfigure(1, weight=1)
        return entry

    def _build_calculator_tab(self, tab: ttk.Frame) -> None:
        paned = ttk.Panedwindow(tab, orient="horizontal")
        paned.pack(fill="both", expand=True)
        left_scroll = ScrollFrame(paned)
        right_scroll = ScrollFrame(paned)
        paned.add(left_scroll, weight=2); paned.add(right_scroll, weight=3)
        left = left_scroll.content
        ttk.Label(left, text=self.t("basic"), style="Section.TLabel").pack(anchor="w", padx=12, pady=(12, 5))
        model_box = ttk.Frame(left, padding=(12, 0))
        model_box.pack(fill="x")
        search_row = ttk.Frame(model_box); search_row.pack(fill="x", pady=3)
        ttk.Entry(search_row, textvariable=self.vars["model_search"]).pack(side="left", fill="x", expand=True)
        ttk.Button(search_row, text=self.t("search"), command=self._refresh_model_choices).pack(side="left", padx=(5, 0))
        self.model_combo = ttk.Combobox(model_box, textvariable=self.vars["model"], state="readonly", width=54)
        self.model_combo.pack(fill="x", pady=3)
        Tooltip(self.model_combo, lambda: self._tooltip("model"))
        self._refresh_model_choices()
        medium_row = ttk.Frame(model_box); medium_row.pack(fill="x", pady=3)
        ttk.Label(medium_row, text="Environment / Середовище").pack(side="left")
        ttk.Combobox(medium_row, values=("air", "water"), state="readonly", textvariable=self.vars["medium"], width=10).pack(side="right")

        form = ttk.Frame(left, padding=(12, 4)); form.pack(fill="x")
        us = self.unit_system.get()
        self._field(form, 0, "Voltage / Напруга", self.vars["voltage"], "V", "voltage")
        self._field(form, 1, "Battery cells", self.vars["battery_s"], "S")
        self._field(form, 2, "Throttle / Газ", self.vars["throttle"], "%", "throttle")
        self._field(form, 3, "Motor KV", self.vars["kv"], "RPM/V", "kv")
        self._field(form, 4, "Speed / Швидкість", self.vars["speed"], unit_label("speed", us), "speed")
        self._field(form, 5, "All-up mass / Маса", self.vars["mass"], unit_label("mass_kg", us), "mass")
        self._field(form, 6, "Motor count", self.vars["motors"], "")
        self._field(form, 7, "Battery capacity", self.vars["capacity"], "Ah")
        self._field(form, 8, "Battery C-rating", self.vars["c_rating"], "C")
        self._field(form, 9, "ESC limit", self.vars["esc"], "A")
        self.advanced_visible = getattr(self, "advanced_visible", False)
        ttk.Button(left, text=("▾ " if self.advanced_visible else "▸ ") + self.t("advanced"),
                   command=self._toggle_advanced).pack(anchor="w", padx=12, pady=(5, 2))
        self.advanced_frame = ttk.Frame(left, padding=(12, 0))
        if self.advanced_visible:
            self.advanced_frame.pack(fill="x")
        self._field(self.advanced_frame, 0, "Motor Rm", self.vars["rm"], "Ω", "rm")
        self._field(self.advanced_frame, 1, "Motor I0", self.vars["i0"], "A", "i0")
        self._field(self.advanced_frame, 2, "Motor max current", self.vars["motor_max_current"], "A")
        self._field(self.advanced_frame, 3, "Motor max power", self.vars["motor_max_power"], "W")
        self._field(self.advanced_frame, 4, "Fluid density / Густина", self.vars["density"], "kg/m³")
        buttons = ttk.Frame(left, padding=12); buttons.pack(fill="x")
        ttk.Button(buttons, text=self.t("calculate"), style="Accent.TButton", command=self.calculate).pack(side="left", fill="x", expand=True)
        ttk.Button(buttons, text=self.t("add_compare"), command=self.add_current_to_compare).pack(side="left", padx=(6, 0))

        right = right_scroll.content
        ttk.Label(right, text=self.t("results"), style="Section.TLabel").pack(anchor="w", padx=12, pady=(12, 6))
        cards = ttk.Frame(right, padding=(10, 0)); cards.pack(fill="x")
        card_defs = [
            ("thrust", "Thrust / Тяга"), ("current", "Current / Струм"), ("power", "Power / Потужність"),
            ("rpm", "RPM"), ("tw", "T/W"), ("runtime", "Runtime / Час"),
            ("esc_margin", "ESC margin"), ("motor_margin", "Motor margin"),
            ("battery_margin", "Battery margin"), ("structural", "Structural RPM"),
            ("confidence", "Confidence / Достовірність"),
        ]
        for index, (key, title) in enumerate(card_defs):
            frame = ttk.Frame(cards, style="Card.TFrame", padding=8)
            frame.grid(row=index // 3, column=index % 3, sticky="nsew", padx=3, pady=3)
            ttk.Label(frame, text=title, style="CardTitle.TLabel").pack(anchor="w")
            ttk.Label(frame, textvariable=self.result_vars[key], style="CardValue.TLabel").pack(anchor="w")
        for col in range(3): cards.columnconfigure(col, weight=1, uniform="cards")
        eff = ttk.LabelFrame(right, text=self.t("efficiency"), padding=10)
        eff.pack(fill="x", padx=12, pady=8)
        ttk.Label(eff, text="Aerodynamic / Аеродинамічна").grid(row=0, column=0, sticky="w")
        self.aero_bar = ttk.Progressbar(eff, maximum=100); self.aero_bar.grid(row=0, column=1, sticky="ew", padx=8)
        ttk.Label(eff, textvariable=self.result_vars["aero"]).grid(row=0, column=2)
        ttk.Label(eff, text="Powertrain / Силова установка").grid(row=1, column=0, sticky="w", pady=(7, 0))
        self.system_bar = ttk.Progressbar(eff, maximum=100); self.system_bar.grid(row=1, column=1, sticky="ew", padx=8, pady=(7, 0))
        ttk.Label(eff, textvariable=self.result_vars["system"]).grid(row=1, column=2, pady=(7, 0))
        eff.columnconfigure(1, weight=1)
        optimum = ttk.LabelFrame(right, text=self.t("optimum"), padding=10)
        optimum.pack(fill="x", padx=12, pady=4)
        ttk.Label(optimum, textvariable=self.result_vars["optimum"], justify="left", wraplength=760).pack(anchor="w")
        warning = ttk.LabelFrame(right, text=self.t("warnings"), padding=10)
        warning.pack(fill="x", padx=12, pady=(4, 12))
        self.warning_text = tk.Text(warning, height=5, wrap="word", background="#FFF9E8", relief="flat", font=("Segoe UI", 9))
        self.warning_text.pack(fill="x")

    def _toggle_advanced(self) -> None:
        self.advanced_visible = not self.advanced_visible
        self._build_shell()

    def _refresh_model_choices(self) -> None:
        if not hasattr(self, "model_combo"):
            return
        rows = self.repository.search_models(self.vars["model_search"].get(), limit=300)
        values = []
        self.model_lookup.clear()
        for row in rows:
            d = f"{row['diameter_m']/0.0254:.2f}in" if row["diameter_m"] else "?D"
            label = f"{row['model_id']} | {row['manufacturer'] or '?'} | {d} | {row['point_count']} pts"
            values.append(label); self.model_lookup[label] = row["model_id"]
        self.model_combo["values"] = values
        current = self.vars["model"].get()
        if current not in self.model_lookup and values:
            self.vars["model"].set(values[0])

    @staticmethod
    def _optional_float(value: str) -> float | None:
        return float(value) if value.strip() else None

    def _inputs(self) -> CalculationInputs:
        model_id = self.model_lookup.get(self.vars["model"].get(), self.vars["model"].get().split(" | ")[0])
        us = self.unit_system.get()
        speed = to_si(float(self.vars["speed"].get()), "speed", us)
        mass = to_si(float(self.vars["mass"].get()), "mass_kg", us)
        density = float(self.vars["density"].get())
        if self.vars["medium"].get() == "water" and abs(density - 1.225) < 0.01:
            density = 998.2
        return CalculationInputs(
            model_id=model_id, voltage_v=float(self.vars["voltage"].get()),
            throttle=float(self.vars["throttle"].get()) / 100.0, motor_kv=float(self.vars["kv"].get()),
            motor_resistance_ohm=self._optional_float(self.vars["rm"].get()),
            motor_i0_a=self._optional_float(self.vars["i0"].get()),
            motor_max_current_a=self._optional_float(self.vars["motor_max_current"].get()),
            motor_max_power_w=self._optional_float(self.vars["motor_max_power"].get()),
            esc_current_a=float(self.vars["esc"].get()), battery_capacity_ah=float(self.vars["capacity"].get()),
            battery_c_rating=float(self.vars["c_rating"].get()), battery_s=int(float(self.vars["battery_s"].get())),
            speed_m_s=float(speed), mass_kg=float(mass), motor_count=int(float(self.vars["motors"].get())),
            density_kg_m3=density, medium=self.vars["medium"].get(),
        )

    def calculate(self) -> None:
        try:
            inputs = self._inputs()
            result = self.calculator.calculate(inputs)
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"Calculation error / Помилка розрахунку:\n{exc}")
            return
        self.current_inputs, self.current_result = inputs, result
        self._display_result(result, inputs)
        self._refresh_testing_trace()

    def _display_result(self, result: CalculationResult, inputs: CalculationInputs | None) -> None:
        if inputs is None:
            return
        us = self.unit_system.get()
        point = result.point
        total_current = point.current_a * inputs.motor_count
        total_power = point.electrical_power_w * inputs.motor_count
        self.result_vars["thrust"].set(f"{from_si(result.total_thrust_n, 'force', us):.3g} {unit_label('force', us)}")
        self.result_vars["current"].set(f"{total_current:.3g} A")
        self.result_vars["power"].set(f"{from_si(total_power, 'power', us):.3g} {unit_label('power', us)}")
        self.result_vars["rpm"].set(f"{point.rpm:,.0f}")
        self.result_vars["tw"].set(f"{result.thrust_to_weight:.2f}")
        self.result_vars["runtime"].set(f"{result.runtime_min:.1f} min")
        self.result_vars["esc_margin"].set(f"{result.esc_margin_percent:+.0f}%")
        motor_margin = result.motor_current_margin_percent if result.motor_current_margin_percent is not None else result.motor_power_margin_percent
        self.result_vars["motor_margin"].set("n/a" if motor_margin is None else f"{motor_margin:+.0f}%")
        self.result_vars["battery_margin"].set(f"{result.battery_margin_percent:+.0f}%")
        self.result_vars["structural"].set("n/a" if result.structural_rpm is None else f"{point.rpm:,.0f} / {result.structural_rpm:,.0f}")
        self.result_vars["confidence"].set(f"{point.confidence*100:.0f}% · {point.evidence}")
        aero = point.aero_efficiency * 100; system = point.system_efficiency * 100
        self.result_vars["aero"].set(f"{aero:.1f}%"); self.result_vars["system"].set(f"{system:.1f}%")
        if hasattr(self, "aero_bar"):
            self.aero_bar["value"] = aero; self.system_bar["value"] = system
        if result.optimum:
            opt = result.optimum
            diff = (point.system_efficiency - opt.system_efficiency) * 100
            self.result_vars["optimum"].set(
                f"RPM {opt.rpm:,.0f} · throttle {result.recommended_throttle*100:.0f}% · {result.recommended_voltage_v:.1f} V · "
                f"{result.recommended_s}S\nηsystem {opt.system_efficiency*100:.1f}% · thrust {from_si(opt.thrust_n*inputs.motor_count,'force',us):.3g} "
                f"{unit_label('force',us)} · current {opt.current_a*inputs.motor_count:.2f} A · current mode Δ {diff:+.1f} pp"
            )
        else:
            self.result_vars["optimum"].set("No valid sweep point / Немає допустимої точки sweep")
        if hasattr(self, "warning_text"):
            self.warning_text.delete("1.0", "end")
            messages = result.warnings or ["No critical warnings / Критичних попереджень немає"]
            self.warning_text.insert("1.0", "\n".join("• " + item for item in messages))

    def _build_database_tab(self, tab: ttk.Frame) -> None:
        top = ttk.Frame(tab, padding=10); top.pack(fill="x")
        summary = self.repository.summary()
        labels = [("models", "Models / Моделі"), ("characteristics", "Characteristics / Характеристики"),
                  ("sources", "Sources / Джерела"), ("models_with_experiments", "Real tests / Реальні тести"),
                  ("prediction_only_models", "Prediction only / Лише прогноз")]
        for index, (key, label) in enumerate(labels):
            card = ttk.Frame(top, style="Card.TFrame", padding=8); card.grid(row=0, column=index, sticky="nsew", padx=3)
            ttk.Label(card, text=label, style="CardTitle.TLabel").pack(anchor="w")
            ttk.Label(card, text=f"{summary.get(key,0):,}", style="CardValue.TLabel").pack(anchor="w")
            top.columnconfigure(index, weight=1)
        controls = ttk.Frame(tab, padding=(10, 2)); controls.pack(fill="x")
        self.db_search = tk.StringVar(value="")
        ttk.Entry(controls, textvariable=self.db_search).pack(side="left", fill="x", expand=True)
        ttk.Button(controls, text=self.t("search"), command=self._refresh_database_tree).pack(side="left", padx=4)
        ttk.Button(controls, text=self.t("import"), command=self.import_data).pack(side="left", padx=4)
        ttk.Button(controls, text=self.t("export_db"), command=self.export_db).pack(side="left")
        paned = ttk.Panedwindow(tab, orient="vertical"); paned.pack(fill="both", expand=True, padx=10, pady=(2, 10))
        model_frame = ttk.Frame(paned); detail_frame = ttk.Frame(paned)
        paned.add(model_frame, weight=3); paned.add(detail_frame, weight=2)
        cols = ("id", "raw", "maker", "size", "evidence", "points", "geometry")
        self.db_tree = ttk.Treeview(model_frame, columns=cols, show="headings")
        heads = ("Model_ID", "Original", "Manufacturer", "D×P", "Evidence", "Points", "Geometry")
        widths = (240, 140, 110, 90, 110, 75, 75)
        for col, head, width in zip(cols, heads, widths):
            self.db_tree.heading(col, text=head); self.db_tree.column(col, width=width, anchor="w")
        scroll = ttk.Scrollbar(model_frame, orient="vertical", command=self.db_tree.yview)
        self.db_tree.configure(yscrollcommand=scroll.set); self.db_tree.pack(side="left", fill="both", expand=True); scroll.pack(side="right", fill="y")
        self.db_tree.bind("<<TreeviewSelect>>", self._database_selection)
        pcols = ("rpm", "j", "ct", "cp", "eta", "thrust", "power", "class", "source")
        self.point_tree = ttk.Treeview(detail_frame, columns=pcols, show="headings")
        for col in pcols:
            self.point_tree.heading(col, text=col.upper()); self.point_tree.column(col, width=95, anchor="e" if col not in {"class","source"} else "w")
        pscroll = ttk.Scrollbar(detail_frame, orient="vertical", command=self.point_tree.yview)
        self.point_tree.configure(yscrollcommand=pscroll.set); self.point_tree.pack(side="left", fill="both", expand=True); pscroll.pack(side="right", fill="y")
        self._refresh_database_tree()

    def _refresh_database_tree(self) -> None:
        if not hasattr(self, "db_tree"): return
        self.db_tree.delete(*self.db_tree.get_children())
        for row in self.repository.search_models(self.db_search.get(), limit=500):
            d = row["diameter_m"] / 0.0254 if row["diameter_m"] else None
            p = row["pitch_m"] / 0.0254 if row["pitch_m"] else None
            size = f"{d:.2f}×{p:.2f} in" if d and p else "?"
            evidence = "EXP" if row["has_experiment"] else ("PRED" if row["has_prediction"] else ("CFD" if row["has_cfd"] else "CAT"))
            self.db_tree.insert("", "end", iid=row["model_id"], values=(row["model_id"], row["original_name"], row["manufacturer"], size,
                                                                         evidence, row["point_count"], row["geometry_count"]))

    def _database_selection(self, _event=None) -> None:
        selection = self.db_tree.selection()
        if not selection: return
        self.point_tree.delete(*self.point_tree.get_children())
        for row in self.repository.model_points(selection[0], limit=1500):
            values = (f"{row['rpm']:.0f}" if row["rpm"] is not None else "", f"{row['advance_ratio_j']:.4f}" if row["advance_ratio_j"] is not None else "",
                      f"{row['ct']:.5f}" if row["ct"] is not None else "", f"{row['cp']:.5f}" if row["cp"] is not None else "",
                      f"{row['efficiency']:.3f}" if row["efficiency"] is not None else "", f"{row['thrust_n']:.3f}" if row["thrust_n"] is not None else "",
                      f"{row['power_w']:.2f}" if row["power_w"] is not None else "", row["evidence_class"], row["relative_path"])
            self.point_tree.insert("", "end", values=values)

    def import_data(self) -> None:
        path = filedialog.askopenfilename(title=self.t("import"), filetypes=[("Supported", "*.db *.zip *.zipx *.xlsx *.csv *.dat *.pe0"), ("All", "*.*")])
        if not path: return
        try:
            service = RuntimeImportService(self.repository.connection, self.database_path, self.paths["backups"])
            report = service.import_path(path)
            self.repository.clear_caches()
            messagebox.showinfo(APP_NAME, json.dumps(report, ensure_ascii=False, indent=2))
            self._build_shell()
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"Import failed / Імпорт не виконано:\n{exc}")

    def export_db(self) -> None:
        target = filedialog.asksaveasfilename(defaultextension=".db", initialfile="propellers.db", filetypes=[("SQLite", "*.db")])
        if not target: return
        export_database(self.repository.connection, Path(target))
        messagebox.showinfo(APP_NAME, f"Exported / Експортовано:\n{target}")

    def _build_payload(self) -> dict[str, Any]:
        inputs = self._inputs()
        return {
            "name": self.vars["build_name"].get().strip() or "Untitled",
            "description": self.vars["build_description"].get().strip(),
            "note": self.vars["build_note"].get().strip(),
            "propeller_model_id": inputs.model_id, "motor_kv": inputs.motor_kv, "battery_s": inputs.battery_s,
            "battery_capacity_ah": inputs.battery_capacity_ah, "esc_current_a": inputs.esc_current_a,
            "motor_count": inputs.motor_count, "mass_kg": inputs.mass_kg, "payload_kg": 0.0,
            "advanced": {"voltage_v": inputs.voltage_v, "throttle": inputs.throttle, "speed_m_s": inputs.speed_m_s,
                         "motor_resistance_ohm": inputs.motor_resistance_ohm, "motor_i0_a": inputs.motor_i0_a,
                         "motor_max_current_a": inputs.motor_max_current_a, "motor_max_power_w": inputs.motor_max_power_w,
                         "battery_c_rating": inputs.battery_c_rating, "density_kg_m3": inputs.density_kg_m3,
                         "medium": inputs.medium},
        }

    def _build_builds_tab(self, tab: ttk.Frame) -> None:
        paned = ttk.Panedwindow(tab, orient="horizontal"); paned.pack(fill="both", expand=True, padx=10, pady=10)
        form = ttk.Frame(paned, padding=8); listing = ttk.Frame(paned)
        paned.add(form, weight=2); paned.add(listing, weight=3)
        ttk.Label(form, text="Custom build / Кастомна збірка", style="Section.TLabel").grid(row=0, column=0, columnspan=3, sticky="w", pady=(0,8))
        self._field(form, 1, "Name / Назва", self.vars["build_name"])
        ttk.Label(form, text="Description / Опис").grid(row=2, column=0, sticky="nw", pady=3)
        self.build_description_text = tk.Text(form, height=5, width=36, wrap="word", font=("Segoe UI",9)); self.build_description_text.grid(row=2,column=1,columnspan=2,sticky="nsew",pady=3)
        self.build_description_text.insert("1.0", self.vars["build_description"].get())
        ttk.Label(form, text="Note / Примітка").grid(row=3, column=0, sticky="nw", pady=3)
        self.build_note_text = tk.Text(form, height=4, width=36, wrap="word", font=("Segoe UI",9)); self.build_note_text.grid(row=3,column=1,columnspan=2,sticky="nsew",pady=3)
        self.build_note_text.insert("1.0", self.vars["build_note"].get())
        ttk.Label(form, text="Propeller, motor, battery, ESC, mass and all advanced parameters are captured from Calculator.",
                  wraplength=420, foreground="#5A737C").grid(row=4,column=0,columnspan=3,sticky="w",pady=8)
        button_grid = ttk.Frame(form); button_grid.grid(row=5,column=0,columnspan=3,sticky="ew")
        actions = [(self.t("save"), self.save_build_new), (self.t("update"), self.update_build),
                   (self.t("save_as"), self.save_build_new), (self.t("delete"), self.delete_build),
                   (self.t("duplicate"), self.duplicate_build), (self.t("add_compare"), self.add_build_to_compare),
                   ("Export / Експорт", self.export_build), ("Import / Імпорт", self.import_build)]
        for index, (text, command) in enumerate(actions):
            ttk.Button(button_grid,text=text,command=command).grid(row=index//2,column=index%2,sticky="ew",padx=2,pady=2)
        button_grid.columnconfigure(0,weight=1); button_grid.columnconfigure(1,weight=1)
        cols=("id","name","prop","kv","s","capacity","motors","mass","updated")
        self.build_tree=ttk.Treeview(listing,columns=cols,show="headings")
        for col,width in zip(cols,(45,150,210,70,45,70,55,70,130)):
            self.build_tree.heading(col,text=col.upper()); self.build_tree.column(col,width=width)
        scroll=ttk.Scrollbar(listing,orient="vertical",command=self.build_tree.yview); self.build_tree.configure(yscrollcommand=scroll.set)
        self.build_tree.pack(side="left",fill="both",expand=True); scroll.pack(side="right",fill="y")
        self.build_tree.bind("<<TreeviewSelect>>",self._select_build)
        self._refresh_builds()

    def _sync_build_text(self) -> None:
        if hasattr(self,"build_description_text"):
            self.vars["build_description"].set(self.build_description_text.get("1.0","end").strip())
            self.vars["build_note"].set(self.build_note_text.get("1.0","end").strip())

    def _refresh_builds(self) -> None:
        if not hasattr(self,"build_tree"): return
        self.build_tree.delete(*self.build_tree.get_children())
        for row in self.repository.builds():
            self.build_tree.insert("","end",iid=str(row["build_id"]),values=(row["build_id"],row["name"],row["propeller_model_id"],
                row["motor_kv"],row["battery_s"],row["battery_capacity_ah"],row["motor_count"],row["mass_kg"],row["updated_at"]))

    def _select_build(self,_event=None) -> None:
        selection=self.build_tree.selection()
        if not selection:return
        row=self.repository.get_build(int(selection[0]));
        if row is None:return
        self.current_build_id=int(row["build_id"]); self.vars["build_name"].set(row["name"]); self.vars["build_description"].set(row["description"] or ""); self.vars["build_note"].set(row["note"] or "")
        if hasattr(self,"build_description_text"):
            self.build_description_text.delete("1.0","end");self.build_description_text.insert("1.0",row["description"] or "")
            self.build_note_text.delete("1.0","end");self.build_note_text.insert("1.0",row["note"] or "")

    def save_build_new(self) -> None:
        try:
            self._sync_build_text(); self.current_build_id=self.repository.save_build(self._build_payload()); self._refresh_builds()
        except Exception as exc: messagebox.showerror(APP_NAME,str(exc))

    def update_build(self) -> None:
        if self.current_build_id is None: return self.save_build_new()
        self._sync_build_text(); self.repository.save_build(self._build_payload(),self.current_build_id); self._refresh_builds()

    def delete_build(self) -> None:
        if self.current_build_id is None:return
        if messagebox.askyesno(APP_NAME,"Delete selected build? / Видалити вибрану збірку?"):
            self.repository.delete_build(self.current_build_id); self.current_build_id=None; self._refresh_builds()

    def duplicate_build(self) -> None:
        if self.current_build_id is None:return
        self.current_build_id=self.repository.duplicate_build(self.current_build_id); self._refresh_builds()

    def export_build(self) -> None:
        self._sync_build_text(); target=filedialog.asksaveasfilename(defaultextension=".json",filetypes=[("JSON","*.json")])
        if target: Path(target).write_text(json.dumps(self._build_payload(),ensure_ascii=False,indent=2),encoding="utf-8")

    def import_build(self) -> None:
        path=filedialog.askopenfilename(filetypes=[("JSON","*.json")]);
        if not path:return
        try:
            payload=json.loads(Path(path).read_text(encoding="utf-8")); self.current_build_id=self.repository.save_build(payload); self._refresh_builds()
        except Exception as exc: messagebox.showerror(APP_NAME,str(exc))

    def _result_item(self,label:str,result:CalculationResult,inputs:CalculationInputs) -> dict[str,Any]:
        point=result.point
        return {"label":label,"thrust":result.total_thrust_n,"current":point.current_a*inputs.motor_count,
                "power":point.electrical_power_w*inputs.motor_count,"torque":point.torque_nm*inputs.motor_count,
                "efficiency":point.system_efficiency,"aero":point.aero_efficiency,"tw":result.thrust_to_weight,
                "runtime":result.runtime_min,"voltage":inputs.voltage_v,"rpm_margin":result.structural_margin_percent,
                "esc_margin":result.esc_margin_percent,"motor_margin":result.motor_current_margin_percent,
                "battery_margin":result.battery_margin_percent,"confidence":point.confidence,"source":point.source_type,
                "warnings":"; ".join(result.warnings),"mass":inputs.mass_kg,"result":result,"inputs":inputs}

    def add_current_to_compare(self) -> None:
        if self.current_result is None:self.calculate()
        if self.current_result and self.current_inputs:
            self.compare_items.append(self._result_item(self.current_inputs.model_id,self.current_result,self.current_inputs));self._refresh_compare()

    def add_build_to_compare(self) -> None:
        self.add_current_to_compare()

    def _build_compare_tab(self,tab:ttk.Frame) -> None:
        controls=ttk.Frame(tab,padding=10);controls.pack(fill="x")
        ttk.Button(controls,text=self.t("add_compare"),command=self.add_current_to_compare).pack(side="left")
        ttk.Label(controls,text="Rank / Критерій:").pack(side="left",padx=(12,4))
        criteria=("maximum thrust","maximum time","minimum current","maximum efficiency","best compatibility","minimum mass")
        ttk.Combobox(controls,values=criteria,state="readonly",textvariable=self.vars["compare_criterion"],width=22).pack(side="left")
        ttk.Button(controls,text=self.t("refresh"),command=self._refresh_compare).pack(side="left",padx=4)
        ttk.Button(controls,text="Clear / Очистити",command=lambda:(self.compare_items.clear(),self._refresh_compare())).pack(side="left")
        cols=("rank","name","thrust","current","power","torque","eff","aero","tw","time","voltage","rpm_margin","esc","motor","battery","confidence","source","warnings")
        self.compare_tree=ttk.Treeview(tab,columns=cols,show="headings")
        for col in cols:
            self.compare_tree.heading(col,text=col.upper());self.compare_tree.column(col,width=90 if col not in {"name","source","warnings"} else 180)
        self.compare_tree.tag_configure("best",background="#DCF4E5");self.compare_tree.tag_configure("middle",background="#FFF6D6");self.compare_tree.tag_configure("risk",background="#FCE1E1")
        x=ttk.Scrollbar(tab,orient="horizontal",command=self.compare_tree.xview);y=ttk.Scrollbar(tab,orient="vertical",command=self.compare_tree.yview)
        self.compare_tree.configure(xscrollcommand=x.set,yscrollcommand=y.set);self.compare_tree.pack(fill="both",expand=True,padx=10);x.pack(fill="x",padx=10);y.place(relx=1.0,rely=0.08,relheight=0.84,anchor="ne")
        self._refresh_compare()

    def _refresh_compare(self) -> None:
        if not hasattr(self,"compare_tree"):return
        criterion=self.vars["compare_criterion"].get(); reverse=criterion not in {"minimum current","minimum mass"}
        keymap={"maximum thrust":"thrust","maximum time":"runtime","minimum current":"current","maximum efficiency":"efficiency","minimum mass":"mass"}
        if criterion=="best compatibility": key=lambda item:min(item["esc_margin"],item["battery_margin"],item["rpm_margin"] if item["rpm_margin"] is not None else 100)
        else:key=lambda item:item.get(keymap.get(criterion,"efficiency")) or -1e9
        items=sorted(self.compare_items,key=key,reverse=reverse);self.compare_tree.delete(*self.compare_tree.get_children())
        us=self.unit_system.get()
        for idx,item in enumerate(items,1):
            tag="best" if idx==1 else ("risk" if item["warnings"] else "middle")
            values=(idx,item["label"],f"{from_si(item['thrust'],'force',us):.3g}",f"{item['current']:.2f}",f"{from_si(item['power'],'power',us):.3g}",
                    f"{from_si(item['torque'],'torque',us):.3g}",f"{item['efficiency']*100:.1f}%",f"{item['aero']*100:.1f}%",f"{item['tw']:.2f}",
                    f"{item['runtime']:.1f}",f"{item['voltage']:.1f}",self._fmt_margin(item['rpm_margin']),self._fmt_margin(item['esc_margin']),
                    self._fmt_margin(item['motor_margin']),self._fmt_margin(item['battery_margin']),f"{item['confidence']*100:.0f}%",item['source'],item['warnings'])
            self.compare_tree.insert("","end",values=values,tags=(tag,))

    @staticmethod
    def _fmt_margin(value:float|None)->str:return "n/a" if value is None else f"{value:+.0f}%"

    def _build_frame_tab(self,tab:ttk.Frame) -> None:
        paned=ttk.Panedwindow(tab,orient="horizontal");paned.pack(fill="both",expand=True,padx=10,pady=10)
        form=ttk.Frame(paned,padding=8);results=ttk.Frame(paned,padding=8);paned.add(form,weight=2);paned.add(results,weight=3)
        ttk.Label(form,text="Frame model / Модель рами",style="Section.TLabel").grid(row=0,column=0,columnspan=3,sticky="w",pady=(0,8))
        us=self.unit_system.get();self._field(form,1,"Diagonal / Діагональ",self.vars["frame_diagonal"],unit_label("length_m",us))
        ttk.Label(form,text="Geometry").grid(row=2,column=0,sticky="w");ttk.Combobox(form,values=("X","H","+","custom"),state="readonly",textvariable=self.vars["frame_geometry"]).grid(row=2,column=1,sticky="ew")
        self._field(form,3,"Motor count",self.vars["frame_motors"]);self._field(form,4,"Arm width",self.vars["arm_width"],unit_label("length_m",us));self._field(form,5,"Arm thickness",self.vars["arm_thickness"],unit_label("length_m",us))
        ttk.Label(form,text="Material").grid(row=6,column=0,sticky="w");ttk.Combobox(form,values=("Carbon fiber","Aluminum","Wood","Custom"),textvariable=self.vars["frame_material"]).grid(row=6,column=1,sticky="ew")
        self._field(form,7,"Frame mass",self.vars["frame_mass"],unit_label("mass_kg",us));self._field(form,8,"Payload",self.vars["payload"],unit_label("mass_kg",us))
        ttk.Button(form,text=self.t("recommend"),style="Accent.TButton",command=self.calculate_frame).grid(row=9,column=0,columnspan=3,sticky="ew",pady=10)
        ttk.Label(results,text="Checks and 3 recommendations / Перевірки та 3 рекомендації",style="Section.TLabel").pack(anchor="w")
        self.frame_text=tk.Text(results,wrap="word",font=("Consolas",10),background="#FFFFFF",relief="solid",borderwidth=1);self.frame_text.pack(fill="both",expand=True,pady=(8,0))

    def calculate_frame(self) -> None:
        try:
            us=self.unit_system.get();diagonal=to_si(float(self.vars["frame_diagonal"].get()),"length_m",us);width=to_si(float(self.vars["arm_width"].get()),"length_m",us);thickness=to_si(float(self.vars["arm_thickness"].get()),"length_m",us)
            frame_mass=to_si(float(self.vars["frame_mass"].get()),"mass_kg",us);payload=to_si(float(self.vars["payload"].get()),"mass_kg",us);motors=int(self.vars["frame_motors"].get())
        except Exception as exc:return messagebox.showerror(APP_NAME,str(exc))
        spacing=diagonal/math.sqrt(2) if self.vars["frame_geometry"].get() in {"X","+"} else diagonal*0.65;max_d=max(0.02,spacing-0.02)
        material=self.vars["frame_material"].get();props={"Carbon fiber":(70e9,600e6),"Aluminum":(69e9,240e6),"Wood":(11e9,45e6),"Custom":(30e9,120e6)};young,yield_strength=props[material]
        length=diagonal/2;force=(frame_mass+payload)*9.80665/motors*2.0;inertia=width*thickness**3/12;stress=6*force*length/(max(width*thickness**2,1e-12));deflection=force*length**3/(3*young*max(inertia,1e-15));safety=yield_strength/max(stress,1)
        rows=self.repository.connection.execute("""SELECT m.*,MAX(COALESCE(p.efficiency,0)) best_eta,COUNT(p.performance_id) pts
            FROM models m JOIN performance_points p ON p.model_id=m.model_id WHERE m.diameter_m BETWEEN ? AND ? AND m.medium='air'
            GROUP BY m.model_id ORDER BY m.has_experiment DESC,best_eta DESC,pts DESC LIMIT 3""",(max_d*0.62,max_d)).fetchall()
        lines=[f"Disk spacing: {spacing:.3f} m",f"Recommended maximum prop diameter (20 mm clearance): {max_d/0.0254:.2f} in",f"Estimated arm stress: {stress/1e6:.2f} MPa",f"Estimated tip deflection: {deflection*1000:.2f} mm",f"Simplified safety factor: {safety:.2f}","Resonance: simplified warning only; verify motor/prop excitation frequencies on the real frame.",""]
        for idx,row in enumerate(rows,1):
            best=self.repository.connection.execute("SELECT rpm,efficiency FROM performance_points WHERE model_id=? ORDER BY COALESCE(efficiency,0) DESC LIMIT 1",(row["model_id"],)).fetchone();rpm=best["rpm"] if best else 6000
            cells=4 if row["diameter_m"]<0.33 else (6 if row["diameter_m"]<0.55 else 8);kv=rpm/(cells*3.7*0.8)
            lines.append(f"{idx}. {row['model_id']} | D={row['diameter_m']/0.0254:.2f} in | ηmax={float(row['best_eta'] or 0)*100:.1f}% | recommend ≈{kv:.0f} KV, {cells}S ({cells*3.7:.1f} V), verify on bench")
        if safety<2:lines.append("WARNING: safety factor < 2 in the simplified beam model.")
        self.frame_text.delete("1.0","end");self.frame_text.insert("1.0","\n".join(lines))

    def _build_testing_tab(self,tab:ttk.Frame) -> None:
        ttk.Label(tab,text="Open calculation trace / Відкриті розрахунки",style="Section.TLabel").pack(anchor="w",padx=10,pady=10)
        cols=("name","formula","value","unit");self.trace_tree=ttk.Treeview(tab,columns=cols,show="headings")
        for col,width in zip(cols,(180,300,180,130)):self.trace_tree.heading(col,text=col.upper());self.trace_tree.column(col,width=width)
        self.trace_tree.pack(fill="both",expand=True,padx=10,pady=(0,6))
        ttk.Button(tab,text="Recalculate / Перерахувати",command=self.calculate).pack(anchor="e",padx=10,pady=(0,10));self._refresh_testing_trace()

    def _refresh_testing_trace(self) -> None:
        if not hasattr(self,"trace_tree"):return
        self.trace_tree.delete(*self.trace_tree.get_children())
        if not self.current_result:return
        for item in self.current_result.trace:self.trace_tree.insert("","end",values=(item["name"],item["formula"],f"{item['value']:.10g}",item["unit"]))

    def _build_help_tab(self,tab:ttk.Frame) -> None:
        text=tk.Text(tab,wrap="word",font=("Segoe UI",10),padx=18,pady=14,background="#FFFFFF",relief="flat");text.pack(fill="both",expand=True,padx=10,pady=10)
        text.insert("1.0",HELP_UK if self.language.get()=="uk" else HELP_EN);text.configure(state="disabled")

    def _build_about_tab(self,tab:ttk.Frame) -> None:
        frame=ttk.Frame(tab,padding=35);frame.pack(fill="both",expand=True)
        ttk.Label(frame,text=APP_NAME,style="Title.TLabel").pack(anchor="w",pady=(30,8))
        ttk.Label(frame,text=f"Version {APP_VERSION}\nAuthor / Автор: {AUTHOR}\nWindows 10/11 x64 · Offline · Portable one-file EXE\nWorking database: {self.database_path}",
                  justify="left",font=("Segoe UI",11)).pack(anchor="w")
        ttk.Separator(frame).pack(fill="x",pady=20)
        ttk.Label(frame,text="Data provenance remains separated: physical experiment · CFD/numerical · APC prediction · catalog · geometry · structural RPM limits.",wraplength=900).pack(anchor="w")


def main() -> None:
    app = PropellerApp()
    app.mainloop()


if __name__ == "__main__":
    main()
