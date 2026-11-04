"""Extract selected provider identities from an NPPES bulk CSV to staging.

The input can be an extracted NPPES data CSV or a ZIP with an explicitly
selected CSV member; it cannot be a registry API response. It hashes and then
streams the source and never infers a practice affiliation.
"""
import argparse
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import zipfile
from practiceiq.identity import normalize_npi

REQUIRED = ("NPI", "Entity Type Code")
OPTIONAL = ("Provider Organization Name (Legal Business Name)",
            "Provider Last Name (Legal Name)", "Provider First Name",
            "NPI Deactivation Date", "NPI Reactivation Date")


def stage(source: Path, output: Path, target_npis: set[str], *, member: str | None = None) -> dict:
    targets = {normalize_npi(value) for value in target_npis}
    if not targets:
        raise ValueError("at least one target NPI is required")
    if output.exists() or source.resolve() == output.resolve():
        raise ValueError("output already exists or is the source")
    output.parent.mkdir(parents=True, exist_ok=True)
    matched = set()
    # Checksum the entire source file while preserving streaming memory usage.
    digest = hashlib.sha256()
    with source.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    with tempfile.TemporaryDirectory(dir=output.parent) as temp:
        staged = Path(temp) / 'providers.csv'
        if member is not None:
            archive = zipfile.ZipFile(source)
            try:
                raw = archive.open(member)
            except Exception:
                archive.close()
                raise
            src_context = io.TextIOWrapper(raw, encoding='utf-8-sig', newline='')
        else:
            archive = None
            src_context = source.open(newline='', encoding='utf-8-sig')
        try:
            with src_context as src, staged.open('w', newline='', encoding='utf-8') as dst:
                reader = csv.reader(src)
                headers = next(reader, [])
                if len(headers) != len(set(headers)) or not set(REQUIRED).issubset(headers):
                    raise ValueError('NPPES file is missing required headers or has duplicates')
                indices = {field: headers.index(field) for field in REQUIRED + OPTIONAL if field in headers}
                writer = csv.DictWriter(dst, fieldnames=REQUIRED + OPTIONAL)
                writer.writeheader()
                for row in reader:
                    if len(row) != len(headers):
                        raise ValueError(f'malformed source row at line {reader.line_num}')
                    npi = row[indices['NPI']].strip()
                    if npi not in targets:
                        continue
                    if npi in matched:
                        raise ValueError('duplicate target NPI in source')
                    entity = row[indices['Entity Type Code']].strip()
                    if entity not in ('1', '2'):
                        raise ValueError('unrecognized NPPES entity type')
                    result = {field: row[index].strip() for field, index in indices.items()}
                    result['NPI'], result['Entity Type Code'] = npi, entity
                    writer.writerow(result)
                    matched.add(npi)
        finally:
            if archive is not None:
                archive.close()
        # Never silently replace an existing output.
        os.link(staged, output)
    return {'source_sha256': digest.hexdigest(), 'requested': len(targets),
            'matched': len(matched), 'not_found': len(targets - matched),
            'unmatched_npis': sorted(targets - matched),
            'note': 'Entity code 1 is individual; 2 is organization. Practice affiliations require separate evidence.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--member', help='exact CSV member name when source is a ZIP')
    parser.add_argument('--npis', type=Path, required=True, help='text file with one NPI per line')
    args = parser.parse_args()
    targets = set(args.npis.read_text(encoding='utf-8').splitlines())
    print(json.dumps(stage(args.source, args.output, targets, member=args.member), indent=2))


if __name__ == '__main__':
    main()
