"""Prepare a staged SQL import from a validated DocGraph-format CSV.

This utility prepares SQL only. Release stays staged until its period,
direction, suppression, licensing and coverage are checked by an operator.
"""
import argparse
import csv
from datetime import date
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
from pathlib import Path
import tempfile
from practiceiq.identity import normalize_npi
from practiceiq.prepare_affiliation_import import literal


def prepare(source: Path, output: Path, *, year: int, version: str, synthetic: bool = False):
    if output.exists() or output.resolve() == source.resolve():
        raise ValueError('output exists or is source')
    if not version.strip() or not 1900 <= year <= 2100:
        raise ValueError('dataset year and version are required')
    digest = hashlib.sha256()
    with source.open('rb') as stream:
        for block in iter(lambda:stream.read(1048576),b''): digest.update(block)
    fingerprint = digest.hexdigest()
    source_label = "SYNTHETIC - NOT DOCGRAPH" if synthetic else "CareSet DocGraph"
    release = "(select id from practiceiq.dataset_releases where source=" + literal(source_label) + " and version=" + literal(version) + ' and sha256=' + literal(fingerprint) + ')'
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent) as folder:
        staged = Path(folder) / 'import.sql'
        with source.open(newline='',encoding='utf-8-sig') as src, staged.open('w',encoding='utf-8') as dst:
            reader=csv.DictReader(src)
            required={'FROM_NPI','TO_NPI','PATIENT_COUNT'}
            if not reader.fieldnames or not required.issubset(reader.fieldnames) or len(set(reader.fieldnames)) != len(reader.fieldnames):
                raise ValueError('missing or duplicate DocGraph columns')
            dst.write("BEGIN;\nSET LOCAL standard_conforming_strings = on;\n")
            dst.write('INSERT INTO practiceiq.dataset_releases(source,version,period_start,period_end,sha256,status,is_synthetic) VALUES (' + ','.join(map(literal,[source_label,version,date(year,1,1),date(year,12,31),fingerprint,'staged'])) + (',true' if synthetic else ',false') + ') ON CONFLICT(source,version,sha256) DO NOTHING;\n')
            seen=set();count=0
            for row in reader:
                fr=normalize_npi(row['FROM_NPI']);to=normalize_npi(row['TO_NPI'])
                if fr==to or (fr,to) in seen: raise ValueError('self or duplicate edge')
                seen.add((fr,to))
                def integer(key,required=False):
                    value=(row.get(key) or '').strip()
                    if not value and not required: return 'NULL'
                    if not value.isascii() or not value.isdigit(): raise ValueError('invalid '+key)
                    return str(int(value))
                def number(key):
                    value=(row.get(key) or '').strip()
                    if not value:return 'NULL'
                    try: n=Decimal(value)
                    except InvalidOperation: raise ValueError('invalid '+key) from None
                    if not n.is_finite() or n<0:raise ValueError('invalid '+key)
                    return str(n)
                patients=integer('PATIENT_COUNT',True);transactions=integer('TRANSACTION_COUNT')
                avg=number('AVERAGE_DAY_WAIT');std=number('STD_DAY_WAIT')
                dst.write('INSERT INTO practiceiq.providers(npi,entity_type) VALUES ('+literal(fr)+",'unknown'),("+literal(to)+",'unknown') ON CONFLICT(npi) DO NOTHING;\n")
                dst.write('INSERT INTO practiceiq.referral_edges(release_id,from_npi,to_npi,patient_count,transaction_count,average_day_wait,std_day_wait) VALUES ('+release+','+','.join([literal(fr),literal(to),patients,transactions,avg,std])+') ON CONFLICT(release_id,from_npi,to_npi) DO NOTHING;\n')
                count+=1
            if count==0:raise ValueError('no DocGraph rows')
            dst.write('COMMIT;\n')
        os.link(staged,output)
    return {'rows':count,'sha256':fingerprint,'dataset_year':year,'version':version,'release_status':'staged','executed':False}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('source',type=Path);p.add_argument('output',type=Path)
    p.add_argument('--year',type=int,required=True);p.add_argument('--version',required=True);p.add_argument('--synthetic',action='store_true')
    args=p.parse_args()
    print(json.dumps(prepare(args.source,args.output,year=args.year,version=args.version,synthetic=args.synthetic),indent=2))

if __name__ == '__main__':main()
