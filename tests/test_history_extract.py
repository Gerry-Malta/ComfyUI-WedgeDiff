import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import history_extract as hx  # noqa: E402


PROMPT_ID = "abc-123"

GRAPH = {
    "1": {"class_type": "KSampler", "inputs": {"cfg": 7.0, "model": ["2", 0]}},
    "2": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "x.safetensors"}},
    "9": {"class_type": "SaveImage", "inputs": {"images": ["1", 0]}},
}

CANVAS_WORKFLOW = {"nodes": [{"id": 1}, {"id": 2}, {"id": 9}], "links": []}

# A realistic /history/{prompt_id} response
HISTORY_RESPONSE = {
    PROMPT_ID: {
        "prompt": [
            12,
            PROMPT_ID,
            GRAPH,
            {"extra_pnginfo": {"workflow": CANVAS_WORKFLOW}},
            ["9"],
        ],
        "outputs": {
            "9": {
                "images": [
                    {"filename": "ComfyUI_00042.png", "subfolder": "", "type": "output"},
                ]
            }
        },
        "status": {"status_str": "success", "completed": True},
    }
}


class TestUnwrap(unittest.TestCase):
    def test_unwrap_single_record(self):
        rec = hx.unwrap_record(HISTORY_RESPONSE, PROMPT_ID)
        self.assertIsNotNone(rec)
        self.assertIn("prompt", rec)

    def test_unwrap_missing_id(self):
        self.assertIsNone(hx.unwrap_record(HISTORY_RESPONSE, "nope"))

    def test_unwrap_empty(self):
        self.assertIsNone(hx.unwrap_record({}, PROMPT_ID))


class TestExtractGraph(unittest.TestCase):
    def setUp(self):
        self.rec = hx.unwrap_record(HISTORY_RESPONSE, PROMPT_ID)

    def test_exec_graph_is_the_api_prompt(self):
        self.assertEqual(hx.extract_exec_graph(self.rec), GRAPH)

    def test_exec_graph_feeds_diff_normalize(self):
        # the whole point of the pivot: the extracted graph is the same
        # shape diff.py already consumes
        from diff import normalize_graph

        normalized = normalize_graph(hx.extract_exec_graph(self.rec))
        self.assertEqual(normalized["1"].class_type, "KSampler")
        self.assertEqual(normalized["1"].widgets, {"cfg": 7.0})
        self.assertEqual(normalized["1"].links, {"model": ("2", 0)})

    def test_canvas_graph_extracted_when_present(self):
        self.assertEqual(hx.extract_canvas_graph(self.rec), CANVAS_WORKFLOW)

    def test_canvas_graph_none_when_absent(self):
        rec = {"prompt": [1, "x", GRAPH, {}, []]}
        self.assertIsNone(hx.extract_canvas_graph(rec))

    def test_malformed_prompt_returns_none(self):
        self.assertIsNone(hx.extract_exec_graph({"prompt": [1]}))
        self.assertIsNone(hx.extract_exec_graph({}))


class TestExtractOutputs(unittest.TestCase):
    def setUp(self):
        self.rec = hx.unwrap_record(HISTORY_RESPONSE, PROMPT_ID)

    def test_single_image(self):
        self.assertEqual(hx.extract_output_paths(self.rec), ["ComfyUI_00042.png"])

    def test_subfolder_joined_posix(self):
        rec = {
            "outputs": {
                "9": {"images": [{"filename": "f.png", "subfolder": "wan/run5", "type": "output"}]}
            }
        }
        self.assertEqual(hx.extract_output_paths(rec), ["wan/run5/f.png"])

    def test_video_gifs_key(self):
        rec = {
            "outputs": {
                "9": {"gifs": [{"filename": "out.mp4", "subfolder": "", "type": "output"}]}
            }
        }
        self.assertEqual(hx.extract_output_paths(rec), ["out.mp4"])

    def test_input_type_skipped(self):
        rec = {
            "outputs": {
                "9": {"images": [{"filename": "echo.png", "subfolder": "", "type": "input"}]}
            }
        }
        self.assertEqual(hx.extract_output_paths(rec), [])

    def test_multiple_nodes_deterministic_order(self):
        rec = {
            "outputs": {
                "20": {"images": [{"filename": "b.png", "type": "output"}]},
                "3": {"images": [{"filename": "a.png", "type": "output"}]},
            }
        }
        # sorted by (len, value): "3" before "20"
        self.assertEqual(hx.extract_output_paths(rec), ["a.png", "b.png"])

    def test_empty_outputs(self):
        self.assertEqual(hx.extract_output_paths({"outputs": {}}), [])
        self.assertEqual(hx.extract_output_paths({}), [])


class TestThumbnail(unittest.TestCase):
    def test_prefers_image(self):
        self.assertEqual(
            hx.pick_thumbnail(["out.mp4", "frame.png"]), "frame.png"
        )

    def test_falls_back_to_first(self):
        self.assertEqual(hx.pick_thumbnail(["out.mp4"]), "out.mp4")

    def test_empty(self):
        self.assertIsNone(hx.pick_thumbnail([]))


if __name__ == "__main__":
    unittest.main()
