from __future__ import annotations

import json
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate, Frame, Image, KeepTogether, LongTable, PageBreak, PageTemplate,
    Paragraph, Spacer, Table, TableStyle,
)


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "work" / "deliverables"
OUTPUT.mkdir(parents=True, exist_ok=True)
AUDIT = json.loads((ROOT / "work" / "reports" / "audit_report.json").read_text(encoding="utf-8"))

font_dir = Path("C:/Windows/Fonts")
pdfmetrics.registerFont(TTFont("Segoe", font_dir / "segoeui.ttf"))
pdfmetrics.registerFont(TTFont("Segoe-Bold", font_dir / "segoeuib.ttf"))

DARK = colors.HexColor("#102029")
DARK2 = colors.HexColor("#18323D")
TEAL = colors.HexColor("#14A897")
PALE = colors.HexColor("#DCEDEB")
MUTED = colors.HexColor("#5F747D")
LINE = colors.HexColor("#B7CDD2")

styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name="CoverTitle", fontName="Segoe-Bold", fontSize=25, leading=30, textColor=colors.white,
                          alignment=TA_LEFT, spaceAfter=10))
styles.add(ParagraphStyle(name="CoverSub", fontName="Segoe", fontSize=12, leading=17, textColor=colors.HexColor("#B8DAD7")))
styles.add(ParagraphStyle(name="H1x", fontName="Segoe-Bold", fontSize=18, leading=22, textColor=DARK, spaceBefore=4, spaceAfter=9))
styles.add(ParagraphStyle(name="H2x", fontName="Segoe-Bold", fontSize=13, leading=17, textColor=colors.HexColor("#087E72"), spaceBefore=9, spaceAfter=5))
styles.add(ParagraphStyle(name="Bodyx", fontName="Segoe", fontSize=9.3, leading=13.2, textColor=DARK, spaceAfter=5))
styles.add(ParagraphStyle(name="Smallx", fontName="Segoe", fontSize=8, leading=10.5, textColor=MUTED, spaceAfter=3))
styles.add(ParagraphStyle(name="Bulletx", fontName="Segoe", fontSize=9.2, leading=13, textColor=DARK, leftIndent=13, firstLineIndent=-8, bulletIndent=3, spaceAfter=2))
styles.add(ParagraphStyle(name="Codex", fontName="Segoe", fontSize=9.2, leading=13, textColor=DARK,
                          backColor=colors.HexColor("#EEF4F4"), borderColor=LINE, borderWidth=0.5,
                          borderPadding=6, spaceBefore=4, spaceAfter=6))
styles.add(ParagraphStyle(name="Captionx", fontName="Segoe", fontSize=7.6, leading=10, textColor=MUTED,
                          alignment=TA_CENTER, spaceBefore=3, spaceAfter=8))
styles.add(ParagraphStyle(name="Warningx", fontName="Segoe-Bold", fontSize=9.2, leading=13, textColor=colors.HexColor("#8B2E26"),
                          backColor=colors.HexColor("#FBE8E5"), borderColor=colors.HexColor("#DCA39C"), borderWidth=0.6,
                          borderPadding=7, spaceBefore=5, spaceAfter=7))


def footer(canvas, document) -> None:
    canvas.saveState()
    canvas.setAuthor("Ivan Soprun")
    canvas.setTitle("Propeller Calculator Professional UA v3 - Українська інструкція")
    canvas.setFont("Segoe", 7.4)
    canvas.setFillColor(MUTED)
    canvas.drawString(18 * mm, 10 * mm, "Propeller Calculator Professional UA v3 · Автор: Ivan Soprun")
    canvas.drawRightString(192 * mm, 10 * mm, f"Сторінка {document.page}")
    canvas.setStrokeColor(TEAL)
    canvas.setLineWidth(0.6)
    canvas.line(18 * mm, 14 * mm, 192 * mm, 14 * mm)
    canvas.restoreState()


doc = BaseDocTemplate(str(OUTPUT / "Propeller_Calculator_v3_Інструкція_UA.pdf"), pagesize=A4,
                      leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=18 * mm,
                      title="Propeller Calculator Professional UA v3 - Українська інструкція", author="Ivan Soprun")
frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="normal")
doc.addPageTemplates([PageTemplate(id="all", frames=frame, onPage=footer)])
story = []


def p(text: str, style: str = "Bodyx") -> None:
    story.append(Paragraph(text, styles[style]))


def bullet(text: str) -> None:
    story.append(Paragraph("• " + text, styles["Bulletx"]))


def shot(filename: str, caption: str, width: float = 174 * mm) -> None:
    source = ROOT / "work" / "visual_qa" / filename
    probe = Image(str(source))
    height = width * probe.imageHeight / probe.imageWidth
    image = Image(str(source), width=width, height=height)
    image.hAlign = "CENTER"
    story.append(image)
    p(caption, "Captionx")


# Cover
cover = Table([[Paragraph("PROPELLER CALCULATOR<br/>PROFESSIONAL UA v3", styles["CoverTitle"])],
               [Paragraph("Професійний автономний калькулятор силової установки та база характеристик пропелерів", styles["CoverSub"])],
               [Paragraph("Windows 10/11 x64 · Portable one-file EXE · Offline", styles["CoverSub"])],
               [Paragraph("Автор програми / Author: <b>Ivan Soprun</b>", styles["CoverSub"])]],
              colWidths=[174 * mm], rowHeights=[50 * mm, 27 * mm, 13 * mm, 16 * mm])
cover.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), DARK), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                           ("LEFTPADDING", (0, 0), (-1, -1), 14 * mm), ("RIGHTPADDING", (0, 0), (-1, -1), 10 * mm),
                           ("LINEBELOW", (0, 0), (-1, 0), 2, TEAL)]))
story.append(Spacer(1, 25 * mm))
story.append(cover)
story.append(Spacer(1, 13 * mm))
p("Версія документа: 3.3 · Повний початковий аудит, база і результати тестів поставляються поруч із програмою.", "Smallx")
story.append(PageBreak())

p("1. Призначення та безпечне використання", "H1x")
p("Програма оцінює робочу точку зв’язки мотор-пропелер-батарея-ESC, тягу, струм, потужність, момент, час роботи, запаси компонентів, аеродинамічну та системну ефективність. Вона також переглядає сирі характеристики, зберігає збірки, порівнює варіанти й виконує спрощену перевірку рами.")
p("Важливо: розрахунок не замінює стендові випробування, контроль температури й вібрацій, перевірку кріплень, вимоги виробника, аналіз кавітації у воді або сертифікацію конструкції.", "Warningx")
p("Системні вимоги", "H2x")
bullet("Windows 10 або Windows 11, x64; права адміністратора не потрібні.")
bullet("Excel, Python та інтернет не потрібні. Всі залежності й початкова SQLite-база вбудовані в EXE.")
bullet("Підтримуються дисплеї 1366×768 і 1920×1080 та масштабування Windows 100-200%. На вузькому логічному екрані калькулятор переходить у вертикальне компонування зі смугою прокрутки.")
p("Перший запуск", "H2x")
bullet("Запустіть EXE з будь-якої доступної для читання папки. Однофайловий EXE може стартувати довше при першому запуску, бо розпаковує Qt-компоненти у тимчасову папку.")
bullet("Робоча база автоматично створюється в <b>%LocalAppData%\\IvanSoprun\\PropellerCalculatorProfessionalUA\\propellers.db</b>.")
bullet("Новий EXE не перезаписує робочу базу, налаштування або збережені збірки.")
shot("1366x768_1_Калькулятор.png", "Головний екран у роздільності 1366×768, SI, українська мова.")

p("2. Верхня панель: мова, одиниці, підказки", "H1x")
bullet("<b>УКР / ENG</b> перемикає назви вкладок, режими калькулятора, поля, таблиці, кнопки, графіки, довідку збірок, повідомлення та методику без перезапуску.")
bullet("<b>SI / Imperial</b> змінює введення та показ довжини, маси, швидкості, сили, моменту й потужності. Внутрішні величини завжди залишаються SI.")
bullet("Перемикання SI → Imperial → SI не змінює фізичний результат. Тест: 1.5 kg → 3.306933933 lb → 1.5 kg; обчислена тяга незмінна до 1×10⁻⁹ N.")
bullet("Прапорець <b>ПІДКАЗКИ ПРИ НАВЕДЕННІ</b> вмикає або вимикає hover-popup. Пояснення також показується у стабільній контекстній панелі після наведення/фокусування, а кнопка <b>?</b> відкриває велике вікно з повним текстом. Для кожного основного поля наведено зміст, джерело, вплив збільшення/зменшення, типовий діапазон, формулу й критичність.")
p("3. Два режими калькулятора", "H1x")
bullet("<b>Простий режим</b> - окремий швидкий калькулятор з обов'язковими параметрами, шістьма головними результатами, дворядковим порівнянням і графіками тяги/струму.")
bullet("<b>Інженерний режим</b> - окремий повний калькулятор з Rm, I0, лімітами мотора, густини, усіма запасами, sweep, п'ятьма графіками та відкритими попередженнями.")
bullet("Поля двох режимів синхронізовані: зміна моделі або числа в одному режимі відразу переноситься в інший без втрати точності.")
p("Відтворення випробування і власні параметри", "H2x")
bullet("<b>Відтворити випробування з бази</b> вибирає конкретну вихідну характеристику початкового файла й фіксує її RPM та J. Для APC:8X9, наприклад, характеристика UIUC 6395 RPM дає 57.50 W, і незалежний математичний рядок при тих самих умовах також дає 57.50 W.")
bullet("<b>Власні параметри</b> визначають RPM із KV, напруги, газу та моторної моделі. Ручна зміна робочого поля автоматично вмикає цей режим. Вибір іншого пропелера знову завантажує його вихідну характеристику з бази.")
bullet("Propeller-файли містять RPM/J/Ct/Cp/тягу/потужність, але зазвичай не містять модель мотора, батарею, KV, ESC чи масу апарата. Автоматично підібрані S, напруга, KV, C та ESC явно позначені як <b>похідна рекомендація, не параметри тесту</b>.")
p("Два незалежно показані рядки результату", "H2x")
bullet("<b>Вихідна характеристика бази</b> - вибраний у режимі відтворення або найближчий для власних параметрів фактичний рядок початкового файла: RPM, J, Ct, Cp, η, наявні тяга/потужність і точний шлях джерела. Інтерполяція в цьому рядку не виконується, відсутні значення залишаються n/a.")
bullet("<b>Математичний розрахунок</b> - незалежний результат після Ct/Cp та формул. Пояснення під таблицею показує співвідношення RPM, кубічний множник P∝RPM³ і різницю потужності. Тяга та механічна потужність у таблиці наведені на один мотор; верхня картка - сумарна електрична потужність усіх моторів.")
data = [
    ["Поле", "Звідки взяти", "Основний вплив"],
    ["Model_ID", "Маркування лопаті/упаковки", "Вибирає діаметр, крок і Ct/Cp-криві"],
    ["Medium", "air або water", "У воді ρ≈997 kg/m³; кавітація не моделюється"],
    ["Battery type", "LiPo / Li-ion / LiFePO4", "Ucell 3.7 / 3.6 / 3.2 V і корисна ємність"],
    ["Voltage", "Телеметрія або S×Ucell", "Підвищує RPM, струм і потужність"],
    ["Throttle", "Команда 0-100%", "Ефективна напруга ≈ U×throttle"],
    ["KV", "Паспорт мотора", "RPM/V без навантаження"],
    ["Speed", "Розрахункова швидкість потоку", "Визначає J=V/(nD); 0 - статика"],
    ["Mass", "Зважування готового апарата", "Визначає T/W"],
    ["ESC, Ah, C, S", "Паспорти ESC і батареї", "Запаси струму та час роботи"],
    ["Rm, I0", "Моторна карта або стенд", "Баланс моментів і втрати мотора"],
]
table = LongTable([[Paragraph(str(cell), styles["Smallx"]) for cell in row] for row in data], colWidths=[35 * mm, 58 * mm, 81 * mm], repeatRows=1)
table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), TEAL), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                           ("FONTNAME", (0, 0), (-1, 0), "Segoe-Bold"), ("GRID", (0, 0), (-1, -1), 0.4, LINE),
                           ("VALIGN", (0, 0), (-1, -1), "TOP"), ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F2F6F7")])]))
story.append(table)
p("Результати", "H2x")
bullet("Компактні картки: загальна тяга, загальний струм, <b>загальна електрична потужність</b>, RPM, T/W, час, запаси ESC/мотора/батареї, структурний RPM і достовірність. Значення форматуються без нечитабельного запису на кшталт 1.36e+03 W; великі значення показуються у kW.")
bullet("Дві окремі шкали: аеродинамічна ефективність пропелера та орієнтовна ефективність усієї силової установки.")
bullet("Sweep перебирає допустимі S, напругу й газ, відкидає недостатню тягу та перевищення лімітів і показує оптимальну точку, рекомендовані RPM/газ/напругу/S, тягу та струм.")
bullet("Без Rm або I0 програма явно пише «ОЦІНКА ЗА СПРОЩЕНОЮ МОДЕЛЛЮ» та перелічує відсутні параметри.")
bullet("Графіки навантаження будуються у 10 точках від 10% до 100% газу: тяга, сумарний струм, електрична потужність, RPM, аеродинамічна й системна ефективність. Жовта вертикаль показує поточний газ, пунктирні лінії - ліміти ESC, батареї, мотора та структурного RPM.")

p("Два вбудовані навчальні приклади", "H2x")
bullet("<b>Приклад 1 — дані бази:</b> APC:8X9, 6395 RPM, J=0, Ct=0.1115, Cp=0.1119. Вихідний та математичний рядки дають приблизно 57.50 W механічної потужності одного пропелера. Верхня картка є сумарною електричною потужністю всієї установки, тому напряму з 57.50 W не порівнюється.")
bullet("<b>Приклад 2 — власна збірка:</b> APC:10X5, LiPo 4S/14.8 V, 500 KV, 100%, 4 мотори, 1.5 kg, ESC 40 A, 5 Ah 30C. Очікувана спрощена оцінка: 5920 RPM, 21.15 N, 21.25 A, 314.5 W, T/W 1.44, 11.3 хв. Кнопка на сторінці прикладу завантажує всі поля у калькулятор.")

p("4. База даних та пошук характеристик", "H1x")
shot("1366x768_2_База даних.png", "База: повністю українські заголовки, загальна статистика, пошук моделі та всі сирі характеристики вибраного Model_ID.")
bullet("Верхні картки окремо показують кількість моделей, характеристик, джерел, моделей із фізичними випробуваннями та моделей лише з прогнозом.")
bullet("Пошук працює за Model_ID, сирою назвою, виробником, серією та SKU. Нижня таблиця містить RPM, J, Ct, Cp, η, тягу, потужність, клас доказів і початковий файл; її можна фільтрувати текстом.")
p("Імпорт і merge", "H2x")
bullet("Підтримуються сумісний propellers.db; ZIP/ZIPX із UIUC, APC PERFILES/PE0 або ENOLA; APC XLSX; підтримувані DAT/PE0. Неоднозначний одиночний CSV відхиляється з поясненням, бо без надійного Model_ID змішування небезпечне.")
bullet("Перед зміною створюється повний backup у LocalAppData. Дані обробляються транзакційно: помилка скасовує зміни.")
bullet("Нові ключі додаються, змінений content_hash оновлюється, незмінні ключі пропускаються, старі відсутні записи не видаляються. Повторний імпорт того самого джерела не збільшує кількість точок.")
bullet("Звіт імпорту показує before/after, додано, оновлено, пропущено, конфлікти й помилки; результат доступний одразу без перезапуску.")
bullet("Кнопка <b>Експорт propellers.db</b> створює цілісну копію робочої SQLite-бази.")

p("5. Збережені збірки", "H1x")
p("Збірка містить назву, опис, пропелер, назви мотора/батареї/ESC/рами, KV, S, ємність, кількість моторів, масу, корисне навантаження, розширені параметри, примітку й дати. Компоненти додатково зберігаються у saved_build_components.")
bullet("Верхня панель «Що саме вводити» докладно пояснює кожне поле та містить приклади. Назва має бути унікальною; мотор/ESC/батарея/рама - з точним виробником і моделлю; опис - призначення та робочий режим; примітка - стендові температури, дата й обмеження.")
bullet("Перед збереженням потрібно виконати потрібний розрахунок: Model_ID, напруга, газ, KV, Rm/I0, батарея, ESC, маса та інші числові параметри автоматично беруться з активного калькулятора.")
bullet("Праворуч є повний склад модулів: польотний контролер/автопілот, PDB, RC-приймач, GPS/GNSS, телеметрія, VTX, антени, камера, підвіс, Remote ID, датчики, шасі, проводка та власні рядки. Для кожного зберігаються модель, кількість і маса одного.")
bullet("Модулі впливають на фізичний результат лише через масу. Натискайте «Врахувати масу в розрахунку», тільки якщо ця маса ще не входить у повну масу апарата. Повторне натискання оновлює, а не дублює вже застосовану масу.")
bullet("Доступні: Зберегти, Оновити, Зберегти як нову, Видалити з підтвердженням, Дублювати, Додати до порівняння, Експорт JSON та Імпорт JSON.")
bullet("Збірки живуть у робочій SQLite-базі й не втрачаються після закриття програми або заміни EXE.")
shot("1366x768_3_Збережені збірки.png", "Збережені збірки: докладна довідка з прикладами, параметри та список конфігурацій.")

p("6. Порівняння", "H1x")
bullet("До таблиці можна додати поточну ручну/каталогову конфігурацію або вибрану збережену збірку.")
bullet("Порівнюються тяга, струм, потужність, момент, поточний і максимальний ηsystem, ηaero, T/W, час, рекомендована напруга, запас RPM, ESC/мотор/батарея, достовірність, джерело та попередження.")
bullet("Критерії: максимальна тяга, максимальний час, мінімальний струм, максимальна ефективність, найкраща сумісність, мінімальна маса. Перше місце позначається зеленим; ризикові рядки - червоним.")

story.append(PageBreak())
p("7. Рама й рекомендації", "H1x")
shot("1366x768_5_Рама.png", "Спрощена перевірка рами та три варіанти пропелер-KV-S із бази.")
bullet("Спочатку вибирається стандартний клас рами 65-1000 mm або «Власний розмір». Діагональ — це відстань між осями найдальших моторів, не зовнішній габарит. Також вводяться геометрія X/H/+/custom, кількість моторів, ширина/товщина променів, матеріал, маса й корисне навантаження.")
bullet("Виводяться відстань осей, максимально рекомендований діаметр із 20 mm зазором, перекриття дисків, напруження, прогин, коефіцієнт міцності та попередження про резонанс.")
bullet("Три рекомендації ранжуються за наявністю експерименту й ефективністю. Орієнтовні KV/S/напруга завжди потребують стендової перевірки.")

p("8. Тестування й відкриті формули", "H1x")
p("Вкладка «Тестування» показує фактичні проміжні величини поточного розрахунку. Значення можна вручну перенести у звичайний калькулятор.")
p("n = RPM / 60; &nbsp;&nbsp; J = V/(n·D)<br/>T = Ct·ρ·n²·D⁴<br/>P = Cp·ρ·n³·D⁵<br/>Q = P/(2πn)<br/>T/W = Ttotal/(m·g)<br/>runtime = usable_fraction(chemistry)·Capacity / Itotal", "Codex")
p("Інтерполяція й екстраполяція", "H2x")
bullet("Статичні точки J=0 інтерполюються окремо по RPM - вони не змішуються з динамічними J-кривими.")
bullet("Динамічні точки: лінійна інтерполяція по J у двох сусідніх RPM-кривих, потім по RPM.")
bullet("Поза таблицею використовується найближчий край, вмикається ознака екстраполяції та зменшується показник достовірності.")
p("Класи достовірності", "H2x")
bullet("experiment: базова достовірність 94%; prediction: 72%; CFD: 66%; numerical/BEMT: 60%; екстраполяція віднімає 25 процентних пунктів.")
bullet("UIUC physical experiment, ENOLA experiment/CFD/BEMT та APC manufacturer prediction зберігаються окремо в кожній точці й показуються в інтерфейсі.")

p("9. Склад початкової бази", "H1x")
totals = AUDIT["totals"]
data = [["Показник", "Точне значення"], ["Моделей", f"{totals['models']:,}"],
        ["Характеристик", f"{totals['characteristics']:,}"], ["Джерел", totals["sources"]],
        ["Моделей із фізичним експериментом", totals["models_with_experiments"]],
        ["Моделей лише з прогнозом", totals["prediction_only_models"]],
        ["Геометричних точок", f"{totals['geometries']:,}"], ["RPM-limit rows", totals["rpm_limit_rows"]],
        ["Дублікатів performance key", totals["performance_duplicate_keys"]], ["Дублікатів Model_ID", totals["model_duplicate_ids"]]]
table = Table(data, colWidths=[115 * mm, 55 * mm])
table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), TEAL), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                           ("FONTNAME", (0, 0), (-1, 0), "Segoe-Bold"), ("FONTNAME", (0, 1), (-1, -1), "Segoe"),
                           ("FONTSIZE", (0, 0), (-1, -1), 9), ("GRID", (0, 0), (-1, -1), 0.4, LINE),
                           ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F2F6F7")])]))
story.append(table)
p("Єдиний нерозпізнаний файл", "H2x")
p("UIUC <b>images/pspbrwse.jbf</b>, SHA-256 045138E4253ACA536BB75BBC818F1EB453002BA6F44828E78B8F26444AC6032A, 9,804 bytes. Це службовий бінарний thumbnail-файл Paint Shop Pro без інженерних даних. Він не відкинутий мовчки - записаний у журналі з причиною.")
p("Повні SHA-256 усіх семи джерел, 4,760 рядків журналу файлів, 2,031 відповідність сирої назви→Model_ID, діапазони RPM/J, причини пропусків і ручні звірки містяться у фінальному XLSX-аудиті.")

p("10. Перевірки перед передачею", "H1x")
checks = ["Python automated suite: 41 unit tests + 14-block UI functional test, all PASS", "SQLite quick_check = ok; foreign_key_check = 0", "Дублікати Model_ID і performance point_key = 0",
          "Повторний імпорт: кількість точок не зростає", "Змінена точка оновлюється; нова додається",
          "Збережена збірка та повний склад accessory rows переживають перезапуск", "SI→Imperial→SI зберігає фізичну тягу",
          "Статичний, динамічний, повітряний і водний режими виконуються",
          "Простий та інженерний калькулятори синхронізовані; вихідна й математична строки відокремлені",
          "APC:8X9 у режимі відтворення: 6395 RPM; вихідна й математична потужність = 57.50 W/мотор",
          "Стандартні рами 65-1000 mm і власний розмір; повний склад модулів із масою",
          "Два навчальні приклади завантажуються безпосередньо у калькулятор",
          "Ручна зміна вмикає Custom; вибір нової моделі повертає її вихідні параметри",
          "LiPo/Li-ion/LiFePO4 змінюють Ucell і корисну частку ємності; перевіряється відповідність S і напруги",
          "П'ять графіків мають по 10 sweep-точок; ефективність має дві окремі серії",
          "UA/EN змінює поля й таблиці; всі зареєстровані підказки та дві контекстні панелі працюють",
          "Усі 8 вкладок відрендерені на 1366×768 і 1920×1080; калькулятор перевірений при 200% DPI"]
for item in checks:
    bullet("PASS - " + item)
p("Після отримання файлів перевірте SHA-256 EXE за допомогою PowerShell:", "H2x")
p("Get-FileHash .\\Propeller_Calculator_Professional_UA_v3_3.exe -Algorithm SHA256", "Codex")
p("Хеш має точно збігатися з SHA256SUMS.txt. Якщо не збігається - не запускайте файл.", "Warningx")

doc.build(story)

markdown = f"""# Propeller Calculator Professional UA v3 - коротка інструкція

**Автор програми: Ivan Soprun**

## Запуск

Запустіть один EXE у Windows 10/11 x64. Python, Excel, інтернет і права адміністратора не потрібні.
Робоча база створюється у `%LocalAppData%\\IvanSoprun\\PropellerCalculatorProfessionalUA\\propellers.db` і не перезаписується при заміні EXE.

## Основний порядок роботи

1. Оберіть УКР/ENG і SI/Imperial.
2. Оберіть «Простий режим» для швидкого підбору або «Інженерний режим» для Rm/I0, повних запасів, sweep та всіх графіків. Поля обох режимів синхронізовані.
3. Виберіть Model_ID. «Відтворити випробування з бази» завантажить RPM/J вихідної характеристики та окремо позначену похідну рекомендацію S/KV/ESC. Ручна зміна поля вмикає «Власні параметри».
4. Виберіть LiPo, Li-ion або LiFePO4, S, середовище, напругу, газ, KV, швидкість, масу й ESC. За можливості введіть Rm та I0; без них результат позначається як спрощена оцінка.
5. Порівняйте дві строки при однакових RPM/J у режимі бази. Таблиця показує механічну потужність одного пропелера, верхня картка - сумарну електричну потужність усіх моторів.
6. Перевірте графіки тяги, струму, потужності, RPM та ефективності, ліміти, попередження і sweep-рекомендацію.
7. Використовуйте «Перевірка формул» для ручного контролю проміжних значень.

## Підказки та збірки

Hover-підказки доповнені контекстною панеллю та великим вікном за кнопкою `?`; їх можна вимкнути глобальним прапорцем.
На вкладці «Збережені збірки» верхня довідка пояснює всі поля. Праворуч зберігається повний склад: польотник/автопілот, PDB, приймач, GPS, телеметрія, VTX, антени, камера, підвіс, Remote ID, датчики, шасі, проводка та власні модулі з кількістю й масою.
У «Методиці» є повний опис можливостей і два приклади з кнопкою автоматичного завантаження у калькулятор.

## База й імпорт

Імпорт - merge із backup і транзакцією. Підтримуються сумісний DB, розпізнані UIUC/APC/ENOLA ZIP/ZIPX, APC XLSX/DAT/PE0.
Старі записи не видаляються, дублікати не множаться. Неоднозначний CSV відхиляється з причиною.

## Точний склад бази

- {totals['models']:,} моделей;
- {totals['characteristics']:,} характеристик;
- {totals['sources']} джерел;
- {totals['models_with_experiments']} моделей із фізичними випробуваннями;
- {totals['prediction_only_models']} моделей лише з прогнозом;
- 0 дублікатів Model_ID і performance key.

Повна інструкція - у PDF, повний аудит - у XLSX. Перевірте `Propeller_Calculator_Professional_UA_v3_3.exe` за `SHA256SUMS.txt` перед запуском.
"""
(OUTPUT / "README_UA.md").write_text(markdown, encoding="utf-8")
print(OUTPUT / "Propeller_Calculator_v3_Інструкція_UA.pdf")
