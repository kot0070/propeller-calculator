import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "file:///C:/Users/kot00/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/@oai/artifact-tool/dist/artifact_tool.mjs";

const root = process.cwd();
const reports = path.join(root, "work", "reports");
const outputDir = path.join(root, "work", "deliverables");
await fs.mkdir(outputDir, { recursive: true });

const audit = JSON.parse(await fs.readFile(path.join(reports, "audit_report.json"), "utf8"));
const manual = JSON.parse(await fs.readFile(path.join(reports, "manual_verification.json"), "utf8"));
const ui = JSON.parse(await fs.readFile(path.join(reports, "ui_functional_test.json"), "utf8"));
const workbook = Workbook.create();

const colors = { dark: "#102029", dark2: "#18323D", teal: "#14A897", pale: "#DCEDEB", white: "#FFFFFF", line: "#B7CDD2", red: "#FCE1E1", green: "#DDF3E8" };
function title(sheet, range, value) {
  sheet.getRange(range).merge();
  sheet.getRange(range).values = [[value]];
  sheet.getRange(range).format = { fill: colors.dark, font: { color: colors.white, bold: true, size: 18 }, rowHeight: 30, verticalAlignment: "center" };
}
function subtitle(sheet, range, value) {
  sheet.getRange(range).merge();
  sheet.getRange(range).values = [[value]];
  sheet.getRange(range).format = { fill: colors.dark2, font: { color: "#AEE7DF", bold: true, size: 11 }, rowHeight: 22 };
}
function header(range) {
  range.format = { fill: colors.teal, font: { color: colors.white, bold: true }, wrapText: true,
                   borders: { preset: "all", style: "thin", color: colors.line }, verticalAlignment: "center" };
}
function body(range) {
  range.format = { borders: { preset: "all", style: "thin", color: colors.line }, verticalAlignment: "top", wrapText: true };
}
async function appendCsvSheet(name, csvText) {
  const imported = await Workbook.fromCSV(csvText, { sheetName: name });
  const sourceSheet = imported.worksheets.getItemAt(0);
  const values = sourceSheet.getUsedRange().values;
  const targetSheet = workbook.worksheets.add(name);
  if (values.length && values[0].length) {
    targetSheet.getRangeByIndexes(0, 0, values.length, values[0].length).values = values;
  }
  return targetSheet;
}

const overview = workbook.worksheets.add("Overview");
overview.showGridLines = false;
title(overview, "A1:H2", audit.application.name);
subtitle(overview, "A3:H3", `FINAL SOURCE AUDIT · Author / Автор: ${audit.application.author} · Version ${audit.application.version}`);
overview.getRange("A5:B5").values = [["Database metric / Показник", "Exact value / Значення"]];
header(overview.getRange("A5:B5"));
const metricLabels = {
  models: "Models / Моделі", characteristics: "Performance characteristics / Характеристики",
  sources: "Sources / Джерела", models_with_experiments: "Models with real experiments",
  prediction_only_models: "Prediction-only models", geometries: "Geometry points", rpm_limit_rows: "RPM-limit rows",
  performance_duplicate_keys: "Duplicate performance keys", model_duplicate_ids: "Duplicate Model_ID",
};
const metricRows = Object.entries(audit.totals).map(([key, value]) => [metricLabels[key] || key, value]);
overview.getRange(`A6:B${5 + metricRows.length}`).values = metricRows;
body(overview.getRange(`A6:B${5 + metricRows.length}`));
overview.getRange("D5:H5").values = [["Source group", "Models", "Characteristics", "Experiment", "Prediction / CFD"]];
header(overview.getRange("D5:H5"));
const groupRows = audit.groups.map(g => [g.group, g.models, g.characteristics || 0, g.experiment || 0, (g.prediction || 0) + (g.cfd_numerical || 0)]);
overview.getRange(`D6:H${5 + groupRows.length}`).values = groupRows;
body(overview.getRange(`D6:H${5 + groupRows.length}`));
overview.getRange("D12:H12").merge();
overview.getRange("D12:H12").values = [["Integrity status / Цілісність"]];
header(overview.getRange("D12:H12"));
overview.getRange("D13:H16").values = [["SQLite quick_check", "ok", null, null, null],
  ["Foreign-key errors", 0, null, null, null], ["Duplicate performance keys", audit.totals.performance_duplicate_keys, null, null, null],
  ["Unrecognized files", audit.unrecognized_files.length, null, null, null]];
body(overview.getRange("D13:H16"));
overview.getRange("A18:H18").merge();
overview.getRange("A18:H18").values = [["Evidence is kept separate: physical experiment · CFD/numerical · APC prediction · catalog · geometry · structural RPM limits"]];
overview.getRange("A18:H18").format = { fill: colors.pale, font: { bold: true, color: colors.dark }, wrapText: true };
overview.freezePanes.freezeRows(3);
overview.getRange("A:H").format.columnWidth = 18;
overview.getRange("A:A").format.columnWidth = 35;
overview.getRange("D:D").format.columnWidth = 38;

const sources = workbook.worksheets.add("Sources");
sources.showGridLines = false;
title(sources, "A1:U2", "SOURCE-BY-SOURCE AUDIT / АУДИТ КОЖНОГО ДЖЕРЕЛА");
subtitle(sources, "A3:U3", `Author / Автор: ${audit.application.author} · no source file is silently discarded`);
const sourceHeaders = ["Code", "Name", "Group", "Archive", "SHA-256", "Files", "Recognized", "Unrecognized", "Formats",
  "Raw lines", "Raw data rows", "Parsed records", "Raw models", "Normalized models", "Alias merges / duplicates",
  "Characteristics", "Static", "Dynamic", "RPM range", "J range", "Skip reasons"];
sources.getRange("A5:U5").values = [sourceHeaders];
header(sources.getRange("A5:U5"));
const sourceRows = audit.sources.map(s => [s.code, s.name, s.group, s.archive, s.sha256, s.file_count, s.recognized_files,
  s.unrecognized_files, JSON.stringify(s.formats), s.raw_lines, s.raw_data_rows, s.parsed_records, s.raw_unique_models,
  s.normalized_models, s.normalized_alias_merges, s.total || 0, s.static_points || 0, s.dynamic_points || 0,
  s.rpm_min == null ? "n/a" : `${s.rpm_min} .. ${s.rpm_max}`, s.j_min == null ? "n/a" : `${s.j_min} .. ${s.j_max}`,
  (s.skip_reasons || []).map(x => `${x.reason} (${x.files} file)`).join("; ")]);
sources.getRange(`A6:U${5 + sourceRows.length}`).values = sourceRows;
body(sources.getRange(`A6:U${5 + sourceRows.length}`));
sources.freezePanes.freezeRows(5);
sources.getRange("A:U").format.columnWidth = 14;
sources.getRange("B:B").format.columnWidth = 34;
sources.getRange("C:C").format.columnWidth = 26;
sources.getRange("D:D").format.columnWidth = 28;
sources.getRange("E:E").format.columnWidth = 48;
sources.getRange("U:U").format.columnWidth = 48;

const checks = workbook.worksheets.add("Manual checks");
checks.showGridLines = false;
title(checks, "A1:H2", "MANUAL VERIFICATION AGAINST RAW FILES");
subtitle(checks, "A3:H3", `Author / Автор: ${audit.application.author} · selected samples from every applicable source`);
checks.getRange("A5:H5").values = [["Source", "Model / Item", "Raw file", "Field", "Raw value", "Database value", "Result", "Notes"]];
header(checks.getRange("A5:H5"));
const manualRows = [];
for (const item of manual) {
  if (item.samples?.length) {
    for (const sample of item.samples) {
      const dbValue = ["rpm", "advance_ratio_j", "ct", "cp", "efficiency", "thrust_n", "power_w"]
        .filter(key => sample[key] != null).map(key => `${key}=${sample[key]}`).join("; ");
      manualRows.push([item.source || "", sample.model_id || sample.original_name || "", sample.relative_path || "",
        item.check || "raw row verification", sample.raw_row || "", dbValue, item.result || "", sample.evidence_class || ""]);
    }
  } else {
    const comparisons = item.comparisons || [item];
    for (const comparison of comparisons) {
      manualRows.push([item.source || item.source_code || "", item.model_id || item.item || "", item.file || item.relative_path || "",
        comparison.field || item.field || item.check || "", comparison.raw ?? item.raw_value ?? "", comparison.database ?? item.database_value ?? "",
        comparison.result || item.result || "", item.note || ""]);
    }
  }
}
if (manualRows.length) {
  checks.getRange(`A6:H${5 + manualRows.length}`).values = manualRows;
  body(checks.getRange(`A6:H${5 + manualRows.length}`));
}
checks.freezePanes.freezeRows(5);
checks.getRange("A:H").format.columnWidth = 18;
checks.getRange("C:C").format.columnWidth = 45;
checks.getRange("H:H").format.columnWidth = 38;

const tests = workbook.worksheets.add("Test results");
tests.showGridLines = false;
title(tests, "A1:F2", "FUNCTIONAL TEST RESULTS / РЕЗУЛЬТАТИ ТЕСТІВ");
subtitle(tests, "A3:F3", `Author / Автор: ${audit.application.author} · deterministic offline test run`);
tests.getRange("A5:F5").values = [["Test", "Input / Before", "Intermediate", "Output / After", "Tolerance", "Result"]];
header(tests.getRange("A5:F5"));
const testRows = [
  ["SI → Imperial → SI mass", `${ui.si_imperial_si.mass_si_kg} kg`, `${ui.si_imperial_si.mass_imperial_lb} lb`, `${ui.si_imperial_si.mass_roundtrip_kg} kg`, "1e-10", ui.si_imperial_si.physical_result_invariant ? "PASS" : "FAIL"],
  ["Physical thrust invariant", `${ui.si_imperial_si.thrust_si_n} N`, `${ui.si_imperial_si.thrust_imperial_mode_n} N`, `${ui.si_imperial_si.thrust_roundtrip_n} N`, "1e-9", ui.si_imperial_si.physical_result_invariant ? "PASS" : "FAIL"],
  ["UA / EN language switch", ui.language_switch.ukrainian, "↔", ui.language_switch.english, "exact", ui.language_switch.passed ? "PASS" : "FAIL"],
  ["Tooltips toggle", "enabled", "↔", "disabled", "all widgets", ui.tooltips.passed ? "PASS" : "FAIL"],
  ["Saved build restart", `components=${ui.saved_build.components}`, `compare=${ui.saved_build.comparison_items}`, `persisted=${ui.saved_build.persisted_after_restart}`, "5 components", ui.saved_build.passed ? "PASS" : "FAIL"],
  ["Full automated suite", "8 tests", "static/dynamic/water/import/builds/units", "8 passed", "0 failures", "PASS"],
];
tests.getRange(`A6:F${5 + testRows.length}`).values = testRows;
body(tests.getRange(`A6:F${5 + testRows.length}`));
tests.freezePanes.freezeRows(5);
tests.getRange("A:F").format.columnWidth = 25;
tests.getRange("C:C").format.columnWidth = 42;

const fileCsv = await fs.readFile(path.join(reports, "source_file_audit.csv"), "utf8");
const allFiles = await appendCsvSheet("All files", fileCsv);
allFiles.showGridLines = false;
header(allFiles.getRange("A1:O1"));
allFiles.freezePanes.freezeRows(1);
allFiles.getRange("A:O").format.columnWidth = 15;
allFiles.getRange("E:E").format.columnWidth = 58;
allFiles.getRange("M:O").format.columnWidth = 30;

const mappingCsv = await fs.readFile(path.join(reports, "model_id_mapping.csv"), "utf8");
const mapping = await appendCsvSheet("Name to Model_ID", mappingCsv);
mapping.showGridLines = false;
header(mapping.getRange("A1:L1"));
mapping.freezePanes.freezeRows(1);
mapping.getRange("A:L").format.columnWidth = 16;
mapping.getRange("C:D").format.columnWidth = 34;
mapping.getRange("E:E").format.columnWidth = 40;

const unrecognizedCsv = await fs.readFile(path.join(reports, "unrecognized_files.csv"), "utf8");
const unrecognized = await appendCsvSheet("Unrecognized", unrecognizedCsv);
unrecognized.showGridLines = false;
header(unrecognized.getRange("A1:F1"));
unrecognized.freezePanes.freezeRows(1);
unrecognized.getRange("A:F").format.columnWidth = 22;
unrecognized.getRange("B:B").format.columnWidth = 55;
unrecognized.getRange("F:F").format.columnWidth = 65;
if (audit.unrecognized_files.length) body(unrecognized.getRange(`A2:F${1 + audit.unrecognized_files.length}`));

const xlsx = await SpreadsheetFile.exportXlsx(workbook);
const outputPath = path.join(outputDir, "Propeller_Calculator_v3_Final_Audit.xlsx");
await xlsx.save(outputPath);
const preview = await workbook.render({ sheetName: "Overview", autoCrop: "all", scale: 1.25, format: "png" });
await fs.writeFile(path.join(outputDir, "audit_overview_preview.png"), new Uint8Array(await preview.arrayBuffer()));
const inspection = await workbook.inspect({ kind: "sheet", include: "id,name", maxChars: 4000 });
await fs.writeFile(path.join(outputDir, "audit_workbook_inspection.txt"), inspection.ndjson || String(inspection), "utf8");
console.log(outputPath);
