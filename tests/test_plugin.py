#!/usr/bin/env python3
"""Exercise the real evaluator plugin, including rendering under Xvfb."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import unittest


parser = argparse.ArgumentParser()
parser.add_argument("--nix", required=True)
parser.add_argument("--plugin", required=True)
options, remaining = parser.parse_known_args()
ROOT = Path(__file__).resolve().parent.parent
RAY = f"import {ROOT / 'lib'}"
CONFIG = '{ width = 64; height = 64; hidden = true; fps = 0; maxFrames = 3; }'


class PluginTests(unittest.TestCase):
    def evaluate(self, expression, *, error=None, flags=(), env=None):
        result = subprocess.run(
            [options.nix, "--option", "plugin-files", options.plugin,
             "--eval", "--strict", "--json", *flags, "--expr", expression],
            text=True, capture_output=True, timeout=30,
            env={**os.environ, **(env or {})},
        )
        if error is not None:
            self.assertNotEqual(result.returncode, 0, result.stdout)
            self.assertIn(error, result.stderr)
            # A signal/crash must never count as a successful rejection.
            self.assertGreater(result.returncode, 0, result.stderr)
            return None
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_registration(self):
        result = self.evaluate('''{
          raylib = builtins.typeOf builtins.raylib;
          legacyRun = builtins.typeOf builtins.raylibRun;
          validate = builtins.typeOf builtins.raylibValidate;
          version = builtins.raylibVersion;
        }''')
        self.assertEqual(result["raylib"], "lambda")
        self.assertEqual(result["legacyRun"], "lambda")
        self.assertEqual(result["validate"], "lambda")
        self.assertIsInstance(result["version"], str)
        self.assertTrue(result["version"])

    def test_example(self):
        self.assertEqual(self.evaluate(
            f"import {ROOT / 'examples/hello.nix'} {{ hidden = true; maxFrames = 2; }}"
        ), {"frames": 2, "state": {"x": 400, "y": 225}})

    def test_validation_is_pure(self):
        self.assertEqual(self.evaluate("builtins.raylibValidate []", flags=["--pure-eval"]), 0)

    def test_all_commands(self):
        expression = f'''let
          ray = {RAY};
          color = ray.colors.red;
          commands = [
            (ray.clear ray.colors.white)
            (ray.text {{ text = "hello λ"; x = 1; y = 2; size = 10; inherit color; }})
            (ray.rectangle {{ x = 2; y = 2; width = 10; height = 12; inherit color; }})
            (ray.rectangleLines {{ x = 2; y = 2; width = 10; height = 12; inherit color; }})
            (ray.circle {{ x = 20; y = 20; radius = 3.5; inherit color; }})
            (ray.circleLines {{ x = 20; y = 20; radius = 3; inherit color; }})
            (ray.line {{ x1 = -1; y1 = 2; x2 = 20; y2 = 20; inherit color; }})
            (ray.pixel {{ x = 3; y = 4; inherit color; }})
            (ray.fps 0 0)
          ];
        in {{
          validated = ray.validate commands;
          rendered = ray.run {CONFIG} (frame: {{ inherit commands; state = frame.frame; }});
        }}'''
        self.assertEqual(self.evaluate(expression), {
            "validated": 9, "rendered": {"frames": 3, "state": 2},
        })

    def test_empty_commands_and_default_state(self):
        self.assertEqual(self.evaluate(
            f'builtins.raylib {CONFIG} (_: {{ commands = []; }})'
        ), {"frames": 3, "state": None})

    def test_partial_application_without_display(self):
        self.assertEqual(self.evaluate("builtins.typeOf (builtins.raylib {})", env={
            "DISPLAY": "", "WAYLAND_DISPLAY": "",
        }), "lambda")

    def test_frame_snapshot_and_state(self):
        self.assertEqual(self.evaluate(f'''builtins.raylib ({CONFIG} // {{ state = 0; }})
          (frame:
            assert frame.frame == frame.state;
            assert frame.width == 64 && frame.height == 64;
            assert builtins.isFloat frame.time && builtins.isFloat frame.delta;
            assert builtins.isInt frame.mouseX && builtins.isInt frame.mouseY;
            assert builtins.isList frame.keysDown && builtins.isList frame.keysPressed;
            assert builtins.isList frame.mouseDown && builtins.isList frame.mousePressed;
            {{ commands = []; state = frame.state + 1; }})'''),
            {"frames": 3, "state": 3})

    def test_validation_without_display(self):
        self.assertEqual(self.evaluate("builtins.raylibValidate []", env={
            "DISPLAY": "", "WAYLAND_DISPLAY": "",
        }), 0)

    def test_bad_commands(self):
        cases = [
            ('{}', "expected a list"),
            ('[ {} ]', "missing attribute 'op'"),
            ('[ { op = "oops"; } ]', "unknown drawing operation"),
            ('[ { op = "clear"; color = [0 0 0]; } ]', "color must be"),
            ('[ { op = "clear"; color = [0 0 0 256]; } ]', "integer in [0, 255]"),
            ('[ { op = "clear"; color = [(-1) 0 0 255]; } ]', "integer in [0, 255]"),
            ('[ { op = "clear"; color = [0.5 0 0 255]; } ]', "expected an integer"),
            ('[ { op = "clear"; color = [0 0 0 255]; typo = true; } ]', "unknown attribute 'typo'"),
            ('[ { op = "circle"; x = 0; y = 0; radius = -1; color = [0 0 0 255]; } ]', "finite number"),
            ('[ { op = "circle"; x = 0; y = 0; radius = 1.0e100; color = [0 0 0 255]; } ]', "finite number"),
            ('[ { op = "pixel"; x = 2147483648; y = 0; color = [0 0 0 255]; } ]', "integer in"),
            ('[ { op = "text"; text = "a"; x = 0; y = 0; size = 0; color = [0 0 0 255]; } ]', "integer in"),
        ]
        for commands, error in cases:
            with self.subTest(commands=commands):
                self.evaluate(f"builtins.raylibValidate {commands}", error=error)



if __name__ == "__main__":
    unittest.main(argv=[__file__, *remaining], verbosity=2)
