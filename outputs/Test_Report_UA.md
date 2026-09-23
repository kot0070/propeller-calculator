# Фінальний звіт тестування — Propeller Calculator Professional UA v3

**Автор програми: Ivan Soprun**  
Версія: 3.3.0  
Платформа: Windows 10/11 x64, portable one-file EXE, offline, asInvoker  
EXE-пакувальник: PyInstaller 6.21.0 з офіційного PyPI  
Інтерфейс: PySide6 6.9.1 (Qt), з офіційного PyPI  
Цифровий підпис: **NotSigned** — сертифікат підпису не надавався; автентичність перевіряти за SHA-256.

## Підсумок

- Статус: **PASS**.
- Моделей: **1,053**.
- Характеристик: **335,434**.
- Джерел: **7**.
- Моделей із фізичними випробуваннями: **250**.
- Моделей лише з прогнозом: **379**.
- Геометричних точок: **24,643**; RPM-limit rows: **887**.
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
| APC Product Data File 2026-02 | 1 | 1 | 0 | 843 | 0 | `4C0DD96F7CB04DB95D721A11123FB2ED47956DFA136138A8062D5EE9B4AEB8F2` |
| ENOLA Propeller Database 2026 (attached Propeller_Database archive) | 190 | 190 | 0 | 13 | 5025 | `C9E92C5E5BE0AEADAB0D42E2DED5D85822F3E8B8E00029D434A68822E108CA98` |
| Attached CFD aircraft configuration dataset | 3 | 3 | 0 | 0 | 0 | `0BC48F9B4B8229FEC2C4968D96C5C5FA810AF54CFF5BDE8BD7DA9BDE01F697A1` |
| UIUC Propeller Database Volumes 1-4 | 3652 | 3651 | 1 | 245 | 30222 | `089B66DB10391B9A3AD53AAC1B95FA63D24BB7130F0DC1E6A4E7D971C5645995` |
| APC Propeller RPM Limits Rev 5 | 1 | 1 | 0 | 0 | 0 | `67527A6064BAF0128D75CFE50E04F1FFDA7CD04FADB5C001CD8C586A1572ED5B` |
| APC PERFILES performance predictions 2026-02 | 460 | 460 | 0 | 454 | 300187 | `FDEAEE160617B4006C6A96335050091AF4349A1DD33362A1B1B6E74DFA77561F` |
| APC PE0 geometry files 2026-02 | 453 | 453 | 0 | 453 | 0 | `85A97375DD9FFAEB38022CEF1B5D79AC86C56F2960E9917369AD0E55CE37DF38` |

## Єдиний нерозпізнаний файл

`UIUC_2022/images/pspbrwse.jbf`, 9,804 bytes, SHA-256
`045138E4253ACA536BB75BBC818F1EB453002BA6F44828E78B8F26444AC6032A`.
Причина: службовий бінарний thumbnail-файл Paint Shop Pro без інженерних даних; файл не відкинуто мовчки.

## Відомі обмеження

- Без Rm/I0 моторна частина прямо позначається як спрощена оцінка.
- Water mode переносить безрозмірні коефіцієнти повітряних даних на густину води, показує обов’язкове попередження й не моделює кавітацію.
- Модель рами є спрощеною балочною оцінкою; резонанс і міцність перевіряються фізично.
- EXE не має комерційного code-signing сертифіката; Windows SmartScreen може показати попередження.
