"""Pure camera math and evaluator-driven matrix/scissor pixel tests."""

import os
from pathlib import Path


class CameraCases:
    def _camera_pixels(self, camera="{}", commands=None, *, assets="{}"):
        commands = commands or '[ { op = "rectangle"; x = 1; y = 2; width = 4; height = 4; color = [255 0 0 255]; } ]'
        return self._capture(f'''[
          {{ op = "clear"; color = [0 0 0 255]; }}
          {{ op = "camera2D"; camera = {camera}; commands = {commands}; }}
        ]''', assets=assets)

    def test_camera_math_is_pure(self):
        for name in ("raylibWorldToScreen2D", "raylibScreenToWorld2D"):
            with self.subTest(name=name):
                result = self.evaluate(f"builtins.{name} {{}} {{ x = 3.5; y = -2; }}", flags=["--pure-eval"],
                                       env={"DISPLAY": "", "WAYLAND_DISPLAY": ""})
                self.assertEqual(result, {"x": 3.5, "y": -2.0})
                self.assertIsInstance(result["x"], float)
                self.assertIsInstance(result["y"], float)

    def test_camera_target_offset_zoom(self):
        self.assertEqual(self.evaluate('''let
          camera = { target = { x = 10; y = 20; }; offset = { x = 100; y = 50; }; zoom = 2; };
        in {
          screen = builtins.raylibWorldToScreen2D camera { x = 12; y = 23; };
          world = builtins.raylibScreenToWorld2D camera { x = 104; y = 56; };
        }'''), {"screen": {"x": 104.0, "y": 56.0}, "world": {"x": 12.0, "y": 23.0}})

    def test_camera_clockwise_rotation(self):
        for rotation, y in ((90, 20), (450, 20), (-90, 12)):
            with self.subTest(rotation=rotation):
                result = self.evaluate(f'''builtins.raylibWorldToScreen2D {{
                  offset = {{ x = 16; y = 16; }}; zoom = 2; rotation = {rotation};
                }} {{ x = 2; y = 0; }}''')
                self.assertAlmostEqual(result["x"], 16, places=4)
                self.assertAlmostEqual(result["y"], y, places=4)

    def test_camera_round_trip_and_helpers(self):
        library = Path(__file__).resolve().parent.parent / "lib"
        result = self.evaluate(f'''let
          ray = import {library};
          camera = {{ target = {{ x = -12.5; y = 3.75; }}; offset = {{ x = 16.5; y = -20.25; }};
                      zoom = 1.7; rotation = 37.5; }};
          point = {{ x = 4.5; y = 17; }};
        in ray.screenToWorld2D camera (ray.worldToScreen2D camera point)''', env={"DISPLAY": "", "WAYLAND_DISPLAY": ""})
        self.assertAlmostEqual(result["x"], 4.5, places=4)
        self.assertAlmostEqual(result["y"], 17, places=4)

    def test_bad_camera_specs(self):
        for camera, error in (
            ("[]", "expected a set"),
            ("{ zoon = 1; }", "unknown attribute 'zoon'"),
            ("{ target = {}; }", "missing attribute 'x'"),
            ("{ offset = { x = 0; }; }", "missing attribute 'y'"),
            ("{ target = { x = true; y = 0; }; }", "expected"),
            ("{ offset = { x = 0; y = 0; z = 0; }; }", "unknown attribute 'z'"),
            ("{ zoom = 0; }", "'zoom' must be positive"),
            ("{ zoom = -1; }", "finite number"),
            ("{ zoom = 1.0e-100; }", "'zoom' must be positive"),
            ("{ zoom = 1.0e100; }", "finite number"),
            ("{ rotation = 1.0e100; }", "finite number"),
            ("{ zoom = 1.0e30; }", "finite and invertible"),
            ("{ zoom = 1.0e-30; }", "finite and invertible"),
            ("{ target = { x = 3.0e38; y = 0; }; zoom = 2; }", "finite and invertible"),
        ):
            with self.subTest(camera=camera):
                self.evaluate(f"builtins.raylibWorldToScreen2D {camera} {{ x = 0; y = 0; }}", error=error)

    def test_bad_camera_points(self):
        for point, error in (("{}", "missing attribute 'x'"), ("{ x = 0; }", "missing attribute 'y'"),
                             ("{ x = 0; y = 0; z = 0; }", "unknown attribute 'z'"),
                             ("{ x = 1.0e100; y = 0; }", "finite number")):
            with self.subTest(point=point):
                self.evaluate(f"builtins.raylibScreenToWorld2D {{}} {point}", error=error)

    def test_camera_conversion_overflow(self):
        for name, zoom in (("raylibWorldToScreen2D", "10"), ("raylibScreenToWorld2D", "0.1")):
            with self.subTest(name=name):
                self.evaluate(f"builtins.{name} {{ zoom = {zoom}; }} {{ x = 3.0e38; y = 0; }}",
                              error="converted point must have finite coordinates")

    def test_camera_validation_is_pure(self):
        self.assertEqual(self.evaluate('''builtins.raylibValidate [
          { op = "camera2D"; camera = { zoom = 2; rotation = -45; }; commands = [
            { op = "clip"; x = 0; y = 0; width = 4; height = 4; commands = [
              { op = "texture"; texture = "unloaded"; x = 0; y = 0; }
            ]; }
          ]; }
        ]''', flags=["--pure-eval"], env={"DISPLAY": "", "WAYLAND_DISPLAY": ""}), 1)

    def test_bad_camera_commands(self):
        for command, error in (
            ('{ op = "camera2D"; commands = []; }', "missing attribute 'camera'"),
            ('{ op = "camera2D"; camera = {}; }', "missing attribute 'commands'"),
            ('{ op = "camera2D"; camera = {}; commands = null; }', "expected a list"),
            ('{ op = "camera2D"; camera = {}; commands = []; typo = true; }', "unknown attribute 'typo'"),
            ('{ op = "camera2D"; camera = {}; commands = [ { op = "invalid-child"; } ]; }', "unknown drawing operation"),
        ):
            with self.subTest(command=command):
                self.evaluate(f"builtins.raylibValidate [ {command} ]", error=error)
        self.evaluate('''builtins.raylibValidate [ { op = "clip"; x = 0; y = 0; width = 0; height = 0;
          commands = [ { op = "camera2D"; camera.zoom = 0; commands = []; } ];
        } ]''', error="'zoom' must be positive")

    def test_camera_and_mixed_nesting_limits(self):
        for mixed in (False, True):
            for depth in (64, 65):
                expression = f'''let nested = n: if n == 0 then [] else [ (
                  (if {str(mixed).lower()} && n - (builtins.div n 2) * 2 == 0
                   then {{ op = "clip"; x = 0; y = 0; width = 32; height = 32; }}
                   else {{ op = "camera2D"; camera = {{}}; }}) // {{ commands = nested (n - 1); }}
                ) ]; in builtins.raylibValidate (nested {depth})'''
                with self.subTest(mixed=mixed, depth=depth):
                    if depth == 64:
                        self.assertEqual(self.evaluate(expression), 1)
                    else:
                        self.evaluate(expression, error="nesting must not exceed 64 levels")

    def test_deep_camera_rendering(self):
        pixels = self._capture('''let nested = n: if n == 0 then [
          { op = "rectangle"; x = 0; y = 0; width = 4; height = 3; color = [255 0 0 255]; }
        ] else [ { op = "camera2D"; camera = { offset = { x = 4; y = 6; }; zoom = 2; };
                   commands = nested (n - 1); } ];
        in [ { op = "clear"; color = [0 0 0 255]; } ] ++ nested 64''')
        self.assert_clip_region(pixels, 4, 6, 12, 12)

    def test_identity_camera_pixels(self):
        commands = '[ { op = "rectangle"; x = 1; y = 2; width = 4; height = 4; color = [255 0 0 255]; } ]'
        self.assertEqual(self._camera_pixels(commands=commands),
                         self._capture(f'[ {{ op = "clear"; color = [0 0 0 255]; }} ] ++ {commands}'))

    def test_camera_translation_and_zoom_pixels(self):
        pixels = self._camera_pixels(
            "{ target = { x = 10; y = 20; }; offset = { x = 8; y = 6; }; zoom = 2; }",
            '[ { op = "rectangle"; x = 10; y = 20; width = 4; height = 3; color = [255 0 0 255]; } ]',
        )
        self.assert_clip_region(pixels, 8, 6, 16, 12)

    def test_camera_rotation_pixels(self):
        for rotation, region in ((90, (10, 18, 14, 26)), (-90, (18, 6, 22, 14))):
            with self.subTest(rotation=rotation):
                pixels = self._camera_pixels(f"{{ offset = {{ x = 16; y = 16; }}; zoom = 2; rotation = {rotation}; }}",
                  '[ { op = "rectangle"; x = 1; y = 1; width = 4; height = 2; color = [255 0 0 255]; } ]')
                self.assert_clip_region(pixels, *region)

    def test_nested_camera_replacement_and_restoration(self):
        pixels = self._capture('''[
          { op = "clear"; color = [0 0 0 255]; }
          { op = "camera2D"; camera = { offset = { x = 4; y = 4; }; zoom = 2; }; commands = [
            { op = "rectangle"; x = 0; y = 0; width = 4; height = 4; color = [255 0 0 255]; }
            { op = "camera2D"; camera.offset = { x = 20; y = 4; }; commands = [
              { op = "rectangle"; x = 0; y = 0; width = 4; height = 4; color = [0 255 0 255]; }
            ]; }
            { op = "rectangle"; x = 0; y = 6; width = 4; height = 2; color = [0 0 255 255]; }
          ]; }
          { op = "pixel"; x = 28; y = 28; color = [255 255 255 255]; }
        ]''')
        for y in range(32):
            for x in range(32):
                color = (0, 0, 0)
                if 4 <= x < 12 and 4 <= y < 12:
                    color = (255, 0, 0)
                if 20 <= x < 24 and 4 <= y < 8:
                    color = (0, 255, 0)
                if 4 <= x < 12 and 16 <= y < 20:
                    color = (0, 0, 255)
                if (x, y) == (28, 28):
                    color = (255, 255, 255)
                self.assert_pixel(pixels, x, y, color)

    def test_camera_and_window_clipping_pixels(self):
        for camera_first in (False, True):
            with self.subTest(camera_first=camera_first):
                pixels = self._capture(f'''let
                  drawing = [ {{ op = "rectangle"; x = 0; y = 0; width = 16; height = 16; color = [255 0 0 255]; }} ];
                  camera = {{ offset = {{ x = 4; y = 4; }}; zoom = 2; }};
                  clip = {{ op = "clip"; x = 8; y = 8; width = 4; height = 4; }};
                in [ {{ op = "clear"; color = [0 0 0 255]; }} ] ++
                  (if {str(camera_first).lower()} then [ {{ op = "camera2D"; inherit camera;
                    commands = [ (clip // {{ commands = drawing; }}) ]; }} ]
                   else [ (clip // {{ commands = [ {{ op = "camera2D"; inherit camera; commands = drawing; }} ]; }}) ])''')
                self.assert_clip_region(pixels, 8, 8, 12, 12)

    def test_camera_text_and_texture_pixels(self):
        assets = f"{{ textures.logo = {self.texture_path}; fonts.ui = {self.font_path}; }}"
        for command in (
            '{ op = "text"; font = "ui"; text = "A"; x = 1; y = 2; size = 4; color = [255 0 0 255]; }',
            '{ op = "texture"; texture = "logo"; x = 1; y = 2; scale = 2; tint = [255 0 0 255]; }',
        ):
            with self.subTest(command=command):
                pixels = self._camera_pixels("{ offset = { x = 4; y = 4; }; zoom = 2; }", f"[ {command} ]", assets=assets)
                self.assert_clip_region(pixels, 6, 8, 14, 16)

    def test_camera_does_not_transform_clear(self):
        pixels = self._camera_pixels("{ offset = { x = 1000; y = 1000; }; zoom = 2; }",
                                     '[ { op = "clear"; color = [255 0 0 255]; } ]')
        self.assertEqual(set(pixels), {(255, 0, 0)})

    def test_camera_does_not_leak_between_frames(self):
        pixels = self._capture('''if frame.frame == 0 then [
          { op = "clear"; color = [0 0 0 255]; }
          { op = "camera2D"; camera = { offset = { x = 8; y = 8; }; zoom = 2; }; commands = [
            { op = "rectangle"; x = 4; y = 4; width = 8; height = 4; color = [255 0 0 255]; }
          ]; }
        ] else [
          { op = "clear"; color = [0 0 0 255]; }
          { op = "rectangle"; x = 4; y = 4; width = 8; height = 4; color = [255 0 0 255]; }
        ]''', frames=2)
        self.assert_clip_region(pixels, 4, 4, 12, 8)

    def test_camera_exception_cleanup(self):
        self.assertEqual(self.evaluate('''let
          config = { hidden = true; maxFrames = 1; fps = 0; };
          failed = builtins.tryEval (builtins.raylib config (_: { commands = [
            { op = "camera2D"; camera = {}; commands = [ (throw "camera child failed") ]; }
          ]; }));
        in assert !failed.success; builtins.raylib config (_: { commands = []; })'''), {"frames": 1, "state": None})

    def test_camera_batch_validates_before_drawing(self):
        if not self.capture_library:
            self.skipTest("pass --capture-library to enable framebuffer pixel tests")
        destination = self.asset_directory / "invalid-camera.ppm"
        preload = str(Path(self.capture_library).resolve())
        if os.environ.get("LD_PRELOAD"):
            preload += " " + os.environ["LD_PRELOAD"]
        self.evaluate('''builtins.raylib { hidden = true; maxFrames = 1; fps = 0; } (_: {
          commands = [ { op = "camera2D"; camera = {}; commands = [
            { op = "clear"; color = [255 0 0 255]; }
            { op = "invalid-child"; }
          ]; } ];
        })''', error="unknown drawing operation", env={"LD_PRELOAD": preload, "NIXRAY_TEST_CAPTURE": str(destination)})
        self.assertFalse(destination.exists(), "invalid camera batch reached EndDrawing")

    def test_camera_example(self):
        example = Path(__file__).resolve().parent.parent / "examples/camera.nix"
        self.assertEqual(self.evaluate(f"import {example} {{ hidden = true; maxFrames = 2; }}"),
                         {"frames": 2, "state": {"x": 0.0, "y": 0.0, "zoom": 1.0, "rotation": 0.0}})

    def test_camera_example_input(self):
        example = Path(__file__).resolve().parent.parent / "examples/camera.nix"
        result = self._input_evaluate(f"import {example} {{ hidden = true; maxFrames = 4; }}")
        self.assertEqual(result["frames"], 4)
        self.assertEqual(result["state"]["zoom"], 0.8125)
        self.assertEqual(result["state"]["rotation"], 0.0)
