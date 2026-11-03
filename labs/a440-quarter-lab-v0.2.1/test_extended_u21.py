#!/usr/bin/env python3
# ============================================================
# BEACON COMPUTING INITIATIVE
# Component: A440 U2.0 Extended Function and Failure-Path Audit
# Developer Seal: CJB-DEV-2026
# Execution: isolated temporary state; no external containers
# ============================================================
import contextlib
import copy
import io
import json
import math
import os
import sqlite3
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock
from http.server import ThreadingHTTPServer

import model
import endpoint


class ExtendedAudit(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="bci-a440-exhaustive-")
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)
        self.contract = model.restaurant_contract()

    def _value(self, month=0):
        return model.restaurant_values(month)

    def _lab(self):
        return model.A440Lab(self.contract, self.folder / "lab", model.restaurant_values)

    def test_01_legacy_net_features_and_verification(self):
        endpoint.ID = 1
        payload = endpoint.record(0)
        self.assertIs(model.verify(payload, "endpoint-01", 0), payload)
        with self.assertRaisesRegex(ValueError, "mismatch"):
            model.verify(payload, "endpoint-99", 0)
        with self.assertRaisesRegex(ValueError, "Quarter incomplete"):
            model.snapshot([payload])
        samples = []
        for i in range(1, 21):
            endpoint.ID = i
            samples.append(endpoint.record(7))
        self.assertEqual(model.snapshot(samples)["sources"], 20)
        n = model.Net()
        x = model.feature([1, 2, 3, 4], 8, 2)
        self.assertEqual(len(x), 6)
        prior = n.forward(x)[0]
        n.train([(x, 1.)], epochs=1)
        self.assertNotEqual(prior, n.forward(x)[0])
        self.assertEqual(len(n.parameters()["w"]), 10)

    def test_02_legacy_network_fetch_and_baseline(self):
        endpoint.ID = 5
        value = endpoint.record(8)
        class DummyResponse:
            def __enter__(self):
                return io.BytesIO(json.dumps(value).encode())
            def __exit__(self, *_):
                return False
        with mock.patch.object(model.urllib.request, "urlopen", return_value=DummyResponse()) as wrapped:
            self.assertEqual(model.get(5, "/quarter/8")["agent"], "endpoint-05")
            self.assertIn("endpoint-05:8000/quarter/8", wrapped.call_args.args[0])
        def fake_get(i, route):
            endpoint.ID = i
            return {"records": [endpoint.record(k) for k in range(8)]}
        old_data = model.DATA
        with mock.patch.object(model, "DATA", {}), mock.patch.object(model, "get", side_effect=fake_get):
            model.load_baseline()
            self.assertEqual(len(model.DATA), 20)
            self.assertEqual(len(model.examples()), 80)
            self.assertEqual(len(model.forecast_quarters(8, 4)), 4)
            self.assertGreaterEqual(model.predict_source(1, 8), 0)
        self.assertIs(model.DATA, old_data)

    def test_03_legacy_checkpoint_and_report(self):
        old_db = model.DB
        with mock.patch.object(model, "DB", self.folder / "legacy-state"):
            with mock.patch.object(model, "HISTORY", [{"quarter": 7, "metrics": {"sales": 1000, "costs": 400, "net_sales": 950}, "period": "baseline"}]):
                with mock.patch.object(model, "FORECAST", {"8": {"sales": 1200}}):
                    with mock.patch.object(model, "MODEL_VERSION", 1), mock.patch.object(model, "READY", True):
                        with mock.patch.object(model, "forecast_quarters", return_value=[{"sales": 1200}]*4):
                            r = model.report()
                            self.assertEqual(r["status"], "running")
                        model.save()
                        self.assertTrue((model.DB / "SHA256.json").exists())
        self.assertIs(model.DB, old_db)
        with mock.patch.object(model, "READY", False), mock.patch.object(model, "ERROR", "Initializing"):
            self.assertEqual(model.report()["status"], "initializing")
        with mock.patch.object(model, "READY", False), mock.patch.object(model, "ERROR", "startup error"):
            self.assertEqual(model.report()["status"], "blocked")
        model.atomic(self.folder / "simple.json", {"ok": True})
        self.assertEqual(json.loads((self.folder / "simple.json").read_text())["ok"], True)

    def test_04_legacy_complete_quarter_loop_bounded(self):
        def fake_get(i, route):
            endpoint.ID = i
            if route == "/baseline":
                return {"records": [endpoint.record(k) for k in range(8)]}
            if route == "/quarter/8":
                return endpoint.record(8)
            raise ValueError("audit controlled termination")
        def stop_sleep(*_):
            raise RuntimeError("end bounded live audit")
        with contextlib.redirect_stdout(io.StringIO()), \
             mock.patch.object(model, "get", side_effect=fake_get), \
             mock.patch.object(model, "DATA", {}), \
             mock.patch.object(model, "HISTORY", []), \
             mock.patch.object(model, "FORECAST", {}), \
             mock.patch.object(model, "NET", model.Net()), \
             mock.patch.object(model, "MODEL_VERSION", 0), \
             mock.patch.object(model, "READY", False), \
             mock.patch.object(model, "ERROR", "Initializing"), \
             mock.patch.object(model, "START", -9999999999.), \
             mock.patch.object(model, "SECONDS", 1), \
             mock.patch.object(model, "DB", self.folder / "legacy-loop"), \
             mock.patch.object(model.time, "sleep", side_effect=stop_sleep):
            model.loop()
            self.assertEqual(len(model.HISTORY), 9)
            self.assertEqual(model.MODEL_VERSION, 2)
            self.assertTrue(model.READY)
            self.assertIn("end bounded", model.ERROR)
            self.assertTrue((model.DB / "a440_state.json").exists())

    def test_05_helpers_and_calendar(self):
        self.assertEqual(model.canonical({"b": 1, "a": 2}), '{"a":2,"b":1}')
        self.assertEqual(len(model.digest({"a": 1})), 64)
        self.assertEqual(model.bounded(99, 0, 1), 1)
        self.assertEqual(model.money(1234.56), "$1,234.56")
        self.assertEqual(model.date_label(28), "2026-05")
        target = self.folder / "nested" / "state.json"
        h = model.atomic_json(target, {"value": 3})
        self.assertEqual(len(h), 64)
        self.assertEqual(json.loads(target.read_text())["value"], 3)
        with self.assertRaises(ValueError):
            model.canonical({"nan": float("nan")})

    def test_06_contract_formula_validation_and_cycle_guards(self):
        obj = self.contract.config()
        self.assertEqual(model.Contract.parse(obj).config(), obj)
        self.assertEqual(self.contract.formula_unit("kitchen_sales"), "USD")
        self.assertEqual(set(self.contract.formula_leaves("kitchen_sales")), {"food_sales", "delivery_sales"})
        self.assertAlmostEqual(self.contract.totals(self._value())["total_sales"], sum(self._value()[k] for k in ("food_sales", "bar_sales", "delivery_sales")))
        self.assertEqual(self.contract.evaluate_formula("food_sales", self._value()), self._value()["food_sales"])
        with self.assertRaises(ValueError):
            model.Contract("", [model.Metric("a", "b", "USD", "revenue")])
        with self.assertRaises(ValueError):
            model.Contract("x", [model.Metric("a", "b", "USD", "revenue"),model.Metric("a", "b", "USD", "revenue")])
        with self.assertRaises(ValueError):
            model.Contract("x", [model.Metric("a", "b", "USD", "revenue")], {"bad":{"op":"sum","args":["a","bad"]}})
        with self.assertRaises(ValueError):
            model.Contract("x", [model.Metric("a", "b", "USD", "revenue")], {"double":{"op":"sum","args":["a","a"]}})
        with self.assertRaises(ValueError):
            model.Contract("x", [model.Metric("a", "b", "USD", "revenue"),model.Metric("c", "b", "hours", "labor")], {"mix":{"op":"sum","args":["a","c"]}})
        with self.assertRaises(ValueError):
            self.contract.evaluate_formula("nonexistent", self._value())

    def test_07_evidence_validation_all_constraints(self):
        metric = self.contract.metrics["food_sales"]
        rec = model.Evidence.make(self.contract.tenant, 0, metric, 15)
        self.assertTrue(model.validate_evidence(rec, self.contract))
        self.assertEqual(model.Evidence.parse(rec.__dict__), rec)
        self.assertEqual(rec.body()["source"], "pos-food")
        for changes in ({"sha256": "0"*64}, {"tenant": "other"}, {"unit": "hours"}, {"month": -1}, {"month": 1.5}, {"value": float("inf")}):
            with self.subTest(changes=changes):
                with self.assertRaises(ValueError):
                    model.validate_evidence(model.dataclasses.replace(rec, **changes), self.contract)

    def test_08_ledger_idempotent_conflict_and_event_integrity(self):
        ledger = model.Ledger(self.folder / "ledger.db")
        rows = model.synthetic_records(self.contract,self._value(),0)
        ledger.insert_month(self.contract,rows)
        ledger.insert_month(self.contract,rows)
        self.assertEqual(len(ledger.history(self.contract)),1)
        self.assertEqual(len(ledger.integrity_digest(self.contract.tenant)),64)
        with self.assertRaises(ValueError):
            ledger.insert_month(self.contract,rows[:-1])
        changed = list(rows)
        changed[0] = model.Evidence.make(self.contract.tenant,0,self.contract.metrics["food_sales"],999.)
        with self.assertRaises(ValueError):
            ledger.insert_month(self.contract,changed)
        ledger.insert_event(self.contract.tenant,0,"event-a",{"note":"test"})
        ledger.insert_event(self.contract.tenant,0,"event-a",{"note":"test"})
        with self.assertRaises(ValueError):
            ledger.insert_event(self.contract.tenant,0,"event-a",{"note":"different"})
        self.assertEqual(len(ledger.events(self.contract.tenant)),1)
        checksum = ledger.verified_snapshot(self.folder / "snapshot.db")
        self.assertEqual(len(checksum),64)
        with ledger.db:
            ledger.db.execute("UPDATE events SET data_json='{}' WHERE event_id='event-a'")
        with self.assertRaisesRegex(ValueError,"Event integrity"):
            ledger.events(self.contract.tenant)
        ledger.db.close()

    def test_09_ledger_missing_month_and_corrupted_database(self):
        ledger = model.Ledger(self.folder / "gapped.db")
        ledger.insert_month(self.contract,model.synthetic_records(self.contract,self._value(1),1))
        with self.assertRaisesRegex(ValueError,"Incomplete chronological"):
            ledger.history(self.contract)
        ledger.db.close()

    def test_10_temporal_feature_hash_and_leakage(self):
        history = [self._value(i) for i in range(24)]
        scales = model.baseline_scales(history,self.contract)
        encoder = model.TemporalEncoder(self.contract,scales)
        b1 = encoder.bucket("source:pos-food")
        self.assertEqual(b1, encoder.bucket("source:pos-food"))
        self.assertTrue(4 <= b1[0] < model.INPUTS)
        with self.assertRaises(ValueError):
            model.baseline_scales(history[:2],self.contract)
        with self.assertRaises(ValueError):
            encoder.encode([],0)
        with self.assertRaises(ValueError):
            encoder.encode(history[:5],6)
        x = encoder.encode(history[:15],15)
        history[23]["food_sales"] = 10**15
        self.assertEqual(x,encoder.encode(history[:15],15))
        self.assertTrue(all(0 <= key < model.INPUTS for key in x))
        self.assertTrue(all(math.isfinite(val) for val in x.values()))

    def test_11_network_heads_train_export_restore_rejection(self):
        net = model.UniversalNet()
        feat = {0:1.,1:.2,4:.9}
        p0,_ = net.forward(feat,"revenue")
        net.train_one(feat,"revenue",1.2,.01)
        p1,_ = net.forward(feat,"revenue")
        self.assertNotEqual(p0,p1)
        self.assertIn("revenue",net.heads)
        checkpoint = net.export()
        restored = model.UniversalNet.restore(copy.deepcopy(checkpoint))
        self.assertEqual(restored.forward(feat,"revenue")[0],p1)
        for bad in (dict(checkpoint,architecture="wrong"),dict(checkpoint,width=42),dict(checkpoint,hidden=2)):
            with self.assertRaises(ValueError):
                model.UniversalNet.restore(bad)
        bad=copy.deepcopy(checkpoint);bad["w"][0]=[1.]
        with self.assertRaises(ValueError):model.UniversalNet.restore(bad)
        bad=copy.deepcopy(checkpoint);bad["bias"][0]=float("nan")
        with self.assertRaises(ValueError):model.UniversalNet.restore(bad)
        bad=copy.deepcopy(checkpoint);bad["heads"]["revenue"]["w"]=[.5]
        with self.assertRaises(ValueError):model.UniversalNet.restore(bad)

    def test_12_learning_baseline_candidate_and_bounds(self):
        hist=[self._value(m) for m in range(27)]
        learner=model.Learning(self.contract,hist[:24])
        self.assertGreaterEqual(learner.baseline(hist[:24]),0)
        self.assertTrue(learner.targets)
        self.assertGreaterEqual(learner.predict(hist[:24],"food_sales"),0)
        self.assertIn("forecast_metrics",learner.next_quarter(hist[:24]))
        with self.assertRaises(ValueError):learner.baseline(hist[:23])
        with self.assertRaises(ValueError):learner.score(learner.net,hist,[27])
        with self.assertRaises(ValueError):learner.candidate_gate(hist[:25], previous_end=26)
        decision=learner.candidate_gate(hist,previous_end=24)
        self.assertIn("promoted",decision)
        self.assertIn("old_normalized_MAE",decision)
        self.assertEqual(len(learner.decisions),1)

    def test_13_contract_profiles_and_synthetic_generator(self):
        for kind,(factory,generator) in model.PROFILES.items():
            with self.subTest(kind=kind):
                contract=factory()
                vals=generator(12)
                self.assertEqual(set(vals),set(contract.metrics))
                rec=model.synthetic_records(contract,vals,12)
                self.assertEqual(len(rec),len(vals))
                self.assertTrue(all(model.validate_evidence(x,contract) for x in rec))
                if kind!="restaurant":self.assertEqual(model.synthetic_events(contract,28),[])
        self.assertEqual(len(model.synthetic_events(self.contract,24)),1)
        self.assertEqual(len(model.synthetic_events(self.contract,26)),1)
        self.assertEqual(len(model.synthetic_events(self.contract,28)),1)
        self.assertEqual(model.synthetic_events(self.contract,29),[])
        with self.assertRaises(ValueError):
            model.synthetic_records(self.contract,{"a":1},0)
        self.assertEqual(model.anomaly_questions(self.contract,[self._value()]),[])
        results=model.anomaly_questions(self.contract,[self._value(27),self._value(28)])
        self.assertTrue(results)
        self.assertEqual(results[0]["status"],"hypothesis_to_investigate_not_causal_conclusion")

    def test_14_business_empty_bootstrap_query_routes(self):
        lab=self._lab()
        self.assertEqual(lab.summary()["status"],"empty")
        self.assertEqual(lab.ask("sales")["status"],"no_data")
        with self.assertRaises(ValueError):lab.add_synthetic_month(0) if lab.generator is None else lab.close_quarter()
        lab.bootstrap()
        self.assertEqual(lab.summary()["complete_months"],24)
        self.assertEqual(lab.ask("What were sales and profit?")["status"],"evidence_grounded")
        self.assertEqual(lab.ask("How many employees are working overtime?")["status"],"evidence_grounded")
        self.assertEqual(lab.ask("What is next quarter forecast?")["status"],"model_estimate")
        self.assertEqual(lab.ask("How are food costs?")["status"],"unsupported_intent")
        self.assertEqual(lab.ask("food cogs")["metric"],"food_cogs")
        with self.assertRaises(ValueError):lab.bootstrap()
        no_gen=model.A440Lab(self.contract,self.folder/"external-only")
        with self.assertRaises(ValueError):no_gen.add_synthetic_month(0)
        lab.db.db.close();no_gen.db.db.close()

    def test_15_business_quarter_replay_budget_and_recovery(self):
        lab=self._lab();lab.bootstrap()
        outputs=[lab.close_quarter() for _ in range(4)]
        self.assertEqual(len(outputs),4)
        self.assertEqual(outputs[-1]["period"],"2026-10..2026-12")
        over=lab.ask("Why did kitchen go over budget?")
        self.assertIn("2026-05",[m for m,v in over["months_over_budget"]])
        staffing=lab.ask("Tell me about employee departures and overtime")
        self.assertEqual(len(staffing["historical_events"]),3)
        self.assertIn("employees_active_at_close",outputs[-1]["actuals"])
        self.assertEqual(lab.summary()["complete_months"],36)
        self.assertIn("2027",model.date_label(36))
        restored=model.A440Lab(self.contract,lab.state_dir,model.restaurant_values)
        restored.load()
        self.assertEqual(restored.summary()["model_version"],lab.summary()["model_version"])
        with self.assertRaises(ValueError):restored.bootstrap()
        restored.db.db.close();lab.db.db.close()

    def test_16_business_ingestion_path(self):
        contract=model.retail_contract()
        path=self.folder/"retail"
        lab=model.A440Lab(contract,path)
        for m in range(27):
            lab.db.insert_month(contract,model.synthetic_records(contract,model.retail_values(m),m))
        self.assertEqual(lab.train_ingested()["replayed_quarters"],1)
        with self.assertRaises(ValueError):lab.train_ingested()
        loaded=model.A440Lab(contract,path)
        loaded.load()
        self.assertEqual(loaded.summary()["complete_months"],27)
        loaded.db.db.close();lab.db.db.close()

    def test_17_http_business_and_legacy(self):
        lab=self._lab();lab.bootstrap()
        model.BusinessHandler.lab=lab
        server=ThreadingHTTPServer(("127.0.0.1",0),model.BusinessHandler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            url=f"http://127.0.0.1:{server.server_port}"
            with urllib.request.urlopen(url+"/status") as r:
                self.assertEqual(json.load(r)["status"],"running")
            with urllib.request.urlopen(url+"/ask?q=next%20quarter%20forecast") as r:
                self.assertEqual(json.load(r)["status"],"model_estimate")
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                urllib.request.urlopen(url+"/invalid")
            self.assertEqual(ctx.exception.code,404)
        finally:
            server.shutdown();server.server_close();thread.join(timeout=2)
        with mock.patch.object(model,"READY",False),mock.patch.object(model,"ERROR","Initializing"):
            server=ThreadingHTTPServer(("127.0.0.1",0),model.Handler)
            t=threading.Thread(target=server.serve_forever,daemon=True);t.start()
            try:
                url=f"http://127.0.0.1:{server.server_port}"
                with urllib.request.urlopen(url+"/health") as r:
                    self.assertEqual(json.load(r)["status"],"initializing")
                with self.assertRaises(urllib.error.HTTPError):urllib.request.urlopen(url+"/unknown")
            finally:
                server.shutdown();server.server_close();t.join(timeout=2)
        lab.db.db.close()

    def test_18_architecture_and_dispatch(self):
        manifest=model.architecture_manifest()
        self.assertEqual(manifest["model"],"A440-U2.0 integrated")
        with mock.patch.object(sys,"argv",["model.py","--architecture"]),contextlib.redirect_stdout(io.StringIO()) as out:
            model.main()
            self.assertIn("architecture_ready",out.getvalue())
        with mock.patch.object(sys,"argv",["model.py","--show-contract"]),contextlib.redirect_stdout(io.StringIO()) as out:
            model.main()
            self.assertIn("restaurant-001",out.getvalue())
        with mock.patch.object(sys,"argv",["model.py"]),mock.patch.object(model,"launch_legacy_runtime") as launched:
            model.main();launched.assert_called_once()
        with mock.patch.object(sys,"argv",["model.py","--legacy"]),mock.patch.object(model,"launch_legacy_runtime") as launched:
            model.main();launched.assert_called_once()
        with mock.patch.object(sys,"argv",["model.py","--legacy","bad"]):
            with self.assertRaises(SystemExit):model.main()
        with mock.patch.object(sys,"argv",["model.py","--architecture","bad"]):
            with self.assertRaises(SystemExit):model.main()
        with mock.patch.object(sys,"argv",["model.py","--quarter-seconds","0"]),contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):model.cli()

    def test_20_foundation_test_runner_dispatch(self):
        # The real twelve foundation tests are run separately by audit_runner.
        # Here we verify the runner's success handling without duplicating training.
        with mock.patch.object(unittest.defaultTestLoader,"loadTestsFromTestCase",return_value=unittest.TestSuite()):
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertTrue(model.run_tests())

    def test_19_legacy_runtime_gate(self):
        with mock.patch.object(model,"SECONDS",0):
            with self.assertRaises(RuntimeError):model.launch_legacy_runtime()


if __name__ == "__main__":
    unittest.main(verbosity=2)
