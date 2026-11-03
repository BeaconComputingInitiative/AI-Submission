#!/usr/bin/env python3
# ============================================================
# BEACON COMPUTING INITIATIVE
# Developer Seal: CJB-DEV-2026
# Component: A440 U2.1 Architectural Regression Tests
# ============================================================
import copy
import json
import math
import tempfile
import unittest
from pathlib import Path
from unittest import mock
import model


class U21Tests(unittest.TestCase):
    def setUp(self):
        self.contract = model.restaurant_contract()

    def test_01_role_and_metric_heads_are_distinct(self):
        net = model.UniversalNet()
        x = {0: 1., 1: .2, 7: .13}
        a = ("revenue", "restaurant-001", "food_sales")
        b = ("revenue", "restaurant-001", "bar_sales")
        _, _ = net.forward(x, a)
        _, _ = net.forward(x, b)
        role, key_a = net.task_parts(a)
        _, key_b = net.task_parts(b)
        self.assertNotEqual(key_a, key_b)
        self.assertIn(role, net.heads)
        old_a = copy.deepcopy(net.heads[key_a])
        old_b = copy.deepcopy(net.heads[key_b])
        net.train_one(x, a, 1., .02)
        self.assertNotEqual(old_a, net.heads[key_a])
        self.assertEqual(old_b, net.heads[key_b])
        r = model.UniversalNet.restore(net.export())
        self.assertEqual(net.forward(x,a)[0],r.forward(x,a)[0])
        self.assertEqual(net.forward(x,b)[0],r.forward(x,b)[0])

    def test_02_head_validation_rejects_bad_tasks(self):
        for task in ((), ("revenue", "tenant"), ("", "tenant", "metric"), 4):
            with self.assertRaises(ValueError): model.UniversalNet.task_parts(task)

    def test_03_temporal_features_use_past_only(self):
        rows = [model.restaurant_values(i) for i in range(27)]
        encoder = model.TemporalEncoder(self.contract,model.baseline_scales(rows[:24],self.contract))
        first = encoder.encode(rows[:24],24)
        rows[26]["food_sales"] = 1e16
        second = encoder.encode(rows[:24],24)
        self.assertEqual(first,second)
        self.assertEqual(encoder.bucket("lag:3:food_sales"),encoder.bucket("lag:3:food_sales"))

    def test_04_shift_evidence_rejects_tamper_and_impossible_hours(self):
        with tempfile.TemporaryDirectory() as td:
            ledger = model.Ledger(Path(td)/"shift.db")
            body={"tenant":self.contract.tenant,"month":24,"shift_id":"a","employee_id":"EMP-K001",
                  "department":"kitchen","role":"cook","scheduled_hours":8.,"actual_hours":10.,"overtime_hours":2.}
            good={**body,"sha256":model.digest(body)}
            ledger.insert_shifts(self.contract,[good])
            ledger.insert_shifts(self.contract,[good])
            with self.assertRaisesRegex(ValueError,"SHA-256"):
                ledger.insert_shifts(self.contract,[{**good,"overtime_hours":3.}])
            too={**body,"actual_hours":25.}
            with self.assertRaisesRegex(ValueError,"Impossible"):
                ledger.insert_shifts(self.contract,[{**too,"sha256":model.digest(too)}])
            conflicting={**body,"actual_hours":9.,"overtime_hours":1.}
            with self.assertRaisesRegex(ValueError,"conflict"):
                ledger.insert_shifts(self.contract,[{**conflicting,"sha256":model.digest(conflicting)}])
            s=ledger.shift_summary(self.contract.tenant)
            self.assertEqual(s["overtime_employee_count"],1)
            self.assertAlmostEqual(s["total_overtime_hours"],2.)
            self.assertEqual(s["shift_records"],1)
            ledger.db.close()

    def test_05_no_shift_evidence_does_not_invent_headcount(self):
        with tempfile.TemporaryDirectory() as td:
            ledger = model.Ledger(Path(td)/"shift.db")
            self.assertIsNone(ledger.shift_summary(self.contract.tenant)["overtime_employee_count"])
            ledger.db.close()

    def test_06_two_departures_appear_in_shift_data(self):
        old=model.synthetic_employee_shifts(self.contract,24,model.restaurant_values(24))
        now=model.synthetic_employee_shifts(self.contract,26,model.restaurant_values(26))
        self.assertEqual(len({x["employee_id"] for x in old}),27)
        self.assertEqual(len({x["employee_id"] for x in now}),26)
        self.assertNotIn("EMP-K005",{x["employee_id"] for x in old})
        self.assertNotIn("EMP-K006",{x["employee_id"] for x in now})
        self.assertAlmostEqual(sum(x["overtime_hours"] for x in now),model.restaurant_values(26)["overtime_hours"])
        self.assertEqual(len(model.synthetic_employee_shifts(self.contract,23,model.restaurant_values(23))),0)

    def test_07_shift_integrity_part_of_ledger_digest(self):
        with tempfile.TemporaryDirectory() as td:
            ledger=model.Ledger(Path(td)/"x.db")
            earlier=ledger.integrity_digest(self.contract.tenant)
            records=model.synthetic_employee_shifts(self.contract,24,model.restaurant_values(24))
            ledger.insert_shifts(self.contract,records)
            self.assertNotEqual(earlier,ledger.integrity_digest(self.contract.tenant))
            ledger.db.execute("UPDATE employee_shifts SET overtime_hours=99 WHERE employee_id='EMP-K001'")
            ledger.db.commit()
            with self.assertRaisesRegex(ValueError,"integrity mismatch"):
                ledger.shift_summary(self.contract.tenant)
            ledger.db.close()

    def test_08_six_month_gate_rejects_no_improvement(self):
        hist=[model.restaurant_values(i) for i in range(27)]
        learning=model.Learning(self.contract,hist[:24]);learning.baseline(hist[:24])
        before=model.digest(learning.net.export())
        with mock.patch.object(learning,"fit",return_value=None):
            decision=learning.candidate_gate(hist,24)
        self.assertFalse(decision["promoted"])
        self.assertEqual(decision["validation_months"],6)
        self.assertEqual(decision["validation_start"],"2025-10")
        self.assertTrue(decision["training_excludes_validation_window"])
        self.assertEqual(before,model.digest(learning.net.export()))
        with self.assertRaisesRegex(ValueError,"one newly closed quarter"):
            learning.candidate_gate(hist,25)

    def test_09_checkpoint_wrong_version_fails(self):
        net=model.UniversalNet(); data=net.export()
        self.assertEqual(data["architecture"],"A440-U2.1.0")
        with self.assertRaisesRegex(ValueError,"migration"):
            model.UniversalNet.restore({**data,"architecture":"A440-U1.0.0"})

    def test_10_generic_metric_investigation_has_sources(self):
        with tempfile.TemporaryDirectory() as td:
            lab=model.A440Lab(self.contract,td,model.restaurant_values)
            for month in range(24):
                lab.add_synthetic_month(month)
            info=lab.investigate("Why did food cogs change?")
            self.assertEqual(info["metric"],"food_cogs")
            self.assertFalse(info["causal_claim"])
            self.assertIn("inventory",info["provenance_sources"])
            lab.db.db.close()

    def test_11_cross_industry_metric_heads_same_width(self):
        for factory, generator in ((model.retail_contract,model.retail_values),
                                   (model.logistics_contract,model.logistics_values)):
            contract=factory(); history=[generator(i) for i in range(24)]
            learner=model.Learning(contract,history);learner.baseline(history)
            self.assertEqual(learner.net.export()["width"],model.INPUTS)
            self.assertTrue(any(n.startswith("metric::") for n in learner.net.heads))

    def test_12_catchup_shift_reconciliation_and_question(self):
        with tempfile.TemporaryDirectory() as td:
            lab=model.A440Lab(self.contract,td,model.restaurant_values)
            lab.bootstrap()
            self.assertFalse(lab.db.shift_summary(self.contract.tenant)["available"])
            for _ in range(4): lab.close_quarter()
            summary=lab.db.shift_summary(self.contract.tenant,33,35)
            self.assertTrue(summary["available"])
            self.assertEqual(summary["employee_count"],26)
            self.assertEqual(summary["overtime_employee_count"],4)
            self.assertEqual(lab.ask("How many employees are working overtime?")["employee_shift_evidence"]["overtime_employee_count"],4)
            self.assertEqual(len(lab.db.events(self.contract.tenant)),3)
            self.assertIn("2026-05",[p for p,_ in lab.ask("Why is the kitchen over budget?")["months_over_budget"]])
            restored=model.A440Lab(self.contract,td,model.restaurant_values)
            restored.load()
            self.assertEqual(restored.db.shift_summary(self.contract.tenant,33,35)["employee_count"],26)
            lab.db.db.close();restored.db.db.close()

if __name__=="__main__":
    unittest.main(verbosity=2)
