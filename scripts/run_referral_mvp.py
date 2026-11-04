"""Run a local demo using explicit practice, affiliation, provider and edge files."""
import argparse
import csv
import json
from pathlib import Path
from practiceiq.mvp import get_referral_opportunities, load_affiliations, load_practices, load_providers


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--practice-id',required=True)
    p.add_argument('--practices',type=Path,required=True)
    p.add_argument('--affiliations',type=Path,required=True)
    p.add_argument('--providers',type=Path,required=True)
    p.add_argument('--edges',type=Path,required=True)
    p.add_argument('--synthetic',action='store_true',help='mark input edges as invented test data')
    args=p.parse_args()
    with args.edges.open(newline='',encoding='utf-8-sig') as f:
        edges=[{'from_npi':r['FROM_NPI'].strip(),'to_npi':r['TO_NPI'].strip(),'patient_count':int(r['PATIENT_COUNT'])} for r in csv.DictReader(f)]
    result=get_referral_opportunities(args.practice_id,load_practices(args.practices),load_affiliations(args.affiliations),load_providers(args.providers),edges,synthetic=args.synthetic)
    print(json.dumps(result,indent=2))

if __name__ == '__main__': main()
