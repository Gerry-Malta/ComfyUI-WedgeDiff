import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import db  # noqa: E402
import server_routes as sr  # noqa: E402


def make_history(prompt_id, graph, outputs=None):
    return {
        prompt_id: {
            "prompt": [1, prompt_id, graph, {}, []],
            "outputs": outputs or {},
            "status": {"completed": True},
        }
    }


GRAPH_V1 = {"1": {"class_type": "KSampler", "inputs": {"cfg": 7.0}}}
GRAPH_V2 = {"1": {"class_type": "KSampler", "inputs": {"cfg": 8.5}}}

OUTPUTS = {"9": {"images": [{"filename": "r1.png", "subfolder": "", "type": "output"}]}}


class TestCaptureLogic(unittest.TestCase):
    def setUp(self):
        self.conn = db.connect(":memory:")

    def tearDown(self):
        self.conn.close()

    def test_capture_stores_new_run(self):
        hist = make_history("p1", GRAPH_V1, OUTPUTS)
        res = sr.capture_logic(self.conn, "wf", "p1", hist)
        self.assertTrue(res["ok"])
        self.assertTrue(res["is_new"])
        self.assertEqual(res["output_count"], 1)

    def test_capture_attaches_outputs(self):
        hist = make_history("p1", GRAPH_V1, OUTPUTS)
        res = sr.capture_logic(self.conn, "wf", "p1", hist)
        run = db.get_run(self.conn, res["run_id"])
        self.assertEqual(run["output_paths"], ["r1.png"])
        self.assertEqual(run["thumbnail_path"], "r1.png")

    def test_capture_dedupes_identical_graph(self):
        sr.capture_logic(self.conn, "wf", "p1", make_history("p1", GRAPH_V1))
        res2 = sr.capture_logic(self.conn, "wf", "p2", make_history("p2", GRAPH_V1))
        self.assertFalse(res2["is_new"])
        self.assertEqual(len(db.get_history(self.conn, "wf")), 1)

    def test_capture_new_row_on_change(self):
        sr.capture_logic(self.conn, "wf", "p1", make_history("p1", GRAPH_V1))
        res2 = sr.capture_logic(self.conn, "wf", "p2", make_history("p2", GRAPH_V2))
        self.assertTrue(res2["is_new"])
        self.assertEqual(len(db.get_history(self.conn, "wf")), 2)

    def test_capture_missing_prompt_id(self):
        res = sr.capture_logic(self.conn, "wf", "ghost", {})
        self.assertFalse(res["ok"])
        self.assertIn("not found", res["reason"])

    def test_capture_malformed_record(self):
        bad = {"p1": {"prompt": [1], "outputs": {}}}
        res = sr.capture_logic(self.conn, "wf", "p1", bad)
        self.assertFalse(res["ok"])


class TestSyncLogic(unittest.TestCase):
    def setUp(self):
        self.conn = db.connect(":memory:")

    def tearDown(self):
        self.conn.close()

    def test_sync_backfills_all_new(self):
        full = {}
        full.update(make_history("p1", GRAPH_V1))
        full.update(make_history("p2", GRAPH_V2))
        stored = sr.sync_logic(self.conn, "wf", full)
        self.assertEqual(stored, 2)
        self.assertEqual(len(db.get_history(self.conn, "wf")), 2)

    def test_sync_skips_already_stored(self):
        sr.capture_logic(self.conn, "wf", "p1", make_history("p1", GRAPH_V1))
        full = {}
        full.update(make_history("p1", GRAPH_V1))   # already stored (same graph)
        full.update(make_history("p2", GRAPH_V2))   # new
        stored = sr.sync_logic(self.conn, "wf", full)
        self.assertEqual(stored, 1)
        self.assertEqual(len(db.get_history(self.conn, "wf")), 2)


if __name__ == "__main__":
    unittest.main()
