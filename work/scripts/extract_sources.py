from __future__ import annotations

import hashlib
import json
import pathlib
import shutil
import zipfile


ARCHIVES = {
    "Propeller_Database": pathlib.Path(r"C:\Users\kot00\Downloads\Propeller_Database.zip"),
    "Dataset": pathlib.Path(r"C:\Users\kot00\Downloads\Dataset.zip"),
    "UIUC-propDB": pathlib.Path(r"C:\Users\kot00\Downloads\UIUC-propDB.zip"),
    "APC_PERFILES_202602": pathlib.Path(r"C:\Users\kot00\Downloads\PERFILES_WEB-202602.zipx"),
    "APC_PE0_202602": pathlib.Path(r"C:\Users\kot00\Downloads\PE0-FILES_WEB-202602.zipx"),
}


def safe_target(root: pathlib.Path, member_name: str) -> pathlib.Path:
    normalized = member_name.replace("\\", "/")
    relative = pathlib.PurePosixPath(normalized)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("unsafe archive path")
    target = root.joinpath(*relative.parts).resolve()
    if root.resolve() not in target.parents and target != root.resolve():
        raise ValueError("path escapes extraction root")
    return target


def extract_one(label: str, archive_path: pathlib.Path, output_root: pathlib.Path) -> list[dict]:
    root = output_root / label
    root.mkdir(parents=True, exist_ok=True)
    records: list[dict] = []
    with zipfile.ZipFile(archive_path) as archive:
        for info in archive.infolist():
            record = {
                "source": label,
                "archive": str(archive_path),
                "member": info.filename,
                "is_directory": info.is_dir(),
                "expected_bytes": info.file_size,
                "crc32": f"{info.CRC:08X}",
                "compression_method": info.compress_type,
                "status": "pending",
                "error": None,
            }
            try:
                target = safe_target(root, info.filename)
                if info.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    record["status"] = "directory"
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    digest = hashlib.sha256()
                    actual = 0
                    with archive.open(info, "r") as source, target.open("wb") as destination:
                        while chunk := source.read(1024 * 1024):
                            destination.write(chunk)
                            digest.update(chunk)
                            actual += len(chunk)
                    record["status"] = "extracted"
                    record["path"] = str(target)
                    record["actual_bytes"] = actual
                    record["sha256"] = digest.hexdigest().upper()
                    if actual != info.file_size:
                        raise ValueError(f"size mismatch: expected {info.file_size}, got {actual}")
            except Exception as exc:
                record["status"] = "error"
                record["error"] = f"{type(exc).__name__}: {exc}"
            records.append(record)
    return records


def extract_nested_zips(output_root: pathlib.Path, records: list[dict]) -> list[dict]:
    nested_records: list[dict] = []
    for record in records:
        if record.get("status") != "extracted" or not str(record.get("path", "")).lower().endswith(".zip"):
            continue
        nested_path = pathlib.Path(record["path"])
        relative_name = nested_path.relative_to(output_root).as_posix().replace("/", "__")
        try:
            nested_records.extend(extract_one(f"_nested/{relative_name}", nested_path, output_root))
        except Exception as exc:
            nested_records.append({
                "source": record["source"],
                "archive": str(nested_path),
                "member": None,
                "status": "error",
                "error": f"{type(exc).__name__}: {exc}",
                "nested_container": True,
            })
    return nested_records


def main() -> None:
    output_root = pathlib.Path("work/extracted").resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    all_records: list[dict] = []
    for label, archive in ARCHIVES.items():
        records = extract_one(label, archive, output_root)
        all_records.extend(records)
        errors = sum(record["status"] == "error" for record in records)
        extracted = sum(record["status"] == "extracted" for record in records)
        print(f"{label}: extracted={extracted}, errors={errors}")
    nested = extract_nested_zips(output_root, all_records)
    all_records.extend(nested)
    print(f"nested archive members: extracted={sum(r.get('status') == 'extracted' for r in nested)}, errors={sum(r.get('status') == 'error' for r in nested)}")
    manifest = pathlib.Path("work/source_audit/extraction_manifest.json")
    manifest.write_text(json.dumps({"records": all_records}, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
