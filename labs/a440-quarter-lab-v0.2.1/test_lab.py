#!/usr/bin/env python3
# BEACON COMPUTING INITIATIVE
# Developer Seal: CJB-DEV-2026
# Component: A440 Quarter Lab Contract Tests
import unittest
import endpoint,model
class LabTests(unittest.TestCase):
    def setUp(self):
        self.data={}
        for i in range(1,21):
            endpoint.ID=i
            self.data[i]=[model.verify(endpoint.record(q),f'endpoint-{i:02d}',q) for q in range(8)]
    def test_twenty_distinct_sources(self):
        self.assertEqual(len({self.data[i][0]['agent'] for i in self.data}),20)
    def test_chord_all_sources_required(self):
        with self.assertRaises(ValueError):model.snapshot([self.data[i][0] for i in range(1,20)])
    def test_chord_arithmetic(self):
        r=model.snapshot([self.data[i][7] for i in range(1,21)])
        self.assertEqual(r['sources'],20)
        self.assertAlmostEqual(r['net_sales'],round(r['sales']-r['returns'],2),places=2)
    def test_integrity_rejects_change(self):
        x=dict(self.data[1][0]);x['sales']+=100
        with self.assertRaises(ValueError):model.verify(x,'endpoint-01',0)
    def test_train_and_predict(self):
        model.DATA.update(self.data)
        samples=model.examples();self.assertEqual(len(samples),80)
        model.NET.train(samples,epochs=2)
        result=model.forecast_quarters(8,4)
        self.assertEqual(len(result),4)
        self.assertTrue(all(x['sales']>=0 for x in result))
    def test_quarters_do_not_share_synthetic_history(self):
        a=self.data[1][5]['sales'];b=self.data[2][5]['sales']
        self.assertNotEqual(a,b)
if __name__=='__main__':unittest.main(verbosity=2)
