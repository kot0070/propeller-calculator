from __future__ import annotations

import hashlib
import json
import os
import pathlib
import zipfile
from collections import Counter


SOURCES = [
    pathlib.Path(r"C:\Users\kot00\Downloads\PROP-DATA-FILE_202602.xlsx"),
    pathlib.Path(r"C:\Users\kot00\Downloads\Propeller_Database.zip"),
    pathlib.Path(r"C:\Users\kot00\Downloads\Dataset.zip"),
    pathlib.Path(r"C:\Users\kot00\Downloads\UIUC-propDB.zip"),
    pathlib.Path(r"C:\Users\kot00\Downloads\APC-Propeller-RPM-Limits-rev5.pdf"),
    pathlib.Path(r"C:\Users\kot00\Downloads\PERFILES_WEB-202602.zipx"),
    pathlib.Path(r"C:\Users\kot00\Downloads\PE0-FILES_WEB-202602.zipx"),
]


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def suffix(name: str) -> str:
    leaf = pathlib.PurePosixPath(name.replace("\\", "/")).name
    if "." not in leaf or leaf.startswith(".") and leaf.count(".") == 1:
        return "[no extension]"
    return "." + leaf.rsplit(".", 1)[1].lower()


def inventory(path: pathlib.Path) -> dict:
    stat = path.stat()
    result = {
        "path": str(path),
        "name": path.name,
        "bytes": stat.st_size,
        "mtime": stat.st_mtime,
        "sha256": sha256(path),
    }
    if path.suffix.lower() in {".zip", ".zipx", ".xlsx"}:
        try:
            with zipfile.ZipFile(path) as archive:
                members = archive.infolist()
                files = [m for m in members if not m.is_dir()]
                result["archive"] = {
                    "members_total": len(members),
                    "files": len(files),
                    "directories": len(members) - len(files),
                    "uncompressed_bytes": sum(m.file_size for m in files),
                    "compressed_bytes": sum(m.compress_size for m in files),
                    "extensions": dict(sorted(Counter(suffix(m.filename) for m in files).items())),
                    "compression_methods": dict(sorted(Counter(str(m.compress_type) for m in files).items())),
                    "encrypted_files": sum(bool(m.flag_bits & 0x1) for m in files),
                    "duplicate_member_names": len(files) - len({m.filename for m in files}),
                    "members": [
                        {
                            "name": m.filename,
                            "bytes": m.file_size,
                            "compressed_bytes": m.compress_size,
                            "crc32": f"{m.CRC:08X}",
                            "compression_method": m.compress_type,
                            "encrypted": bool(m.flag_bits & 0x1),
                        }
                        for m in files
                    ],
                }
        except Exception as exc:
            result["archive_error"] = f"{type(exc).__name__}: {exc}"
    return result


def main() -> None:
    output = pathlib.Path(os.environ.get("PROP_AUDIT_OUTPUT", "work/source_audit/source_inventory.json"))
    output.parent.mkdir(parents=True, exist_ok=True)
    data = {"sources": [inventory(path) for path in SOURCES]}
    output.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    for item in data["sources"]:
        arc = item.get("archive", {})
        print(json.dumps({
            "name": item["name"],
            "bytes": item["bytes"],
            "sha256": item["sha256"],
            "files": arc.get("files"),
            "extensions": arc.get("extensions"),
            "methods": arc.get("compression_methods"),
            "archive_error": item.get("archive_error"),
        }, ensure_ascii=False))


if __name__ == "__main__":
    main()
