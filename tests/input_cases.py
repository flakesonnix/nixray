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

    def _input_frames(self, value):
        return self._input_evaluate(f'''builtins.raylib {{
          width = 32; height = 32; hidden = true; fps = 0; maxFrames = 4; state = [];
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
