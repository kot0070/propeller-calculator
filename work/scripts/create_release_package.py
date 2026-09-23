from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "outputs"
OUTPUT.mkdir(parents=True, exist_ok=True)
REPORTS = ROOT / "work" / "reports"
DELIVERABLES = ROOT / "work" / "deliverables"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


copies = {
    ROOT / "dist" / "Propeller_Calculator_Professional_UA_v3.exe": "Propeller_Calculator_Professional_UA_v3_3.exe",
    DELIVERABLES / "Propeller_Calculator_v3_Інструкція_UA.pdf": "Propeller_Calculator_v3_Інструкція_UA.pdf",
    DELIVERABLES / "README_UA.md": "README_UA.md",
    DELIVERABLES / "Propeller_Calculator_v3_Final_Audit.xlsx": "Propeller_Calculator_v3_Final_Audit.xlsx",
    REPORTS / "audit_report.md": "Final_Audit_Summary.md",
    REPORTS / "audit_report.json": "Final_Audit.json",
    REPORTS / "source_file_audit.csv": "All_Source_Files_Audit.csv",
    REPORTS / "model_id_mapping.csv": "Model_ID_Mapping.csv",
    REPORTS / "unrecognized_files.csv": "Unrecognized_Files.csv",
    REPORTS / "manual_verification.json": "Manual_Verification.json",
    REPORTS / "ui_functional_test.json": "UI_Functional_Test.json",
    ROOT / "work" / "visual_qa" / "1366x768_1_Калькулятор.png": "UI_Preview.png",
}
for source, filename in copies.items():
    shutil.copy2(source, OUTPUT / filename)

audit = json.loads((REPORTS / "audit_report.json").read_text(encoding="utf-8"))
totals = audit["totals"]
source_rows = "\n".join(
    f"| {source['name']} | {source['file_count']} | {source['recognized_files']} | {source['unrecognized_files']} | "
    f"{source['normalized_models']} | {source['total'] or 0} | `{source['sha256']}` |"
    for source in audit["sources"]
)
test_report = f"""# Фінальний звіт тестування — Propeller Calculator Professional UA v3

**Автор програми: Ivan Soprun**  
Версія: 3.3.0  
Платформа: Windows 10/11 x64, portable one-file EXE, offline, asInvoker  
EXE-пакувальник: PyInstaller 6.21.0 з офіційного PyPI  
Інтерфейс: PySide6 6.9.1 (Qt), з офіційного PyPI  
Цифровий підпис: **NotSigned** — сертифікат підпису не надавався; автентичність перевіряти за SHA-256.

## Підсумок

- Статус: **PASS**.
- Моделей: **{totals['models']:,}**.
- Характеристик: **{totals['characteristics']:,}**.
- Джерел: **{totals['sources']}**.
- Моделей із фізичними випробуваннями: **{totals['models_with_experiments']}**.
- Моделей лише з прогнозом: **{totals['prediction_only_models']}**.
- Геометричних точок: **{totals['geometries']:,}**; RPM-limit rows: **{totals['rpm_limit_rows']}**.
- Дублікатів Model_ID: **0**; дублікатів performance point_key: **0**.
- Нерозпізнаних файлів: **1** із 4,760; файл збережено в журналі з SHA-256 і причиною.

## Перевірки

| Перевірка | Результат |
|---|---|
| Python automated suite: static/dynamic/air/water/units/source-point/battery/import/persistence/accessories | PASS — 12/12 |
| SQLite quick_check / foreign_key_check | PASS — ok / 0 |
| Повторний merge того самого DB | PASS — кількість точок не зросла |
| Оновлення зміненої та додавання нової точки | PASS |
| Транзакційний import history і унікальні backup-файли | PASS |
| Збірка після перезапуску | PASS — повний склад core + accessory component rows |
| SI → Imperial → SI | PASS — 1.5 kg → 3.306933933 lb → 1.5 kg |
| Незмінність фізичної тяги при перемиканні одиниць | PASS — допуск 1×10⁻⁹ N |
| Окремі простий та інженерний калькулятори | PASS — 2 режими, синхронізовані поля |
| Вихідна характеристика бази / математичний результат | PASS — 2 окремі рядки з точним source file |
| APC:8X9 — точне відтворення джерела | PASS — 6395 RPM; raw = math = 57.50 W/мотор |
| Ручна зміна / вибір нової моделі | PASS — Custom вмикається; нова модель повертає Database point |
| LiPo / Li-ion / LiFePO4 | PASS — номінальна напруга, usable capacity і контроль S/voltage |
| Формат потужності | PASS — без scientific notation; W/kW і чіткий total electrical label |
| Графіки навантаження | PASS — thrust/current/power/RPM по 10 точок; 2 efficiency series; ліміти компонентів |
| Стандартні розміри рами | PASS — 65–1000 mm, Custom, точне SI/Imperial відображення |
| Модулі й аксесуари | PASS — модель, кількість, маса, підсумок і SQLite component rows |
| Навчальні приклади | PASS — APC:8X9 database test і APC:10X5 custom build завантажуються в калькулятор |
| UA/EN | PASS — вкладки, режими, поля бази, заголовки збірок і довідка змінюються без перезапуску |
| Підказки | PASS — усі зареєстровані віджети; hover on/off; 2 контекстні панелі з повним текстом |
| Ручні звірки з початковими файлами | PASS — 7/7 наборів, 25 raw samples |
| Візуальна перевірка 8 вкладок, обох калькуляторів, 3 сторінок методики та UA/EN | PASS — 29 renders |
| 1366×768 при 200% DPI, адаптивне вертикальне компонування | PASS |
| Український PDF | PASS — усі сторінки відрендерено й переглянуто |
| XLSX-аудит | PASS — 7 листів; Overview відрендерено; 4,760 file rows; 2,031 mappings |
| Windows EXE metadata | PASS — CompanyName/Author: Ivan Soprun; version 3.3.0 |
| Чистий запуск one-file EXE | PASS — процес активний, робоча база створена атомарно |
| Робоча база після чистого запуску | PASS — 296,177,664 bytes; quick_check=ok; 1,053/335,434 |
| Повторний EXE-запуск не стирає збірки | PASS — build, параметри й accessory inventory збережені |

Тестовий стенд після підтвердження запуску примусово завершує прихований процес, тому його службовий exit code не є кодом штатного закриття програми. Штатне збереження/перезапуск перевірено окремо на Qt-рівні й повторним EXE-запуском.

## Джерела

| Джерело | Файлів | Розпізнано | Не розпізнано | Моделей | Характеристик | SHA-256 |
|---|---:|---:|---:|---:|---:|---|
{source_rows}

## Єдиний нерозпізнаний файл

`UIUC_2022/images/pspbrwse.jbf`, 9,804 bytes, SHA-256
`045138E4253ACA536BB75BBC818F1EB453002BA6F44828E78B8F26444AC6032A`.
Причина: службовий бінарний thumbnail-файл Paint Shop Pro без інженерних даних; файл не відкинуто мовчки.

## Відомі обмеження

- Без Rm/I0 моторна частина прямо позначається як спрощена оцінка.
- Water mode переносить безрозмірні коефіцієнти повітряних даних на густину води, показує обов’язкове попередження й не моделює кавітацію.
- Модель рами є спрощеною балочною оцінкою; резонанс і міцність перевіряються фізично.
- EXE не має комерційного code-signing сертифіката; Windows SmartScreen може показати попередження.
"""
(OUTPUT / "Test_Report_UA.md").write_text(test_report, encoding="utf-8")

artifact_files = sorted(path for path in OUTPUT.iterdir() if path.is_file() and path.name not in {
    "SHA256SUMS.txt", "Release_Manifest.json", "Propeller_Calculator_Professional_UA_v3.exe",
    "Propeller_Calculator_Professional_UA_v3_2.exe"})
manifest = {
    "application": "Propeller Calculator Professional UA v3",
    "version": "3.3.0",
    "author": "Ivan Soprun",
    "platform": "Windows 10/11 x64",
    "distribution": "portable one-file EXE; offline; no administrator rights",
    "digital_signature": "NotSigned",
    "database": totals,
    "source_groups": audit["groups"],
    "unrecognized_files": audit["unrecognized_files"],
    "artifacts": [{"file": path.name, "bytes": path.stat().st_size, "sha256": sha256(path)} for path in artifact_files],
}
(OUTPUT / "Release_Manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

hash_files = sorted(path for path in OUTPUT.iterdir() if path.is_file() and path.name not in {
    "SHA256SUMS.txt", "Propeller_Calculator_Professional_UA_v3.exe",
    "Propeller_Calculator_Professional_UA_v3_2.exe"})
lines = [f"{sha256(path)} *{path.name}" for path in hash_files]
(OUTPUT / "SHA256SUMS.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
print(json.dumps({"files": len(hash_files) + 1, "exe_sha256": sha256(OUTPUT / "Propeller_Calculator_Professional_UA_v3_3.exe")}, indent=2))
