#!/usr/bin/env python3
"""Exercise the real evaluator plugin, including rendering under Xvfb."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import unittest

from asset_cases import AssetCases
from texture_cases import TextureCases
from texture_control_cases import TextureControlCases
from texture_advanced_cases import TextureAdvancedCases
from pixel_cases import PixelCases
from input_cases import InputCases
from device_input_cases import DeviceInputCases
from window_cases import WindowCases
from text_cases import TextCases
from text_advanced_cases import TextAdvancedCases
from shape_cases import ShapeCases
from drawing_cases import DrawingCases
from drawing_extra_cases import DrawingExtraCases
from curve_cases import CurveCases
from clip_cases import ClipCases
from camera_cases import CameraCases
from three_d_cases import ThreeDCases
from model_cases import ModelCases
from lighting_cases import LightingCases
from image_cases import ImageCases
from render_cases import RenderCases
from collision_cases import CollisionCases
from collision_extra_cases import CollisionExtraCases
from blend_cases import BlendCases
from shader_cases import ShaderCases
from audio_cases import AudioCases
from audio_control_cases import AudioControlCases
from synth_cases import SynthCases


parser = argparse.ArgumentParser()
parser.add_argument("--nix", required=True)
parser.add_argument("--plugin", required=True)
parser.add_argument("--capture-library")
parser.add_argument("--input-library")
parser.add_argument("--audio-library")
parser.add_argument("--window-library")
parser.add_argument("--model-library")
parser.add_argument("--texture-library")
options, remaining = parser.parse_known_args()
ROOT = Path(__file__).resolve().parent.parent
RAY = f"import {ROOT / 'lib'}"
CONFIG = '{ width = 64; height = 64; hidden = true; fps = 0; maxFrames = 3; }'


class PluginTests(
    AssetCases, TextureCases, TextureControlCases, TextureAdvancedCases, PixelCases, InputCases, TextCases, TextAdvancedCases, ShapeCases, DrawingCases, DrawingExtraCases,
    ImageCases, LightingCases, ModelCases, ThreeDCases, WindowCases, DeviceInputCases, CurveCases, ClipCases, CameraCases, RenderCases,
    CollisionCases, CollisionExtraCases, BlendCases, ShaderCases, AudioCases, AudioControlCases, SynthCases, unittest.TestCase,
):
    capture_library = options.capture_library
    input_library = options.input_library
    audio_library = options.audio_library
    window_library = options.window_library
    model_library = options.model_library
    texture_library = options.texture_library

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
          validateAudio = builtins.typeOf builtins.raylibValidateAudio;
          version = builtins.raylibVersion;
          worldToScreen = builtins.typeOf builtins.raylibWorldToScreen2D;
          screenToWorld = builtins.typeOf builtins.raylibScreenToWorld2D;
        }''')
        self.assertEqual(result["raylib"], "lambda")
        self.assertEqual(result["legacyRun"], "lambda")
        self.assertEqual(result["validate"], "lambda")
        self.assertEqual(result["validateAudio"], "lambda")
        self.assertEqual(result["worldToScreen"], "lambda")
        self.assertEqual(result["screenToWorld"], "lambda")
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
          assets = {{
            renderTextures.scene = {{ width = 8; height = 8; }};
            shaders.fx = {{ fragment = {ROOT / 'examples/shaders/tint.fs'}; uniforms = {{
              gain = {{ type = "float"; value = 1; }};
              tint = {{ type = "vec3"; value = [1 1 1]; }};
            }}; }};
          }};
          commands = [
            (ray.clear ray.colors.white)
            (ray.clip {{ x = 0; y = 0; width = 32; height = 32;
                        commands = [ (ray.pixel {{ x = 3; y = 4; inherit color; }}) ]; }})
            (ray.camera2D {{ camera = {{}}; commands = [ (ray.pixel {{ x = 3; y = 4; inherit color; }}) ]; }})
            (ray.blend {{ mode = "additive"; commands = [ (ray.pixel {{ x = 3; y = 4; inherit color; }}) ]; }})
            (ray.shader {{ shader = "fx"; commands = [ (ray.pixel {{ x = 3; y = 4; inherit color; }}) ]; }})
            (ray.paint {{ texture = "scene"; commands = [ (ray.pixel {{ x = 1; y = 1; inherit color; }}) ]; }})
            (ray.text {{ text = "hello λ"; x = 1; y = 2; size = 10; inherit color; }})
            (ray.rectangle {{ x = 2; y = 2; width = 10; height = 12; inherit color; }})
            (ray.rectangleLines {{ x = 2; y = 2; width = 10; height = 12; inherit color; }})
            (ray.circle {{ x = 20; y = 20; radius = 3.5; inherit color; }})
            (ray.circleLines {{ x = 20; y = 20; radius = 3; inherit color; }})
            (ray.triangle {{ x1 = 1; y1 = 1; x2 = 1; y2 = 10; x3 = 10; y3 = 1; inherit color; }})
            (ray.triangleLines {{ x1 = 1; y1 = 1; x2 = 1; y2 = 10; x3 = 10; y3 = 1; inherit color; }})
            (ray.ellipse {{ x = 20; y = 20; radiusX = 4.5; radiusY = 2; inherit color; }})
            (ray.ellipseLines {{ x = 20; y = 20; radiusX = 4; radiusY = 2.5; inherit color; }})
            (ray.rectangleRounded {{ x = 2; y = 2; width = 10; height = 12; roundness = 0.5; inherit color; }})
            (ray.rectangleRoundedLines {{ x = 2; y = 2; width = 10; height = 12;
                                         roundness = 1; segments = 8; inherit color; }})
            (ray.line {{ x1 = -1; y1 = 2; x2 = 20; y2 = 20; inherit color; }})
            (ray.pixel {{ x = 3; y = 4; inherit color; }})
            (ray.fps 0 0)
          ];
        in {{
          validated = ray.validate commands;
          rendered = ray.run ({CONFIG} // {{ inherit assets; }}) (frame: {{ inherit commands; state = frame.frame; }});
        }}'''
        self.assertEqual(self.evaluate(expression), {
            "validated": 20, "rendered": {"frames": 3, "state": 2},
        })

    def test_empty_commands_and_default_state(self):
        self.assertEqual(self.evaluate(
            f'builtins.raylib {CONFIG} (_: {{ commands = []; }})'
        ), {"frames": 3, "state": None})

    def test_legacy_run_alias(self):
        self.assertEqual(self.evaluate(
            f'builtins.raylibRun {CONFIG} (_: {{ commands = []; }})'
        ), {"frames": 3, "state": None})

    def test_empty_assets(self):
        self.assertEqual(self.evaluate(
            f'builtins.raylib ({CONFIG} // {{ assets = {{ textures = {{}}; fonts = {{}}; }}; }})'
            ' (_: { commands = []; })'
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
            assert builtins.isFloat frame.mouseWheelX && builtins.isFloat frame.mouseWheelY;
            assert builtins.isString frame.textInput;
            assert builtins.isFunction frame.measureText;
            assert frame.audio == {{ enabled = false; sounds = {{}}; music = {{}}; }};
            assert builtins.isList frame.keysDown && builtins.isList frame.keysPressed;
            assert builtins.isList frame.mouseDown && builtins.isList frame.mousePressed;
            assert builtins.isList frame.keysReleased && builtins.isList frame.mouseReleased;
            {{ commands = []; state = frame.state + 1; }})'''),
            {"frames": 3, "state": 3})

    def test_early_close(self):
        self.assertEqual(self.evaluate(f'''builtins.raylib ({CONFIG} // {{ maxFrames = 0; }})
          (frame: {{ commands = []; close = frame.frame == 1; state = "done"; }})'''),
            {"frames": 2, "state": "done"})

    def test_omitted_state_is_preserved(self):
        self.assertEqual(self.evaluate(f'''builtins.raylib ({CONFIG} // {{ state = 42; }})
          (_: {{ commands = []; }})'''), {"frames": 3, "state": 42})

    def test_state_can_retain_callback_input(self):
        self.assertEqual(self.evaluate(f'''let
          result = builtins.raylib {CONFIG}
            (frame: {{ commands = []; state = _: frame.frame; }});
        in result.state null'''), 2)

    def test_repeated_windows_and_exception_cleanup(self):
        self.assertEqual(self.evaluate(f'''let
          failed = builtins.tryEval (builtins.raylib {CONFIG}
            (_: builtins.throw "callback failed"));
          first = builtins.raylib {CONFIG} (_: {{ commands = []; }});
          second = builtins.raylib ({CONFIG} // {{ hidden = false; resizable = true; }})
            (_: {{ commands = []; }});
        in assert !failed.success;
          builtins.seq first second'''), {"frames": 3, "state": None})

    def test_command_exception_cleanup(self):
        self.assertEqual(self.evaluate(f'''let
          failed = builtins.tryEval (builtins.raylib {CONFIG}
            (_: {{ commands = [ (throw "bad command") ]; }}));
        in assert !failed.success;
          builtins.raylib {CONFIG} (_: {{ commands = []; }})'''),
            {"frames": 3, "state": None})

    def test_nested_windows_rejected(self):
        self.evaluate(f'''builtins.raylib {CONFIG}
          (_: builtins.raylib {CONFIG} (_: {{ commands = []; }}))''',
          error="nested runs are not supported")

    def test_validation_without_display(self):
        self.assertEqual(self.evaluate("builtins.raylibValidate []", env={
            "DISPLAY": "", "WAYLAND_DISPLAY": "",
        }), 0)

    def test_window_without_display_rejected(self):
        self.evaluate(f"builtins.raylib {CONFIG} (_: {{ commands = []; }})",
                      env={"DISPLAY": "", "WAYLAND_DISPLAY": ""},
                      error="requires a graphical session")

    def test_unavailable_display_rejected(self):
        self.evaluate(f"builtins.raylib {CONFIG} (_: {{ commands = []; }})",
                      env={"DISPLAY": ":65530", "WAYLAND_DISPLAY": ""},
                      error="could not initialize a raylib window")

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

    def test_bad_configuration(self):
        for config, error in [
            ('{ width = 0; }', "'width' must be"),
            ('{ height = -1; }', "'height' must be"),
            ('{ fps = -1; }', "'fps' must be"),
            ('{ maxFrames = -1; }', "'maxFrames' must be"),
            ('{ hidden = 1; }', "expected a Boolean"),
            ('{ widht = 64; }', "unknown attribute 'widht'"),
            ('{ assets = []; }', "expected a set"),
            ('{ assets.typo = {}; }', "unknown attribute 'typo'"),
            ('{ assets.textures = []; }', "expected a set"),
            ('{ assets.textures."" = /tmp; }', "asset names must be nonempty"),
            ('{ assets.fonts.ui = 42; }', "asset paths must be"),
            ('{ assets.textures.logo = "relative.png"; }', "asset paths must be"),
        ]:
            with self.subTest(config=config):
                self.evaluate(f"builtins.raylib {config} (_: {{ commands = []; }})", error=error)
        self.evaluate(f"builtins.raylib {CONFIG} 42", error="expected a function")

    def test_bad_callback_result(self):
        for output, error in [
            ('[]', "expected a set"),
            ('{}', "missing attribute 'commands'"),
            ('{ commands = []; typo = true; }', "unknown attribute 'typo'"),
            ('{ commands = []; close = 1; }', "expected a Boolean"),
        ]:
            with self.subTest(output=output):
                self.evaluate(f"builtins.raylib {CONFIG} (_: {output})", error=error)

    def test_pure_and_restricted_evaluation_rejected(self):
        for flag in ("--pure-eval", "--restrict-eval"):
            with self.subTest(flag=flag):
                self.evaluate(f"builtins.raylib {CONFIG} (_: {{ commands = []; }})",
                              flags=[flag], error="requires impure, unrestricted evaluation")

    def test_state_is_forced_at_frame_boundary(self):
        self.evaluate(f'''builtins.raylib {CONFIG}
          (_: {{ commands = []; state = {{ unused = throw "state failed"; }}; }})''',
          error="state failed")

    def test_many_frames_without_nix_recursion(self):
        self.assertEqual(self.evaluate(f'''builtins.raylib
          ({CONFIG} // {{ maxFrames = 1500; state = 0; }})
          (frame: {{ commands = []; state = frame.state + 1; }})'''),
          {"frames": 1500, "state": 1500})


if __name__ == "__main__":
    unittest.main(argv=[__file__, *remaining], verbosity=2)
