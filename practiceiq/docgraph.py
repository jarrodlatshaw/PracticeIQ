"""Validate a DocGraph CSV into a staging CSV; never connect to a database implicitly."""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile

from practiceiq.identity import normalize_npi

REQUIRED = ("FROM_NPI", "TO_NPI", "PATIENT_COUNT")
OPTIONAL = ("TRANSACTION_COUNT", "AVERAGE_DAY_WAIT", "STD_DAY_WAIT")


def stage(source: Path, output: Path, release: str, period: str) -> dict:
    if not release.strip() or not period.strip():
        raise ValueError("release and period are required")
    if output.exists() or output.resolve() == source.resolve():
        raise ValueError("output already exists or is the source")
    output.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    with source.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    count = 0
    with tempfile.TemporaryDirectory(dir=output.parent) as temp:
        staged = Path(temp) / "staged.csv"
        db = sqlite3.connect(str(Path(temp) / "keys.sqlite"))
        try:
            db.execute("create table keys (source text, destination text, primary key(source,destination)) without rowid")
            with source.open(newline="", encoding="utf-8-sig") as src, staged.open("w", newline="", encoding="utf-8") as dst:
                reader = csv.DictReader(src)
                headers = [h.strip().upper() for h in (reader.fieldnames or [])]
                if len(headers) != len(set(headers)) or not set(REQUIRED).issubset(headers):
                    raise ValueError("missing or duplicate required headers")
                reader.fieldnames = headers
                writer = csv.DictWriter(dst, fieldnames=REQUIRED + OPTIONAL)
                writer.writeheader()
                for line, row in enumerate(reader, 2):
                    try:
                        if None in row:
                            raise ValueError("extra CSV fields")
                        result = {key: (row.get(key) or "").strip() for key in REQUIRED + OPTIONAL}
                        result["FROM_NPI"] = normalize_npi(result["FROM_NPI"])
                        result["TO_NPI"] = normalize_npi(result["TO_NPI"])
                        if result["FROM_NPI"] == result["TO_NPI"]:
                            raise ValueError("self edge")
                        for field in ("PATIENT_COUNT", "TRANSACTION_COUNT"):
                            value = result[field]
                            if not value and field != "PATIENT_COUNT":
                                continue
                            if not value.isascii() or not value.isdigit():
                                raise ValueError(f"{field} must be a nonnegative integer")
                        for field in ("AVERAGE_DAY_WAIT", "STD_DAY_WAIT"):
                            if result[field]:
                                from decimal import Decimal, InvalidOperation
                                try:
                                    value = Decimal(result[field])
                                except InvalidOperation:
                                    raise ValueError(f"invalid {field}") from None
                                if not value.is_finite() or value < 0:
                                    raise ValueError(f"invalid {field}")
                        db.execute("insert into keys values (?, ?)", (result["FROM_NPI"], result["TO_NPI"]))
                        writer.writerow(result)
                        count += 1
                    except (ValueError, sqlite3.IntegrityError) as exc:
                        raise ValueError(f"line {line}: {exc or 'duplicate edge'}") from exc
            if count == 0:
                raise ValueError("input contains no data rows")
            # Hard link ensures we do not overwrite a concurrently created file.
            os.link(staged, output)
        finally:
            db.close()
    return {"release": release, "period": period, "sha256": digest.hexdigest(), "rows": count,
            "note": "staging only; verify source direction, suppression, licensing and identity before promotion"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--release", required=True)
    parser.add_argument("--period", required=True)
    args = parser.parse_args()
    print(json.dumps(stage(args.source, args.output, args.release, args.period), indent=2))


if __name__ == "__main__":
    main()
