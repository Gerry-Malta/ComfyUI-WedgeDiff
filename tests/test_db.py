import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import db  # noqa: E402

GRAPH_V1 = {"1": {"class_type": "KSampler", "inputs": {"cfg": 7.0}}}
GRAPH_V2 = {"1": {"class_type": "KSampler", "inputs": {"cfg": 8.5}}}


class TestDb(unittest.TestCase):
    def setUp(self):
        self.conn = db.connect(":memory:")

    def tearDown(self):
        self.conn.close()

    def test_insert_creates_new_row(self):
        run_id, is_new = db.insert_or_touch(self.conn, "wf.json", GRAPH_V1)
        self.assertTrue(is_new)
        self.assertIsNotNone(run_id)

    def test_identical_rerun_does_not_duplicate(self):
        run_id_1, _ = db.insert_or_touch(self.conn, "wf.json", GRAPH_V1)
        run_id_2, is_new = db.insert_or_touch(self.conn, "wf.json", GRAPH_V1)
        self.assertFalse(is_new)
        self.assertEqual(run_id_1, run_id_2)
        history = db.get_history(self.conn, "wf.json")
        self.assertEqual(len(history), 1)

    def test_changed_graph_creates_new_row(self):
        run_id_1, _ = db.insert_or_touch(self.conn, "wf.json", GRAPH_V1)
        run_id_2, is_new = db.insert_or_touch(self.conn, "wf.json", GRAPH_V2)
        self.assertTrue(is_new)
        self.assertNotEqual(run_id_1, run_id_2)
        history = db.get_history(self.conn, "wf.json")
        self.assertEqual(len(history), 2)

    def test_history_is_newest_first(self):
        run_id_1, _ = db.insert_or_touch(self.conn, "wf.json", GRAPH_V1)
        time.sleep(0.01)
        run_id_2, _ = db.insert_or_touch(self.conn, "wf.json", GRAPH_V2)
        history = db.get_history(self.conn, "wf.json")
        self.assertEqual(history[0]["run_id"], run_id_2)
        self.assertEqual(history[1]["run_id"], run_id_1)

    def test_workflows_are_isolated(self):
        db.insert_or_touch(self.conn, "wf_a.json", GRAPH_V1)
        db.insert_or_touch(self.conn, "wf_b.json", GRAPH_V1)
        self.assertEqual(len(db.get_history(self.conn, "wf_a.json")), 1)
        self.assertEqual(len(db.get_history(self.conn, "wf_b.json")), 1)

    def test_attach_outputs(self):
        run_id, _ = db.insert_or_touch(self.conn, "wf.json", GRAPH_V1)
        ok = db.attach_outputs(
            self.conn, run_id, ["output/ComfyUI_00001.png"], "output/thumb.png"
        )
        self.assertTrue(ok)
        run = db.get_run(self.conn, run_id)
        self.assertEqual(run["output_paths"], ["output/ComfyUI_00001.png"])
        self.assertEqual(run["thumbnail_path"], "output/thumb.png")

    def test_attach_outputs_unknown_run_returns_false(self):
        self.assertFalse(db.attach_outputs(self.conn, "does-not-exist", []))

    def test_get_run_roundtrips_graph_json(self):
        run_id, _ = db.insert_or_touch(self.conn, "wf.json", GRAPH_V1)
        run = db.get_run(self.conn, run_id)
        self.assertEqual(run["graph_json"], GRAPH_V1)


if __name__ == "__main__":
    unittest.main()


class TestGroups(unittest.TestCase):
    def setUp(self):
        self.conn = db.connect(":memory:")

    def tearDown(self):
        self.conn.close()

    def test_list_groups_counts(self):
        db.insert_or_touch(self.conn, "alpha", GRAPH_V1)
        db.insert_or_touch(self.conn, "alpha", GRAPH_V2)  # 2 distinct in alpha
        db.insert_or_touch(self.conn, "beta", GRAPH_V1)   # 1 in beta
        groups = {g["label"]: g["count"] for g in db.list_groups(self.conn)}
        self.assertEqual(groups, {"alpha": 2, "beta": 1})

    def test_list_groups_empty(self):
        self.assertEqual(db.list_groups(self.conn), [])

    def test_delete_group_removes_rows(self):
        db.insert_or_touch(self.conn, "alpha", GRAPH_V1)
        db.insert_or_touch(self.conn, "alpha", GRAPH_V2)
        db.insert_or_touch(self.conn, "beta", GRAPH_V1)
        deleted = db.delete_group(self.conn, "alpha")
        self.assertEqual(deleted, 2)
        labels = [g["label"] for g in db.list_groups(self.conn)]
        self.assertEqual(labels, ["beta"])  # alpha gone, beta remains

    def test_delete_unknown_group_returns_zero(self):
        self.assertEqual(db.delete_group(self.conn, "ghost"), 0)
