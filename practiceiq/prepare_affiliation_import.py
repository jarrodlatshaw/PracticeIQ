"""Prepare, but never execute, an idempotent SQL import of staged candidates."""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from practiceiq.identity import normalize_npi


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def literal(value):
    if value is None:
        return 'NULL'
    value = str(value)
    if '\x00' in value:
        raise ValueError('NUL is not allowed in PostgreSQL text')
    return "'" + value.replace("'", "''") + "'"


def prepare(candidates: Path, manifest: Path, output: Path):
    if output.exists():
        raise ValueError('output already exists')
    meta = json.loads(manifest.read_text(encoding='utf-8'))
    actual = sha256(candidates)
    if actual != meta['candidate_file_sha256']:
        raise ValueError('candidate file checksum does not match manifest')
    cms = sorted(item['sha256'] for item in meta['cms_files'])
    hashes = cms + [meta['practice_export_sha256'], meta['nppes_source_sha256'], actual]
    if not cms or any(not re.fullmatch(r'[0-9a-f]{64}', h) for h in hashes):
        raise ValueError('invalid source checksum')
    with candidates.open(newline='', encoding='utf-8-sig') as stream:
        rows = list(csv.DictReader(stream))
    if not rows or len(rows) != meta['candidate_rows']:
        raise ValueError('candidate count does not match manifest')
    method = meta['matching_method']
    fingerprint = hashlib.sha256(json.dumps({'hashes':hashes, 'method':method},sort_keys=True).encode()).hexdigest()
    seen = set()
    columns = ['practice_id','clinician_npi','cms_group_pac_id','cms_group_name','cms_address_1','cms_city','cms_zip','evidence','clinician_practice_count','group_practice_count']
    statements = ['BEGIN;', 'SET LOCAL standard_conforming_strings = on;',
        "SELECT pg_advisory_xact_lock(hashtextextended(" + literal(fingerprint) + ",0));",
        'INSERT INTO practiceiq.affiliation_evidence_batches (cms_file_sha256s,practice_export_sha256,nppes_source_sha256,cms_release_date,matching_method,import_fingerprint) VALUES (ARRAY[' + ','.join(map(literal,cms)) + '],'
        + ','.join(map(literal,[meta['practice_export_sha256'],meta['nppes_source_sha256'],meta.get('cms_release_date'),method,fingerprint])) + ') ON CONFLICT (import_fingerprint) DO NOTHING;']
    for row in rows:
        normalize_npi(row['clinician_npi'])
        key = (row['practice_id'],row['clinician_npi'],row['cms_group_pac_id'])
        if not all(key) or key in seen:
            raise ValueError('duplicate or incomplete candidate key')
        seen.add(key)
        for name in ('clinician_practice_count','group_practice_count'):
            if not row[name].isascii() or not row[name].isdigit() or int(row[name]) < 1:
                raise ValueError('invalid practice count')
        values = ','.join(literal(row[column]) for column in columns)
        statements.append('INSERT INTO practiceiq.affiliation_evidence_candidates (batch_id,' + ','.join(columns) + ') SELECT id,' + values + ' FROM practiceiq.affiliation_evidence_batches WHERE import_fingerprint=' + literal(fingerprint) + ' ON CONFLICT (batch_id,practice_id,clinician_npi,cms_group_pac_id) DO NOTHING;')
    statements.append('COMMIT;')
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent) as temp:
        staged = Path(temp) / 'import.sql'
        staged.write_text('\n'.join(statements)+'\n',encoding='utf-8')
        os.link(staged, output)
    return {'rows':len(rows), 'fingerprint':fingerprint, 'sha256':sha256(output), 'executed':False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('candidates',type=Path)
    parser.add_argument('manifest',type=Path)
    parser.add_argument('output',type=Path)
    args = parser.parse_args()
    print(json.dumps(prepare(args.candidates,args.manifest,args.output),indent=2))


if __name__ == '__main__':
    main()
