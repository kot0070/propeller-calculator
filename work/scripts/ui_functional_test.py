from __future__ import annotations

import json
import os
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from propcalc.qt_app import PropellerMainWindow


def main() -> None:
    reports = ROOT / "work" / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="propcalc-ui-test-") as folder:
        database = Path(folder) / "working.db"
        source = sqlite3.connect(ROOT / "work" / "build" / "propellers.db")
        target = sqlite3.connect(database)
        source.backup(target)
        source.close()
        target.close()
        app = QApplication([])
        window = PropellerMainWindow(database)
        window.show()
        app.processEvents()
        window.calculate()
        dual_modes_uk = [window.calculator_modes.tabText(i) for i in range(window.calculator_modes.count())]
        reference_rows = [window.reference_tables[0].item(i, 0).text() for i in range(2)]
        reference_source = window.reference_tables[0].item(0, 8).text()
        chart_counts = {
            "thrust": len(window.thrust_chart.series[0].points),
            "current": len(window.current_chart.series[0].points),
            "power": len(window.power_chart.series[0].points),
            "rpm": len(window.rpm_chart.series[0].points),
            "efficiency_series": len(window.efficiency_chart.series),
        }
        model_index = window.model_combos[0].findData("APC:8X9")
        window.model_combos[0].setCurrentIndex(model_index)
        app.processEvents()
        window.calculate()
        database_point = {
            "mode": window.state["configuration_mode"],
            "reference_point_id": window.state["reference_point_id"],
            "rpm": window.current_result.point.rpm,
            "raw_power": window.reference_tables[0].item(0, 7).text(),
            "math_power": window.reference_tables[0].item(1, 7).text(),
            "total_power_card": window.simple_result_labels["power"].text(),
        }
        kv_widget = window.edit_widgets["kv"][0]
        window._sync_edit_value("kv", "900", kv_widget)
        window.calculate()
        custom_mode = {"mode": window.state["configuration_mode"], "rpm": window.current_result.point.rpm}
        battery_combo = window.combo_widgets["battery_type"][0]
        battery_combo.setCurrentIndex(battery_combo.findData("Li-ion"))
        app.processEvents()
        chemistry = {"type": window.state["battery_type"], "voltage": window.state["voltage"],
                     "mode": window.state["configuration_mode"]}
        next_model_index = window.model_combos[0].findData("APC:9X6")
        window.model_combos[0].setCurrentIndex(next_model_index)
        app.processEvents()
        window.calculate()
        model_reset = {"model": window.selected_model_id, "mode": window.state["configuration_mode"],
                       "battery_type": window.state["battery_type"],
                       "rpm": window.current_result.point.rpm,
                       "reference_rpm": float(window.state["reference_rpm"])}
        thrust_si = window.current_result.total_thrust_n
        mass_si = float(window.state["mass"])
        window._switch_units("Imperial")
        app.processEvents()
        window.calculate()
        thrust_imperial_mode = window.current_result.total_thrust_n
        mass_lb = float(window.state["mass"])
        window._switch_units("SI")
        app.processEvents()
        window.calculate()
        thrust_roundtrip = window.current_result.total_thrust_n
        mass_roundtrip = float(window.state["mass"])
        window._switch_language("en")
        app.processEvents()
        english_tab = window.tabs.tabText(0)
        english_mode = window.calculator_modes.tabText(1)
        english_db_header = window.model_table.horizontalHeaderItem(1).text()
        english_build_header = window.build_table.horizontalHeaderItem(1).text()
        window._switch_language("uk")
        app.processEvents()
        ukrainian_tab = window.tabs.tabText(0)
        ukrainian_mode = window.calculator_modes.tabText(1)
        ukrainian_db_header = window.model_table.horizontalHeaderItem(1).text()
        ukrainian_build_header = window.build_table.horizontalHeaderItem(1).text()
        window._toggle_tooltips(False)
        tips_off = all(not widget.toolTip() for widget, _ in window.tip_widgets)
        window._toggle_tooltips(True)
        tips_on = all(widget.toolTip() for widget, _ in window.tip_widgets)
        window._show_context_help("voltage")
        context_help_lengths = [len(label.text()) for label in window.context_help_labels]
        source_mode_labels = {
            "mode": window.combo_widgets["configuration_mode"][0].itemText(0),
            "condition": window.reference_point_combos[0].toolTip(),
        }
        window._load_source_example()
        app.processEvents()
        source_example = {"model": window.selected_model_id, "mode": window.state["configuration_mode"],
                          "rpm": window.current_result.point.rpm}
        window._load_custom_example()
        app.processEvents()
        custom_example = {"model": window.selected_model_id, "mode": window.state["configuration_mode"],
                          "rpm": window.current_result.point.rpm,
                          "frame_preset": window.state["frame_size_preset"]}
        frame_combo = window.combo_widgets["frame_size_preset"][0]
        frame_450_disabled = not window.edit_widgets["frame_diagonal"][0].isEnabled()
        frame_combo.setCurrentIndex(frame_combo.findData("custom"))
        app.processEvents()
        frame_custom_enabled = window.edit_widgets["frame_diagonal"][0].isEnabled()
        frame_combo.setCurrentIndex(frame_combo.findData("650"))
        app.processEvents()
        frame_preset = {"value": window.state["frame_size_preset"],
                        "diagonal": float(window.state["frame_diagonal"]),
                        "field_disabled": not window.edit_widgets["frame_diagonal"][0].isEnabled()}
        window.tabs.setCurrentIndex(2)
        app.processEvents()
        window.accessory_table.item(3, 0).setCheckState(Qt.CheckState.Checked)
        window.accessory_table.item(3, 2).setText("M10 GNSS")
        app.processEvents()
        window._snapshot_accessories()
        enabled_accessories = [item for item in window.build_accessories if item["enabled"]]
        accessory_mass = sum(item["mass_kg"] * item["quantity"] for item in enabled_accessories)
        mass_before_modules = float(window.state["mass"])
        window._apply_accessory_mass_to_payload()
        mass_after_modules = float(window.state["mass"])
        window._apply_accessory_mass_to_payload()
        mass_after_repeat = float(window.state["mass"])
        window.edits["build_name"].setText("Restart persistence QA")
        window.save_build_new()
        build_id = window.current_build_id
        component_count = window.repository.connection.execute(
            "SELECT COUNT(*) FROM saved_build_components WHERE build_id=?", (build_id,)).fetchone()[0]
        window.add_build_to_compare()
        compare_count = len(window.compare_items)
        window.close()
        reopened = PropellerMainWindow(database)
        persisted = reopened.repository.get_build(build_id) is not None
        reopened.close()
        report = {
            "si_imperial_si": {
                "mass_si_kg": mass_si, "mass_imperial_lb": mass_lb, "mass_roundtrip_kg": mass_roundtrip,
                "thrust_si_n": thrust_si, "thrust_imperial_mode_n": thrust_imperial_mode,
                "thrust_roundtrip_n": thrust_roundtrip,
                "physical_result_invariant": abs(thrust_si - thrust_imperial_mode) < 1e-9 and abs(thrust_si - thrust_roundtrip) < 1e-9,
            },
            "language_switch": {"english": english_tab, "ukrainian": ukrainian_tab,
                                "english_mode": english_mode, "ukrainian_mode": ukrainian_mode,
                                "english_database_header": english_db_header,
                                "ukrainian_database_header": ukrainian_db_header,
                                "english_build_header": english_build_header,
                                "ukrainian_build_header": ukrainian_build_header,
                                "passed": english_tab == "Calculator" and ukrainian_tab == "Калькулятор"
                                and english_mode == "Engineering mode" and ukrainian_mode == "Інженерний режим"
                                and english_db_header == "Original name" and ukrainian_db_header == "Початкова назва"
                                and english_build_header == "Name" and ukrainian_build_header == "Назва"},
            "tooltips": {"disabled": tips_off, "enabled_for_every_registered_widget": tips_on,
                         "context_help_lengths": context_help_lengths,
                         "passed": tips_off and tips_on and len(context_help_lengths) == 2
                         and min(context_help_lengths) > 180},
            "dual_calculators": {"tabs": dual_modes_uk, "count": len(dual_modes_uk),
                                 "passed": dual_modes_uk == ["Простий режим", "Інженерний режим"]},
            "source_vs_math": {"rows": reference_rows, "raw_source": reference_source,
                               "passed": reference_rows == ["Вихідна характеристика бази", "Математичний розрахунок"]
                               and reference_source not in {"", "n/a"}},
            "clear_source_mode": {**source_mode_labels,
                                  "passed": source_mode_labels["mode"] == "Відтворити випробування з бази"
                                  and len(source_mode_labels["condition"]) > 180},
            "database_point_mode": {**database_point,
                "passed": database_point["mode"] == "database"
                and database_point["reference_point_id"] == "7363"
                and abs(database_point["rpm"] - 6395.0) < 1e-9
                and database_point["raw_power"] == database_point["math_power"]
                and "e+" not in database_point["total_power_card"].lower()},
            "custom_and_chemistry": {**custom_mode, **chemistry,
                "passed": custom_mode["mode"] == "custom" and custom_mode["rpm"] > 10000
                and chemistry["type"] == "Li-ion" and chemistry["voltage"] == "14.4"
                and chemistry["mode"] == "custom"},
            "new_model_resets_source_defaults": {**model_reset,
                "passed": model_reset["model"] == "APC:9X6" and model_reset["mode"] == "database"
                and model_reset["battery_type"] == "LiPo"
                and abs(model_reset["rpm"] - model_reset["reference_rpm"]) < 1e-9},
            "load_charts": {"series_points": chart_counts,
                            "current_limits": len(window.current_chart.limits),
                            "passed": all(value == 10 for key, value in chart_counts.items() if key != "efficiency_series")
                            and chart_counts["efficiency_series"] == 2 and len(window.current_chart.limits) >= 2},
            "worked_examples": {"source": source_example, "custom": custom_example,
                                "passed": source_example["model"] == "APC:8X9"
                                and source_example["mode"] == "database" and abs(source_example["rpm"] - 6395) < 1e-9
                                and custom_example["model"] == "APC:10X5"
                                and custom_example["mode"] == "custom"
                                and custom_example["frame_preset"] == "450"},
            "frame_presets": {"default_450_disabled": frame_450_disabled,
                              "custom_enabled": frame_custom_enabled, **frame_preset,
                              "passed": frame_450_disabled and frame_custom_enabled
                              and frame_preset["value"] == "650"
                              and abs(frame_preset["diagonal"] - 0.65) < 1e-12
                              and frame_preset["field_disabled"]},
            "accessory_inventory": {"enabled": len(enabled_accessories), "mass_kg": accessory_mass,
                                    "mass_before": mass_before_modules, "mass_after": mass_after_modules,
                                    "mass_after_repeat": mass_after_repeat,
                                    "passed": len(enabled_accessories) == 5
                                    and abs(accessory_mass - 0.102) < 1e-8
                                    and abs(mass_after_modules - mass_before_modules - accessory_mass) < 1e-8
                                    and abs(mass_after_repeat - mass_after_modules) < 1e-10},
            "saved_build": {"build_id": build_id, "components": component_count,
                            "comparison_items": compare_count, "persisted_after_restart": persisted,
                            "passed": component_count == 10 and compare_count == 1 and persisted},
        }
        report["passed"] = all((report["si_imperial_si"]["physical_result_invariant"],
                                report["language_switch"]["passed"], report["tooltips"]["passed"],
                                report["dual_calculators"]["passed"], report["source_vs_math"]["passed"],
                                report["clear_source_mode"]["passed"],
                                report["database_point_mode"]["passed"], report["custom_and_chemistry"]["passed"],
                                report["new_model_resets_source_defaults"]["passed"],
                                report["load_charts"]["passed"],
                                report["worked_examples"]["passed"], report["frame_presets"]["passed"],
                                report["accessory_inventory"]["passed"],
                                report["saved_build"]["passed"]))
        (reports / "ui_functional_test.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
