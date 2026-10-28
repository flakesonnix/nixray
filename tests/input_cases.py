"""Binding tests with deterministic raylib polling states, not physical devices."""

import os
from pathlib import Path


class InputCases:
    def _input_evaluate(self, expression):
        if not self.input_library:
            self.skipTest("pass --input-library to enable input fixture tests")
        library = Path(self.input_library).resolve()
        self.assertTrue(library.is_file(), f"missing input fixture library: {library}")
        preload = str(library)
        if os.environ.get("LD_PRELOAD"):
            preload += " " + os.environ["LD_PRELOAD"]
        return self.evaluate(expression, env={"LD_PRELOAD": preload})

    def _input_frames(self, value, *, frames=4):
        return self._input_evaluate(f'''builtins.raylib {{
          width = 32; height = 32; hidden = true; fps = 0; maxFrames = {frames}; state = [];
        }} (frame: {{ commands = []; state = frame.state ++ [ ({value}) ]; }})''')

    def test_key_release_transitions(self):
        self.assertEqual(self._input_frames('''{
          down = frame.keysDown; pressed = frame.keysPressed; released = frame.keysReleased;
        }'''), {"frames": 4, "state": [
            {"down": [65], "pressed": [65], "released": []},
            {"down": [], "pressed": [], "released": [65]},
            {"down": [348], "pressed": [348], "released": []},
            {"down": [], "pressed": [], "released": [348]},
        ]})

    def test_mouse_release_transitions(self):
        self.assertEqual(self._input_frames('''{
          down = frame.mouseDown; pressed = frame.mousePressed; released = frame.mouseReleased;
        }'''), {"frames": 4, "state": [
            {"down": [0], "pressed": [0], "released": []},
            {"down": [], "pressed": [], "released": [0]},
            {"down": [6], "pressed": [6], "released": []},
            {"down": [], "pressed": [], "released": [6]},
        ]})

    def test_release_helpers(self):
        library = Path(__file__).resolve().parent.parent / "lib"
        self.assertEqual(self._input_frames(f'''let ray = import {library}; in {{
          key = ray.keyReleased frame ray.keys.a;
          mouse = ray.mouseReleased frame ray.mouse.left;
        }}'''), {"frames": 4, "state": [
            {"key": False, "mouse": False}, {"key": True, "mouse": True},
            {"key": False, "mouse": False}, {"key": False, "mouse": False},
        ]})

    def test_mouse_wheel_axes(self):
        self.assertEqual(self._input_frames('{ x = frame.mouseWheelX; y = frame.mouseWheelY; }'),
                         {"frames": 4, "state": [
                             {"x": 1.5, "y": -2.0}, {"x": 0.0, "y": 1.25},
                             {"x": -0.5, "y": 0.0}, {"x": 0.0, "y": 0.0},
                         ]})

    def test_text_input_queue_utf8(self):
        self.assertEqual(self._input_frames("frame.textInput"), {"frames": 4, "state": [
            "Aä🙂", "λ€\n", "\ufffd" * 4, "",
        ]})

    def test_text_input_scalar_boundaries(self):
        self.assertEqual(self._input_frames("frame.textInput", frames=6), {"frames": 6, "state": [
            "Aä🙂", "λ€\n", "\ufffd" * 4, "",
            "\x7f\u0080\u07ff\u0800\uffff\U00010000\U0010ffff", "",
        ]})

    def test_text_input_is_snapshot_value(self):
        self.assertEqual(self._input_evaluate('''builtins.raylib {
          width = 32; height = 32; hidden = true; fps = 0; maxFrames = 2;
        } (frame: { commands = []; state =
          if frame.frame == 0 then (_: frame.textInput) else frame.state null;
        })'''), {"frames": 2, "state": "Aä🙂"})

    def test_empty_text_input(self):
        self.assertEqual(self.evaluate('''builtins.raylib {
          width = 32; height = 32; hidden = true; fps = 0; maxFrames = 1;
        } (frame: assert frame.textInput == ""; { commands = []; })'''),
          {"frames": 1, "state": None})

    def test_input_example(self):
        example = Path(__file__).resolve().parent.parent / "examples/input.nix"
        for frames, text in ((4, "Aä🙂λ€\n" + "\ufffd" * 4), (6, "")):
            with self.subTest(frames=frames):
                self.assertEqual(self._input_evaluate(f'''import {example} {{
                  hidden = true; maxFrames = {frames};
                }}'''), {"frames": frames, "state": {"text": text, "radius": 37.0, "warm": True}})
