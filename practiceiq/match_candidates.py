"""Generate review-only clinician/practice candidates from exact locations."""
import argparse
from collections import Counter, defaultdict
import csv
import json
import os
from pathlib import Path
import re
import tempfile


def normalize(value):
    return re.sub(r'\s+', ' ', str(value or '').strip().upper())


def match(practice_export: Path, clinician_roster: Path, output: Path) -> dict:
    if output.exists():
        raise ValueError('output already exists')
    practices = []
    with practice_export.open(newline='', encoding='utf-8-sig') as stream:
        for batch in csv.DictReader(stream):
            values = json.loads(batch['practices'])
            if not isinstance(values, list):
                raise ValueError('practice batch must be an array')
            practices.extend(values)
    ids = [p.get('practice_id') for p in practices]
    if not all(isinstance(x, str) and x.strip() for x in ids) or len(ids) != len(set(ids)):
        raise ValueError('practice IDs must be nonempty and unique')
    indexed = defaultdict(list)
    for p in practices:
        key = (normalize(p.get('address_1')), normalize(p.get('address_2')),
               normalize(p.get('city')), normalize(p.get('state')), str(p.get('zip5') or '').strip()[:5])
        if all((key[0], key[2], key[3], key[4])):
            indexed[key].append(p)
    matched_ids, counts = set(), Counter()
    fields = ('practice_id','practice_name','clinician_npi','clinician_first_name','clinician_last_name',
              'address_1','address_2','city','state','zip5','evidence','match_status','practices_at_address')
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent) as tmp:
        staged = Path(tmp) / 'candidates.csv'
        with clinician_roster.open(newline='', encoding='utf-8-sig') as stream, staged.open('w',newline='',encoding='utf-8') as out:
            writer = csv.DictWriter(out, fieldnames=fields)
            writer.writeheader()
            for row in csv.DictReader(stream):
                key = (normalize(row['Provider First Line Business Practice Location Address']),
                       normalize(row['Provider Second Line Business Practice Location Address']),
                       normalize(row['Provider Business Practice Location Address City Name']),
                       normalize(row['Provider Business Practice Location Address State Name']),
                       str(row['Provider Business Practice Location Address Postal Code']).strip()[:5])
                matches = indexed.get(key, [])
                for practice in matches:
                    writer.writerow({'practice_id':practice['practice_id'], 'practice_name':practice.get('practice_name'),
                                     'clinician_npi':row['NPI'], 'clinician_first_name':row['Provider First Name'],
                                     'clinician_last_name':row['Provider Last Name (Legal Name)'],
                                     **{k:practice.get(k) for k in ('address_1','address_2','city','state','zip5')},
                                     'evidence':'exact primary address, city, state and ZIP',
                                     'match_status':'candidate_requires_review', 'practices_at_address':len(matches)})
                    matched_ids.add(practice['practice_id'])
                    counts['candidate_rows'] += 1
                    if len(matches) > 1: counts['shared_address_rows'] += 1
        os.link(staged, output)
    return {'input_practices':len(practices), 'practices_with_usable_address':sum(map(len,indexed.values())),
            'matched_practices':len(matched_ids), 'candidate_rows':counts['candidate_rows'],
            'candidates_at_shared_practice_addresses':counts['shared_address_rows'],
            'limitations':'Address match is not proof of affiliation; NPPES primary locations only; no active-status or license verification.'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('practice_export', type=Path)
    parser.add_argument('clinician_roster', type=Path)
    parser.add_argument('output', type=Path)
    args=parser.parse_args()
    print(json.dumps(match(args.practice_export,args.clinician_roster,args.output),indent=2))


if __name__ == '__main__':
    main()
