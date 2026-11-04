"""Small local referral-opportunity prototype; no network or database writes."""
import csv
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from datetime import datetime
from math import isfinite
from practiceiq.calculations import opportunity, Scenarios
from practiceiq.geography import distance_miles


@dataclass(frozen=True)
class Config:
    radius_miles: float = 25.0
    collections_per_patient: Decimal = Decimal('1800')
    volume_cap: float = 200.0
    source_size_cap: float = 10.0
    flow_weight: float = .40
    revenue_weight: float = .25
    proximity_weight: float = .15
    leakage_weight: float = .10
    size_weight: float = .10
    capture_low: Decimal = Decimal('0.05')
    capture_base: Decimal = Decimal('0.10')
    capture_high: Decimal = Decimal('0.15')

# Taxonomy labels are resolved from individual NPPES taxonomy, not organization label.
ORTHO_SOURCES = {'207Q00000X', '207R00000X', '207P00000X', '208100000X',
                 '2081P2900X', '2081S0010X', '207QS0010X', '207X00000X'}
SOURCE_SPECIALTIES = {'207Q00000X':'Family Medicine', '207R00000X':'Internal Medicine',
                      '207P00000X':'Emergency Medicine', '208100000X':'Physical Medicine and Rehabilitation',
                      '2081P2900X':'Pain Medicine', '2081S0010X':'Sports Medicine', '207QS0010X':'Sports Medicine'}
ORTHO_DEST = {'207X00000X', '207XS0106X', '207XS0114X', '207XS0117X',
              '207XX0004X', '207XX0005X'}


def _active(provider):
    """Check deactivation relative to reactivation; reject unparseable dates."""
    try:
        deact = provider.get('NPI Deactivation Date', '').strip()
        react = provider.get('NPI Reactivation Date', '').strip()
        deact = datetime.strptime(deact, '%m/%d/%Y').date() if deact else None
        react = datetime.strptime(react, '%m/%d/%Y').date() if react else None
        return deact is None or (react is not None and react > deact)
    except ValueError:
        return False


def _point(row):
    try:
        lat, lon = float(row['latitude']), float(row['longitude'])
        distance_miles(lat, lon, lat, lon)
        return lat, lon
    except (KeyError, ValueError, TypeError):
        return None


def _org(row):
    import re
    return re.sub(r'[^A-Z0-9]', '', (row.get('legal_name') or row.get('practice_name') or '').upper())


def load_practices(path):
    with open(path, newline='', encoding='utf-8-sig') as f:
        return {r['practice_id']: r for r in csv.DictReader(f)}


def load_affiliations(path):
    with open(path, newline='', encoding='utf-8-sig') as f:
        return list(csv.DictReader(f))


def load_providers(path):
    with open(path, newline='', encoding='utf-8-sig') as f:
        return {r['NPI']: r for r in csv.DictReader(f)}


def get_referral_opportunities(practice_id, practices, affiliations, providers, edges, *, config=Config(), synthetic=False):
    """Caller supplies one source release; specialty, market and affiliates are inferred.

    CMS group+name+address matches are used as high-confidence when a clinician
    is linked to one practice only; conflicts are excluded. Labels and patient
    counts are estimates, not unique patients or verified referrals.
    """
    if practice_id not in practices:
        raise ValueError('practice not found')
    client = practices[practice_id]
    point = _point(client)
    if point is None:
        raise ValueError('client coordinates unavailable')
    if client['primary_specialty_code'] not in ORTHO_DEST:
        raise ValueError('V1 compatibility mapping currently supports orthopedics only')
    weights = [config.flow_weight,config.revenue_weight,config.proximity_weight,config.leakage_weight,config.size_weight]
    if not all(isfinite(x) for x in [config.radius_miles,config.volume_cap,config.source_size_cap,*weights]) or config.radius_miles <= 0 or config.volume_cap <= 0 or config.source_size_cap <= 0 or any(w < 0 for w in weights) or abs(sum(weights)-1)>1e-9:
        raise ValueError('invalid score configuration')
    scenarios = Scenarios(config.capture_low, config.capture_base, config.capture_high)
    if not config.collections_per_patient.is_finite() or config.collections_per_patient < 0:
        raise ValueError('invalid benchmark')
    by_npi, groups = defaultdict(set), defaultdict(set)
    for a in affiliations:
        if a['practice_id'] in practices:
            by_npi[a['clinician_npi']].add(a['practice_id'])
            groups[a['practice_id']].add(a['cms_group_pac_id'])
    members = defaultdict(set)
    for npi, ps in by_npi.items():
        if len(ps) == 1 and npi in providers and _active(providers[npi]):
            members[next(iter(ps))].add(npi)
    client_members=members[practice_id]
    if not client_members:
        raise ValueError('no unambiguous client clinicians available')
    selected = {}
    for pid,p in practices.items():
        pt=_point(p)
        if pt is None or not members[pid] or p['state'].upper() != 'VA': continue
        distance=distance_miles(*point,*pt)
        if distance > config.radius_miles: continue
        selected[pid]=distance
    competitors={pid for pid in selected if pid != practice_id and practices[pid]['primary_specialty_code'] in ORTHO_DEST
                 and _org(practices[pid]) != _org(client) and not (groups[pid] & groups[practice_id])}
    dest_to_practice={npi:pid for pid in competitors | {practice_id} for npi in members[pid]}
    source_practice={}
    for pid in selected:
        if pid == practice_id or pid in competitors or _org(practices[pid]) == _org(client) or (groups[pid] & groups[practice_id]): continue
        for npi in members[pid]:
            provider=providers[npi]
            code=next((provider.get(f'Healthcare Provider Taxonomy Code_{i}','') for i in range(1,16) if provider.get(f'Healthcare Provider Primary Taxonomy Switch_{i}','').upper() == 'Y'), provider.get('Healthcare Provider Taxonomy Code_1',''))
            if code in ORTHO_SOURCES and code not in ORTHO_DEST:
                source_practice[npi]=pid
    totals=defaultdict(lambda: {'client':0,'competitor':0})
    seen=set()
    for edge in edges:
        key=(edge['from_npi'],edge['to_npi'])
        if key in seen: raise ValueError('duplicate edge')
        seen.add(key)
        count=edge['patient_count']
        if count is None: raise ValueError('missing edge count; coverage cannot be inferred')
        if isinstance(count,bool) or not isinstance(count,int) or count<0: raise ValueError('invalid edge count')
        source,dest=key
        if source not in source_practice or dest not in dest_to_practice: continue
        totals[source]['client' if dest_to_practice[dest]==practice_id else 'competitor']+=count
    results=[]
    for npi,t in totals.items():
        source_pid=source_practice[npi]; practice=practices[source_pid]; provider=providers[npi]
        leak=t['competitor']; observed=leak+t['client']; distance=selected[source_pid]
        money=opportunity(observed,t['client'],config.collections_per_patient,scenarios)
        flow=min(leak/config.volume_cap,1)*100
        revenue=min(float(money['revenue']['base'])/(config.volume_cap*float(scenarios.base)*float(config.collections_per_patient)),1)*100 if config.collections_per_patient>0 and scenarios.base>0 else 0
        proximity=max(0,1-distance/config.radius_miles)*100
        leakage=leak/observed*100 if observed else 0
        size=min(len(members[source_pid])/config.source_size_cap,1)*100
        components={'flow':flow,'revenue':revenue,'proximity':proximity,'leakage':leakage,'source_size':size}
        score=sum(components[k]*w for k,w in zip(components,weights))
        results.append({'source_npi':npi,'provider_name':(' '.join([provider.get('Provider First Name',''),provider.get('Provider Last Name (Legal Name)','')])).strip(),
            'source_practice':practice['practice_name'],'source_practice_id':source_pid,'source_specialty':SOURCE_SPECIALTIES.get(next((provider.get(f'Healthcare Provider Taxonomy Code_{i}','') for i in range(1,16) if provider.get(f'Healthcare Provider Primary Taxonomy Switch_{i}','').upper()=='Y'),provider.get('Healthcare Provider Taxonomy Code_1','')), 'Unknown'),
            'latitude':float(practice['latitude']),'longitude':float(practice['longitude']),'distance_miles':round(distance,2),'drive_time_minutes':None,
            'observed_market_flow':observed,'client_flow':t['client'],'competitor_flow':leak,'estimated_leakage':leak,
            'revenue_low':float(money['revenue']['low']),'revenue_base':float(money['revenue']['base']),'revenue_high':float(money['revenue']['high']),
            'opportunity_score':round(score,1),'score_components':{k:round(v,1) for k,v in components.items()},
            'affiliation_confidence':'high (rule-based, not statistically calibrated)','affiliation_evidence':'CMS group name and address plus NPPES primary location; single practice match'})
    results.sort(key=lambda r:(-r['opportunity_score'],r['source_npi']))
    return {'practice_id':practice_id,'practice_name':client['practice_name'],'specialty':client['primary_specialty'],
        'latitude':point[0],'longitude':point[1], 'market_summary':{'competitor_count':len(competitors),'potential_referral_sources':len(source_practice),'sources_with_observed_edges':len(results)},
        'assumptions':{'radius_miles':config.radius_miles,'capture_rates':[float(scenarios.low),float(scenarios.base),float(scenarios.high)],'collections_per_patient':float(config.collections_per_patient),'currency':'USD','synthetic_edges':synthetic},
        'limitations':['Counts sum provider-pair patient sharing and may overlap; not unique patients or confirmed referrals.',
          'Unobserved or suppressed edges are not necessarily zero. NPPES and CMS snapshots may be stale; organization matching is incomplete.',
          'Revenue and score are illustrative, not measured actuals. Source specialty uses the NPPES primary taxonomy.'],
        'opportunities':results}
