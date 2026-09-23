"""Synthetic-only unit, transport-contract, filesystem and CLI tests."""
from __future__ import annotations
import contextlib
import copy
import csv
import dataclasses
import io
import json
import random
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from companions.doi_intake import doi_intake as d


def source(values=None, **changes):
    base = d.demo_source()
    if values is not None:
        rows = tuple((a if isinstance(a, d.Cell) else (d.BLANK if a is None else d.Cell("TEXT", a)),
                      b if isinstance(b, d.Cell) else (d.BLANK if b is None else d.Cell("TEXT", b))) for a,b in values)
        changes.update(rows=rows, row_count=len(rows)+1)
    return dataclasses.replace(base, **changes)


def make(values=None, **kw):
    return d.make_plan(source(values), "test-run", **kw)


def record(number="91000001", **changes):
    r = {"order_number": number, "observed_at": "2026-09-21T14:00:00-04:00",
         "lookup_state": "completed", "followup_at": None, "last_known_status": "Shipped",
         "evidence_ref": "SYNTHETIC-UNIT-TEST"}
    return {**r, **changes}


def history(*records):
    return {"schema_version": d.HISTORY_SCHEMA, "records": list(records)}


def gc(value):
    if value is None:
        return {}
    key = "boolValue" if isinstance(value,bool) else "numberValue" if isinstance(value,(int,float)) else "stringValue"
    return {"userEnteredValue": {key:value}, "effectiveValue": {key:value}}


def provider(values=None):
    values = values or [("91000001", "Jude"), ("91000002", "Other Rep"), ("91000001", "JUDE")]
    props = {"sheetId": 1267803554, "title": "DOI Wednesday", "gridProperties": {"rowCount":len(values)+1, "columnCount":15}}
    meta = {"spreadsheetId":d.WORKBOOK_ID, "sheets":[{"properties":copy.deepcopy(props)}]}
    body = {"spreadsheetId":d.WORKBOOK_ID, "sheets":[{"properties":copy.deepcopy(props), "data":[
        {"rowData":[{"values":[{},{}]}]},
        {"startColumn":4, "rowData":[{"values":[gc("Rep"),gc("# Of Orders"),gc("Completed")]}]},
        {"startRow":1, "rowData":[{"values":[gc(a),gc(b)]} for a,b in values]}]}]}
    return meta,body


class FakeResponse:
    def __init__(self, value=None, code=200, raw=None):
        self.status_code=code
        self.raw = raw if raw is not None else json.dumps(value).encode()
        self.closed=False
    def iter_content(self, chunk_size=65536):
        for start in range(0,len(self.raw),chunk_size):
            yield self.raw[start:start+chunk_size]
    def close(self):
        self.closed=True


class FakeSession:
    def __init__(self, responses):
        self.responses=iter(responses); self.calls=[]
    def get(self,url,**kwargs):
        self.calls.append((url,kwargs))
        return next(self.responses)


class IDsAndOwners(unittest.TestCase):
    def test_valid_text_ids(self):
        for value in ["1","91000001",str(d.MAX_ID)]:
            self.assertEqual(d.canonical_id(value),value)
    def test_reject_ambiguous_text_ids(self):
        for value in ["0","01"," 1","1 ","+1","-1","1.0","1e3","1,000","١٢٣","１２３",str(d.MAX_ID+1),"=123",""]:
            with self.subTest(value=value): self.assertIsNone(d.canonical_id(value))
    def test_no_float_bool_or_int_text_coercion(self):
        for value in [1,1.0,True,False,None,{},[]]: self.assertIsNone(d.canonical_id(value))
        for value in [1.0,True,False]: self.assertIsNone(d.canonical_id(value,numeric=True))
    def test_exact_numeric_lexemes(self):
        for value,result in [("123.000","123"),("1.1",None),("1e3",None),("+1",None),("0",None),(str(d.MAX_ID+1),None)]:
            self.assertEqual(d.canonical_id(d.NumberLexeme(value),numeric=True),result)
    def test_numeric_integer(self): self.assertEqual(d.canonical_id(123,numeric=True),"123")
    def test_json_preserves_decimal_lexeme(self):
        parsed=d.decode_json('{"numberValue": 91000001.00}',api_numbers=True)
        self.assertIsInstance(parsed["numberValue"],d.NumberLexeme)
        self.assertEqual(str(parsed["numberValue"]),"91000001.00")
    def test_json_rejects_duplicate_members(self):
        with self.assertRaises(d.IntakeError): d.decode_json('{"a":1,"a":2}')
    def test_json_rejects_nonfinite(self):
        for raw in ['NaN','Infinity','-Infinity']:
            with self.assertRaises(d.IntakeError): d.decode_json(raw)
    def test_ascii_owner_normalization(self):
        for value in ["Jude","JUDE","jUdE","\t Jude\r\n"]:
            self.assertEqual(d.assignee(d.Cell("TEXT",value)),"JUDE")
    def test_unicode_and_alias_owners_do_not_match(self):
        for value in ["\u00a0Jude\u00a0","\u200bJude","\vJude","\fJude","Ju de","Jude Lewis","Jude,Sam","Judé","Јude"]:
            self.assertEqual(d.assignee(d.Cell("TEXT",value)),"OTHER")
    def test_empty_scalar_and_physical_blank_are_different(self):
        self.assertEqual(d.assignee(d.Cell("TEXT","")),"EMPTY_TEXT")
        self.assertEqual(d.assignee(d.Cell("TEXT"," \t")),"EMPTY_TEXT")
        self.assertEqual(d.assignee(d.BLANK),"MALFORMED")
    def test_formula_effective_jude_is_not_text(self):
        cell=d.google_cell({"userEnteredValue":{"formulaValue":'="Jude"'},"effectiveValue":{"stringValue":"Jude"}})
        self.assertEqual(cell.kind,"FORMULA")
        self.assertEqual(d.assignee(cell),"MALFORMED")
    def test_date_boolean_error_cell_types(self):
        datecell=gc(45000); datecell["effectiveFormat"]={"numberFormat":{"type":"DATE"}}
        self.assertEqual(d.google_cell(datecell).kind,"DATE_TIME")
        self.assertEqual(d.google_cell(gc(True)).kind,"BOOLEAN")
        self.assertEqual(d.google_cell({"effectiveValue":{"errorValue":{"type":"REF"}}}).kind,"ERROR")
    def test_effective_only_and_disagreement_unsupported(self):
        self.assertEqual(d.google_cell({"effectiveValue":{"stringValue":"Jude"}}).kind,"UNSUPPORTED")
        self.assertEqual(d.google_cell({"userEnteredValue":{"stringValue":"Other"},"effectiveValue":{"stringValue":"Jude"}}).kind,"UNSUPPORTED")
    def test_numeric_and_empty_cells(self):
        self.assertEqual(d.google_cell(gc(91000001)),d.Cell("NUMBER","91000001"))
        self.assertEqual(d.google_cell(gc("")),d.Cell("TEXT",""))
        self.assertEqual(d.google_cell({}),d.BLANK)
        self.assertEqual(d.google_cell(gc(91000001.0)).kind,"INVALID_NUMBER")


class IntakeAndHistory(unittest.TestCase):
    def test_demo_reconciliation(self):
        p=make()
        self.assertEqual(p["counts"],{"record_rows":11,"jude_occurrences":8,"out_of_scope_rows":3,"blank_rows":1,
            "unique_jude_orders":7,"duplicate_jude_occurrences":1,"held_orders":1,"lookup_orders":6})
        self.assertTrue(all(p["reconciliation"].values()))
    def test_duplicate_source_references_retained(self):
        p=make([("100","Jude"),(None,None),("100","JUDE")])
        self.assertEqual(p["lookup_queue"][0]["source_rows"],[2,4])
        self.assertEqual(len(p["source_occurrences"]),2)
    def test_conflict_is_held_even_if_other_rep_appears_first(self):
        p=make([("100","Other Rep"),("100","Jude"),("101","Jude")])
        self.assertEqual([j["order_number"] for j in p["lookup_queue"]],["101"])
        self.assertEqual(p["held_orders"][0]["source_rows"],[3])
    def test_foreign_names_ids_and_rows_not_persisted(self):
        p=make([("777777","PRIVATE_OTHER_REP"),("100","Jude"),("100","PRIVATE_OTHER_REP")])
        raw=json.dumps(p)
        self.assertNotIn("PRIVATE_OTHER_REP",raw); self.assertNotIn("777777",raw)
        self.assertEqual(p["held_orders"][0]["source_rows"],[3])
    def test_empty_text_other_assignment_is_not_conflict(self):
        p=make([("100",""),("100","Jude")])
        self.assertEqual(len(p["lookup_queue"]),1)
    def test_anchor_mismatch_blocks(self):
        anchors=dict(d.demo_source().anchors); anchors["E1"]=d.Cell("TEXT","Rep ")
        with self.assertRaises(d.IntakeError): d.make_plan(source(anchors=anchors),"run")
    def test_nonblank_top_left_blocks(self):
        anchors=dict(d.demo_source().anchors); anchors["A1"]=d.Cell("TEXT","")
        with self.assertRaises(d.IntakeError): d.make_plan(source(anchors=anchors),"run")
    def test_merged_inputs_block(self):
        with self.assertRaises(d.IntakeError): d.make_plan(source(merged_input=True),"run")
    def test_malformed_jude_row_blocks_whole_batch(self):
        with self.assertRaisesRegex(d.IntakeError,"entire batch"):
            make([("100","Jude"),("not-an-order","Jude")])
    def test_malformed_out_of_scope_row_also_blocks(self):
        with self.assertRaises(d.IntakeError): make([("100","Jude"),("bad","Other Rep")])
    def test_blank_rep_on_populated_row_blocks(self):
        with self.assertRaises(d.IntakeError): make([("100",None)])
    def test_blank_order_on_populated_row_blocks(self):
        with self.assertRaises(d.IntakeError): make([(None,"Jude")])
    def test_formula_order_blocks(self):
        with self.assertRaises(d.IntakeError): make([(d.Cell("FORMULA"),"Jude")])
    def test_formula_rep_blocks(self):
        with self.assertRaises(d.IntakeError): make([("100",d.Cell("FORMULA"))])
    def test_no_jude_is_valid_empty_queue(self):
        p=make([("100","Other Rep")]); self.assertEqual(p["status"],"NO_JUDE_ORDERS")
        self.assertEqual(p["lookup_queue"],[])
    def test_source_order_default(self):
        p=make([("200","Jude"),("100","Jude")])
        self.assertEqual([j["order_number"] for j in p["lookup_queue"]],["200","100"])
    def test_followup_sort_expected_order(self):
        p=make(sort="followups",history=d.demo_history())
        self.assertEqual([j["order_number"] for j in p["lookup_queue"]],
                         ["91000003","91000005","91000001","91000006","91000008","91000009"])
    def test_terminal_history_never_suppresses_fresh_lookup(self):
        for status in ["Shipped","Canceled","Excluded","FULL_DS","Resolved","Other rep"]:
            p=make([("91000001","Jude")],history=history(record(last_known_status=status)))
            self.assertEqual(len(p["lookup_queue"]),1)
            self.assertTrue(p["lookup_queue"][0]["requires_fresh_order_admin_read"])
    def test_history_without_sort_does_not_reorder(self):
        self.assertEqual([j["order_number"] for j in make(history=d.demo_history())["lookup_queue"]],
                         [j["order_number"] for j in make()["lookup_queue"]])
    def test_future_history_blocks(self):
        with self.assertRaises(d.IntakeError): make(history=history(record(observed_at="2026-09-24T12:00:00Z")))
    def test_naive_history_timestamp_blocks(self):
        with self.assertRaises(d.IntakeError): make(history=history(record(observed_at="2026-09-21T12:00:00")))
    def test_latest_history_conflict_preserved(self):
        p=make(history=history(record(),record(last_known_status="Canceled")),sort="followups")
        j=next(j for j in p["lookup_queue"] if j["order_number"]=="91000001")
        self.assertTrue(j["historical_context"]["conflicting_latest"])
        self.assertIsNone(j["historical_context"]["latest"])
        self.assertEqual(len(j["historical_context"]["observations"]),2)
    def test_identical_history_rows_deduplicate(self):
        p=make(history=history(record(),record()))
        self.assertEqual(len(p["lookup_queue"][0]["historical_context"]["observations"]),1)
    def test_history_irrelevant_order_not_exported(self):
        p=make(history=history(record(number="888888",last_known_status="PRIVATE_STATUS")))
        self.assertNotIn("PRIVATE_STATUS",json.dumps(p)); self.assertNotIn("888888",json.dumps(p))
    def test_history_unknown_fields_fail(self):
        r=record(); r["unexpected"]=1
        with self.assertRaises(d.IntakeError): make(history=history(r))
    def test_missing_evidence_ref_blocks(self):
        with self.assertRaises(d.IntakeError): make(history=history(record(evidence_ref="")))
    def test_lookup_state_is_not_assumed(self):
        with self.assertRaises(d.IntakeError): make(history=history(record(lookup_state="ready")))
    def test_no_execution_or_business_claims(self):
        p=make(); self.assertFalse(p["execution_authorized"])
        self.assertEqual(p["order_admin_reads"],0); self.assertEqual(p["source_writes"],0)
        for j in p["lookup_queue"]:
            self.assertNotIn("order_total",j); self.assertNotIn("split_eligible",j)
    def test_randomized_count_and_dedup_invariants(self):
        rng=random.Random(4231)
        for _ in range(100):
            values=[(str(rng.randrange(100,121)),rng.choice(["Jude","JUDE","Other Rep",""])) for _ in range(100)]
            p=make(values)
            self.assertTrue(all(p["reconciliation"].values()))
            all_numbers=[j["order_number"] for j in p["lookup_queue"]+p["held_orders"]]
            self.assertEqual(len(all_numbers),len(set(all_numbers)))
    def test_run_path_and_day_guards(self):
        for run in ["../bad","a/b","CON","con.txt","NUL.log","LPT1.txt","NUL","LPT1","name.","", "x"*81]:
            with self.assertRaises(d.IntakeError): d.validate_source_options("wednesday","2026-09-23",run)
        with self.assertRaises(d.IntakeError): d.validate_source_options("monday","2026-09-23","run")
        with self.assertRaises(d.IntakeError): d.validate_source_options("wednesday","09/23/2026","run")


class GoogleTransport(unittest.TestCase):
    def test_exact_read_only_requests_and_empty_rows(self):
        meta,body=provider([(91000001,"Jude"),(None,None),(91000001,"JUDE")])
        session=FakeSession([FakeResponse(meta),FakeResponse(body),FakeResponse(body)])
        s=d.acquire_google(session,"wednesday","2026-09-23",clock=lambda:"2026-09-23T15:00:00Z")
        p=d.make_plan(s,"live-mock")
        self.assertEqual(p["lookup_queue"][0]["source_rows"],[2,4])
        self.assertEqual(len(session.calls),3)
        for url,kw in session.calls:
            self.assertEqual(url,d.API+d.WORKBOOK_ID)
            self.assertFalse(kw["allow_redirects"])
        self.assertEqual(session.calls[1][1]["params"]["ranges"],
                         ["'DOI Wednesday'!A1:B1","'DOI Wednesday'!E1:G1","'DOI Wednesday'!A2:B4"])
    def test_changed_second_read_blocks(self):
        meta,body=provider(); different=copy.deepcopy(body)
        different["sheets"][0]["data"][2]["rowData"][0]["values"][0]=gc("91000009")
        session=FakeSession([FakeResponse(meta),FakeResponse(body),FakeResponse(different)])
        with self.assertRaises(d.IntakeError) as caught: d.acquire_google(session,"wednesday","2026-09-23")
        self.assertEqual(caught.exception.code,"SOURCE_CHANGED_DURING_READ")
    def test_read_grid_growth_blocks(self):
        meta,body=provider(); body["sheets"][0]["properties"]["gridProperties"]["rowCount"]+=1
        session=FakeSession([FakeResponse(meta),FakeResponse(body)])
        with self.assertRaises(d.IntakeError): d.acquire_google(session,"wednesday","2026-09-23")
    def test_missing_range_blocks(self):
        meta,body=provider(); body["sheets"][0]["data"].pop()
        with self.assertRaises(d.IntakeError): d.source_from_google(body,meta["sheets"][0]["properties"],"wednesday","2026-09-23","2026-09-23T15:00:00Z")
    def test_anchor_range_cannot_supply_record_rows(self):
        meta,body=provider()
        body["sheets"][0]["data"][0]["rowData"].append({"values": [gc("91000099"),gc("Jude")]})
        with self.assertRaises(d.IntakeError):
            d.source_from_google(body,meta["sheets"][0]["properties"],"wednesday","2026-09-23","2026-09-23T15:00:00Z")
    def test_empty_rows_outside_requested_range_block(self):
        meta,body=provider()
        body["sheets"][0]["data"][1]["rowData"].append({})
        with self.assertRaises(d.IntakeError):
            d.source_from_google(body,meta["sheets"][0]["properties"],"wednesday","2026-09-23","2026-09-23T15:00:00Z")
    def test_wrong_workbook_or_tab_blocks(self):
        for key,value in [("spreadsheetId","other")]:
            meta,_=provider(); meta[key]=value
            with self.assertRaises(d.IntakeError): d.selected_properties(meta,"wednesday")
        meta,_=provider(); meta["sheets"][0]["properties"]["title"]="Wrong tab"
        with self.assertRaises(d.IntakeError): d.selected_properties(meta,"wednesday")
    def test_row_limit_never_truncates(self):
        meta,_=provider(); meta["sheets"][0]["properties"]["gridProperties"]["rowCount"]=d.MAX_ROWS+1
        with self.assertRaises(d.IntakeError): d.selected_properties(meta,"wednesday")
    def test_input_merge_blocks_even_when_values_look_valid(self):
        meta,body=provider(); body["sheets"][0]["merges"]=[{"startRowIndex":1,"endRowIndex":3,"startColumnIndex":0,"endColumnIndex":1}]
        s=d.source_from_google(body,meta["sheets"][0]["properties"],"wednesday","2026-09-23","2026-09-23T15:00:00Z")
        with self.assertRaises(d.IntakeError): d.make_plan(s,"test")
    def test_unrelated_merge_does_not_block(self):
        meta,body=provider(); body["sheets"][0]["merges"]=[{"startRowIndex":1,"endRowIndex":3,"startColumnIndex":8,"endColumnIndex":10}]
        s=d.source_from_google(body,meta["sheets"][0]["properties"],"wednesday","2026-09-23","2026-09-23T15:00:00Z")
        self.assertFalse(s.merged_input)
    def test_403_is_not_retried_and_body_not_leaked(self):
        session=FakeSession([FakeResponse(code=403,raw=b"PRIVATE_TOKEN_OR_CUSTOMER_DATA")])
        with self.assertRaises(d.IntakeError) as caught: d._read_get(session,{})
        self.assertEqual(len(session.calls),1); self.assertEqual(caught.exception.code,"GOOGLE_ACCESS_DENIED")
        self.assertNotIn("PRIVATE",str(caught.exception))
    def test_throttling_has_bounded_backoff(self):
        waits=[]; session=FakeSession([FakeResponse(code=429),FakeResponse(code=503),FakeResponse({"ok":True})])
        self.assertEqual(d._read_get(session,{},sleep=waits.append),{"ok":True})
        self.assertEqual(waits,[1,2])
    def test_retries_exhaust(self):
        session=FakeSession([FakeResponse(code=429) for _ in range(4)]); waits=[]
        with self.assertRaises(d.IntakeError): d._read_get(session,{},sleep=waits.append)
        self.assertEqual(len(session.calls),4); self.assertEqual(waits,[1,2,4])
    def test_redirect_not_followed(self):
        session=FakeSession([FakeResponse(code=302)])
        with self.assertRaises(d.IntakeError): d._read_get(session,{})
        self.assertFalse(session.calls[0][1]["allow_redirects"])
    def test_response_size_blocks_not_truncates(self):
        session=FakeSession([FakeResponse(raw=b'x'*200)])
        with mock.patch.object(d,"MAX_BYTES",100):
            with self.assertRaises(d.IntakeError): d._read_get(session,{})
    def test_extra_range_cell_blocks(self):
        meta,body=provider(); body["sheets"][0]["data"][2]["rowData"][0]["values"].append(gc("PRIVATE_C_COLUMN"))
        with self.assertRaises(d.IntakeError): d.source_from_google(body,meta["sheets"][0]["properties"],"wednesday","2026-09-23","2026-09-23T15:00:00Z")


class FilesystemAndCLI(unittest.TestCase):
    def setUp(self): self.temp=tempfile.TemporaryDirectory(); self.root=Path(self.temp.name)
    def tearDown(self): self.temp.cleanup()
    def test_bundle_outputs_verify(self):
        p=make(); path,replayed=d.save_bundle(p,self.root)
        self.assertFalse(replayed); self.assertEqual(d.verify_bundle(path)["run_id"],"test-run")
        with (path/"lookup_queue.csv").open(encoding="utf-8-sig",newline="") as f:
            self.assertEqual(len(list(csv.DictReader(f))),6)
    def test_exact_replay_does_not_rewrite(self):
        p=make(); path,_=d.save_bundle(p,self.root)
        before={f.name:f.read_bytes() for f in path.iterdir()}
        changed_time=dataclasses.replace(source(),captured_at="2026-09-23T16:00:00Z")
        p2=d.make_plan(changed_time,"test-run")
        _,replayed=d.save_bundle(p2,self.root)
        self.assertTrue(replayed); self.assertEqual(before,{f.name:f.read_bytes() for f in path.iterdir()})
    def test_changed_material_refuses_overwrite(self):
        p=make(); path,_=d.save_bundle(p,self.root); before=(path/"intake.json").read_bytes()
        with self.assertRaises(d.IntakeError) as caught: d.save_bundle(make([("1","Jude")]),self.root)
        self.assertEqual(caught.exception.code,"RUN_CONFLICT"); self.assertEqual(before,(path/"intake.json").read_bytes())
    def test_changed_sort_refuses_overwrite(self):
        d.save_bundle(make(),self.root)
        with self.assertRaises(d.IntakeError): d.save_bundle(make(sort="followups"),self.root)
    def test_changed_history_refuses_overwrite(self):
        d.save_bundle(make(),self.root)
        with self.assertRaises(d.IntakeError): d.save_bundle(make(history=history(record())),self.root)
    def test_new_run_requeues_same_orders(self):
        p=make(); d.save_bundle(p,self.root)
        p2=d.make_plan(source(),"next-run"); d.save_bundle(p2,self.root)
        self.assertEqual(len(p2["lookup_queue"]),len(p["lookup_queue"]))
        self.assertNotEqual(p["lookup_queue"][0]["run_order_key"],p2["lookup_queue"][0]["run_order_key"])
    def test_tamper_detected(self):
        path,_=d.save_bundle(make(),self.root); (path/"lookup_queue.csv").write_text("tampered")
        with self.assertRaises(d.IntakeError): d.verify_bundle(path)
        with self.assertRaises(d.IntakeError): d.save_bundle(make(),self.root)
    def test_lock_prevents_concurrent_writes(self):
        (self.root/".test-run.lock").write_text("synthetic-lock")
        with self.assertRaises(d.IntakeError): d.save_bundle(make(),self.root)
        self.assertFalse((self.root/"test-run").exists())
    def test_partial_directory_not_reused(self):
        (self.root/"test-run").mkdir()
        with self.assertRaises(d.IntakeError): d.save_bundle(make(),self.root)
    def test_failure_receipt_has_no_queue_or_claimed_counts(self):
        args=d.parser().parse_args(["demo","--out",str(self.root)])
        path=d.record_failure(self.root,args,d.IntakeError("SOURCE_SCHEMA_UNRECOGNIZED","Source blocked."))
        r=json.loads(path.read_text()); self.assertEqual(r["lookup_queue"],[]); self.assertIsNone(r["counts"])
        self.assertFalse(r["candidate_queue_prepared"]); self.assertEqual(r["order_admin_reads"],0)
    def test_csv_formula_guard(self):
        raw=d.csv_bytes(["x"],[{"x":"=1+1"},{"x":" @SUM(A1)"},{"x":"normal"}]).decode("utf-8-sig")
        rows=list(csv.DictReader(io.StringIO(raw)))
        self.assertEqual(rows[0]["x"],"'=1+1"); self.assertTrue(rows[1]["x"].startswith("'")); self.assertEqual(rows[2]["x"],"normal")
    def test_cli_demo_and_verify(self):
        out=io.StringIO()
        with contextlib.redirect_stdout(out):
            code=d.main(["demo","--out",str(self.root)])
            verified=d.main(["verify",str(self.root/"demo-wednesday")])
        self.assertEqual(code,0); self.assertEqual(verified,0)
        self.assertIn("SYNTHETIC",out.getvalue())
    def test_cli_live_access_denied_produces_only_failure(self):
        with mock.patch.object(d,"google_session",side_effect=d.IntakeError("GOOGLE_ACCESS_DENIED","No permission.")):
            with contextlib.redirect_stderr(io.StringIO()):
                code=d.main(["sheets","--day","wednesday","--source-date","2026-09-23","--run-id","live-test","--out",str(self.root)])
        self.assertEqual(code,2); self.assertFalse((self.root/"live-test").exists())
        self.assertEqual(len(list((self.root/"failures").glob("*.json"))),1)
    def test_cli_bad_date_does_not_attempt_google(self):
        with mock.patch.object(d,"google_session") as session, contextlib.redirect_stderr(io.StringIO()):
            code=d.main(["sheets","--day","wednesday","--source-date","2026-09-21","--run-id","live-test","--out",str(self.root)])
        self.assertEqual(code,2); session.assert_not_called()
    def test_cli_missing_history_does_not_publish(self):
        with contextlib.redirect_stderr(io.StringIO()):
            code=d.main(["demo","--out",str(self.root),"--history",str(self.root/"missing.json")])
        self.assertEqual(code,2); self.assertFalse((self.root/"demo-wednesday").exists())


if __name__ == "__main__": unittest.main(verbosity=2)
