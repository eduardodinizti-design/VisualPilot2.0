import unittest
from table_reading.presentation import describe_regions

class RegionPresentationTests(unittest.TestCase):
    def test_rejected_region_not_a_table_or_card_reading(self):
        rows=[dict(table_index=1,local_box=[1,2,3,4],status='COMPLETE_CANDIDATE',hero_cards=['Tc','Ks'],reading_status='EXPERIMENTAL_CANDIDATES'),
              dict(table_index=2,local_box=[5,6,7,8],status='UNCERTAIN',reasons=['FULL_BOUNDARY_NOT_ESTABLISHED'])]
        lines=describe_regions({'tables':rows})
        self.assertIn('leitura: 1 | Regioes rejeitadas: 1',lines[0])
        self.assertIn('Tc / Ks',lines[1])
        self.assertIn('FULL_BOUNDARY_NOT_ESTABLISHED',lines[2])
        self.assertIn('OCR nao executado',lines[2])
        self.assertNotIn('Hero:',lines[2]);self.assertNotIn('lobby',lines[2])
    def test_unknown_reason_is_preserved(self):
        lines=describe_regions({'tables':[dict(table_index=1,local_box=[],status='PARTIAL',reasons=['NEW_REASON'])]})
        self.assertIn('NEW_REASON',lines[1])
    def test_missing_reason_and_empty_report(self):
        self.assertEqual(len(describe_regions({'tables':[]})),1)
        lines=describe_regions({'tables':[dict(table_index=1,local_box=[],status='UNCERTAIN')]})
        self.assertIn('REASON_NOT_REPORTED',lines[1])
