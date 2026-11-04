"""Prepare local CSVs for loading practice and NPPES provider snapshots."""
import argparse
import csv
from pathlib import Path
from practiceiq.mvp import _active


def prepare(practices, providers, output_dir):
    output_dir.mkdir(parents=True,exist_ok=True)
    practice_output=output_dir/'mvp-practices-import.csv'
    provider_output=output_dir/'mvp-providers-import.csv'
    if practice_output.exists() or provider_output.exists():
        raise ValueError('output already exists')
    with practices.open(newline='',encoding='utf-8-sig') as src, practice_output.open('x',newline='',encoding='utf-8') as dst:
        w=csv.writer(dst)
        for row in csv.DictReader(src):
            w.writerow([row[k] for k in ('practice_id','practice_name','legal_name','primary_specialty','primary_specialty_code','latitude','longitude','state')])
    with providers.open(newline='',encoding='utf-8-sig') as src, provider_output.open('x',newline='',encoding='utf-8') as dst:
        w=csv.writer(dst)
        for row in csv.DictReader(src):
            primary=next((row.get(f'Healthcare Provider Taxonomy Code_{i}','') for i in range(1,16)
                          if row.get(f'Healthcare Provider Primary Taxonomy Switch_{i}','').upper()=='Y'),'')
            w.writerow([row['NPI'],'individual',row['Provider First Name'],row['Provider Last Name (Legal Name)'],
                        primary,'true' if _active(row) else 'false'])
    return practice_output,provider_output


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--practices',type=Path,required=True);p.add_argument('--providers',type=Path,required=True)
    p.add_argument('--output-dir',type=Path,required=True)
    args=p.parse_args()
    for path in prepare(args.practices,args.providers,args.output_dir): print(path)

if __name__ == '__main__':main()
