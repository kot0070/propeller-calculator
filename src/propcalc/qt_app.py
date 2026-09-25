from __future__ import annotations

import json
import math
import os
import shutil
import sqlite3
import sys
import time
import uuid
from datetime import datetime
from html import escape as _html_escape
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import QEvent, QPointF, QRectF, QSignalBlocker, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontDatabase, QPainter, QPdfWriter, QPen, QTextDocument
from PySide6.QtWidgets import (
    QApplication, QBoxLayout, QCheckBox, QComboBox, QFileDialog, QFormLayout, QFrame, QGridLayout,
    QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMainWindow, QMessageBox,
    QPlainTextEdit, QProgressBar, QPushButton, QScrollArea, QSplitter, QStatusBar,
    QTabWidget, QTableWidget, QTableWidgetItem, QTextBrowser, QToolButton, QVBoxLayout, QWidget,
)

from .appdata import export_database, prepare_working_database
from .calculator import CalculationInputs, CalculationResult, PropellerCalculator, battery_spec
from .charts import ChartSeries, LoadChart
from .config import APP_NAME, APP_VERSION, AUTHOR
from .localization import BUILD_GUIDE, FIELD_HELP, UI_TEXT
from .repository import Repository
from .runtime_import import RuntimeImportService
from .units import from_si, to_si, unit_label


TEXT = {
    "uk": {
        "calculator": "Калькулятор", "database": "База", "builds": "Збірки",
        "compare": "Порівняння", "frame": "Рама", "testing": "Тестування",
        "help": "Методика", "about": "Про програму", "calculate": "РОЗРАХУВАТИ",
        "search": "Пошук", "import": "Імпортувати", "export": "Експорт propellers.db",
        "basic": "ОСНОВНА КОНФІГУРАЦІЯ", "advanced": "ДОДАТКОВІ ПАРАМЕТРИ",
        "results": "ТЕЛЕМЕТРІЯ РОЗРАХУНКУ", "warnings": "ПОПЕРЕДЖЕННЯ",
        "add_compare": "Додати до порівняння", "save": "Зберегти збірку",
        "update": "Оновити збірку", "save_as": "Зберегти як нову", "delete": "Видалити",
        "duplicate": "Дублювати", "clear": "Очистити", "recommend": "Розрахувати й рекомендувати",
    },
    "en": {
        "calculator": "Calculator", "database": "Database", "builds": "Builds",
        "compare": "Comparison", "frame": "Frame", "testing": "Testing",
        "help": "Methodology", "about": "About", "calculate": "CALCULATE",
        "search": "Search", "import": "Import", "export": "Export propellers.db",
        "basic": "CORE CONFIGURATION", "advanced": "ADVANCED PARAMETERS",
        "results": "CALCULATION TELEMETRY", "warnings": "WARNINGS",
        "add_compare": "Add to comparison", "save": "Save build", "update": "Update build",
        "save_as": "Save as new", "delete": "Delete", "duplicate": "Duplicate",
        "clear": "Clear", "recommend": "Calculate and recommend",
    },
}

DEFAULTS = {
    "voltage": "14.8", "throttle": "100", "kv": "500", "speed": "0", "mass": "1.5",
    "motors": "4", "esc": "40", "capacity": "5.0", "c_rating": "30", "battery_s": "4",
    "battery_type": "LiPo", "configuration_mode": "database", "reference_point_id": "",
    "reference_rpm": "",
    "rm": "", "i0": "", "motor_max_current": "", "motor_max_power": "", "density": "1.225",
    "medium": "air", "build_name": "My build", "build_description": "", "build_note": "",
    "motor_name": "Custom BLDC", "battery_name": "Custom LiPo", "esc_name": "Custom ESC",
    "frame_name": "Custom frame", "build_payload": "0",
    "frame_size_preset": "450", "frame_diagonal": "0.45", "frame_geometry": "X", "frame_motors": "4",
    "arm_width": "0.02", "arm_thickness": "0.004", "frame_material": "Carbon fiber",
    "frame_mass": "0.8", "payload": "0.3", "compare_criterion": "maximum efficiency",
}

FRAME_SIZE_PRESETS_MM = (65, 75, 85, 100, 120, 150, 180, 210, 250, 300, 330, 350,
                         400, 450, 500, 550, 600, 650, 700, 800, 1000)

ACCESSORY_DEFAULTS: tuple[dict[str, Any], ...] = (
    {"category": "flight_controller", "model": "", "quantity": 1, "mass_kg": 0.015, "enabled": True},
    {"category": "power_distribution", "model": "", "quantity": 1, "mass_kg": 0.020, "enabled": True},
    {"category": "receiver", "model": "", "quantity": 1, "mass_kg": 0.005, "enabled": True},
    {"category": "gps", "model": "", "quantity": 1, "mass_kg": 0.012, "enabled": False},
    {"category": "telemetry", "model": "", "quantity": 1, "mass_kg": 0.020, "enabled": False},
    {"category": "vtx", "model": "", "quantity": 1, "mass_kg": 0.015, "enabled": False},
    {"category": "antenna", "model": "", "quantity": 1, "mass_kg": 0.010, "enabled": False},
    {"category": "camera", "model": "", "quantity": 1, "mass_kg": 0.025, "enabled": False},
    {"category": "gimbal", "model": "", "quantity": 1, "mass_kg": 0.150, "enabled": False},
    {"category": "remote_id", "model": "", "quantity": 1, "mass_kg": 0.025, "enabled": False},
    {"category": "sensors", "model": "", "quantity": 1, "mass_kg": 0.015, "enabled": False},
    {"category": "landing_gear", "model": "", "quantity": 1, "mass_kg": 0.080, "enabled": False},
    {"category": "wiring", "model": "", "quantity": 1, "mass_kg": 0.050, "enabled": True},
)

TOOLTIPS = {
    "model": (
        "Нормалізована модель. Маркування — на лопаті чи упаковці. Більший діаметр підвищує тягу й навантаження; більший крок — швидкість і струм. Критичність: висока.",
        "Normalized model. Find its marking on the blade or package. Larger diameter raises thrust/load; more pitch raises speed/current. Criticality: high."),
    "voltage": (
        "Робоча напруга під навантаженням. Джерело: телеметрія або S×3.7 V. Збільшення підвищує RPM і струм. Типово 7.4–44.4 V. Критичність: висока.",
        "Loaded voltage from telemetry or S×3.7 V. Increasing raises RPM and current. Typical 7.4–44.4 V. Criticality: high."),
    "throttle": (
        "Газ 0–100%. Еквівалентна напруга ≈ U×газ; потужність росте приблизно як RPM³. Критичність: висока.",
        "Throttle 0–100%. Effective voltage ≈ V×throttle; power rises roughly with RPM³. Criticality: high."),
    "kv": (
        "KV — RPM/V без навантаження. Більше KV підвищує RPM і струм; менше KV краще для великих пропелерів. Типово 100–3000 KV.",
        "KV is no-load RPM/V. Higher KV raises RPM/current; lower KV suits larger propellers. Typical 100–3000 KV."),
    "speed": (
        "Швидкість потоку. J=V/(n·D). 0 — статичний режим. Зміна швидкості зміщує робочу точку. Критичність: висока у польоті.",
        "Flow speed. J=V/(n·D). Zero is static. Speed shifts the operating point. Criticality: high in flight."),
    "mass": (
        "Повна маса з батареєю та навантаженням. Виміряти вагами. Збільшення зменшує T/W. Типово 0.1–25 kg. Критичність: висока.",
        "All-up mass with battery/payload, measured on a scale. Increasing lowers T/W. Typical 0.1–25 kg. Criticality: high."),
    "rm": (
        "Опір обмотки Rm, Ω, із моторної карти або вимірювання. Менше Rm зменшує I²R-втрати. Без Rm модель спрощена. Типово 0.01–0.5 Ω.",
        "Winding resistance Rm in Ω from a motor map/measurement. Lower Rm reduces I²R loss. Missing Rm triggers a simplified model."),
    "i0": (
        "Струм холостого ходу I0 з паспорта/стенду. Більше I0 означає більші втрати. Без I0 модель спрощена. Типово 0.2–5 A.",
        "No-load current I0 from a datasheet/bench. Higher I0 means more loss. Missing I0 triggers a simplified model."),
}

HELP_UK = """<h1>Повний опис програми</h1>
<h2>Швидкий порядок роботи</h2><ol><li>Виберіть мову та SI/Imperial.</li><li>У простому або інженерному
калькуляторі виберіть пропелер.</li><li>Для перевірки опублікованих даних виберіть «Відтворити випробування з
бази»; для власного апарата — «Власні параметри».</li><li>Введіть батарею, мотор, ESC, масу й швидкість,
натисніть «Розрахувати» та перевірте попередження.</li><li>За потреби збережіть повну збірку або додайте її до
порівняння.</li></ol>
<h2>Що таке вихідна характеристика з бази</h2><p>Це один конкретний рядок початкового файла з RPM, J,
Ct і Cp. Він потрібний для точного відтворення стендової/чисельної умови та незалежної перевірки формулами. Це
<b>не</b> параметри мотора, батареї, ESC чи апарата, якщо джерело їх не містило.</p>
<h2>Можливості за вкладками</h2><ul><li><b>Калькулятор:</b> простий і інженерний режими, дві строки
«база/математика», графіки навантаження, запаси й sweep ефективності.</li><li><b>База:</b> пошук моделей і всіх
характеристик, джерела та файли.</li><li><b>Збережені збірки:</b> повний склад силової установки, рами, модулів
і аксесуарів, JSON імпорт/експорт.</li><li><b>Порівняння:</b> ранжування варіантів.</li><li><b>Рама:</b> стандартні
розміри, власний розмір, зазор, спрощена міцність і три рекомендації.</li><li><b>Перевірка формул:</b> відкриті
проміжні величини.</li></ul>
<h2>Класи джерел</h2><p>UIUC — фізичні випробування; ENOLA окремо зберігає experiment, CFD і BEMT;
APC PERFILES — прогноз виробника; Product Data — каталог; PE0 — геометрія; APC RPM Rev 5 — структурні ліміти.
Класи не змішуються.</p>
<h2>Формули в SI</h2><p><code>n=RPM/60</code>; <code>J=V/(n·D)</code>;
<code>T=Ct·ρ·n²·D⁴</code>; <code>P=Cp·ρ·n³·D⁵</code>; <code>Q=P/(2πn)</code>;
<code>ηprop=Ct·J/Cp</code>; для статики <code>FOM=Ct^(3/2)/(√2·Cp)</code>;
<code>Kt=60/(2π·KV)</code>. За наявності Rm/I0 RPM знаходиться балансом моментів.</p>
<h2>Інтерполяція і достовірність</h2><p>Лінійна інтерполяція виконується спочатку по J у сусідніх
RPM-кривих, потім по RPM. За межами таблиці береться край, позначається екстраполяція та знижується достовірність.
Експеримент має вищу вагу, ніж CFD/прогноз; каталог і геометрія самі по собі не є характеристикою.</p>
<h2>Де брати значення</h2><p>KV/Rm/I0/max I/max P — паспорт, моторна карта або стенд; S, Ah, C і
хімія — етикетка батареї; ліміт ESC — тривалий паспортний; маса — зважування готового апарата; швидкість —
цільовий режим; стандартне повітря ρ=1.225 кг/м³.</p>
<h2>Батареї</h2><p>Номінали комірки: LiPo 3.7 V, Li-ion 3.6 V, LiFePO4 3.2 V. Оціночна
корисна частка ємності: 0.80, 0.85, 0.90. <code>U=S·Ucell</code>; <code>t=Ah·usable/I·60</code>.</p>
<h2>Модулі збірки</h2><p>Польотний контролер, PDB, приймач, GPS, телеметрія, VTX, антена, камера,
підвіс, Remote ID, датчики, шасі, проводка та власні рядки зберігаються у складі збірки. Вони не змінюють
аеродинаміку напряму; натисніть «Врахувати масу в розрахунку», лише якщо ця маса ще не входить у повну масу.</p>
<h2>Обмеження</h2><p>Без Rm/I0 показується «оцінка за спрощеною моделлю». Програма не замінює
стенд, теплову, вібраційну, кавітаційну та міцнісну перевірку або вимоги виробника. Рама — спрощена балочна модель.</p>"""

HELP_EN = """<h1>Complete application guide</h1>
<h2>Quick workflow</h2><ol><li>Select language and SI/Imperial.</li><li>Select a propeller in Simple or Engineering
mode.</li><li>Use “Reproduce a database test” to verify published data, or “Custom inputs” for your own aircraft.</li>
<li>Enter battery, motor, ESC, mass and speed, calculate, then review every warning.</li><li>Save the complete build or
add it to Comparison.</li></ol>
<h2>What is a database test condition?</h2><p>It is one exact original-file row containing RPM, J, Ct and Cp. It
reproduces a bench/numerical condition and lets the equations check it independently. It is <b>not</b> the motor,
battery, ESC or aircraft specification unless the source explicitly included those values.</p>
<h2>Features by tab</h2><ul><li><b>Calculator:</b> Simple and Engineering modes, database/math rows, load
charts, safety margins and efficiency sweep.</li><li><b>Database:</b> model and characteristic search with provenance.</li>
<li><b>Saved builds:</b> complete power system, frame, module/accessory inventory and JSON exchange.</li>
<li><b>Comparison:</b> criterion-based ranking.</li><li><b>Frame:</b> standard/custom sizes, clearance, simplified strength
and three recommendations.</li><li><b>Formula verification:</b> open intermediate values.</li></ul>
<h2>Evidence classes</h2><p>UIUC is physical testing; ENOLA keeps experiment, CFD and BEMT separate; APC
PERFILES is manufacturer prediction; Product Data is catalog; PE0 is geometry; RPM Rev 5 is structural limits.</p>
<h2>SI equations</h2><p><code>n=RPM/60</code>; <code>J=V/(n·D)</code>; <code>T=Ct·ρ·n²·D⁴</code>;
<code>P=Cp·ρ·n³·D⁵</code>; <code>Q=P/(2πn)</code>; <code>ηprop=Ct·J/Cp</code>; static
<code>FOM=Ct^(3/2)/(√2·Cp)</code>; <code>Kt=60/(2π·KV)</code>. With Rm/I0, RPM follows torque balance.</p>
<h2>Interpolation and confidence</h2><p>Interpolation is linear in J inside adjacent RPM curves and then in RPM.
Outside the table the edge is used, extrapolation is marked and confidence falls. Experiment outranks CFD/prediction;
catalog and geometry alone are not performance evidence.</p>
<h2>Input sources</h2><p>Use a datasheet, motor map or bench for KV/Rm/I0/max I/max P; battery label for
chemistry/S/Ah/C; continuous ESC rating; measured all-up mass; intended flow speed; standard air ρ=1.225 kg/m³.</p>
<h2>Batteries</h2><p>Nominal cells: LiPo 3.7 V, Li-ion 3.6 V, LiFePO4 3.2 V. Estimated usable fractions:
0.80, 0.85 and 0.90. <code>V=S·Vcell</code>; <code>t=Ah·usable/I·60</code>.</p>
<h2>Build modules</h2><p>Flight controller, PDB, receiver, GPS, telemetry, VTX, antenna, camera, gimbal,
Remote ID, sensors, landing gear, wiring and custom rows are saved as inventory. They affect aerodynamics only through
mass; click “Apply mass to calculation” only if that mass is not already included in all-up mass.</p>
<h2>Limitations</h2><p>Missing Rm/I0 is labeled a simplified-model estimate. The program does not replace
bench, thermal, vibration, cavitation, structural or manufacturer-limit validation. Frame analysis is simplified.</p>"""

EXAMPLE_1_UK = """<h1>Приклад 1 — перевірка рядка бази</h1>
<p><b>Мета:</b> зрозуміти різницю між вихідною характеристикою та власною конфігурацією.</p>
<ol><li>Завантажте приклад: модель <b>APC:8X9</b>, режим «Відтворити випробування з бази».</li>
<li>Вибрана статична характеристика має приблизно <b>6395 RPM, J=0, Ct=0.1115, Cp=0.1119</b>.</li>
<li>Перший рядок показує початкові значення файла, другий повторно застосовує
<code>P=Cp·ρ·n³·D⁵</code>. За однакових RPM/J обидва дають близько <b>57.50 W механічної потужності
одного пропелера</b>.</li><li>Верхня картка електричної потужності може бути іншою: вона належить усій силовій
установці, враховує кількість моторів і втрати.</li></ol>
<p>Змініть KV, напругу або газ — програма перейде до «Власні параметри». Щоб повернути точне відтворення,
знову виберіть режим бази та потрібну характеристику.</p>"""

EXAMPLE_1_EN = """<h1>Example 1 — verify a database row</h1>
<p><b>Goal:</b> understand the difference between a database condition and your own configuration.</p>
<ol><li>Load this example: <b>APC:8X9</b>, “Reproduce a database test”.</li><li>The selected static condition is
approximately <b>6395 RPM, J=0, Ct=0.1115, Cp=0.1119</b>.</li><li>The first row shows the original-file values;
the second reapplies <code>P=Cp·ρ·n³·D⁵</code>. With identical RPM/J both give about <b>57.50 W shaft power per
propeller</b>.</li><li>The upper electrical-power card may differ because it represents the complete powertrain, motor count
and losses.</li></ol><p>Editing KV, voltage or throttle switches to Custom inputs. Select the database mode and condition again
to restore exact reproduction.</p>"""

EXAMPLE_2_UK = """<h1>Приклад 2 — власна квадрокоптерна збірка</h1>
<p><b>Вхід:</b> APC:10X5; LiPo 4S/14.8 V; 500 KV; 100% газу; 0 m/s; 4 мотори; повна маса 1.5 kg;
ESC 40 A; батарея 5 Ah 30C; режим «Власні параметри».</p>
<p><b>Очікувана спрощена оцінка:</b> близько 5920 RPM, 21.15 N загальної тяги, 21.25 A загального струму,
314.5 W загальної електричної потужності, T/W 1.44 та 11.3 хв. Результат може трохи змінитися після оновлення бази.</p>
<ol><li>Перевірте червоні попередження та підпис «спрощена модель»: Rm/I0 не задані.</li><li>На «Рама»
виберіть 450 mm, X, 4 мотори та розрахуйте зазор/рекомендації.</li><li>На «Збережені збірки» введіть точні
моделі мотора, батареї, ESC і рами; позначте GPS, камеру, Remote ID тощо, введіть їх маси.</li><li>Якщо модулі
ще не входять у повну масу — натисніть «Врахувати масу в розрахунку», потім збережіть.</li></ol>"""

EXAMPLE_2_EN = """<h1>Example 2 — custom quadcopter build</h1>
<p><b>Inputs:</b> APC:10X5; LiPo 4S/14.8 V; 500 KV; 100% throttle; 0 m/s; 4 motors; 1.5 kg all-up mass;
40 A ESC; 5 Ah 30C battery; Custom inputs.</p><p><b>Expected simplified estimate:</b> about 5920 RPM, 21.15 N total
thrust, 21.25 A total current, 314.5 W total electrical power, T/W 1.44 and 11.3 min. Results may shift slightly after
a database update.</p><ol><li>Review red warnings and the simplified-model label: Rm/I0 are missing.</li><li>On Frame,
select 450 mm, X and 4 motors, then calculate clearance/recommendations.</li><li>On Saved builds, enter exact motor,
battery, ESC and frame models; select GPS, camera, Remote ID, etc. and their masses.</li><li>If module mass is not already
in all-up mass, apply it to the calculation, then save.</li></ol>"""

STYLE = """
QMainWindow, QWidget {background:#111820;color:#DCE7EC;font-family:'Segoe UI';font-size:10pt}
QFrame#header {background:#0B1117;border-bottom:1px solid #344651}
QFrame#header QLabel {background:transparent}
QLabel#appTitle {font-size:17pt;font-weight:700;color:#F3F7F8;letter-spacing:1px}
QLabel#subTitle {color:#7FA0AD;font-size:9pt}
QLabel#section {color:#6FD3C6;font-size:9pt;font-weight:700;letter-spacing:1px}
QTabWidget::pane {border:1px solid #2E404A;background:#111820}
QTabBar::tab {background:#17232C;color:#8FA7B1;padding:9px 15px;margin-right:1px;border-top:2px solid transparent}
QTabBar::tab:selected {background:#1D2A33;color:#F4FAFA;border-top:2px solid #26C2B2;font-weight:600}
QTabWidget#calculatorModes::pane {border:1px solid #35515A;border-radius:8px;background:#121B22;margin-top:2px}
QTabWidget#calculatorModes QTabBar::tab {font-size:11pt;min-width:180px;padding:10px 22px}
QTabWidget#calculatorModes QTabBar::tab:selected {background:#173B3A;color:#7DE2D5;border-top:3px solid #36D2C0}
QGroupBox {font-weight:700;color:#9DB5BF;border:1px solid #32444E;border-radius:7px;margin-top:12px;padding-top:10px;background:#18232C}
QGroupBox::title {subcontrol-origin:margin;left:11px;padding:0 5px;color:#63CDBF}
QLineEdit,QComboBox,QPlainTextEdit,QTextBrowser,QTableWidget {background:#0E151B;color:#E1EBEF;border:1px solid #334A55;border-radius:4px;padding:5px;selection-background-color:#168F84}
QLineEdit:focus,QComboBox:focus {border:1px solid #35C9B8}
QComboBox QAbstractItemView {background:#17232C;color:#E1EBEF;selection-background-color:#168F84}
QPushButton {background:#23343E;color:#DDE8EC;border:1px solid #405762;border-radius:5px;padding:7px 11px;font-weight:600}
QPushButton:hover {background:#2B414C;border-color:#5F7B86}
QPushButton#primary {background:#16A394;color:white;border:1px solid #38CDBD;font-weight:800;letter-spacing:1px}
QPushButton#primary:hover {background:#20B8A8}
QToolButton {background:#20343D;color:#6FD3C6;border:1px solid #41616B;border-radius:12px;font-weight:800}
QToolButton:hover {background:#2A4A52;color:white;border-color:#6FD3C6}
QFrame#card {background:#192630;border:1px solid #314650;border-radius:7px}
QFrame#card:hover {border-color:#43808A}
QLabel#cardTitle {color:#7897A3;font-size:8.5pt;font-weight:600}
QLabel#cardValue {color:#F1F7F8;font-size:14pt;font-weight:700}
QProgressBar {border:1px solid #36505B;border-radius:5px;text-align:center;background:#0D1419;color:#EAF4F5;height:18px}
QProgressBar::chunk {background:#19A797;border-radius:4px}
QHeaderView::section {background:#20313B;color:#9FB6BF;padding:6px;border:0;border-right:1px solid #344A55;font-weight:700}
QTableWidget {gridline-color:#263943;alternate-background-color:#151F27}
QScrollBar:vertical {background:#111820;width:11px} QScrollBar::handle:vertical {background:#38515C;border-radius:5px;min-height:24px}
QScrollBar:horizontal {background:#111820;height:11px} QScrollBar::handle:horizontal {background:#38515C;border-radius:5px;min-width:24px}
QStatusBar {background:#0C1318;color:#73909B;border-top:1px solid #2B3C45}
QLabel#modeIntro {background:#13252B;color:#A7D8D3;border-left:3px solid #2FC6B5;padding:8px;border-radius:3px}
QToolTip {background:#E7F2F2;color:#102126;border:1px solid #3A7775;padding:10px;font-size:10pt}
"""


class CalcInputErrors(ValueError):
    """Parse failures for calculator numeric fields.

    Carries ``field_errors`` as a list of ``(field_key, raw_value)`` tuples
    in parse order. Raised by ``_inputs``; handled inline by ``calculate``
    (no modal), while all other exceptions keep the critical modal.
    """

    def __init__(self, field_errors: list[tuple[str, str]]) -> None:
        super().__init__("; ".join(f"{key}={raw!r}" for key, raw in field_errors))
        self.field_errors = field_errors


RESTORE_REQUIRED_TABLES = ("models", "performance_points", "sources")


def validate_restore_candidate(path: str | Path) -> tuple[bool, str]:
    """Fail-closed validation for a database file picked for restore.

    Opens the candidate read-only and checks ``PRAGMA quick_check``,
    the required tables and a basic model-count sanity check.
    Returns ``(ok, message)``; never raises and never touches the
    working database.
    """
    candidate = Path(path)
    if not candidate.is_file():
        return False, f"File does not exist: {candidate}"
    connection: sqlite3.Connection | None = None
    try:
        connection = sqlite3.connect(f"file:{candidate.as_posix()}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        quick_rows = connection.execute("PRAGMA quick_check").fetchall()
        quick_values = [str(row[0]) for row in quick_rows]
        if not (len(quick_values) == 1 and quick_values[0].strip().lower() == "ok"):
            detail = "; ".join(quick_values)[:300] or "empty quick_check"
            return False, f"Integrity check failed: {detail}"
        available = {row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        missing = [name for name in RESTORE_REQUIRED_TABLES if name not in available]
        if missing:
            return False, f"Required tables missing: {', '.join(missing)}"
        model_count = connection.execute("SELECT COUNT(*) FROM models").fetchone()[0]
        try:
            model_count = int(model_count)
        except (TypeError, ValueError):
            return False, "Model count sanity check failed"
        if model_count <= 0:
            return False, "Database contains no propeller models"
        return True, f"OK: {model_count} models"
    except Exception as exc:  # noqa: BLE001 - validation must never raise
        return False, f"{type(exc).__name__}: {exc}"
    finally:
        if connection is not None:
            try:
                connection.close()
            except Exception:  # noqa: BLE001 - best effort
                pass


class PropellerMark(QWidget):
    """Small vector propeller/motor mark; scales cleanly at 100–200% DPI."""
    def __init__(self) -> None:
        super().__init__()
        self.setFixedSize(58, 58)

    def paintEvent(self, _event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.translate(self.width() / 2, self.height() / 2)
        painter.setPen(QPen(QColor("#54D6C7"), 2))
        painter.setBrush(QColor("#193A40"))
        for angle in (0, 120, 240):
            painter.save()
            painter.rotate(angle)
            painter.drawEllipse(QRectF(2, -6, 23, 12))
            painter.restore()
        painter.setBrush(QColor("#C4D5DB"))
        painter.drawEllipse(QPointF(0, 0), 6, 6)
        painter.setBrush(QColor("#0B1117"))
        painter.drawEllipse(QPointF(0, 0), 2, 2)


class PropellerMainWindow(QMainWindow):
    def __init__(self, database_path: Path | None = None):
        super().__init__()
        # The offscreen test platform has no automatic font discovery. Windows 10/11
        # always includes Segoe UI, so explicitly registering it also makes visual QA deterministic.
        for font_name in ("segoeui.ttf", "segoeuib.ttf"):
            font_path = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / font_name
            if font_path.exists():
                QFontDatabase.addApplicationFont(str(font_path))
        if database_path is None:
            self.database_path, self.paths = prepare_working_database()
        else:
            self.database_path = Path(database_path)
            base = self.database_path.parent
            self.paths = {"base": base, "database": self.database_path, "backups": base / "backups",
                          "exports": base / "exports", "logs": base / "logs"}
            self.paths["backups"].mkdir(parents=True, exist_ok=True)
        self.repository = Repository(self.database_path)
        self.calculator = PropellerCalculator(self.repository)
        self.language = self._setting("language", "uk")
        self.unit_system = self._setting("unit_system", "SI")
        self.tooltips_enabled = self._setting("tooltips", "1") == "1"
        self.state = dict(DEFAULTS)
        self.build_accessories = [dict(item) for item in ACCESSORY_DEFAULTS]
        self._updating_accessories = False
        self._accessory_mass_applied_kg = 0.0
        self._loading_preset = False
        self.edits: dict[str, QLineEdit] = {}
        self.edit_widgets: dict[str, list[QLineEdit]] = {}
        self.combos: dict[str, QComboBox] = {}
        self.combo_widgets: dict[str, list[QComboBox]] = {}
        self.model_combos: list[QComboBox] = []
        self.reference_point_combos: list[QComboBox] = []
        self.source_preset_labels: list[QLabel] = []
        self.comparison_explain_labels: list[QLabel] = []
        self.tip_widgets: list[tuple[QWidget, str]] = []
        self.tip_keys: dict[int, str] = {}
        self.context_help_labels: list[QLabel] = []
        self.reference_tables: list[QTableWidget] = []
        self.current_result: CalculationResult | None = None
        self.current_inputs: CalculationInputs | None = None
        self.current_build_id: int | None = None
        self.compare_items: list[dict[str, Any]] = []
        self.selected_model_id = ""
        self.result_labels: dict[str, QLabel] = {}
        self.setWindowTitle(f"{APP_NAME} — {AUTHOR}")
        # At 200% scaling a 1366×768 display exposes roughly 683×384 logical pixels.
        # The calculation page is scrollable, so the minimum remains usable there.
        self.setMinimumSize(640, 360)
        self.resize(1366, 768)
        self.setStyleSheet(STYLE)
        self._build_ui()
        QTimer.singleShot(0, self._initialize_calculator)

    def _setting(self, key: str, default: str) -> str:
        row = self.repository.connection.execute("SELECT value FROM app_settings WHERE key=?", (key,)).fetchone()
        return str(row[0]) if row else default

    def _save_setting(self, key: str, value: str) -> None:
        self.repository.connection.execute(
            "INSERT INTO app_settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value))
        self.repository.connection.commit()

    def tr(self, key: str) -> str:
        return UI_TEXT[self.language].get(key, key)

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self.repository.close()
        event.accept()

    def _snapshot(self) -> None:
        self._snapshot_accessories()
        if hasattr(self, "build_description"):
            self.state["build_description"] = self.build_description.toPlainText()
        if hasattr(self, "build_note"):
            self.state["build_note"] = self.build_note.toPlainText()
        for key, widget in self.edits.items():
            self.state[key] = widget.text()
        for key, widget in self.combos.items():
            if key != "model":
                value = widget.currentData()
                self.state[key] = str(value if value is not None else widget.currentText())
        if hasattr(self, "model_combo"):
            self.selected_model_id = str(self.selected_model_id or self.model_combo.currentData() or self.model_combo.currentText())

    def _build_ui(self) -> None:
        old_index = self.tabs.currentIndex() if hasattr(self, "tabs") else 0
        # Dispose the previous UI tree: setCentralWidget() does not delete the
        # replaced central widget, so without this each rebuild (language/units
        # switch) left the old tree as hidden-but-alive children of the window
        # and findChildren() counts (e.g. primary buttons) grew 6->12->18.
        old_central = self.takeCentralWidget()
        self.edits, self.edit_widgets, self.combos, self.combo_widgets = {}, {}, {}, {}
        self.model_combos, self.tip_widgets, self.tip_keys, self.context_help_labels = [], [], {}, []
        self.reference_point_combos, self.source_preset_labels, self.comparison_explain_labels = [], [], []
        self.reference_tables = []
        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        root_layout.addWidget(self._header())
        self.tabs = QTabWidget()
        for key, builder in (
            ("calculator", self._calculator_tab), ("database", self._database_tab),
            ("builds", self._builds_tab), ("compare", self._compare_tab), ("frame", self._frame_tab),
            ("testing", self._testing_tab), ("help", self._help_tab), ("about", self._about_tab)):
            self.tabs.addTab(builder(), self.tr(key))
        root_layout.addWidget(self.tabs, 1)
        self.setCentralWidget(root)
        if old_central is not None:
            old_central.deleteLater()
        self.statusBar().showMessage(f"{self.tr('ready_status')} · {AUTHOR} · {self.database_path}")
        self.tabs.setCurrentIndex(min(old_index, self.tabs.count() - 1))
        self._apply_tooltips()
        self._apply_responsive(self.width())
        self._update_preset_status()
        if self.current_result and self.current_inputs:
            self._display_result(self.current_result, self.current_inputs)
            self._refresh_trace()

    def _header(self) -> QWidget:
        header = QFrame(objectName="header")
        row = QHBoxLayout(header)
        row.setContentsMargins(14, 5, 16, 5)
        self.header_mark = PropellerMark()
        row.addWidget(self.header_mark)
        titles = QVBoxLayout()
        titles.setSpacing(0)
        self.header_title = QLabel(APP_NAME.upper(), objectName="appTitle")
        self.header_subtitle = QLabel(f"{self.tr('offline_subtitle')} · {self.tr('author')}: {AUTHOR}", objectName="subTitle")
        titles.addWidget(self.header_title)
        titles.addWidget(self.header_subtitle)
        row.addLayout(titles)
        row.addStretch(1)
        self.language_label = QLabel(self.tr("language"))
        row.addWidget(self.language_label)
        language = QComboBox()
        language.addItem("УКР", "uk")
        language.addItem("ENG", "en")
        language.setCurrentIndex(0 if self.language == "uk" else 1)
        language.currentIndexChanged.connect(lambda: self._switch_language(str(language.currentData())))
        row.addWidget(language)
        self.units_label = QLabel(self.tr("units"))
        row.addWidget(self.units_label)
        units = QComboBox()
        units.addItems(["SI", "Imperial"])
        units.setCurrentText(self.unit_system)
        units.currentTextChanged.connect(self._switch_units)
        row.addWidget(units)
        tips = QCheckBox(self.tr("tooltips"))
        tips.setChecked(self.tooltips_enabled)
        tips.toggled.connect(self._toggle_tooltips)
        row.addWidget(tips)
        return header

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self._apply_responsive(event.size().width())

    def _apply_responsive(self, width: int) -> None:
        compact = width < 900
        if hasattr(self, "header_title"):
            self.header_title.setText("PROPCALC v3" if compact else APP_NAME.upper())
            self.header_title.setStyleSheet("font-size:13pt" if compact else "")
            self.header_subtitle.setVisible(not compact)
            self.header_mark.setVisible(not compact)
            self.language_label.setVisible(not compact)
            self.units_label.setVisible(not compact)
        for layout_name in ("simple_calculator_layout", "engineering_calculator_layout"):
            layout = getattr(self, layout_name, None)
            if layout is None:
                continue
            direction = QBoxLayout.Direction.TopToBottom if compact else QBoxLayout.Direction.LeftToRight
            layout.setDirection(direction)

    def _switch_language(self, value: str) -> None:
        if value != self.language:
            self._snapshot()
            self.language = value
            self._save_setting("language", value)
            self._build_ui()

    def _switch_units(self, value: str) -> None:
        if value == self.unit_system:
            return
        self._snapshot()
        old = self.unit_system
        for key, quantity in (("speed", "speed"), ("mass", "mass_kg"), ("frame_diagonal", "length_m"),
                              ("arm_width", "length_m"), ("arm_thickness", "length_m"),
                              ("frame_mass", "mass_kg"), ("payload", "mass_kg"),
                              ("build_payload", "mass_kg")):
            try:
                si = to_si(float(self.state[key]), quantity, old)
                self.state[key] = f"{from_si(si, quantity, value):.10g}"
            except (ValueError, TypeError):
                pass
        self.unit_system = value
        self._save_setting("unit_system", value)
        self._build_ui()

    def _toggle_tooltips(self, enabled: bool) -> None:
        self.tooltips_enabled = enabled
        self._save_setting("tooltips", "1" if enabled else "0")
        self._apply_tooltips()

    def _apply_tooltips(self) -> None:
        for widget, key in self.tip_widgets:
            pair = FIELD_HELP.get(key)
            text = pair[0 if self.language == "uk" else 1] if pair else ""
            html = "<div style='width:430px;white-space:normal'>" + text.replace("\n", "<br>") + "</div>"
            widget.setToolTip(html if self.tooltips_enabled else "")
            widget.setToolTipDuration(30000)
            widget.setAccessibleDescription(text)
        if not self.tooltips_enabled:
            for label in self.context_help_labels:
                label.setText(self.tr("hover_help"))

    def _register_tip(self, widget: QWidget, key: str) -> None:
        self.tip_widgets.append((widget, key))
        self.tip_keys[id(widget)] = key
        widget.setMouseTracking(True)
        widget.installEventFilter(self)

    def eventFilter(self, watched, event) -> bool:  # type: ignore[override]
        key = self.tip_keys.get(id(watched))
        if key and self.tooltips_enabled and event.type() in (QEvent.Type.Enter, QEvent.Type.FocusIn):
            self._show_context_help(key)
        return super().eventFilter(watched, event)

    def _help_text(self, key: str) -> str:
        pair = FIELD_HELP.get(key)
        return pair[0 if self.language == "uk" else 1] if pair else key

    def _show_context_help(self, key: str) -> None:
        for label in self.context_help_labels:
            label.setText(self._help_text(key))

    def _open_field_help(self, key: str) -> None:
        message = QMessageBox(self)
        message.setWindowTitle(self.tr("help_panel"))
        message.setIcon(QMessageBox.Icon.Information)
        message.setText(self.tr(key) if key in UI_TEXT[self.language] else key)
        message.setInformativeText(self._help_text(key))
        message.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        message.setStyleSheet("QLabel{min-width:520px;}")
        message.exec()

    @staticmethod
    def _scroll(content: QWidget) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(content)
        return scroll

    def _edit(self, key: str, tip: str | None = None) -> QLineEdit:
        widget = QLineEdit(self.state.get(key, ""))
        widget.setMinimumWidth(92)
        self.edits[key] = widget
        self.edit_widgets.setdefault(key, []).append(widget)
        widget.textEdited.connect(lambda value, k=key, source=widget: self._sync_edit_value(k, value, source))
        if tip:
            self._register_tip(widget, tip)
        return widget

    def _sync_edit_value(self, key: str, value: str, source: QLineEdit) -> None:
        self.state[key] = value
        for widget in self.edit_widgets.get(key, []):
            if widget is not source and widget.text() != value:
                with QSignalBlocker(widget):
                    widget.setText(value)
        if not self._loading_preset and key in {
            "voltage", "throttle", "kv", "speed", "mass", "motors", "esc", "capacity",
            "c_rating", "battery_s", "rm", "i0", "motor_max_current", "motor_max_power", "density",
        }:
            self._activate_custom_mode()
        if not self._loading_preset and key == "mass":
            self._accessory_mass_applied_kg = 0.0
        if not self._loading_preset and key == "frame_diagonal":
            self._set_combo_value("frame_size_preset", "custom")

    def _combo(self, key: str, values: list[Any], tip: str | None = None) -> QComboBox:
        widget = QComboBox()
        for value in values:
            if isinstance(value, tuple):
                widget.addItem(str(value[0]), value[1])
            else:
                widget.addItem(str(value), value)
        wanted = self.state.get(key, values[0][1] if isinstance(values[0], tuple) else values[0])
        index = widget.findData(wanted)
        widget.setCurrentIndex(max(0, index))
        self.combos[key] = widget
        self.combo_widgets.setdefault(key, []).append(widget)
        widget.currentIndexChanged.connect(lambda _index, k=key, source=widget: self._sync_combo_value(k, source))
        if tip:
            self._register_tip(widget, tip)
        return widget

    def _sync_combo_value(self, key: str, source: QComboBox) -> None:
        value = source.currentData()
        self.state[key] = str(value if value is not None else source.currentText())
        for widget in self.combo_widgets.get(key, []):
            if widget is source:
                continue
            index = widget.findData(value)
            if index >= 0 and index != widget.currentIndex():
                with QSignalBlocker(widget):
                    widget.setCurrentIndex(index)
        if self._loading_preset:
            return
        if key == "configuration_mode":
            if self.state[key] == "database":
                self._apply_reference_preset(schedule_calculation=True)
            else:
                self._activate_custom_mode()
        elif key == "battery_type":
            self._activate_custom_mode()
            self._apply_battery_nominal_defaults()
        elif key == "battery_s":
            self._activate_custom_mode()
            self._apply_battery_nominal_defaults(update_c_rating=False)
        elif key == "medium":
            self._activate_custom_mode()
        elif key == "frame_size_preset":
            self._apply_frame_size_preset()

    def _model_selector(self) -> QComboBox:
        widget = QComboBox()
        widget.setEditable(True)
        widget.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        widget.completer().setFilterMode(Qt.MatchFlag.MatchContains)
        widget.completer().setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        for model in self.repository.search_models("", limit=5000):
            widget.addItem(model["model_id"], model["model_id"])
        wanted = self.selected_model_id or "APC:10X5"
        index = widget.findData(wanted)
        if index < 0:
            index = max(0, widget.findText("APC:10X5", Qt.MatchFlag.MatchContains))
        widget.setCurrentIndex(index)
        self.selected_model_id = str(widget.currentData() or widget.currentText())
        widget.currentIndexChanged.connect(lambda _index, source=widget: self._sync_model(source))
        self.model_combos.append(widget)
        self.model_combo = widget
        self.combos["model"] = widget
        self._register_tip(widget, "model")
        return widget

    def _sync_model(self, source: QComboBox) -> None:
        model_id = str(source.currentData() or source.currentText().strip())
        self.selected_model_id = model_id
        for widget in self.model_combos:
            if widget is source:
                continue
            index = widget.findData(model_id)
            if index >= 0 and index != widget.currentIndex():
                with QSignalBlocker(widget):
                    widget.setCurrentIndex(index)
        self._loading_preset = True
        try:
            self._set_combo_value("battery_type", "LiPo")
            self._set_configuration_mode("database")
            self._populate_reference_points(model_id, select_first=True)
        finally:
            self._loading_preset = False
        self._apply_reference_preset(schedule_calculation=True)

    def _set_text_value(self, key: str, value: str) -> None:
        self.state[key] = value
        for widget in self.edit_widgets.get(key, []):
            with QSignalBlocker(widget):
                widget.setText(value)

    def _set_combo_value(self, key: str, value: str) -> None:
        self.state[key] = value
        for widget in self.combo_widgets.get(key, []):
            index = widget.findData(value)
            if index >= 0:
                with QSignalBlocker(widget):
                    widget.setCurrentIndex(index)

    def _set_configuration_mode(self, mode: str) -> None:
        self._set_combo_value("configuration_mode", mode)

    def _activate_custom_mode(self) -> None:
        if self._loading_preset:
            return
        self._set_configuration_mode("custom")
        self.state["reference_rpm"] = ""
        self._update_preset_status()

    def _apply_battery_nominal_defaults(self, update_c_rating: bool = True) -> None:
        try:
            cells = int(float(self.state.get("battery_s", "4")))
        except ValueError:
            return
        spec = battery_spec(self.state.get("battery_type", "LiPo"))
        self._loading_preset = True
        try:
            self._set_text_value("voltage", f"{cells * spec['nominal_v']:.3g}")
            if update_c_rating:
                self._set_text_value("c_rating", f"{spec['typical_c']:.0f}")
        finally:
            self._loading_preset = False
        self._update_preset_status()

    def _reference_point_combo(self) -> QComboBox:
        widget = QComboBox()
        widget.setMinimumContentsLength(24)
        widget.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.reference_point_combos.append(widget)
        self._fill_reference_combo(widget, self.selected_model_id or "APC:10X5")
        widget.currentIndexChanged.connect(lambda _index, source=widget: self._sync_reference_point(source))
        self._register_tip(widget, "reference_point")
        return widget

    def _reference_point_text(self, row: Any) -> str:
        evidence = self._evidence_name(str(row["evidence_class"]))
        mode = ("статика" if self.language == "uk" else "static") if row["is_static"] else (
            "динаміка" if self.language == "uk" else "dynamic")
        return (f"{evidence} · {mode} · {float(row['rpm']):,.0f} RPM · "
                f"J {float(row['advance_ratio_j'] or 0):.3f} · {row['relative_path']}:{row['source_row'] or '-'}")

    def _fill_reference_combo(self, widget: QComboBox, model_id: str) -> None:
        wanted = self.state.get("reference_point_id", "")
        with QSignalBlocker(widget):
            widget.clear()
            for row in self.repository.reference_points(model_id):
                widget.addItem(self._reference_point_text(row), str(row["performance_id"]))
            index = widget.findData(str(wanted)) if wanted else -1
            widget.setCurrentIndex(index if index >= 0 else (0 if widget.count() else -1))

    def _populate_reference_points(self, model_id: str, select_first: bool = False) -> None:
        if select_first:
            self.state["reference_point_id"] = ""
        for widget in self.reference_point_combos:
            self._fill_reference_combo(widget, model_id)
        if self.reference_point_combos and self.reference_point_combos[0].currentIndex() >= 0:
            self.state["reference_point_id"] = str(self.reference_point_combos[0].currentData())

    def _sync_reference_point(self, source: QComboBox) -> None:
        point_id = str(source.currentData() or "")
        if not point_id:
            return
        self.state["reference_point_id"] = point_id
        for widget in self.reference_point_combos:
            if widget is source:
                continue
            index = widget.findData(point_id)
            if index >= 0:
                with QSignalBlocker(widget):
                    widget.setCurrentIndex(index)
        self._set_configuration_mode("database")
        self._apply_reference_preset(schedule_calculation=True)

    def _apply_reference_preset(self, schedule_calculation: bool = False) -> None:
        point_id = self.state.get("reference_point_id", "")
        if not point_id:
            self._populate_reference_points(self.selected_model_id, select_first=True)
            point_id = self.state.get("reference_point_id", "")
        if not point_id:
            self._activate_custom_mode()
            return
        row = self.repository.get_performance_point(int(point_id), self.selected_model_id)
        model = self.repository.get_model(self.selected_model_id)
        if row is None or model is None:
            self._activate_custom_mode()
            return
        diameter = float(model["diameter_m"] or 0.254)
        if diameter <= 0.18:
            cells = 3
        elif diameter <= 0.28:
            cells = 4
        elif diameter <= 0.42:
            cells = 6
        elif diameter <= 0.60:
            cells = 8
        else:
            cells = 12
        chemistry = self.state.get("battery_type", "LiPo")
        spec = battery_spec(chemistry)
        voltage = cells * spec["nominal_v"]
        rpm = float(row["rpm"])
        kv = rpm / max(voltage * 0.80, 0.1)
        speed = row["speed_m_s"]
        if speed is None:
            speed = float(row["advance_ratio_j"] or 0) * (rpm / 60.0) * diameter
        raw_power = float(row["power_w"] or 0)
        estimated_current = raw_power / max(voltage * 0.82, 0.1) + 1.0
        esc = max(10, int(math.ceil(estimated_current * 1.35 / 5.0) * 5))
        medium = str(model["medium"] or "air")
        self._loading_preset = True
        try:
            self._set_configuration_mode("database")
            self._set_combo_value("medium", medium)
            self._set_combo_value("battery_s", str(cells))
            self._set_text_value("voltage", f"{voltage:.3g}")
            self._set_text_value("throttle", "100")
            self._set_text_value("kv", f"{kv:.6g}")
            self._set_text_value("speed", f"{from_si(float(speed), 'speed', self.unit_system):.8g}")
            self._set_text_value("esc", str(esc))
            self._set_text_value("c_rating", f"{spec['typical_c']:.0f}")
            self._set_text_value("rm", "")
            self._set_text_value("i0", "")
            self._set_text_value("motor_max_current", "")
            self._set_text_value("motor_max_power", "")
            self._set_text_value("density", "997" if medium == "water" else "1.225")
            self.state["reference_rpm"] = f"{rpm:.12g}"
        finally:
            self._loading_preset = False
        self._update_preset_status(row)
        if schedule_calculation:
            QTimer.singleShot(0, self.calculate)

    def _update_preset_status(self, row: Any | None = None) -> None:
        if self.state.get("configuration_mode") == "database":
            if row is None and self.state.get("reference_point_id"):
                row = self.repository.get_performance_point(
                    int(self.state["reference_point_id"]), self.selected_model_id)
            if row is not None:
                text = self.tr("database_preset_status").format(
                    rpm=f"{float(row['rpm']):,.0f}", j=f"{float(row['advance_ratio_j'] or 0):.3f}",
                    source=f"{row['relative_path']}:{row['source_row'] or '-'}")
            else:
                text = self.tr("database_preset_missing")
        else:
            text = self.tr("custom_preset_status")
        for label in self.source_preset_labels:
            label.setText(text)

    def _initialize_calculator(self) -> None:
        if self.state.get("configuration_mode") == "database":
            self._apply_reference_preset()
        else:
            self._update_preset_status()
        self.calculate()

    def _field(self, form: QFormLayout, label: str, key: str, unit: str = "", tip: str | None = None) -> None:
        box = QWidget()
        row = QHBoxLayout(box)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(5)
        row.addWidget(self._edit(key, tip), 1)
        if unit:
            unit_label_widget = QLabel(unit)
            unit_label_widget.setMinimumWidth(50)
            row.addWidget(unit_label_widget)
        if tip:
            info = QToolButton()
            info.setText("?")
            info.setFixedSize(24, 24)
            info.setCursor(Qt.CursorShape.PointingHandCursor)
            info.clicked.connect(lambda _checked=False, name=tip: self._open_field_help(name))
            info.setAccessibleName(f"{self.tr('help_panel')}: {label}")
            row.addWidget(info)
            self._register_tip(info, tip)
        label_widget = QLabel(label)
        if tip:
            self._register_tip(label_widget, tip)
        form.addRow(label_widget, box)
        if tip:
            self._register_tip(box, tip)

    def _calculator_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(8, 6, 8, 8)
        self.calc_error_label = QLabel()
        self.calc_error_label.setObjectName("calcInputError")
        self.calc_error_label.setWordWrap(True)
        self.calc_error_label.setVisible(False)
        self.calc_error_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.calc_error_label.setStyleSheet("color:#FF7F71;font-weight:700;")
        self.calc_error_label.setAccessibleName("calcInputError")
        layout.addWidget(self.calc_error_label)
        self._calc_error_originals = {}
        self.calculator_modes = QTabWidget()
        self.calculator_modes.setObjectName("calculatorModes")
        self.calculator_modes.addTab(self._simple_calculator_page(), self.tr("simple_mode"))
        self.calculator_modes.addTab(self._engineering_calculator_page(), self.tr("engineering_mode"))
        saved_mode = int(self._setting("calculator_mode", "0"))
        self.calculator_modes.setCurrentIndex(max(0, min(saved_mode, 1)))
        self.calculator_modes.currentChanged.connect(
            lambda index: self._save_setting("calculator_mode", str(index)))
        layout.addWidget(self.calculator_modes)
        return tab

    def _mode_intro(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setWordWrap(True)
        label.setObjectName("modeIntro")
        return label

    def _medium_combo(self) -> QComboBox:
        labels = [("Повітря" if self.language == "uk" else "Air", "air"),
                  ("Вода" if self.language == "uk" else "Water", "water")]
        combo = self._combo("medium", labels, "medium")
        combo.currentIndexChanged.connect(lambda _index, source=combo: self._medium_changed(str(source.currentData())))
        return combo

    def _add_core_fields(self, form: QFormLayout, include_battery: bool = True) -> None:
        configuration = self._combo("configuration_mode", [
            (self.tr("database_point_mode"), "database"),
            (self.tr("custom_mode"), "custom")], "configuration_mode")
        form.addRow(self.tr("configuration_mode"), configuration)
        model = self._model_selector()
        model_label = QLabel(self.tr("model"))
        self._register_tip(model_label, "model")
        form.addRow(model_label, model)
        reference_point = self._reference_point_combo()
        reference_label = QLabel(self.tr("reference_point"))
        self._register_tip(reference_label, "reference_point")
        form.addRow(reference_label, reference_point)
        source_status = QLabel()
        source_status.setWordWrap(True)
        source_status.setObjectName("modeIntro")
        source_status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.source_preset_labels.append(source_status)
        form.addRow(source_status)
        medium = self._medium_combo()
        medium_label = QLabel(self.tr("medium"))
        self._register_tip(medium_label, "medium")
        form.addRow(medium_label, medium)
        self._field(form, self.tr("voltage"), "voltage", "V", "voltage")
        self._field(form, self.tr("throttle"), "throttle", "%", "throttle")
        self._field(form, self.tr("kv"), "kv", "RPM/V", "kv")
        self._field(form, self.tr("speed"), "speed", unit_label("speed", self.unit_system), "speed")
        self._field(form, self.tr("mass"), "mass", unit_label("mass_kg", self.unit_system), "mass")
        self._field(form, self.tr("motors"), "motors", "", "motors")
        if include_battery:
            self._field(form, self.tr("esc"), "esc", "A", "esc")
            battery_type = self._combo("battery_type", ["LiPo", "Li-ion", "LiFePO4"], "battery_type")
            form.addRow(self.tr("battery_type"), battery_type)
            battery_s = self._combo("battery_s", [(f"{cells}S", str(cells)) for cells in range(2, 13)], "battery_s")
            form.addRow(self.tr("battery_s"), battery_s)
            self._field(form, self.tr("capacity"), "capacity", "Ah", "capacity")
            self._field(form, self.tr("c_rating"), "c_rating", "C", "c_rating")

    def _result_card_grid(self, cards: tuple[tuple[str, str], ...], target: dict[str, QLabel], columns: int = 3) -> QGroupBox:
        group = QGroupBox(self.tr("results"))
        grid = QGridLayout(group)
        for i, (key, title_key) in enumerate(cards):
            card = QFrame(objectName="card")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(8, 6, 8, 6)
            title = QLabel(self.tr(title_key), objectName="cardTitle")
            title.setWordWrap(True)
            title.setMinimumHeight(26)
            card_layout.addWidget(title)
            value = QLabel("—", objectName="cardValue")
            value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            value.setMinimumHeight(25)
            value.setWordWrap(True)
            card_layout.addWidget(value)
            target[key] = value
            grid.addWidget(card, i // columns, i % columns)
        return group

    def _context_help_group(self) -> QGroupBox:
        group = QGroupBox(self.tr("help_panel"))
        layout = QVBoxLayout(group)
        label = QLabel(self.tr("hover_help"))
        label.setWordWrap(True)
        label.setMinimumHeight(76)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.context_help_labels.append(label)
        layout.addWidget(label)
        return group

    def _source_math_group(self, table_name: str = "referenceTable") -> QGroupBox:
        group = QGroupBox(self.tr("source_vs_math"))
        layout = QVBoxLayout(group)
        note = QLabel(self.tr("source_math_note"))
        note.setWordWrap(True)
        layout.addWidget(note)
        table = self._table([self.tr("method"), "RPM", "J", "Ct", "Cp", "η / FOM",
                             self.tr("thrust_per_motor"), self.tr("prop_power_per_motor"), self.tr("source")],
                            table_name)
        table.setRowCount(2)
        table.setMaximumHeight(116)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(8, QHeaderView.ResizeMode.Stretch)
        self.reference_tables.append(table)
        layout.addWidget(table)
        explanation = QLabel()
        explanation.setWordWrap(True)
        explanation.setObjectName("modeIntro")
        explanation.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.comparison_explain_labels.append(explanation)
        layout.addWidget(explanation)
        return group

    def _simple_calculator_page(self) -> QScrollArea:
        content = QWidget()
        outer = QHBoxLayout(content)
        self.simple_calculator_layout = outer
        outer.setContentsMargins(6, 4, 6, 8)
        left = QWidget()
        left.setMaximumWidth(520)
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(self._mode_intro(self.tr("simple_intro")))
        basic = QGroupBox(self.tr("basic"))
        form = QFormLayout(basic)
        self._add_core_fields(form, include_battery=True)
        left_layout.addWidget(basic)
        actions = QHBoxLayout()
        calculate = QPushButton(self.tr("calculate"), objectName="primary")
        calculate.clicked.connect(self.calculate)
        add = QPushButton(self.tr("add_compare"))
        add.clicked.connect(self.add_current_to_compare)
        pdf = QPushButton(
            "Експорт PDF-звіту" if self.language == "uk" else "Export PDF report")
        pdf.setObjectName("exportCalcPdf")
        pdf.setAccessibleName("exportCalcPdf")
        pdf.clicked.connect(self.export_calc_pdf_report)
        actions.addWidget(calculate, 2)
        actions.addWidget(add, 1)
        actions.addWidget(pdf, 1)
        left_layout.addLayout(actions)
        left_layout.addWidget(self._context_help_group())
        left_layout.addStretch(1)
        outer.addWidget(left)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        self.simple_result_labels: dict[str, QLabel] = {}
        simple_cards = (("thrust", "thrust_card"), ("current", "total_current_card"), ("power", "total_power_card"),
                        ("rpm", "rpm_card"), ("tw", "tw_card"), ("runtime", "runtime_card"))
        right_layout.addWidget(self._result_card_grid(simple_cards, self.simple_result_labels))
        right_layout.addWidget(self._source_math_group("referenceTableSimple"))
        note = QLabel(self.tr("simple_summary"))
        note.setWordWrap(True)
        right_layout.addWidget(note)
        charts = QGroupBox(self.tr("load_graphs"))
        chart_layout = QHBoxLayout(charts)
        self.simple_thrust_chart = LoadChart()
        self.simple_current_chart = LoadChart()
        chart_layout.addWidget(self.simple_thrust_chart)
        chart_layout.addWidget(self.simple_current_chart)
        right_layout.addWidget(charts, 1)
        self.simple_warning_text = QPlainTextEdit()
        self.simple_warning_text.setReadOnly(True)
        self.simple_warning_text.setMaximumHeight(90)
        right_layout.addWidget(self.simple_warning_text)
        outer.addWidget(right, 1)
        return self._scroll(content)

    def _engineering_calculator_page(self) -> QScrollArea:
        content = QWidget()
        outer = QHBoxLayout(content)
        self.engineering_calculator_layout = outer
        outer.setContentsMargins(6, 4, 6, 8)
        left = QWidget()
        left.setMaximumWidth(530)
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(self._mode_intro(self.tr("engineering_intro")))
        basic = QGroupBox(self.tr("basic"))
        form = QFormLayout(basic)
        self._add_core_fields(form, include_battery=True)
        left_layout.addWidget(basic)
        advanced = QGroupBox(self.tr("advanced"))
        adv = QFormLayout(advanced)
        self._field(adv, self.tr("rm"), "rm", "Ω", "rm")
        self._field(adv, self.tr("i0"), "i0", "A", "i0")
        self._field(adv, self.tr("motor_max_current"), "motor_max_current", "A", "motor_max_current")
        self._field(adv, self.tr("motor_max_power"), "motor_max_power", "W", "motor_max_power")
        self._field(adv, self.tr("density"), "density", "kg/m³", "density")
        left_layout.addWidget(advanced)
        actions = QHBoxLayout()
        calculate = QPushButton(self.tr("calculate"), objectName="primary")
        calculate.clicked.connect(self.calculate)
        add = QPushButton(self.tr("add_compare"))
        add.clicked.connect(self.add_current_to_compare)
        pdf = QPushButton(
            "Експорт PDF-звіту" if self.language == "uk" else "Export PDF report")
        pdf.setObjectName("exportCalcPdf")
        pdf.setAccessibleName("exportCalcPdf")
        pdf.clicked.connect(self.export_calc_pdf_report)
        actions.addWidget(calculate, 2)
        actions.addWidget(add, 1)
        actions.addWidget(pdf, 1)
        left_layout.addLayout(actions)
        left_layout.addWidget(self._context_help_group())
        left_layout.addStretch(1)
        outer.addWidget(left)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        self.result_labels = {}
        cards = (("thrust", "thrust_card"), ("current", "total_current_card"), ("power", "total_power_card"),
                 ("rpm", "rpm_card"), ("tw", "tw_card"), ("runtime", "runtime_card"),
                 ("esc_margin", "esc_margin_card"), ("motor_margin", "motor_margin_card"),
                 ("battery_margin", "battery_margin_card"), ("structural", "structural_card"),
                 ("confidence", "confidence_card"), ("evidence", "evidence_card"))
        right_layout.addWidget(self._result_card_grid(cards, self.result_labels))
        right_layout.addWidget(self._source_math_group("referenceTableEngineering"))

        efficiency = QGroupBox(self.tr("efficiency"))
        eff = QGridLayout(efficiency)
        eff.addWidget(QLabel(self.tr("aero_eff")), 0, 0)
        self.aero_bar = QProgressBar()
        self.aero_bar.setRange(0, 1000)
        eff.addWidget(self.aero_bar, 0, 1)
        eff.addWidget(QLabel(self.tr("system_eff")), 1, 0)
        self.system_bar = QProgressBar()
        self.system_bar.setRange(0, 1000)
        eff.addWidget(self.system_bar, 1, 1)
        eff.addWidget(QLabel(self.tr("optimum")), 2, 0, Qt.AlignmentFlag.AlignTop)
        self.optimum_label = QLabel("—")
        self.optimum_label.setWordWrap(True)
        self.optimum_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        eff.addWidget(self.optimum_label, 2, 1)
        right_layout.addWidget(efficiency)

        chart_group = QGroupBox(self.tr("load_graphs"))
        graph_layout = QVBoxLayout(chart_group)
        graph_note = QLabel(self.tr("graph_note"))
        graph_note.setWordWrap(True)
        graph_layout.addWidget(graph_note)
        self.graph_tabs = QTabWidget()
        loads_page = QWidget()
        loads_layout = QHBoxLayout(loads_page)
        self.thrust_chart = LoadChart()
        self.current_chart = LoadChart()
        loads_layout.addWidget(self.thrust_chart)
        loads_layout.addWidget(self.current_chart)
        limits_page = QWidget()
        limits_layout = QHBoxLayout(limits_page)
        self.power_chart = LoadChart()
        self.rpm_chart = LoadChart()
        limits_layout.addWidget(self.power_chart)
        limits_layout.addWidget(self.rpm_chart)
        efficiency_page = QWidget()
        efficiency_layout = QVBoxLayout(efficiency_page)
        self.efficiency_chart = LoadChart()
        efficiency_layout.addWidget(self.efficiency_chart)
        self.graph_tabs.addTab(loads_page, f"{self.tr('thrust_card')} + {self.tr('current_card')}")
        self.graph_tabs.addTab(limits_page, f"{self.tr('power_card')} + RPM")
        self.graph_tabs.addTab(efficiency_page, self.tr("efficiency"))
        graph_layout.addWidget(self.graph_tabs)
        right_layout.addWidget(chart_group, 1)

        warning_box = QGroupBox(self.tr("warnings"))
        warning_layout = QVBoxLayout(warning_box)
        self.warning_text = QPlainTextEdit()
        self.warning_text.setReadOnly(True)
        self.warning_text.setMaximumHeight(110)
        warning_layout.addWidget(self.warning_text)
        right_layout.addWidget(warning_box)
        outer.addWidget(right, 1)
        return self._scroll(content)

    @staticmethod
    def _optional(value: str) -> float | None:
        return None if not value.strip() else float(value)

    def _medium_changed(self, medium: str) -> None:
        density_widgets = self.edit_widgets.get("density", [])
        if not density_widgets:
            return
        try:
            current = float(self.state.get("density", density_widgets[-1].text()))
        except ValueError:
            return
        if medium == "water" and abs(current - 1.225) < 0.01:
            value = "997"
        elif medium == "air" and abs(current - 997) < 5:
            value = "1.225"
        else:
            return
        self.state["density"] = value
        for widget in density_widgets:
            widget.setText(value)

    def _inputs(self) -> CalculationInputs:
        self._snapshot()
        errors: list[tuple[str, str]] = []

        def parse_float(key: str) -> float | None:
            raw = str(self.state.get(key, ""))
            try:
                return float(raw)
            except (ValueError, TypeError):
                errors.append((key, raw))
                return None

        def parse_optional(key: str) -> float | None:
            raw = str(self.state.get(key, ""))
            if not raw.strip():
                return None
            try:
                return float(raw)
            except (ValueError, TypeError):
                errors.append((key, raw))
                return None

        def parse_int(key: str) -> int | None:
            raw = str(self.state.get(key, ""))
            try:
                return int(float(raw))
            except (ValueError, TypeError):
                errors.append((key, raw))
                return None

        voltage = parse_float("voltage")
        throttle = parse_float("throttle")
        kv = parse_float("kv")
        esc = parse_float("esc")
        capacity = parse_float("capacity")
        c_rating = parse_float("c_rating")
        density = parse_float("density")
        speed_raw = parse_float("speed")
        mass_raw = parse_float("mass")
        motors = parse_int("motors")
        battery_s = parse_int("battery_s")
        rm = parse_optional("rm")
        i0 = parse_optional("i0")
        motor_max_current = parse_optional("motor_max_current")
        motor_max_power = parse_optional("motor_max_power")
        rpm_override: float | None = None
        source_point_id: int | None = None
        if self.state.get("configuration_mode") == "database":
            ref_rpm_raw = str(self.state.get("reference_rpm", ""))
            if ref_rpm_raw.strip():
                try:
                    rpm_override = float(ref_rpm_raw)
                except (ValueError, TypeError):
                    errors.append(("reference_rpm", ref_rpm_raw))
            ref_pid_raw = str(self.state.get("reference_point_id", ""))
            if ref_pid_raw.strip():
                try:
                    source_point_id = int(ref_pid_raw)
                except (ValueError, TypeError):
                    errors.append(("reference_point_id", ref_pid_raw))
        if errors:
            raise CalcInputErrors(errors)
        assert voltage is not None and throttle is not None and kv is not None
        assert esc is not None and capacity is not None and c_rating is not None
        assert density is not None and speed_raw is not None and mass_raw is not None
        assert motors is not None and battery_s is not None
        return CalculationInputs(
            model_id=str(self.selected_model_id or self.model_combo.currentData() or self.model_combo.currentText().strip()),
            voltage_v=voltage, throttle=throttle / 100,
            motor_kv=kv, motor_resistance_ohm=rm,
            motor_i0_a=i0,
            motor_max_current_a=motor_max_current,
            motor_max_power_w=motor_max_power,
            esc_current_a=esc, battery_capacity_ah=capacity,
            battery_c_rating=c_rating, battery_s=battery_s,
            battery_type=self.state.get("battery_type", "LiPo"),
            speed_m_s=float(to_si(speed_raw, "speed", self.unit_system)),
            mass_kg=float(to_si(mass_raw, "mass_kg", self.unit_system)),
            motor_count=motors, density_kg_m3=density,
            medium=self.state["medium"],
            rpm_override=rpm_override,
            source_point_id=source_point_id)

    def _clear_calc_input_error(self) -> None:
        originals = getattr(self, "_calc_error_originals", {})
        for widget_id, (widget_ref, original) in list(originals.items()):
            try:
                widget_ref.setStyleSheet(original)
            except RuntimeError:
                pass
        self._calc_error_originals = {}
        label = getattr(self, "calc_error_label", None)
        if label is not None:
            label.clear()
            label.setVisible(False)

    def _show_calc_input_error(self, field_errors: list[tuple[str, str]]) -> None:
        self._clear_calc_input_error()
        parts = []
        for key, raw in field_errors:
            label = self.tr(key)
            parts.append(f"{label} ({key}): {raw!r}")
        message = f"{self.tr('calculation_error')}: " + "; ".join(parts)
        label_widget = getattr(self, "calc_error_label", None)
        if label_widget is not None:
            label_widget.setText(message)
            label_widget.setVisible(True)
        first_key = field_errors[0][0]
        widgets: list = []
        widgets.extend(self.edit_widgets.get(first_key, []))
        widgets.extend(self.combo_widgets.get(first_key, []))
        canonical = self.edits.get(first_key) or self.combos.get(first_key)
        if canonical is None and first_key == "reference_point_id":
            combos = getattr(self, "reference_point_combos", [])
            canonical = combos[0] if combos else None
        if canonical is not None and canonical not in widgets:
            widgets.append(canonical)
        for widget in widgets:
            try:
                if id(widget) not in self._calc_error_originals:
                    self._calc_error_originals[id(widget)] = (widget, widget.styleSheet())
                original = self._calc_error_originals[id(widget)][1]
                widget.setStyleSheet(original + "\nQLineEdit{border:1px solid #E5484D;}\nQComboBox{border:1px solid #E5484D;}")
            except RuntimeError:
                pass
        if canonical is not None:
            try:
                canonical.setFocus(Qt.FocusReason.OtherFocusReason)
            except RuntimeError:
                pass

    def calculate(self) -> None:
        self._clear_calc_input_error()
        try:
            inputs = self._inputs()
        except CalcInputErrors as exc:
            self._show_calc_input_error(exc.field_errors)
            return
        try:
            result = self.calculator.calculate(inputs)
        except Exception as exc:
            QMessageBox.critical(self, APP_NAME, f"{self.tr('calculation_error')}:\n{self.tr('details')}: {exc}")
            return
        self.current_inputs, self.current_result = inputs, result
        self.selected_model_id = inputs.model_id
        self._display_result(result, inputs)
        self._refresh_trace()
        self.statusBar().showMessage(f"LIVE · {inputs.model_id} · RPM {result.point.rpm:,.0f} · {self._evidence_name(result.point.evidence)}", 8000)

    def _display_result(self, result: CalculationResult, inputs: CalculationInputs) -> None:
        if not self.result_labels:
            return
        p = result.point
        values = {
            "thrust": self._format_force(result.total_thrust_n),
            "current": f"{p.current_a * inputs.motor_count:,.1f} A",
            "power": self._format_power(p.electrical_power_w * inputs.motor_count),
            "rpm": f"{p.rpm:,.0f}", "tw": f"{result.thrust_to_weight:.2f}",
            "runtime": "—" if math.isnan(result.runtime_min) else f"{result.runtime_min:.1f} min", "esc_margin": f"{result.esc_margin_percent:+.0f}%",
            "battery_margin": f"{result.battery_margin_percent:+.0f}%",
            "structural": "n/a" if result.structural_rpm is None else f"{p.rpm:,.0f} / {result.structural_rpm:,.0f}",
            "confidence": f"{p.confidence * 100:.0f}%", "evidence": f"{self._evidence_name(p.evidence)} · {p.source_type}",
        }
        motor_margin = result.motor_current_margin_percent if result.motor_current_margin_percent is not None else result.motor_power_margin_percent
        values["motor_margin"] = "n/a" if motor_margin is None else f"{motor_margin:+.0f}%"
        for key, value in values.items():
            self.result_labels[key].setText(value)
            self.result_labels[key].setStyleSheet("color:#FF7F71" if key.endswith("margin") and value.startswith("-") else "")
            if key in self.simple_result_labels:
                self.simple_result_labels[key].setText(value)
        self.aero_bar.setValue(round(p.aero_efficiency * 1000))
        self.aero_bar.setFormat(f"{p.aero_efficiency * 100:.1f}%")
        self.system_bar.setValue(round(p.system_efficiency * 1000))
        self.system_bar.setFormat(f"{p.system_efficiency * 100:.1f}%")
        if result.optimum:
            opt = result.optimum
            delta = (p.system_efficiency - opt.system_efficiency) * 100
            self.optimum_label.setText(
                f"RPM {opt.rpm:,.0f} · {result.recommended_throttle * 100:.0f}% · {result.recommended_voltage_v:.1f} V · {result.recommended_s}S\n"
                f"ηsystem {opt.system_efficiency * 100:.1f}% · thrust {from_si(opt.thrust_n * inputs.motor_count, 'force', self.unit_system):.3g} "
                f"{unit_label('force', self.unit_system)} · current {opt.current_a * inputs.motor_count:.2f} A · Δ {delta:+.1f} pp")
        else:
            self.optimum_label.setText(self.tr("no_optimum"))
        warnings = [self._localize_warning(item) for item in result.warnings] or [self.tr("no_warnings")]
        if result.missing_parameters:
            warnings = [self.tr("simplified")] + warnings
        self.warning_text.setPlainText("\n".join("• " + item for item in warnings))
        self.simple_warning_text.setPlainText("\n".join("• " + item for item in warnings))
        self._display_source_math_comparison(result, inputs)
        self._refresh_load_charts(inputs)

    def _format_power(self, value_w: float) -> str:
        if self.unit_system == "Imperial":
            return f"{from_si(value_w, 'power', self.unit_system):,.3f} {unit_label('power', self.unit_system)}"
        if abs(value_w) >= 1000:
            return f"{value_w / 1000:,.2f} kW"
        if abs(value_w) >= 100:
            return f"{value_w:,.1f} W"
        return f"{value_w:,.2f} W"

    def _format_force(self, value_n: float) -> str:
        value = from_si(value_n, "force", self.unit_system)
        return f"{value:,.2f} {unit_label('force', self.unit_system)}"

    def _display_source_math_comparison(self, result: CalculationResult, inputs: CalculationInputs) -> None:
        raw = self.repository.nearest_raw_point(inputs.model_id, result.point.rpm, result.point.j,
                                                result.point.evidence)

        def number(value: Any, digits: int = 5) -> str:
            if value is None:
                return "n/a"
            numeric = float(value)
            if abs(numeric) >= 1000:
                return f"{numeric:,.0f}"
            return f"{numeric:.{digits}f}".rstrip("0").rstrip(".")

        if raw is None:
            raw_values = [self.tr("raw_database"), "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a"]
        else:
            raw_thrust = "n/a" if raw["thrust_n"] is None else self._format_force(float(raw["thrust_n"]))
            raw_power = "n/a" if raw["power_w"] is None else self._format_power(float(raw["power_w"]))
            source = f"{raw['relative_path']}:{raw['source_row'] or '-'}"
            raw_efficiency = "n/a" if raw["efficiency"] is None or (
                bool(raw["is_static"]) and abs(float(raw["efficiency"] or 0)) < 1e-12) else number(raw["efficiency"])
            raw_values = [self.tr("raw_database"), number(raw["rpm"], 8), number(raw["advance_ratio_j"]),
                          number(raw["ct"]), number(raw["cp"]), raw_efficiency,
                          raw_thrust, raw_power, source]
        p = result.point
        math_values = [self.tr("math_result"), f"{p.rpm:.8g}", f"{p.j:.5g}", f"{p.ct:.5g}", f"{p.cp:.5g}",
                       f"{p.aero_efficiency:.5g}",
                       self._format_force(p.thrust_n), self._format_power(p.prop_power_w),
                       "Ct/Cp interpolation + equations" if self.language == "en" else "інтерполяція Ct/Cp + формули"]
        for table in self.reference_tables:
            for row_index, values in enumerate((raw_values, math_values)):
                for column, value in enumerate(values):
                    item = QTableWidgetItem(str(value))
                    item.setBackground(QColor("#17313A" if row_index == 0 else "#173B35"))
                    table.setItem(row_index, column, item)
        if raw is None:
            explanation = self.tr("comparison_no_raw")
        else:
            raw_rpm = float(raw["rpm"] or 0)
            rpm_ratio = p.rpm / raw_rpm if raw_rpm else 0.0
            cubic_factor = rpm_ratio ** 3
            raw_power_w = float(raw["power_w"] or 0)
            delta = ((p.prop_power_w - raw_power_w) / raw_power_w * 100.0) if raw_power_w else 0.0
            explanation = self.tr("comparison_explanation").format(
                raw_rpm=f"{raw_rpm:,.0f}", math_rpm=f"{p.rpm:,.0f}", ratio=f"{rpm_ratio:.3f}",
                factor=f"{cubic_factor:.2f}", raw_power=self._format_power(raw_power_w),
                math_power=self._format_power(p.prop_power_w), delta=f"{delta:+.1f}",
                total_power=self._format_power(p.electrical_power_w * inputs.motor_count), motors=inputs.motor_count)
        for label in self.comparison_explain_labels:
            label.setText(explanation)

    def _evidence_name(self, value: str) -> str:
        if self.language == "en":
            return value
        return {"experiment": "експеримент", "prediction": "прогноз", "cfd": "CFD",
                "numerical": "чисельна модель", "catalog": "каталог", "none": "немає даних"}.get(value, value)

    def _localize_warning(self, warning: str) -> str:
        if self.language == "en":
            return warning
        exact = {
            "Operating point is outside a measured/predicted table range; nearest-edge extrapolation used":
                "Робоча точка поза діапазоном таблиці; використано найближчий край з ознакою екстраполяції.",
            "ESC current limit exceeded": "Перевищено допустимий струм ESC.",
            "Battery C-rating current limit exceeded": "Перевищено струмовий ліміт батареї за C-рейтингом.",
            "Structural RPM limit exceeded": "Перевищено структурний ліміт RPM пропелера.",
            "Water mode uses air-derived dimensionless coefficients; cavitation is not modeled and bench validation is mandatory":
                "Водний режим використовує безрозмірні коефіцієнти з повітряних даних; кавітація не моделюється, стендова перевірка обов'язкова.",
            "Non-positive mass_kg; T/W uses a guarded minimum and is not meaningful":
                "Непозитивна маса; T/W обчислено з мінімальним обмеженням і не має сенсу.",
            "Non-positive density_kg_m3; thrust/power scale with density and are not meaningful":
                "Непозитивна густина середовища; тяга і потужність масштабуються з густиною й не мають сенсу.",
            "Negative battery capacity/C-rating; runtime and margins are not meaningful":
                "Від'ємна ємність батареї або C-рейтинг; час роботи й запаси не мають сенсу.",
            "Negative motor_resistance_ohm; result is not meaningful":
                "Від'ємний опір обмотки мотора; результат не має сенсу.",
            "Negative motor_max_current_a; margin is not meaningful":
                "Від'ємний максимальний струм мотора; запас не має сенсу.",
            "Negative motor_max_power_w; margin is not meaningful":
                "Від'ємна максимальна потужність мотора; запас не має сенсу.",
            "Non-positive motor_count treated as 1":
                "Непозитивна кількість моторів; використано 1.",
            "No valid operating point; runtime is not meaningful":
                "Немає дійсної робочої точки; час роботи не має сенсу.",
        }
        if warning in exact:
            return exact[warning]
        if warning.startswith("Non-finite input "):
            name = warning[len("Non-finite input "):].split(";", 1)[0].strip()
            ua_names = {
                "mass_kg": "маса",
                "density_kg_m3": "густина середовища",
                "voltage_v": "напруга",
                "throttle": "газ",
                "motor_kv": "KV мотора",
                "battery_capacity_ah": "ємність батареї",
                "battery_c_rating": "C-рейтинг батареї",
                "esc_current_a": "струм ESC",
                "speed_m_s": "швидкість потоку",
                "motor_resistance_ohm": "опір обмотки мотора (Rm)",
                "motor_max_current_a": "максимальний струм мотора",
                "motor_max_power_w": "максимальна потужність мотора",
            }
            ua_name = ua_names.get(name, name)
            return f"Некоректне (нескінченне або нечислове) вхідне значення: {ua_name}; результат не має сенсу."
        if warning.startswith("Simplified-model estimate: missing "):
            missing = warning.split("missing ", 1)[1]
            missing = missing.replace("Rm / motor winding resistance", "Rm / опір обмотки мотора")
            missing = missing.replace("I0 / no-load current", "I0 / струм холостого ходу")
            return "Оцінка за спрощеною моделлю: відсутні " + missing
        if warning.startswith("Battery voltage mismatch: "):
            return "Невідповідність батареї: " + warning.split(": ", 1)[1].replace(
                " entered, but ", " введено, але ").replace(" is about ", " має приблизно ").replace(
                    " nominal", " номінально")
        return warning

    def _refresh_load_charts(self, inputs: CalculationInputs) -> None:
        points: list[tuple[float, Any]] = []
        for step in range(1, 11):
            throttle = step / 10.0
            point = self.calculator.operating_point(inputs, throttle=throttle)
            if point is not None:
                points.append((throttle * 100.0, point))
        if not points:
            return
        marker = inputs.throttle * 100.0
        thrust_points = [(x, from_si(p.thrust_n * inputs.motor_count, "force", self.unit_system)) for x, p in points]
        current_points = [(x, p.current_a * inputs.motor_count) for x, p in points]
        power_points = [(x, from_si(p.electrical_power_w * inputs.motor_count, "power", self.unit_system)) for x, p in points]
        rpm_points = [(x, p.rpm) for x, p in points]
        aero_points = [(x, p.aero_efficiency * 100.0) for x, p in points]
        system_points = [(x, p.system_efficiency * 100.0) for x, p in points]
        curve = self.tr("current_point")
        thrust_series = [ChartSeries(curve, "#36D2C0", thrust_points)]
        current_series = [ChartSeries(curve, "#61A9FF", current_points)]
        power_series = [ChartSeries(curve, "#C792EA", power_points)]
        rpm_series = [ChartSeries(curve, "#F4C95D", rpm_points)]
        current_limits = [
            (self.tr("esc_limit"), inputs.esc_current_a * inputs.motor_count, "#FF7F71"),
            (self.tr("battery_limit"), inputs.battery_capacity_ah * inputs.battery_c_rating, "#F6A55A"),
        ]
        if inputs.motor_max_current_a is not None:
            current_limits.append((self.tr("motor_limit"), inputs.motor_max_current_a * inputs.motor_count, "#E36DE0"))
        power_limits: list[tuple[str, float, str]] = []
        if inputs.motor_max_power_w is not None:
            power_limits.append((self.tr("motor_limit"), from_si(inputs.motor_max_power_w * inputs.motor_count,
                                                                  "power", self.unit_system), "#FF7F71"))
        rpm_row = self.repository.structural_rpm(inputs.model_id)
        rpm_limits = []
        if rpm_row and rpm_row["max_rpm"]:
            rpm_limits.append((self.tr("structural_limit"), float(rpm_row["max_rpm"]), "#FF7F71"))
        thrust_unit = unit_label("force", self.unit_system)
        power_unit = unit_label("power", self.unit_system)
        for chart in (self.simple_thrust_chart, self.thrust_chart):
            chart.set_chart(self.tr("chart_thrust"), self.tr("throttle_axis"),
                            f"{self.tr('thrust_axis')}, {thrust_unit}", thrust_series, marker_x=marker)
        for chart in (self.simple_current_chart, self.current_chart):
            chart.set_chart(self.tr("chart_current"), self.tr("throttle_axis"), self.tr("current_axis"),
                            current_series, current_limits, marker)
        self.power_chart.set_chart(self.tr("chart_power"), self.tr("throttle_axis"),
                                   f"{self.tr('power_axis')}, {power_unit}", power_series, power_limits, marker)
        self.rpm_chart.set_chart(self.tr("chart_rpm"), self.tr("throttle_axis"), self.tr("rpm_axis"),
                                 rpm_series, rpm_limits, marker)
        self.efficiency_chart.set_chart(
            self.tr("chart_efficiency"), self.tr("throttle_axis"), self.tr("efficiency_axis"),
            [ChartSeries(self.tr("aerodynamic"), "#36D2C0", aero_points),
             ChartSeries(self.tr("powertrain"), "#C792EA", system_points)], marker_x=marker)

    @staticmethod
    def _table(headers: list[str], name: str = "") -> QTableWidget:
        table = QTableWidget(0, len(headers))
        if name:
            table.setObjectName(name)
            table.setAccessibleName(name)
        table.setHorizontalHeaderLabels(headers)
        table.setAlternatingRowColors(True)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.verticalHeader().setVisible(False)
        return table

    @staticmethod
    def _fill_row(table: QTableWidget, row: int, values: list[Any], data: Any = None) -> None:
        table.insertRow(row)
        for column, value in enumerate(values):
            item = QTableWidgetItem("" if value is None else str(value))
            if column == 0 and data is not None:
                item.setData(Qt.ItemDataRole.UserRole, data)
            table.setItem(row, column, item)

    def _stat_card(self, title: str, value: int) -> QWidget:
        card = QFrame(objectName="card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(9, 5, 9, 5)
        layout.addWidget(QLabel(title, objectName="cardTitle"))
        layout.addWidget(QLabel(f"{value:,}", objectName="cardValue"))
        return card

    def _database_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        summary = self.repository.summary()
        cards = QHBoxLayout()
        for key, title_key in (("models", "models"), ("characteristics", "characteristics"),
                               ("sources", "sources"), ("models_with_experiments", "real_tests"),
                               ("prediction_only_models", "prediction_only")):
            cards.addWidget(self._stat_card(self.tr(title_key), int(summary.get(key, 0))))
        layout.addLayout(cards)
        controls = QHBoxLayout()
        self.db_search = QLineEdit()
        self.db_search.setPlaceholderText(self.tr("model_search_placeholder"))
        self._register_tip(self.db_search, "model")
        self.db_search.returnPressed.connect(self._refresh_models)
        controls.addWidget(self.db_search, 1)
        search = QPushButton(self.tr("search"))
        search.clicked.connect(self._refresh_models)
        controls.addWidget(search)
        imp = QPushButton(self.tr("import"))
        imp.clicked.connect(self.import_data)
        controls.addWidget(imp)
        exp = QPushButton(self.tr("export"))
        exp.clicked.connect(self.export_db)
        controls.addWidget(exp)
        res = QPushButton(
            "Відновити базу даних…" if self.language == "uk" else "Restore database…")
        res.setObjectName("restoreDatabase")
        res.setAccessibleName("restoreDatabase")
        res.clicked.connect(self.restore_database)
        controls.addWidget(res)
        layout.addLayout(controls)
        splitter = QSplitter(Qt.Orientation.Vertical)
        self.model_table = self._table(["Model_ID", self.tr("original"), self.tr("manufacturer"), self.tr("size"),
                                        self.tr("evidence"), self.tr("points"), self.tr("geometry")],
                                       "modelTable")
        self.model_table.itemSelectionChanged.connect(self._model_selected)
        splitter.addWidget(self.model_table)
        points = QWidget()
        points_layout = QVBoxLayout(points)
        points_layout.setContentsMargins(0, 0, 0, 0)
        point_controls = QHBoxLayout()
        point_controls.addWidget(QLabel(self.tr("characteristics_title"), objectName="section"))
        self.point_filter = QLineEdit()
        self.point_filter.setPlaceholderText(self.tr("point_filter_placeholder"))
        self.point_filter.textChanged.connect(self._filter_points)
        point_controls.addWidget(self.point_filter, 1)
        points_layout.addLayout(point_controls)
        self.point_table = self._table(["RPM", "J", "Ct", "Cp", "η", f"{self.tr('thrust_card')} N",
                                        f"{self.tr('power_card')} W", self.tr("class"), self.tr("source_file")],
                                       "pointTable")
        points_layout.addWidget(self.point_table)
        splitter.addWidget(points)
        splitter.setSizes([330, 240])
        layout.addWidget(splitter, 1)
        self._point_rows: list[Any] = []
        self._refresh_models()
        return tab

    def _refresh_models(self) -> None:
        if not hasattr(self, "model_table"):
            return
        self.model_table.setRowCount(0)
        for i, row in enumerate(self.repository.search_models(self.db_search.text(), limit=1000)):
            diameter = row["diameter_m"] / 0.0254 if row["diameter_m"] else None
            pitch = row["pitch_m"] / 0.0254 if row["pitch_m"] else None
            size = f"{diameter:.2f}×{pitch:.2f} in" if diameter and pitch else "?"
            evidence = "EXP" if row["has_experiment"] else ("PRED" if row["has_prediction"] else ("CFD" if row["has_cfd"] else "CAT"))
            self._fill_row(self.model_table, i, [row["model_id"], row["original_name"], row["manufacturer"],
                                                  size, evidence, row["point_count"], row["geometry_count"]], row["model_id"])
        self.model_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in range(1, self.model_table.columnCount()):
            self.model_table.horizontalHeader().setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        if self.model_table.rowCount():
            self.model_table.setCurrentCell(0, 0)

    def _model_selected(self) -> None:
        row_index = self.model_table.currentRow()
        if row_index < 0:
            return
        item = self.model_table.item(row_index, 0)
        model_id = item.data(Qt.ItemDataRole.UserRole) or item.text()
        self._point_rows = self.repository.model_points(str(model_id), limit=10000)
        self._filter_points()

    def _filter_points(self) -> None:
        if not hasattr(self, "point_table"):
            return
        term = self.point_filter.text().strip().lower()
        visible = [row for row in self._point_rows
                   if not term or term in " ".join("" if value is None else str(value) for value in row).lower()]
        self.point_table.setRowCount(0)
        for i, row in enumerate(visible[:5000]):
            def fmt(name: str, digits: int = 6) -> str:
                return "" if row[name] is None else f"{row[name]:.{digits}g}"
            self._fill_row(self.point_table, i, [fmt("rpm", 8), fmt("advance_ratio_j"), fmt("ct"), fmt("cp"),
                                                  fmt("efficiency"), fmt("thrust_n"), fmt("power_w"),
                                                  self._evidence_name(row["evidence_class"]), row["relative_path"]])
        self.point_table.horizontalHeader().setSectionResizeMode(8, QHeaderView.ResizeMode.Stretch)

    def import_data(self) -> None:
        source, _ = QFileDialog.getOpenFileName(
            self, self.tr("import"), "", "Supported (*.db *.zip *.zipx *.xlsx *.csv *.dat *.pe0);;All (*.*)")
        if not source:
            return
        try:
            service = RuntimeImportService(self.repository.connection, self.database_path, self.paths["backups"])
            report = service.import_path(source)
            self.repository.clear_caches()
            QMessageBox.information(self, APP_NAME, json.dumps(report, ensure_ascii=False, indent=2))
            self._snapshot()
            self._build_ui()
        except Exception as exc:
            QMessageBox.critical(self, APP_NAME, f"{self.tr('import_failed')}:\n{self.tr('details')}: {exc}")

    def export_db(self) -> None:
        target, _ = QFileDialog.getSaveFileName(self, self.tr("export"), "propellers.db", "SQLite (*.db)")
        if target:
            export_database(self.repository.connection, Path(target))
            QMessageBox.information(self, APP_NAME, f"{self.tr('exported')}:\n{target}")

    def _remove_sidecar_journals(self) -> None:
        for suffix in (".db-wal", ".db-shm", "-wal", "-shm"):
            sidecar = self.database_path.parent / (self.database_path.name + suffix)
            try:
                if sidecar.exists():
                    sidecar.unlink()
            except OSError:
                pass

    def _safety_backup_before_restore(self) -> Path:
        """Timestamped safety copy of the working DB (restore counterpart of import backup)."""
        backups = self.paths["backups"]
        backups.mkdir(parents=True, exist_ok=True)
        target = backups / (
            f"propellers-before-restore-{time.strftime('%Y%m%d-%H%M%S')}-"
            f"{time.time_ns() % 1_000_000_000:09d}-{uuid.uuid4().hex[:8]}.db")
        destination = sqlite3.connect(target)
        try:
            self.repository.connection.backup(destination)
        finally:
            destination.close()
        return target

    def restore_database_from_path(self, source: str | Path) -> Path:
        """Validate, back up, atomically replace and reopen the working database.

        Raises on any failure; the original working database is left intact
        (fail closed). Returns the safety-backup path on success.
        """
        candidate = Path(source)
        ok, message = validate_restore_candidate(candidate)
        if not ok:
            raise ValueError(message)
        if candidate.resolve() == self.database_path.resolve():
            raise ValueError("The selected database is already the active working database")
        backup = self._safety_backup_before_restore()
        try:
            self.repository.connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except Exception:  # noqa: BLE001 - best effort before close
            pass
        self.repository.close()
        try:
            self._remove_sidecar_journals()
            staging = self.database_path.with_suffix(".db.restoring")
            shutil.copy2(candidate, staging)
            os.replace(staging, self.database_path)
            self._remove_sidecar_journals()
        except Exception:
            self.repository = Repository(self.database_path)
            self.calculator = PropellerCalculator(self.repository)
            self.repository.clear_caches()
            raise
        self.repository = Repository(self.database_path)
        self.calculator = PropellerCalculator(self.repository)
        self.repository.clear_caches()
        return backup

    def restore_database(self) -> None:
        source, _ = QFileDialog.getOpenFileName(
            self,
            "Відновити базу даних…" if self.language == "uk" else "Restore database…",
            "", "SQLite (*.db)")
        if not source:
            return
        try:
            backup = self.restore_database_from_path(source)
        except Exception as exc:  # noqa: BLE001 - user-facing slot
            QMessageBox.critical(
                self, APP_NAME,
                ("Відновлення не виконано" if self.language == "uk" else "Restore failed")
                + f":\n{self.tr('details')}: {exc}")
            return
        self._snapshot()
        self._build_ui()
        QMessageBox.information(
            self, APP_NAME,
            ("Базу даних відновлено" if self.language == "uk" else "Database restored")
            + f":\n{source}\n"
            + ("Резервна копія" if self.language == "uk" else "Safety backup")
            + f":\n{backup}")

    @staticmethod
    def _report_number(value: Any, digits: int = 2) -> str:
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return "n/a"
        if math.isnan(numeric) or math.isinf(numeric):
            return "n/a"
        return f"{numeric:,.{digits}f}"

    def _report_header_html(self, title: str) -> str:
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return (
            f"<h1>{_html_escape(APP_NAME)}</h1>"
            f"<p><b>{_html_escape(title)}</b><br>"
            f"Version: {_html_escape(APP_VERSION)} · Author: {_html_escape(AUTHOR)}<br>"
            f"Generated: {_html_escape(stamp)}</p>"
        )

    def _build_calc_report_html(self) -> str:
        inputs = self.current_inputs
        result = self.current_result
        parts = [self._report_header_html(
            "Звіт розрахунку" if self.language == "uk" else "Calculation report")]
        if inputs is None or result is None:
            parts.append("<p><b>" + _html_escape(
                "Немає дійсного розрахунку; перевірте вхідні дані."
                if self.language == "uk" else
                "No valid calculation available; check the inputs.") + "</b></p>")
            parts.append("<p>Model: " + _html_escape(
                str(self.selected_model_id or "—")) + "</p>")
            return ("<html><body>" + "".join(parts) + "</body></html>")
        point = result.point
        rows = [
            ("Model", str(inputs.model_id)),
            ("Voltage (V)", self._report_number(inputs.voltage_v)),
            ("Throttle (%)", self._report_number(inputs.throttle * 100.0, 1)),
            ("Motor KV (RPM/V)", self._report_number(inputs.motor_kv, 1)),
            ("Speed (m/s)", self._report_number(inputs.speed_m_s, 3)),
            ("Mass (kg)", self._report_number(inputs.mass_kg, 3)),
            ("Motors", str(inputs.motor_count)),
            ("ESC limit (A)", self._report_number(inputs.esc_current_a, 1)),
            ("Battery", f"{_html_escape(str(inputs.battery_type))} "
                        f"{inputs.battery_s}S / {self._report_number(inputs.battery_capacity_ah)} Ah / "
                        f"{self._report_number(inputs.battery_c_rating, 0)}C"),
            ("Medium / density", f"{_html_escape(str(inputs.medium))} / "
                                 f"{self._report_number(inputs.density_kg_m3, 3)} kg/m³"),
        ]
        parts.append("<h2>" + _html_escape("Вхідні дані" if self.language == "uk" else "Inputs") + "</h2>")
        parts.append("<table border='1' cellspacing='0' cellpadding='4'>")
        for name, value in rows:
            parts.append(f"<tr><td>{_html_escape(name)}</td><td>{value}</td></tr>")
        parts.append("</table>")
        motor_margin = (result.motor_current_margin_percent
                        if result.motor_current_margin_percent is not None
                        else result.motor_power_margin_percent)
        cards = [
            ("Total thrust (N)", self._report_number(result.total_thrust_n)),
            ("Total current (A)", self._report_number(point.current_a * inputs.motor_count, 1)),
            ("Total electrical power (W)",
             self._report_number(point.electrical_power_w * inputs.motor_count, 1)),
            ("RPM", self._report_number(point.rpm, 0)),
            ("T/W", self._report_number(result.thrust_to_weight)),
            ("Runtime (min)", self._report_number(result.runtime_min, 1)),
            ("ESC margin (%)", self._report_number(result.esc_margin_percent, 0)),
            ("Motor margin (%)",
             "n/a" if motor_margin is None else self._report_number(motor_margin, 0)),
            ("Battery margin (%)", self._report_number(result.battery_margin_percent, 0)),
            ("Structural RPM",
             "n/a" if result.structural_rpm is None else self._report_number(result.structural_rpm, 0)),
            ("Confidence (%)", self._report_number(point.confidence * 100.0, 0)),
            ("Evidence", f"{_html_escape(str(point.evidence))} · {_html_escape(str(point.source_type))}"),
        ]
        parts.append("<h2>" + _html_escape("Результати" if self.language == "uk" else "Results") + "</h2>")
        parts.append("<table border='1' cellspacing='0' cellpadding='4'>")
        for name, value in cards:
            parts.append(f"<tr><td>{_html_escape(name)}</td><td>{value}</td></tr>")
        parts.append("</table>")
        try:
            raw = self.repository.nearest_raw_point(
                inputs.model_id, point.rpm, point.j, point.evidence)
        except Exception:  # noqa: BLE001 - report must not crash
            raw = None
        parts.append("<h2>" + _html_escape(
            "Джерело проти математики" if self.language == "uk" else "Source vs math") + "</h2>")
        parts.append("<table border='1' cellspacing='0' cellpadding='4'>"
                     "<tr><th>Method</th><th>RPM</th><th>J</th><th>Ct</th><th>Cp</th><th>Source</th></tr>")
        if raw is None:
            parts.append("<tr><td>Source row</td><td colspan='5'>n/a</td></tr>")
        else:
            try:
                source = f"{raw['relative_path']}:{raw['source_row'] or '-'}"
            except Exception:  # noqa: BLE001 - row shape varies
                source = "n/a"
            parts.append(
                "<tr><td>Source row</td>"
                f"<td>{self._report_number(raw['rpm'], 0)}</td>"
                f"<td>{self._report_number(raw['advance_ratio_j'], 3)}</td>"
                f"<td>{self._report_number(raw['ct'])}</td>"
                f"<td>{self._report_number(raw['cp'])}</td>"
                f"<td>{_html_escape(str(source))}</td></tr>")
        parts.append(
            "<tr><td>Math result</td>"
            f"<td>{self._report_number(point.rpm, 0)}</td>"
            f"<td>{self._report_number(point.j, 3)}</td>"
            f"<td>{self._report_number(point.ct)}</td>"
            f"<td>{self._report_number(point.cp)}</td>"
            "<td>Ct/Cp interpolation + equations</td></tr>")
        parts.append("</table>")
        warnings = [self._localize_warning(item) for item in result.warnings] or [self.tr("no_warnings")]
        if result.missing_parameters:
            warnings = [self.tr("simplified")] + warnings
        parts.append("<h2>" + _html_escape("Попередження" if self.language == "uk" else "Warnings") + "</h2>")
        parts.append("<ul>")
        for warning in warnings:
            parts.append(f"<li>{_html_escape(str(warning))}</li>")
        parts.append("</ul>")
        return "<html><body>" + "".join(parts) + "</body></html>"

    def _build_compare_report_html(self) -> str:
        parts = [self._report_header_html(
            "Звіт порівняння" if self.language == "uk" else "Comparison report")]
        if not self.compare_items:
            parts.append("<p><b>" + _html_escape(
                "Список порівняння порожній." if self.language == "uk" else
                "The comparison list is empty.") + "</b></p>")
            return "<html><body>" + "".join(parts) + "</body></html>"
        headers = ["#", "Name", "Thrust N", "Current A", "Power W", "T/W",
                   "Runtime min", "ESC %", "Motor %", "Battery %", "Confidence %", "Source"]
        parts.append(f"<p>{_html_escape(str(len(self.compare_items)))} "
                     + _html_escape("варіантів" if self.language == "uk" else "entries") + "</p>")
        parts.append("<table border='1' cellspacing='0' cellpadding='4'><tr>")
        for header in headers:
            parts.append(f"<th>{_html_escape(header)}</th>")
        parts.append("</tr>")
        for index, item in enumerate(self.compare_items, 1):
            try:
                cells = [
                    str(index), str(item.get("label", "")),
                    self._report_number(item.get("thrust")),
                    self._report_number(item.get("current")),
                    self._report_number(item.get("power"), 1),
                    self._report_number(item.get("tw")),
                    self._report_number(item.get("runtime"), 1),
                    self._report_number(item.get("esc_margin"), 0),
                    ("n/a" if item.get("motor_margin") is None
                     else self._report_number(item.get("motor_margin"), 0)),
                    self._report_number(item.get("battery_margin"), 0),
                    self._report_number(float(item.get("confidence", 0)) * 100.0, 0),
                    str(item.get("source", "")),
                ]
            except Exception:  # noqa: BLE001 - one bad row must not kill the report
                cells = [str(index)] + ["n/a"] * (len(headers) - 1)
            parts.append("<tr>" + "".join(
                f"<td>{_html_escape(cell)}</td>" for cell in cells) + "</tr>")
        parts.append("</table>")
        return "<html><body>" + "".join(parts) + "</body></html>"

    def _write_pdf_report(self, html: str, target: str | Path) -> Path:
        """Render HTML to PDF atomically (temp file + rename, no partial output)."""
        destination = Path(target)
        if not destination.suffix.lower() == ".pdf":
            destination = destination.with_suffix(".pdf")
        destination.parent.mkdir(parents=True, exist_ok=True)
        staging = destination.parent / (destination.name + ".writing")
        try:
            document = QTextDocument()
            document.setHtml(html)
            writer = QPdfWriter(str(staging))
            writer.setTitle(f"{APP_NAME} {APP_VERSION}")
            writer.setCreator(APP_NAME)
            document.print_(writer)
            del writer
            del document
            if not staging.is_file() or staging.stat().st_size == 0:
                raise RuntimeError("PDF writer produced no output")
            os.replace(staging, destination)
        finally:
            try:
                if staging.exists():
                    staging.unlink()
            except OSError:
                pass
        return destination

    def _export_pdf_report(self, html: str, default_name: str) -> None:
        target, _ = QFileDialog.getSaveFileName(
            self,
            "Експорт PDF-звіту" if self.language == "uk" else "Export PDF report",
            default_name, "PDF (*.pdf)")
        if not target:
            return
        try:
            written = self._write_pdf_report(html, target)
        except Exception as exc:  # noqa: BLE001 - user-facing slot
            QMessageBox.critical(
                self, APP_NAME,
                ("Експорт PDF не виконано" if self.language == "uk" else "PDF export failed")
                + f":\n{self.tr('details')}: {exc}")
            return
        QMessageBox.information(
            self, APP_NAME, f"{self.tr('exported')}:\n{written}")

    def export_calc_pdf_report(self) -> None:
        try:
            html = self._build_calc_report_html()
        except Exception as exc:  # noqa: BLE001 - invalid input state must not crash
            QMessageBox.critical(
                self, APP_NAME,
                ("Експорт PDF не виконано" if self.language == "uk" else "PDF export failed")
                + f":\n{self.tr('details')}: {exc}")
            return
        self._export_pdf_report(html, "calculation-report.pdf")

    def export_compare_pdf_report(self) -> None:
        try:
            html = self._build_compare_report_html()
        except Exception as exc:  # noqa: BLE001 - invalid state must not crash
            QMessageBox.critical(
                self, APP_NAME,
                ("Експорт PDF не виконано" if self.language == "uk" else "PDF export failed")
                + f":\n{self.tr('details')}: {exc}")
            return
        self._export_pdf_report(html, "comparison-report.pdf")

    def _payload(self) -> dict[str, Any]:
        self._snapshot_accessories()
        inputs = self._inputs()
        accessory_mass = sum(
            float(item.get("mass_kg", 0)) * max(1, int(item.get("quantity", 1)))
            for item in self.build_accessories if item.get("enabled"))
        return {
            "name": self.state["build_name"].strip() or "Untitled",
            "description": self.state["build_description"], "note": self.state["build_note"],
            "propeller_model_id": inputs.model_id, "motor_kv": inputs.motor_kv,
            "battery_s": inputs.battery_s, "battery_capacity_ah": inputs.battery_capacity_ah,
            "esc_current_a": inputs.esc_current_a, "motor_count": inputs.motor_count,
            "mass_kg": inputs.mass_kg,
            "payload_kg": float(to_si(float(self.state["build_payload"]), "mass_kg", self.unit_system)),
            "advanced": {"voltage_v": inputs.voltage_v, "throttle": inputs.throttle,
                         "speed_m_s": inputs.speed_m_s, "motor_resistance_ohm": inputs.motor_resistance_ohm,
                         "motor_i0_a": inputs.motor_i0_a, "motor_max_current_a": inputs.motor_max_current_a,
                         "motor_max_power_w": inputs.motor_max_power_w, "battery_c_rating": inputs.battery_c_rating,
                         "battery_type": inputs.battery_type,
                         "configuration_mode": self.state.get("configuration_mode", "custom"),
                         "rpm_override": inputs.rpm_override, "source_point_id": inputs.source_point_id,
                         "accessories": self.build_accessories, "accessory_mass_kg": accessory_mass,
                         "density_kg_m3": inputs.density_kg_m3, "medium": inputs.medium,
                         "motor_name": self.state["motor_name"], "battery_name": self.state["battery_name"],
                         "esc_name": self.state["esc_name"], "frame_name": self.state["frame_name"]},
        }

    def _accessory_name(self, category: str) -> str:
        return self.tr(f"module_{category}")

    def _accessory_mass_unit(self) -> str:
        return "g" if self.unit_system == "SI" else "oz"

    def _accessory_mass_from_kg(self, mass_kg: float) -> float:
        return mass_kg * (1000.0 if self.unit_system == "SI" else 35.27396195)

    def _accessory_mass_to_kg(self, displayed: float) -> float:
        return displayed / (1000.0 if self.unit_system == "SI" else 35.27396195)

    def _snapshot_accessories(self) -> None:
        if self._updating_accessories or not hasattr(self, "accessory_table"):
            return
        table = self.accessory_table
        accessories: list[dict[str, Any]] = []
        try:
            row_count = table.rowCount()
        except RuntimeError:
            return
        for row in range(row_count):
            included_item = table.item(row, 0)
            category_item = table.item(row, 1)
            model_item = table.item(row, 2)
            quantity_item = table.item(row, 3)
            mass_item = table.item(row, 4)
            if category_item is None:
                continue
            try:
                quantity = max(1, int(float(quantity_item.text() if quantity_item else "1")))
            except ValueError:
                quantity = 1
            try:
                mass_kg = max(0.0, self._accessory_mass_to_kg(float(mass_item.text() if mass_item else "0")))
            except ValueError:
                mass_kg = 0.0
            accessories.append({
                "category": str(category_item.data(Qt.ItemDataRole.UserRole) or "other"),
                "model": model_item.text().strip() if model_item else "",
                "quantity": quantity, "mass_kg": mass_kg,
                "enabled": bool(included_item and included_item.checkState() == Qt.CheckState.Checked),
            })
        self.build_accessories = accessories

    def _refresh_accessory_table(self) -> None:
        if not hasattr(self, "accessory_table"):
            return
        table = self.accessory_table
        self._updating_accessories = True
        try:
            with QSignalBlocker(table):
                table.setRowCount(len(self.build_accessories))
                for row, accessory in enumerate(self.build_accessories):
                    include = QTableWidgetItem()
                    include.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable |
                                     Qt.ItemFlag.ItemIsUserCheckable)
                    include.setCheckState(Qt.CheckState.Checked if accessory.get("enabled") else Qt.CheckState.Unchecked)
                    table.setItem(row, 0, include)
                    category = QTableWidgetItem(self._accessory_name(str(accessory.get("category", "other"))))
                    category.setData(Qt.ItemDataRole.UserRole, str(accessory.get("category", "other")))
                    category.setFlags(category.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    table.setItem(row, 1, category)
                    table.setItem(row, 2, QTableWidgetItem(str(accessory.get("model", ""))))
                    table.setItem(row, 3, QTableWidgetItem(str(max(1, int(accessory.get("quantity", 1))))))
                    displayed_mass = self._accessory_mass_from_kg(float(accessory.get("mass_kg", 0)))
                    table.setItem(row, 4, QTableWidgetItem(f"{displayed_mass:.10g}"))
                    total = QTableWidgetItem(
                        f"{displayed_mass * max(1, int(accessory.get('quantity', 1))):.10g}")
                    total.setFlags(total.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    table.setItem(row, 5, total)
        finally:
            self._updating_accessories = False
        self._update_accessory_total()

    def _accessory_item_changed(self, _item: QTableWidgetItem) -> None:
        if self._updating_accessories:
            return
        self._snapshot_accessories()
        self._refresh_accessory_table()

    def _update_accessory_total(self) -> None:
        total_kg = sum(
            float(item.get("mass_kg", 0)) * max(1, int(item.get("quantity", 1)))
            for item in self.build_accessories if item.get("enabled"))
        if hasattr(self, "accessory_total_label"):
            count = sum(1 for item in self.build_accessories if item.get("enabled"))
            displayed = self._accessory_mass_from_kg(total_kg)
            self.accessory_total_label.setText(
                self.tr("module_total").format(count=count, mass=f"{displayed:.3f}", unit=self._accessory_mass_unit()))

    def _add_custom_accessory(self) -> None:
        self._snapshot_accessories()
        self.build_accessories.append(
            {"category": "other", "model": "", "quantity": 1, "mass_kg": 0.0, "enabled": True})
        self._refresh_accessory_table()
        self.accessory_table.setCurrentCell(self.accessory_table.rowCount() - 1, 2)

    def _remove_accessory(self) -> None:
        self._snapshot_accessories()
        row = self.accessory_table.currentRow() if hasattr(self, "accessory_table") else -1
        if 0 <= row < len(self.build_accessories):
            self.build_accessories.pop(row)
            self._refresh_accessory_table()

    def _reset_accessories(self) -> None:
        self.build_accessories = [dict(item) for item in ACCESSORY_DEFAULTS]
        self._refresh_accessory_table()

    def _apply_accessory_mass_to_payload(self) -> None:
        self._snapshot_accessories()
        total_kg = sum(
            float(item.get("mass_kg", 0)) * max(1, int(item.get("quantity", 1)))
            for item in self.build_accessories if item.get("enabled"))
        self._set_text_value("build_payload", f"{from_si(total_kg, 'mass_kg', self.unit_system):.10g}")
        try:
            current_mass_kg = float(to_si(float(self.state["mass"]), "mass_kg", self.unit_system))
            base_mass_kg = max(0.0, current_mass_kg - self._accessory_mass_applied_kg)
            updated_mass = from_si(base_mass_kg + total_kg, "mass_kg", self.unit_system)
            self._set_text_value("mass", f"{updated_mass:.10g}")
            self._accessory_mass_applied_kg = total_kg
            self._activate_custom_mode()
            self.calculate()
        except (TypeError, ValueError):
            pass

    def _accessories_group(self) -> QGroupBox:
        group = QGroupBox(self.tr("modules_title"))
        layout = QVBoxLayout(group)
        note = QLabel(self.tr("modules_note"))
        note.setWordWrap(True)
        layout.addWidget(note)
        unit = self._accessory_mass_unit()
        self.accessory_table = self._table([
            self.tr("module_included"), self.tr("module_type"), self.tr("module_model"),
            self.tr("module_quantity"), f"{self.tr('module_mass_each')}, {unit}",
            f"{self.tr('module_mass_total')}, {unit}"],
            "accessoryTable")
        self.accessory_table.setMinimumHeight(310)
        self.accessory_table.itemChanged.connect(self._accessory_item_changed)
        layout.addWidget(self.accessory_table, 1)
        buttons = QHBoxLayout()
        for label, handler in ((self.tr("module_add_other"), self._add_custom_accessory),
                               (self.tr("module_remove"), self._remove_accessory),
                               (self.tr("module_reset"), self._reset_accessories),
                               (self.tr("module_apply_payload"), self._apply_accessory_mass_to_payload)):
            button = QPushButton(label)
            button.clicked.connect(handler)
            buttons.addWidget(button)
        layout.addLayout(buttons)
        self.accessory_total_label = QLabel()
        self.accessory_total_label.setObjectName("modeIntro")
        self.accessory_total_label.setWordWrap(True)
        layout.addWidget(self.accessory_total_label)
        self._refresh_accessory_table()
        self.accessory_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.accessory_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.accessory_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        for column in (3, 4, 5):
            self.accessory_table.horizontalHeader().setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        return group

    def _builds_tab(self) -> QWidget:
        tab = QWidget()
        layout = QHBoxLayout(tab)
        left_panel = QWidget()
        left_panel.setMinimumWidth(500)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        guide_group = QGroupBox(self.tr("build_guide"))
        guide_layout = QVBoxLayout(guide_group)
        guide = QTextBrowser()
        guide.setHtml(BUILD_GUIDE[self.language])
        guide.setMinimumHeight(215)
        guide.setMaximumHeight(215)
        guide.setOpenExternalLinks(False)
        guide_layout.addWidget(guide)
        left_layout.addWidget(guide_group)
        group = QGroupBox(self.tr("custom_build"))
        form = QFormLayout(group)
        build_name = self._edit("build_name", "build_name")
        build_name.setPlaceholderText(self.tr("build_name_hint"))
        form.addRow(self.tr("build_name"), build_name)
        motor_name = self._edit("motor_name", "motor_name")
        motor_name.setPlaceholderText(self.tr("motor_name_hint"))
        form.addRow(self.tr("motor_name"), motor_name)
        battery_name = self._edit("battery_name", "battery_name")
        battery_name.setPlaceholderText(self.tr("battery_name_hint"))
        form.addRow(self.tr("battery_name"), battery_name)
        esc_name = self._edit("esc_name", "esc_name")
        esc_name.setPlaceholderText(self.tr("esc_name_hint"))
        form.addRow(self.tr("esc_name"), esc_name)
        frame_name = self._edit("frame_name", "frame_name")
        frame_name.setPlaceholderText(self.tr("frame_name_hint"))
        form.addRow(self.tr("frame_name"), frame_name)
        payload_box = QWidget()
        payload_layout = QHBoxLayout(payload_box)
        payload_layout.setContentsMargins(0, 0, 0, 0)
        payload_layout.addWidget(self._edit("build_payload", "build_payload"), 1)
        payload_layout.addWidget(QLabel(unit_label("mass_kg", self.unit_system)))
        form.addRow(self.tr("payload"), payload_box)
        self.build_description = QPlainTextEdit(self.state["build_description"])
        self.build_description.setMaximumHeight(95)
        self.build_description.setPlaceholderText(self.tr("description_hint"))
        form.addRow(self.tr("description"), self.build_description)
        self.build_note = QPlainTextEdit(self.state["build_note"])
        self.build_note.setMaximumHeight(85)
        self.build_note.setPlaceholderText(self.tr("note_hint"))
        form.addRow(self.tr("note"), self.build_note)
        note = QLabel(self.tr("build_capture_note"))
        note.setWordWrap(True)
        form.addRow(note)
        buttons = QGridLayout()
        actions: list[tuple[str, Callable[[], None]]] = [
            (self.tr("save"), self.save_build_new), (self.tr("update"), self.update_build),
            (self.tr("save_as"), self.save_build_new), (self.tr("delete"), self.delete_build),
            (self.tr("duplicate"), self.duplicate_build), (self.tr("add_compare"), self.add_build_to_compare),
            (self.tr("export_json"), self.export_build), (self.tr("import_json"), self.import_build)]
        for i, (label, handler) in enumerate(actions):
            button = QPushButton(label)
            button.clicked.connect(handler)
            buttons.addWidget(button, i // 2, i % 2)
        form.addRow(buttons)
        left_layout.addWidget(group)
        left_layout.addStretch(1)
        layout.addWidget(self._scroll(left_panel), 2)
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addWidget(self._accessories_group(), 3)
        builds_group = QGroupBox(self.tr("saved_builds_list"))
        builds_layout = QVBoxLayout(builds_group)
        self.build_table = self._table(["ID", self.tr("name"), self.tr("model"), "KV", "S",
                                        self.tr("module_count"), self.tr("module_mass"), self.tr("update")],
                                       "buildTable")
        self.build_table.itemSelectionChanged.connect(self._select_build)
        builds_layout.addWidget(self.build_table)
        right_layout.addWidget(builds_group, 2)
        layout.addWidget(right_panel, 3)
        self._refresh_builds()
        return tab

    def _sync_build_text(self) -> None:
        self.state["build_description"] = self.build_description.toPlainText().strip()
        self.state["build_note"] = self.build_note.toPlainText().strip()
        self._snapshot()

    def _refresh_builds(self) -> None:
        if not hasattr(self, "build_table"):
            return
        self.build_table.setRowCount(0)
        for i, row in enumerate(self.repository.builds()):
            advanced = json.loads(row["advanced_json"] or "{}")
            accessories = [item for item in advanced.get("accessories", []) if item.get("enabled")]
            accessory_mass = sum(float(item.get("mass_kg", 0)) * max(1, int(item.get("quantity", 1)))
                                 for item in accessories)
            accessory_mass_display = self._accessory_mass_from_kg(accessory_mass)
            self._fill_row(self.build_table, i, [row["build_id"], row["name"], row["propeller_model_id"],
                                                  row["motor_kv"], row["battery_s"], len(accessories),
                                                  f"{accessory_mass_display:.3f} {self._accessory_mass_unit()}",
                                                  row["updated_at"]], row["build_id"])
        self.build_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.build_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        for column in (0, 3, 4, 5, 6, 7):
            self.build_table.horizontalHeader().setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)

    def _select_build(self) -> None:
        index = self.build_table.currentRow()
        if index < 0:
            return
        item = self.build_table.item(index, 0)
        build_id = int(item.data(Qt.ItemDataRole.UserRole) or item.text())
        row = self.repository.get_build(build_id)
        if not row:
            return
        self.current_build_id = build_id
        self.edits["build_name"].setText(row["name"])
        self.build_description.setPlainText(row["description"] or "")
        self.build_note.setPlainText(row["note"] or "")
        advanced = json.loads(row["advanced_json"] or "{}")
        for key, fallback in (("motor_name", "Custom BLDC"), ("battery_name", "Custom LiPo"),
                              ("esc_name", "Custom ESC"), ("frame_name", "Custom frame")):
            self.edits[key].setText(str(advanced.get(key, fallback)))
        self.build_accessories = [dict(item) for item in advanced.get("accessories", ACCESSORY_DEFAULTS)]
        self._refresh_accessory_table()
        payload_display = from_si(float(row["payload_kg"] or 0), "mass_kg", self.unit_system)
        self.edits["build_payload"].setText(f"{payload_display:.10g}")

    def save_build_new(self) -> None:
        try:
            self._sync_build_text()
            self.current_build_id = self.repository.save_build(self._payload())
            self._refresh_builds()
        except Exception as exc:
            QMessageBox.critical(self, APP_NAME, f"{self.tr('calculation_error')}:\n{self.tr('details')}: {exc}")

    def update_build(self) -> None:
        if self.current_build_id is None:
            self.save_build_new()
            return
        self._sync_build_text()
        try:
            payload = self._payload()
        except CalcInputErrors as exc:
            self._show_calc_input_error(exc.field_errors)
            return
        except Exception as exc:
            QMessageBox.critical(self, APP_NAME, f"{self.tr('calculation_error')}:\n{self.tr('details')}: {exc}")
            return
        self.repository.save_build(payload, self.current_build_id)
        self._refresh_builds()

    def delete_build(self) -> None:
        if self.current_build_id is None:
            return
        answer = QMessageBox.question(self, APP_NAME, self.tr("delete_confirm"))
        if answer == QMessageBox.StandardButton.Yes:
            self.repository.delete_build(self.current_build_id)
            self.current_build_id = None
            self._refresh_builds()

    def duplicate_build(self) -> None:
        if self.current_build_id is not None:
            self.current_build_id = self.repository.duplicate_build(self.current_build_id)
            self._refresh_builds()

    def export_build(self) -> None:
        self._sync_build_text()
        target, _ = QFileDialog.getSaveFileName(self, self.tr("export_json"), "build.json", "JSON (*.json)")
        if target:
            try:
                payload = self._payload()
            except CalcInputErrors as exc:
                self._show_calc_input_error(exc.field_errors)
                return
            except Exception as exc:
                QMessageBox.critical(self, APP_NAME, f"{self.tr('calculation_error')}:\n{self.tr('details')}: {exc}")
                return
            Path(target).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def import_build(self) -> None:
        source, _ = QFileDialog.getOpenFileName(self, self.tr("import_json"), "", "JSON (*.json)")
        if not source:
            return
        try:
            payload = json.loads(Path(source).read_text(encoding="utf-8"))
            self.current_build_id = self.repository.save_build(payload)
            self._refresh_builds()
        except Exception as exc:
            QMessageBox.critical(self, APP_NAME, f"{self.tr('import_failed')}:\n{self.tr('details')}: {exc}")

    def _result_item(self, label: str, result: CalculationResult, inputs: CalculationInputs) -> dict[str, Any]:
        point = result.point
        return {"label": label, "thrust": result.total_thrust_n,
                "current": point.current_a * inputs.motor_count,
                "power": point.electrical_power_w * inputs.motor_count,
                "torque": point.torque_nm * inputs.motor_count,
                "efficiency": point.system_efficiency, "aero": point.aero_efficiency,
                "max_efficiency": result.optimum.system_efficiency if result.optimum else point.system_efficiency,
                "recommended_voltage": result.recommended_voltage_v,
                "tw": result.thrust_to_weight, "runtime": result.runtime_min, "voltage": inputs.voltage_v,
                "rpm_margin": result.structural_margin_percent, "esc_margin": result.esc_margin_percent,
                "motor_margin": result.motor_current_margin_percent,
                "battery_margin": result.battery_margin_percent, "confidence": point.confidence,
                "source": point.source_type, "warnings": "; ".join(result.warnings), "mass": inputs.mass_kg}

    def add_current_to_compare(self) -> None:
        if self.current_result is None:
            self.calculate()
        if self.current_result and self.current_inputs:
            self.compare_items.append(self._result_item(
                self.current_inputs.model_id, self.current_result, self.current_inputs))
            self._refresh_compare()

    def add_build_to_compare(self) -> None:
        if self.current_build_id is None:
            self.add_current_to_compare()
            return
        row = self.repository.get_build(self.current_build_id)
        if row is None:
            return
        advanced = json.loads(row["advanced_json"] or "{}")
        inputs = CalculationInputs(
            model_id=row["propeller_model_id"], voltage_v=float(advanced.get("voltage_v", row["battery_s"] * 3.7)),
            throttle=float(advanced.get("throttle", 1.0)), motor_kv=float(row["motor_kv"]),
            motor_resistance_ohm=advanced.get("motor_resistance_ohm"), motor_i0_a=advanced.get("motor_i0_a"),
            motor_max_current_a=advanced.get("motor_max_current_a"), motor_max_power_w=advanced.get("motor_max_power_w"),
            esc_current_a=float(row["esc_current_a"]), battery_capacity_ah=float(row["battery_capacity_ah"]),
            battery_c_rating=float(advanced.get("battery_c_rating", 30)), battery_s=int(row["battery_s"]),
            battery_type=str(advanced.get("battery_type", "LiPo")),
            speed_m_s=float(advanced.get("speed_m_s", 0)), mass_kg=float(row["mass_kg"]),
            motor_count=int(row["motor_count"]), density_kg_m3=float(advanced.get("density_kg_m3", 1.225)),
            medium=str(advanced.get("medium", "air")), rpm_override=advanced.get("rpm_override"),
            source_point_id=advanced.get("source_point_id"))
        result = self.calculator.calculate(inputs)
        self.compare_items.append(self._result_item(row["name"], result, inputs))
        self._refresh_compare()

    def _compare_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        controls = QHBoxLayout()
        add = QPushButton(self.tr("add_compare"))
        add.clicked.connect(self.add_current_to_compare)
        controls.addWidget(add)
        controls.addWidget(QLabel(self.tr("criterion")))
        criterion = self._combo("compare_criterion", [
            (self.tr("crit_max_thrust"), "maximum thrust"),
            (self.tr("crit_max_time"), "maximum time"),
            (self.tr("crit_min_current"), "minimum current"),
            (self.tr("crit_max_eff"), "maximum efficiency"),
            (self.tr("crit_compatibility"), "best compatibility"),
            (self.tr("crit_min_mass"), "minimum mass")])
        criterion.currentIndexChanged.connect(self._refresh_compare)
        controls.addWidget(criterion)
        clear = QPushButton(self.tr("clear"))
        clear.clicked.connect(lambda: (self.compare_items.clear(), self._refresh_compare()))
        controls.addWidget(clear)
        pdf = QPushButton(
            "Експорт PDF-звіту" if self.language == "uk" else "Export PDF report")
        pdf.setObjectName("exportComparePdf")
        pdf.setAccessibleName("exportComparePdf")
        pdf.clicked.connect(self.export_compare_pdf_report)
        controls.addWidget(pdf)
        controls.addStretch(1)
        layout.addLayout(controls)
        self.compare_table = self._table(["#", self.tr("name"), self.tr("thrust_card"), self.tr("current_card"),
                                          self.tr("power_card"), self.tr("torque"), "ηsystem", "ηmax", "ηaero", "T/W",
                                          self.tr("time"), self.tr("recommended_voltage"), self.tr("rpm_margin"),
                                          "ESC", self.tr("motor_name"), self.tr("battery_name"), self.tr("confidence"),
                                          self.tr("source"), self.tr("warnings")],
                                         "compareTable")
        layout.addWidget(self.compare_table)
        self._refresh_compare()
        return tab

    def _refresh_compare(self) -> None:
        if not hasattr(self, "compare_table"):
            return
        combo = self.combos.get("compare_criterion")
        criterion = str(combo.currentData() or combo.currentText()) if combo else self.state["compare_criterion"]
        reverse = criterion not in {"minimum current", "minimum mass"}
        key_map = {"maximum thrust": "thrust", "maximum time": "runtime", "minimum current": "current",
                   "maximum efficiency": "max_efficiency", "minimum mass": "mass"}
        if criterion == "best compatibility":
            key = lambda item: min(item["esc_margin"], item["battery_margin"],
                                   item["rpm_margin"] if item["rpm_margin"] is not None else 100)
        else:
            key = lambda item: self._compare_sort_value(item.get(key_map.get(criterion, "efficiency")))
        items = sorted(self.compare_items, key=key, reverse=reverse)
        self.compare_table.setRowCount(0)
        for i, item in enumerate(items):
            values = [i + 1, item["label"], f"{from_si(item['thrust'], 'force', self.unit_system):.3g}",
                      f"{item['current']:.2f}", f"{from_si(item['power'], 'power', self.unit_system):.3g}",
                      f"{from_si(item['torque'], 'torque', self.unit_system):.3g}",
                      f"{item['efficiency'] * 100:.1f}%", f"{item['max_efficiency'] * 100:.1f}%",
                      f"{item['aero'] * 100:.1f}%", f"{item['tw']:.2f}",
                      "n/a" if isinstance(item['runtime'], float) and math.isnan(item['runtime']) else f"{item['runtime']:.1f}",
                      "n/a" if item["recommended_voltage"] is None else f"{item['recommended_voltage']:.1f}",
                      self._margin(item["rpm_margin"]),
                      self._margin(item["esc_margin"]), self._margin(item["motor_margin"]),
                      self._margin(item["battery_margin"]), f"{item['confidence'] * 100:.0f}%",
                      item["source"], item["warnings"]]
            self._fill_row(self.compare_table, i, values)
            color = QColor("#153A35" if i == 0 else ("#3B2223" if item["warnings"] else "#353121"))
            for column in range(self.compare_table.columnCount()):
                self.compare_table.item(i, column).setBackground(color)
        self.compare_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)

    @staticmethod
    def _compare_sort_value(value: float | None) -> float:
        """Normalize a compare ranking key: None and NaN sort as -1e9.

        NaN is truthy, so the previous ``value or -1e9`` guard let a NaN
        runtime through and a meaningless entry could rank #1 (e.g. under
        "maximum time"). All other values keep the exact old semantics.
        """
        if value is None or (isinstance(value, float) and math.isnan(value)):
            return -1e9
        return value or -1e9

    @staticmethod
    def _margin(value: float | None) -> str:
        return "n/a" if value is None else f"{value:+.0f}%"

    def _frame_size_values(self) -> list[tuple[str, str]]:
        values: list[tuple[str, str]] = []
        for millimeters in FRAME_SIZE_PRESETS_MM:
            if self.unit_system == "SI":
                label = f"{millimeters} mm"
            else:
                label = f"{millimeters / 25.4:.2f} in ({millimeters} mm)"
            values.append((label, str(millimeters)))
        values.append((self.tr("custom_frame_size"), "custom"))
        return values

    def _apply_frame_size_preset(self) -> None:
        preset = self.state.get("frame_size_preset", "custom")
        custom = preset == "custom"
        for widget in self.edit_widgets.get("frame_diagonal", []):
            widget.setEnabled(custom)
        if custom:
            return
        try:
            diagonal_m = float(preset) / 1000.0
        except ValueError:
            return
        self._loading_preset = True
        try:
            self._set_text_value(
                "frame_diagonal", f"{from_si(diagonal_m, 'length_m', self.unit_system):.10g}")
        finally:
            self._loading_preset = False
        if hasattr(self, "frame_results"):
            self.calculate_frame()

    def _frame_tab(self) -> QWidget:
        content = QWidget()
        layout = QHBoxLayout(content)
        group = QGroupBox(self.tr("frame_structure"))
        form = QFormLayout(group)
        size_preset = self._combo("frame_size_preset", self._frame_size_values(), "frame_size_preset")
        form.addRow(self.tr("frame_size_preset"), size_preset)
        self._field(form, self.tr("frame_diagonal"), "frame_diagonal", unit_label("length_m", self.unit_system),
                    "frame_diagonal")
        self._apply_frame_size_preset()
        geometry = self._combo("frame_geometry", [("X", "X"), ("H", "H"), ("+", "+"),
                                                   (("Довільна" if self.language == "uk" else "Custom"), "custom")])
        form.addRow(self.tr("frame_geometry"), geometry)
        self._field(form, self.tr("frame_motors"), "frame_motors", "", "motors")
        self._field(form, self.tr("arm_width"), "arm_width", unit_label("length_m", self.unit_system), "arm_width")
        self._field(form, self.tr("arm_thickness"), "arm_thickness", unit_label("length_m", self.unit_system),
                    "arm_thickness")
        materials = [("Вуглепластик" if self.language == "uk" else "Carbon fiber", "Carbon fiber"),
                     ("Алюміній" if self.language == "uk" else "Aluminum", "Aluminum"),
                     ("Деревина" if self.language == "uk" else "Wood", "Wood"),
                     ("Власний" if self.language == "uk" else "Custom", "Custom")]
        form.addRow(self.tr("frame_material"), self._combo("frame_material", materials))
        self._field(form, self.tr("frame_mass"), "frame_mass", unit_label("mass_kg", self.unit_system), "frame_mass")
        self._field(form, self.tr("payload"), "payload", unit_label("mass_kg", self.unit_system), "build_payload")
        calculate = QPushButton(self.tr("recommend"), objectName="primary")
        calculate.clicked.connect(self.calculate_frame)
        form.addRow(calculate)
        layout.addWidget(group, 2)
        result_group = QGroupBox(self.tr("frame_checks"))
        result_layout = QVBoxLayout(result_group)
        self.frame_results = QPlainTextEdit()
        self.frame_results.setReadOnly(True)
        result_layout.addWidget(self.frame_results)
        layout.addWidget(result_group, 3)
        QTimer.singleShot(0, self.calculate_frame)
        return self._scroll(content)

    def calculate_frame(self) -> None:
        if not hasattr(self, "frame_results"):
            return
        try:
            self._snapshot()
            diagonal = float(to_si(float(self.state["frame_diagonal"]), "length_m", self.unit_system))
            width = float(to_si(float(self.state["arm_width"]), "length_m", self.unit_system))
            thickness = float(to_si(float(self.state["arm_thickness"]), "length_m", self.unit_system))
            frame_mass = float(to_si(float(self.state["frame_mass"]), "mass_kg", self.unit_system))
            payload = float(to_si(float(self.state["payload"]), "mass_kg", self.unit_system))
            motors = int(self.state["frame_motors"])
            geometry, material = self.state["frame_geometry"], self.state["frame_material"]
        except Exception as exc:
            self.frame_results.setPlainText(str(exc))
            return
        spacing = diagonal / math.sqrt(2) if geometry in {"X", "+"} else diagonal * 0.65
        clearance = 0.02
        max_diameter = max(0.02, spacing - clearance)
        young, yield_strength = {"Carbon fiber": (70e9, 600e6), "Aluminum": (69e9, 240e6),
                                 "Wood": (11e9, 45e6), "Custom": (30e9, 120e6)}[material]
        length = diagonal / 2
        design_force = (frame_mass + payload) * 9.80665 / motors * 2
        inertia = width * thickness ** 3 / 12
        stress = 6 * design_force * length / max(width * thickness ** 2, 1e-12)
        deflection = design_force * length ** 3 / (3 * young * max(inertia, 1e-15))
        safety = yield_strength / max(stress, 1)
        candidates = self.repository.connection.execute(
            """SELECT m.*,MAX(CASE WHEN p.efficiency BETWEEN 0 AND 1 THEN p.efficiency END) best_eta,
            COUNT(p.performance_id) pts
            FROM models m JOIN performance_points p ON p.model_id=m.model_id
            WHERE m.diameter_m BETWEEN ? AND ? AND m.medium='air'
            GROUP BY m.model_id HAVING best_eta IS NOT NULL
            ORDER BY m.has_experiment DESC,best_eta DESC,pts DESC LIMIT 3""",
            (max_diameter * 0.62, max_diameter)).fetchall()
        if self.language == "uk":
            lines = ["ПЕРЕВІРКА РАМИ - СПРОЩЕНА БАЛОЧНА МОДЕЛЬ", "-" * 64,
                     f"Відстань між осями моторів: {spacing:.3f} m",
                     f"Необхідний зазор дисків: {clearance * 1000:.0f} mm",
                     f"Максимально рекомендований діаметр: {max_diameter / 0.0254:.2f} in",
                     "Перекриття дисків на цьому ліміті: 0 mm",
                     f"Орієнтовне напруження променя: {stress / 1e6:.2f} MPa",
                     f"Орієнтовний прогин кінця: {deflection * 1000:.2f} mm",
                     f"Спрощений коефіцієнт міцності: {safety:.2f}",
                     "Резонанс: частоти збудження мотор-пропелер потрібно перевірити на реальній рамі.", "",
                     "3 НАЙКРАЩІ ВАРІАНТИ З БАЗИ"]
        else:
            lines = ["FRAME CHECK - SIMPLIFIED BEAM MODEL", "-" * 64,
                     f"Motor-axis spacing: {spacing:.3f} m", f"Required disk clearance: {clearance * 1000:.0f} mm",
                     f"Recommended maximum propeller diameter: {max_diameter / 0.0254:.2f} in",
                     "Disk overlap at this limit: 0 mm", f"Estimated arm stress: {stress / 1e6:.2f} MPa",
                     f"Estimated tip deflection: {deflection * 1000:.2f} mm", f"Simplified safety factor: {safety:.2f}",
                     "Resonance: verify motor/propeller excitation frequencies on the real frame.", "", "TOP 3 DATABASE MATCHES"]
        for index, row in enumerate(candidates, 1):
            best = self.repository.connection.execute(
                "SELECT rpm,efficiency FROM performance_points WHERE model_id=? AND efficiency BETWEEN 0 AND 1 ORDER BY efficiency DESC LIMIT 1",
                (row["model_id"],)).fetchone()
            rpm = best["rpm"] if best and best["rpm"] else 6000
            cells = 4 if row["diameter_m"] < 0.33 else (6 if row["diameter_m"] < 0.55 else 8)
            kv = rpm / (cells * 3.7 * 0.8)
            lines.append(f"{index}. {row['model_id']} | D={row['diameter_m'] / 0.0254:.2f} in | ηmax={float(row['best_eta'] or 0) * 100:.1f}%")
            verification = "потрібна фінальна стендова перевірка" if self.language == "uk" else "final bench verification required"
            lines.append(f"   {self.tr('motor_name')} ≈ {kv:.0f} KV · {cells}S · {cells * 3.7:.1f} V · {verification}")
        if safety < 2:
            lines.append("\nУВАГА: спрощений коефіцієнт міцності менше 2." if self.language == "uk" else
                         "\nWARNING: simplified safety factor is below 2.")
        self.frame_results.setPlainText("\n".join(lines))

    def _testing_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        title = QLabel(self.tr("open_calculation"), objectName="section")
        layout.addWidget(title)
        info = QLabel(self.tr("open_calculation_info"))
        info.setWordWrap(True)
        layout.addWidget(info)
        self.trace_table = self._table([self.tr("variable"), self.tr("formula"), self.tr("value"), self.tr("unit")],
                                      "traceTable")
        layout.addWidget(self.trace_table, 1)
        button = QPushButton(self.tr("recalculate"), objectName="primary")
        button.clicked.connect(self.calculate)
        layout.addWidget(button, 0, Qt.AlignmentFlag.AlignRight)
        self._refresh_trace()
        return tab

    def _refresh_trace(self) -> None:
        if not hasattr(self, "trace_table"):
            return
        self.trace_table.setRowCount(0)
        if not self.current_result:
            return
        for i, item in enumerate(self.current_result.trace):
            self._fill_row(self.trace_table, i, [self._trace_name(item["name"]), item["formula"],
                                                  f"{item['value']:.10g}", item["unit"]])
        self.trace_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)

    def _trace_name(self, name: str) -> str:
        if self.language == "en":
            return name
        return {"Advance ratio": "Коефіцієнт поступу", "Thrust": "Тяга", "Power": "Потужність",
                "Torque": "Момент", "Runtime": "Час роботи"}.get(name, name)

    def _help_tab(self) -> QWidget:
        pages = QTabWidget()
        self.help_pages = pages
        pages.addTab(self._help_page(HELP_UK if self.language == "uk" else HELP_EN), self.tr("full_guide"))
        pages.addTab(
            self._help_page(EXAMPLE_1_UK if self.language == "uk" else EXAMPLE_1_EN,
                            self._load_source_example), self.tr("example_1"))
        pages.addTab(
            self._help_page(EXAMPLE_2_UK if self.language == "uk" else EXAMPLE_2_EN,
                            self._load_custom_example), self.tr("example_2"))
        return pages

    def _help_page(self, html: str, handler: Callable[[], None] | None = None) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        browser = QTextBrowser()
        browser.setHtml(html)
        browser.setOpenExternalLinks(False)
        layout.addWidget(browser, 1)
        if handler is not None:
            button = QPushButton(self.tr("load_example"), objectName="primary")
            button.clicked.connect(handler)
            layout.addWidget(button, 0, Qt.AlignmentFlag.AlignRight)
        return page

    def _select_example_model(self, model_id: str) -> bool:
        if not self.model_combos:
            return False
        source = self.model_combos[0]
        index = source.findData(model_id)
        if index < 0:
            return False
        with QSignalBlocker(source):
            source.setCurrentIndex(index)
        self._sync_model(source)
        return True

    def _load_source_example(self) -> None:
        if not self._select_example_model("APC:8X9"):
            return
        row = self.repository.connection.execute(
            """SELECT performance_id FROM performance_points
               WHERE model_id='APC:8X9' AND rpm IS NOT NULL AND ct IS NOT NULL AND cp IS NOT NULL
               ORDER BY ABS(rpm-6395),ABS(COALESCE(advance_ratio_j,0)),performance_id LIMIT 1""").fetchone()
        if row is not None:
            point_id = str(row["performance_id"])
            self.state["reference_point_id"] = point_id
            for widget in self.reference_point_combos:
                index = widget.findData(point_id)
                if index >= 0:
                    with QSignalBlocker(widget):
                        widget.setCurrentIndex(index)
        self._set_configuration_mode("database")
        self._apply_reference_preset(schedule_calculation=False)
        self.calculate()
        self.tabs.setCurrentIndex(0)
        self.calculator_modes.setCurrentIndex(0)

    def _load_custom_example(self) -> None:
        if not self._select_example_model("APC:10X5"):
            return
        self._loading_preset = True
        try:
            self._set_configuration_mode("custom")
            self._set_combo_value("medium", "air")
            self._set_combo_value("battery_type", "LiPo")
            self._set_combo_value("battery_s", "4")
            for key, value in {
                "voltage": "14.8", "throttle": "100", "kv": "500", "speed": "0",
                "mass": "1.5", "motors": "4", "esc": "40", "capacity": "5",
                "c_rating": "30", "rm": "", "i0": "", "motor_max_current": "",
                "motor_max_power": "", "density": "1.225",
            }.items():
                self._set_text_value(key, value)
            self.state["reference_rpm"] = ""
            self._set_combo_value("frame_size_preset", "450")
            self._set_text_value("frame_diagonal", f"{from_si(0.45, 'length_m', self.unit_system):.10g}")
            self._set_text_value("frame_motors", "4")
            self._set_text_value("build_name", "APC 10x5 · 4S · 450 mm example")
        finally:
            self._loading_preset = False
        self._apply_frame_size_preset()
        self._update_preset_status()
        self.calculate()
        self.tabs.setCurrentIndex(0)
        self.calculator_modes.setCurrentIndex(1)

    def _about_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(48, 36, 48, 36)
        heading = QHBoxLayout()
        heading.addWidget(PropellerMark())
        title_box = QVBoxLayout()
        title = QLabel(APP_NAME.upper(), objectName="appTitle")
        title.setFont(QFont("Segoe UI", 20, QFont.Weight.Bold))
        title_box.addWidget(title)
        title_box.addWidget(QLabel(f"VERSION {APP_VERSION} · {self.tr('author')}: {AUTHOR}"))
        heading.addLayout(title_box)
        heading.addStretch(1)
        layout.addLayout(heading)
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(line)
        summary = self.repository.summary()
        provenance = ("ПОХОДЖЕННЯ: фізичний експеримент · CFD/чисельні дані · прогноз APC · каталог · геометрія · структурні RPM-ліміти"
                      if self.language == "uk" else
                      "PROVENANCE: physical experiment · CFD/numerical · APC prediction · catalog · geometry · structural RPM limits")
        details = QLabel(
            f"WINDOWS 10/11 x64 · OFFLINE · PORTABLE ONE-FILE EXE\n\n"
            f"{self.tr('models')}: {summary.get('models', 0):,}\n"
            f"{self.tr('characteristics')}: {summary.get('characteristics', 0):,}\n"
            f"{self.tr('sources')}: {summary.get('sources', 0):,}\n\n"
            f"{self.tr('working_database')}:\n{self.database_path}\n\n{provenance}")
        details.setWordWrap(True)
        details.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(details)
        layout.addStretch(1)
        return tab


def main() -> None:
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName(AUTHOR)
    window = PropellerMainWindow()
    window.show()
    raise SystemExit(app.exec())


if __name__ == "__main__":
    main()
