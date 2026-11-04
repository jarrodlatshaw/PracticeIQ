"""Find review-only evidence of clinician-group links in CMS and NPPES data."""
import argparse
import csv
import json
import os
from pathlib import Path
import re
import tempfile
from collections import defaultdict


def norm(value):
    return re.sub(r'[^A-Z0-9]+', ' ', (value or '').upper()).strip()


def match(practices_file, candidates_file, cms_files, output):
    if output.exists():
        raise ValueError('output already exists')
    with practices_file.open(newline='', encoding='utf-8-sig') as stream:
        practices = {r['practice_id']: r for r in csv.DictReader(stream)}
    by_npi = defaultdict(list)
    cms_rows = 0
    expected_headers = None
    for path in cms_files:
        with path.open(newline='', encoding='utf-8-sig') as stream:
            reader = csv.DictReader(stream)
            if expected_headers is None:
                expected_headers = reader.fieldnames
            elif reader.fieldnames != expected_headers:
                raise ValueError('CMS files have different headers')
            for row in reader:
                cms_rows += 1
                if row['State'].strip().upper() != 'VA':
                    raise ValueError('CMS file contains non-Virginia rows')
                if row['NPI'].strip() and row['org_pac_id'].strip() and row['Facility Name'].strip():
                    by_npi[row['NPI'].strip()].append(row)
    fields = ['practice_id', 'practice_name', 'clinician_npi', 'cms_group_name', 'cms_group_pac_id',
              'cms_address_1', 'cms_city', 'cms_zip', 'evidence', 'review_status']
    seen, practice_ids, clinician_npis = set(), set(), set()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent) as temp:
        staged = Path(temp) / 'matches.csv'
        with candidates_file.open(newline='', encoding='utf-8-sig') as stream, staged.open('w', newline='', encoding='utf-8') as dst:
            writer = csv.DictWriter(dst, fieldnames=fields)
            writer.writeheader()
            for candidate in csv.DictReader(stream):
                practice = practices.get(candidate['practice_id'])
                if practice is None:
                    raise ValueError('candidate references a missing practice')
                for row in by_npi.get(candidate['clinician_npi'], []):
                    names = {norm(practice['practice_name']), norm(practice['legal_name'])} - {''}
                    if (norm(row['Facility Name']) not in names or not norm(practice['address_1'])
                        or norm(row['adr_ln_1']) != norm(practice['address_1'])
                        or row['ZIP Code'].strip()[:5] != practice['zip5'].strip()[:5]
                        or norm(row['City/Town']) != norm(practice['city'])):
                        continue
                    key = (practice['practice_id'], candidate['clinician_npi'], row['org_pac_id'].strip())
                    if key in seen:
                        continue
                    seen.add(key)
                    practice_ids.add(key[0])
                    clinician_npis.add(key[1])
                    writer.writerow({'practice_id':key[0], 'practice_name':practice['practice_name'],
                        'clinician_npi':key[1], 'cms_group_name':row['Facility Name'], 'cms_group_pac_id':key[2],
                        'cms_address_1':row['adr_ln_1'], 'cms_city':row['City/Town'], 'cms_zip':row['ZIP Code'],
                        'evidence':'NPI, exact normalized group name, street, city, ZIP; NPPES address candidate',
                        'review_status':'candidate_requires_review'})
        os.link(staged, output)
    return {'cms_rows':cms_rows, 'unique_candidate_links':len(seen), 'practices':len(practice_ids),
            'clinicians':len(clinician_npis), 'note':'Evidence for review, not verified current affiliation; CMS release date and completeness not established.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--practices', type=Path, required=True)
    parser.add_argument('--candidates', type=Path, required=True)
    parser.add_argument('--cms', type=Path, nargs='+', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(match(args.practices, args.candidates, args.cms, args.output), indent=2))


if __name__ == '__main__':
    main()
