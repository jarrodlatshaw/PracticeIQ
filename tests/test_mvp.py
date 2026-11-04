import unittest
from practiceiq.mvp import get_referral_opportunities, Config


def practice(pid, name, code, lat):
    return {'practice_id':pid,'practice_name':name,'legal_name':name,'primary_specialty_code':code,
            'primary_specialty':'Orthopedic Surgery' if code=='207X00000X' else 'Family Medicine',
            'latitude':str(lat),'longitude':'-77','state':'VA'}


def provider(npi, taxonomy):
    return {'NPI':npi, 'Provider First Name':'Test','Provider Last Name (Legal Name)':'Provider',
            'Healthcare Provider Taxonomy Code_1':taxonomy,'NPI Deactivation Date':'','NPI Reactivation Date':''}


class MvpTests(unittest.TestCase):
    def setUp(self):
        self.practices={'client':practice('client','Client','207X00000X',38.0),
                        'competitor':practice('competitor','Competitor','207X00000X',38.1),
                        'source':practice('source','Source','207Q00000X',38.05)}
        self.providers={'1000000004':provider('1000000004','207Q00000X'),
                        '1000000012':provider('1000000012','207X00000X'),
                        '1000000020':provider('1000000020','207X00000X')}
        self.affiliations=[{'practice_id':p,'clinician_npi':n,'cms_group_pac_id':p} for p,n in
                           [('client','1000000012'),('competitor','1000000020'),('source','1000000004')]]
        self.edges=[{'from_npi':'1000000004','to_npi':'1000000012','patient_count':60},
                    {'from_npi':'1000000004','to_npi':'1000000020','patient_count':140}]

    def test_end_to_end_discovery_and_scenarios(self):
        r=get_referral_opportunities('client',self.practices,self.affiliations,self.providers,self.edges,synthetic=True)
        self.assertEqual(r['market_summary']['competitor_count'],1)
        self.assertEqual(len(r['opportunities']),1)
        x=r['opportunities'][0]
        self.assertEqual((x['observed_market_flow'],x['client_flow'],x['competitor_flow']),(200,60,140))
        self.assertEqual((x['revenue_low'],x['revenue_base'],x['revenue_high']),(12600,25200,37800))
        self.assertTrue(r['assumptions']['synthetic_edges'])
        self.assertTrue(0 <= x['opportunity_score'] <= 100)

    def test_excludes_ambiguous_and_inactive_affiliations(self):
        self.affiliations.append({'practice_id':'competitor','clinician_npi':'1000000004','cms_group_pac_id':'competitor'})
        r=get_referral_opportunities('client',self.practices,self.affiliations,self.providers,self.edges,synthetic=True)
        self.assertEqual(r['opportunities'],[])
        self.providers['1000000012']['NPI Deactivation Date']='01/01/2023'
        with self.assertRaises(ValueError):
            get_referral_opportunities('client',self.practices,self.affiliations,self.providers,self.edges)

    def test_missing_and_duplicate_edges_rejected(self):
        for edges in ([*self.edges,self.edges[0]],[{**self.edges[0], 'patient_count':None}]):
            with self.assertRaises(ValueError):
                get_referral_opportunities('client',self.practices,self.affiliations,self.providers,edges)
        with self.assertRaises(ValueError):
            get_referral_opportunities('client',self.practices,self.affiliations,self.providers,self.edges,config=Config(radius_miles=0))

if __name__ == '__main__': unittest.main()
