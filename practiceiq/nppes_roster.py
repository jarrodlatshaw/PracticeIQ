"""Stage Virginia individual-NPI records from a specified NPPES bulk ZIP member.

This is a provider-location snapshot, not a practice affiliation or a physician
roster. It includes all NPI-1 entity types, including non-physician clinicians.
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

BASE_FIELDS = (
    'NPI', 'Entity Type Code', 'Provider Last Name (Legal Name)', 'Provider First Name',
    'Provider First Line Business Practice Location Address',
    'Provider Second Line Business Practice Location Address',
    'Provider Business Practice Location Address City Name',
    'Provider Business Practice Location Address State Name',
    'Provider Business Practice Location Address Postal Code',
    'Provider Business Practice Location Address Telephone Number',
    'NPI Deactivation Date', 'NPI Reactivation Date',
)
TAXONOMY_FIELDS = tuple(field for index in range(1, 16) for field in (
    f'Healthcare Provider Taxonomy Code_{index}',
    f'Healthcare Provider Primary Taxonomy Switch_{index}',
))
FIELDS = BASE_FIELDS + TAXONOMY_FIELDS
STATE = 'Provider Business Practice Location Address State Name'


def stage_virginia(source: Path, member: str, output: Path) -> dict:
    if output.exists() or output.resolve() == source.resolve():
        raise ValueError('output exists or is the input')
    output.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    with source.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    rows_scanned = rows_selected = 0
    with tempfile.TemporaryDirectory(dir=output.parent) as temp:
        temporary = Path(temp) / 'roster.csv'
        with zipfile.ZipFile(source) as archive:
            with io.TextIOWrapper(archive.open(member), encoding='utf-8-sig', newline='') as src, temporary.open('w', encoding='utf-8', newline='') as dst:
                reader = csv.reader(src)
                headers = next(reader, [])
                if len(headers) != len(set(headers)) or not set(FIELDS).issubset(headers):
                    raise ValueError('source is missing required columns or has duplicate headers')
                indices = {field: headers.index(field) for field in FIELDS}
                writer = csv.DictWriter(dst, fieldnames=FIELDS)
                writer.writeheader()
                for row in reader:
                    rows_scanned += 1
                    if len(row) != len(headers):
                        raise ValueError(f'malformed source row at line {reader.line_num}')
                    if row[indices['Entity Type Code']].strip() != '1' or row[indices[STATE]].strip().upper() != 'VA':
                        continue
                    selected = {field: row[index].strip() for field, index in indices.items()}
                    selected['NPI'] = normalize_npi(selected['NPI'])
                    writer.writerow(selected)
                    rows_selected += 1
        os.link(temporary, output)
    return {'source_sha256': digest.hexdigest(), 'member': member, 'rows_scanned': rows_scanned,
            'virginia_individual_records': rows_selected,
            'limitations': 'Primary practice location in VA only; not a practice affiliation, license check, or complete Virginia clinician roster.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('member')
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    print(json.dumps(stage_virginia(args.source, args.member, args.output), indent=2))


if __name__ == '__main__':
    main()
