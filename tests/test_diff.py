import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from diff import diff_graphs, hash_graph  # noqa: E402


GRAPH_A = {
    "1": {
        "class_type": "CheckpointLoaderSimple",
        "inputs": {"ckpt_name": "sd_xl.safetensors"},
        "_meta": {"title": "Load Checkpoint"},
    },
    "2": {
        "class_type": "KSampler",
        "inputs": {
            "seed": 42,
            "steps": 20,
            "cfg": 7.0,
            "sampler_name": "euler",
            "model": ["1", 0],
        },
        "_meta": {"title": "KSampler"},
    },
    "3": {
        "class_type": "SaveImage",
        "inputs": {"images": ["2", 0]},
        "_meta": {"title": "Save Image"},
    },
}

# B = A with:
#  - node 1: class_type swapped (CheckpointLoaderSimple -> CheckpointLoaderSimpleXL)
#  - node 2: cfg changed 7.0 -> 8.5 (steps/seed/sampler untouched)
#  - node 4: new VAEDecode inserted between 2 and 3
#  - node 3: images input rewired from node 2 to node 4
GRAPH_B = {
    "1": {
        "class_type": "CheckpointLoaderSimpleXL",
        "inputs": {"ckpt_name": "sd_xl.safetensors"},
        "_meta": {"title": "Load Checkpoint"},
    },
    "2": {
        "class_type": "KSampler",
        "inputs": {
            "seed": 42,
            "steps": 20,
            "cfg": 8.5,
            "sampler_name": "euler",
            "model": ["1", 0],
        },
        "_meta": {"title": "KSampler"},
    },
    "3": {
        "class_type": "SaveImage",
        "inputs": {"images": ["4", 0]},
        "_meta": {"title": "Save Image"},
    },
    "4": {
        "class_type": "VAEDecode",
        "inputs": {"samples": ["2", 0], "vae": ["1", 1]},
        "_meta": {"title": "VAE Decode"},
    },
}


class TestDiffGraphs(unittest.TestCase):
    def setUp(self):
        self.result = diff_graphs(GRAPH_A, GRAPH_B)

    def test_added_node(self):
        self.assertEqual(
            self.result["added_nodes"],
            [{"id": "4", "class_type": "VAEDecode", "title": "VAE Decode"}],
        )

    def test_no_removed_nodes(self):
        self.assertEqual(self.result["removed_nodes"], [])

    def test_type_swap_detected_and_excluded_from_widget_diff(self):
        swaps = self.result["type_swapped"]
        self.assertEqual(len(swaps), 1)
        self.assertEqual(swaps[0]["id"], "1")
        self.assertEqual(swaps[0]["old_type"], "CheckpointLoaderSimple")
        self.assertEqual(swaps[0]["new_type"], "CheckpointLoaderSimpleXL")
        # node 1's ckpt_name didn't change, and even if it had, a type
        # swap should report once, not double up with a widget diff
        swap_ids = [c["id"] for c in self.result["changed"]]
        self.assertNotIn("1", swap_ids)

    def test_widget_change_detected(self):
        changed_by_id = {c["id"]: c for c in self.result["changed"]}
        self.assertIn("2", changed_by_id)
        self.assertEqual(changed_by_id["2"]["widgets"], {"cfg": [7.0, 8.5]})
        # untouched widgets must not appear
        self.assertNotIn("steps", changed_by_id["2"]["widgets"])
        self.assertNotIn("seed", changed_by_id["2"]["widgets"])

    def test_link_rewire_detected(self):
        changed_by_id = {c["id"]: c for c in self.result["changed"]}
        self.assertIn("3", changed_by_id)
        self.assertEqual(
            changed_by_id["3"]["links"],
            {"images": {"old": ["2", 0], "new": ["4", 0]}},
        )
        self.assertEqual(changed_by_id["3"]["widgets"], {})

    def test_unchanged_count(self):
        # common nodes = {1, 2, 3} -> 1 type-swapped, 2 changed, 3 changed
        # => 0 unchanged among common nodes
        self.assertEqual(self.result["unchanged_count"], 0)

    def test_identical_graphs_are_fully_unchanged(self):
        result = diff_graphs(GRAPH_A, GRAPH_A)
        self.assertEqual(result["added_nodes"], [])
        self.assertEqual(result["removed_nodes"], [])
        self.assertEqual(result["type_swapped"], [])
        self.assertEqual(result["changed"], [])
        self.assertEqual(result["unchanged_count"], 3)

    def test_removed_node_detected(self):
        smaller = {"1": GRAPH_A["1"]}
        result = diff_graphs(GRAPH_A, smaller)
        self.assertEqual(
            sorted(n["id"] for n in result["removed_nodes"]), ["2", "3"]
        )
        self.assertEqual(result["added_nodes"], [])


class TestHashGraph(unittest.TestCase):
    def test_identical_graphs_same_hash(self):
        self.assertEqual(hash_graph(GRAPH_A), hash_graph(dict(GRAPH_A)))

    def test_different_graphs_different_hash(self):
        self.assertNotEqual(hash_graph(GRAPH_A), hash_graph(GRAPH_B))

    def test_key_order_does_not_affect_hash(self):
        reordered = {"3": GRAPH_A["3"], "1": GRAPH_A["1"], "2": GRAPH_A["2"]}
        self.assertEqual(hash_graph(GRAPH_A), hash_graph(reordered))


if __name__ == "__main__":
    unittest.main()


class TestDiffLabels(unittest.TestCase):
    def test_labels_present_for_both_graphs(self):
        result = diff_graphs(GRAPH_A, GRAPH_B)
        # node 8 doesn't exist here; use the known nodes
        self.assertIn("labels_a", result)
        self.assertIn("labels_b", result)
        # node "1" is CheckpointLoaderSimple in A, ...XL in B (type swap)
        self.assertEqual(result["labels_a"]["1"]["type"], "CheckpointLoaderSimple")
        self.assertEqual(result["labels_b"]["1"]["type"], "CheckpointLoaderSimpleXL")
        # node "4" (VAEDecode) only exists in B
        self.assertIn("4", result["labels_b"])
        self.assertNotIn("4", result["labels_a"])

    def test_label_title_falls_back_to_type(self):
        g = {"7": {"class_type": "KSampler", "inputs": {}}}  # no _meta
        result = diff_graphs(g, g)
        self.assertEqual(result["labels_a"]["7"]["title"], "KSampler")
