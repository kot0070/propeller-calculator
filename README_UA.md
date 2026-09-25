# Propeller Calculator Professional UA — 3.3.0

[English](README.md)

Автор: **Ivan Soprun**. Офлайн Windows-застосунок для розрахунку й порівняння пропелерів, з українським та англійським інтерфейсом.

Репозиторій містить оригінальний код, тести, скрипти обробки даних, матеріали збірки, інструкцію та звіти. Готовий EXE, вбудована база та вихідні набори даних збережені у [приватному релізі v3.3.0](https://github.com/kot0070/propeller-calculator/releases/tag/v3.3.0).

## MVP-статус — 3.3.0

Статус: **MVP RELEASE CANDIDATE**. Усі 14 релізних гейтів PASS.
Тестові набори: 41 unit + 14-блоковий UI functional, усі зелені.
Workbook: 127 тестів — 58 PASS / 62 N/A (платформи поза скоупом, з доказами) / 7 NOT STARTED (усі не-гейтові).
Продукційна БД: 1053 моделі / 335434 точки.
EXE: `Propeller_Calculator_Professional_UA_v3_3.exe`.
Звіт по агентах: \work/AGENT_PERFORMANCE_REPORT.md\ (сильні/слабкі сторони, рекомендації).
Відомі залишки: CI workflow очікує token scope; занотовано живе прослуховування скрінрідера + переклади другого двійника; відкриті ручні смакові рядки (T043 CTA тощо).

## Готова програма

Завантажте `Propeller_Calculator_Professional_UA_v3_3.exe` з релізу. Python та інсталяція не потрібні. Інструкція: [README_UA.md](outputs/README_UA.md); повний PDF — у `outputs/`.

## Запуск із коду

Потрібен Python 3.11+ для Windows. Команди PowerShell із кореня репозиторію:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Завантажте `propellers-database-v3.3.0.zip` з релізу в корінь проєкту й розпакуйте:

```powershell
New-Item -ItemType Directory -Path work\build -Force
Expand-Archive -LiteralPath .\propellers-database-v3.3.0.zip -DestinationPath .\work\build
.\.venv\Scripts\python.exe .\src\main.py
```

Для завантаження через авторизований GitHub CLI можна використати:

```powershell
gh release download v3.3.0 --repo kot0070/propeller-calculator --pattern propellers-database-v3.3.0.zip
```

База `work/build/propellers.db` містить 1 053 моделі та 335 434 характеристики. Застосунок створює окрему робочу копію у `%LOCALAPPDATA%\IvanSoprun\PropellerCalculatorProfessionalUA`.

## Тести

Після відновлення бази:

```powershell
$env:PYTHONPATH = "$PWD\src"
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## Збірка EXE

```powershell
.\.venv\Scripts\python.exe -m pip install "PyInstaller>=6,<7"
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm PropellerCalculator.spec
```

Результат: `dist/Propeller_Calculator_Professional_UA_v3_3.exe`. Кореневий spec використовує відносні шляхи; попередній оригінальний spec залишено у `work/pyinstaller/`.

## Дані та контроль цілісності

- `propellers-database-v3.3.0.zip` — повна початкова база, потрібна для запуску з коду й тестів.
- `propeller-source-data-v3.3.0.zip` — усі збережені вихідні файли; розпаковуються у `work/extracted/` для дослідження або відтворення імпорту.
- `SHA256SUMS.txt` у релізі — контрольні суми завантажуваних файлів.
- `outputs/` — оригінальні аудит, інструкція, скриншот та звіти попередньої розробки. Їхні результати описують перевірки на момент створення версії.

Скрипти у `work/scripts/` та інвентарі у `work/source_audit/` збережено з оригіналу; деякі допоміжні скрипти містять шляхи й залежності початкового середовища розробки. Вони не потрібні для звичайного запуску.
