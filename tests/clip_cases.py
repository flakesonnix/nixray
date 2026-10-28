"""Scoped clipping, including native scissor restoration and integer bounds."""

import os
from pathlib import Path


class ClipCases:
    def _clipped_pixels(self, bounds, *, commands=None, assets="{}"):
        commands = commands or '[ { op = "rectangle"; x = 0; y = 0; width = 32; height = 32; color = [255 0 0 255]; } ]'
        return self._capture(f'''[
          {{ op = "clear"; color = [0 0 0 255]; }}
          {{ op = "clip"; {bounds} commands = {commands}; }}
        ]''', assets=assets)

    def assert_clip_region(self, pixels, left, top, right, bottom):
        expected = [(255, 0, 0) if left <= x < right and top <= y < bottom else (0, 0, 0)
                    for y in range(32) for x in range(32)]
        self.assertEqual(pixels, expected)

    def test_clip_validation_is_pure(self):
        self.assertEqual(self.evaluate('''builtins.raylibValidate [
          { op = "clip"; x = -1; y = 0; width = 10; height = 20; commands = [
            { op = "clip"; x = 1; y = 2; width = 0; height = 0; commands = [
              { op = "texture"; texture = "unloaded"; x = 0; y = 0; }
            ]; }
          ]; }
        ]''', flags=["--pure-eval"], env={"DISPLAY": "", "WAYLAND_DISPLAY": ""}), 1)

    def test_bad_clip_commands(self):
        base = '{ op = "clip"; x = 0; y = 0; width = 10; height = 10; commands = []; }'
        for override, error in (
            ("x = 2147483648;", "integer in"),
            ("y = -2147483649;", "integer in"),
            ("x = 0.5;", "expected an integer"),
            ("width = -1;", "integer in"),
            ("height = 1.5;", "expected an integer"),
            ("width = 2147483648;", "integer in"),
            ("commands = null;", "expected a list"),
            ('commands = [ { op = "invalid-child"; } ];', "unknown drawing operation"),
            ("typo = true;", "unknown attribute 'typo'"),
        ):
            with self.subTest(override=override):
                self.evaluate(f"builtins.raylibValidate [ ({base} // {{ {override} }}) ]", error=error)
        for field in ("x", "y", "width", "height", "commands"):
            with self.subTest(missing=field):
                self.evaluate(f'builtins.raylibValidate [ (builtins.removeAttrs {base} [ "{field}" ]) ]',
                              error=f"missing attribute '{field}'")

    def test_clip_nesting_limit(self):
        for depth in (64, 65):
            expression = f'''let nested = n: if n == 0 then [] else [ {{
              op = "clip"; x = 0; y = 0; width = 0; height = 0; commands = nested (n - 1);
            }} ]; in builtins.raylibValidate (nested {depth})'''
            with self.subTest(depth=depth):
                if depth == 64:
                    self.assertEqual(self.evaluate(expression, flags=["--pure-eval"]), 1)
                else:
                    self.evaluate(expression, error="clip nesting must not exceed 64 levels")

    def test_deep_clip_rendering(self):
        pixels = self._capture('''let nested = n: if n == 0 then [
          { op = "rectangle"; x = 0; y = 0; width = 32; height = 32; color = [255 0 0 255]; }
        ] else [ { op = "clip"; x = 8; y = 8; width = 4; height = 4; commands = nested (n - 1); } ];
        in [ { op = "clear"; color = [0 0 0 255]; } ] ++ nested 64''')
        self.assert_clip_region(pixels, 8, 8, 12, 12)

    def test_clipped_rectangle_pixels(self):
        self.assert_clip_region(self._clipped_pixels("x = 8; y = 6; width = 10; height = 8;"), 8, 6, 18, 14)

    def test_nested_clip_intersection_and_restoration(self):
        pixels = self._capture('''[
          { op = "clear"; color = [0 0 0 255]; }
          { op = "clip"; x = 4; y = 4; width = 16; height = 16; commands = [
            { op = "rectangle"; x = 0; y = 0; width = 32; height = 32; color = [255 0 0 255]; }
            { op = "clip"; x = 12; y = 0; width = 16; height = 12; commands = [
              { op = "rectangle"; x = 0; y = 0; width = 32; height = 32; color = [0 255 0 255]; }
            ]; }
            { op = "rectangle"; x = 0; y = 14; width = 32; height = 2; color = [0 0 255 255]; }
          ]; }
          { op = "pixel"; x = 28; y = 28; color = [255 255 255 255]; }
        ]''')
        for y in range(32):
            for x in range(32):
                color = (0, 0, 0)
                if 4 <= x < 20 and 4 <= y < 20:
                    color = (255, 0, 0)
                    if x >= 12 and y < 12:
                        color = (0, 255, 0)
                    if 14 <= y < 16:
                        color = (0, 0, 255)
                if (x, y) == (28, 28):
                    color = (255, 255, 255)
                self.assert_pixel(pixels, x, y, color)

    def test_disjoint_clip_preserves_parent(self):
        pixels = self._clipped_pixels("x = 4; y = 4; width = 8; height = 8;", commands='''[
          { op = "clip"; x = 20; y = 20; width = 4; height = 4; commands = [
            { op = "clear"; color = [0 255 0 255]; }
          ]; }
          { op = "rectangle"; x = 0; y = 0; width = 32; height = 32; color = [255 0 0 255]; }
        ]''')
        self.assert_clip_region(pixels, 4, 4, 12, 12)

    def test_clipping_negative_and_extreme_bounds(self):
        for bounds, region in (
            ("x = -4; y = -8; width = 14; height = 20;", (0, 0, 10, 12)),
            ("x = -2147483640; y = -2147483640; width = 2147483647; height = 2147483647;", (0, 0, 7, 7)),
            ("x = 2147483647; y = 2147483647; width = 2147483647; height = 2147483647;", (0, 0, 0, 0)),
            ("x = -2147483648; y = -2147483648; width = 2147483647; height = 2147483647;", (0, 0, 0, 0)),
        ):
            with self.subTest(bounds=bounds):
                self.assert_clip_region(self._clipped_pixels(bounds), *region)

    def test_empty_clips_draw_nothing(self):
        for width, height in ((0, 32), (32, 0), (0, 0)):
            with self.subTest(width=width, height=height):
                self.assertEqual(set(self._clipped_pixels(f"x = 0; y = 0; width = {width}; height = {height};",
                  commands='[ { op = "clear"; color = [255 0 0 255]; } ]')), {(0, 0, 0)})

    def test_empty_clips_still_validate_children(self):
        for bounds in ("x = 0; y = 0; width = 0; height = 0;", "x = 1000; y = 1000; width = 4; height = 4;"):
            for command, error in (
                ('{ op = "texture"; texture = "missing"; x = 0; y = 0; }', "unknown texture 'missing'"),
                ('{ op = "text"; font = "missing"; text = "A"; x = 0; y = 0; size = 12; color = [0 0 0 255]; }',
                 "unknown font 'missing'"),
                ('{ op = "rectangle"; x = 0; y = 0; width = -1; height = 4; color = [0 0 0 255]; }', "integer in"),
            ):
                with self.subTest(bounds=bounds, command=command):
                    self.evaluate(f'''builtins.raylib {self.asset_config} (_: {{ commands = [
                      {{ op = "clip"; {bounds} commands = [ {command} ]; }}
                    ]; }})''', error=error)

    def test_clipped_text_and_texture_pixels(self):
        assets = f"{{ textures.logo = {self.texture_path}; fonts.ui = {self.font_path}; }}"
        for command in (
            '{ op = "texture"; texture = "logo"; x = 4; y = 4; scale = 8; tint = [255 0 0 255]; }',
            '{ op = "text"; font = "ui"; text = "A"; x = 4; y = 4; size = 12; color = [255 0 0 255]; }',
            '{ op = "ellipse"; x = 10; y = 10; radiusX = 10; radiusY = 8; color = [255 0 0 255]; }',
        ):
            with self.subTest(command=command):
                self.assert_clip_region(self._clipped_pixels("x = 8; y = 8; width = 4; height = 4;",
                                                            commands=f"[ {command} ]", assets=assets), 8, 8, 12, 12)

    def test_clipped_clear_obeys_order(self):
        pixels = self._capture('''[
          { op = "clear"; color = [0 0 255 255]; }
          { op = "clip"; x = 4; y = 4; width = 24; height = 24; commands = [
            { op = "rectangle"; x = 0; y = 0; width = 32; height = 32; color = [255 0 0 255]; }
            { op = "clear"; color = [0 255 0 255]; }
            { op = "clip"; x = 8; y = 8; width = 8; height = 8; commands = [
              { op = "clear"; color = [255 255 0 255]; }
            ]; }
          ]; }
        ]''')
        for y in range(32):
            for x in range(32):
                color = (0, 0, 255)
                if 4 <= x < 28 and 4 <= y < 28:
                    color = (0, 255, 0)
                if 8 <= x < 16 and 8 <= y < 16:
                    color = (255, 255, 0)
                self.assert_pixel(pixels, x, y, color)

    def test_clip_does_not_leak_between_frames(self):
        pixels = self._capture('''if frame.frame == 0 then [
          { op = "clear"; color = [0 0 0 255]; }
          { op = "clip"; x = 8; y = 8; width = 8; height = 8; commands = [
            { op = "clear"; color = [255 0 0 255]; }
          ]; }
        ] else [ { op = "clear"; color = [0 0 255 255]; } ]''', frames=2)
        self.assertEqual(set(pixels), {(0, 0, 255)})

    def test_clip_batch_validates_before_drawing(self):
        if not self.capture_library:
            self.skipTest("pass --capture-library to enable framebuffer pixel tests")
        destination = self.asset_directory / "invalid-clip.ppm"
        preload = str(Path(self.capture_library).resolve())
        if os.environ.get("LD_PRELOAD"):
            preload += " " + os.environ["LD_PRELOAD"]
        self.evaluate('''builtins.raylib { hidden = true; maxFrames = 1; fps = 0; } (_: {
          commands = [ { op = "clip"; x = 0; y = 0; width = 10; height = 10; commands = [
            { op = "clear"; color = [255 0 0 255]; }
            { op = "invalid-child"; }
          ]; } ];
        })''', error="unknown drawing operation", env={"LD_PRELOAD": preload, "NIXRAY_TEST_CAPTURE": str(destination)})
        self.assertFalse(destination.exists(), "invalid nested batch reached EndDrawing")

    def test_clip_exception_cleanup(self):
        self.assertEqual(self.evaluate('''let
          config = { hidden = true; maxFrames = 1; fps = 0; };
          failed = builtins.tryEval (builtins.raylib config (_: { commands = [
            { op = "clip"; x = 0; y = 0; width = 10; height = 10; commands = [ (throw "clip child failed") ]; }
          ]; }));
        in assert !failed.success; builtins.raylib config (_: { commands = []; })'''), {"frames": 1, "state": None})

    def test_clip_helper_and_example(self):
        root = Path(__file__).resolve().parent.parent
        self.assertEqual(self.evaluate(f'''let ray = import {root / 'lib'};
          in ray.validate [ (ray.clip {{ x = 0; y = 0; width = 10; height = 10;
            commands = [ (ray.clear ray.colors.red) ]; }}) ]'''), 1)
        self.assertEqual(self.evaluate(f"import {root / 'examples/clipping.nix'} {{ hidden = true; maxFrames = 2; }}"),
                         {"frames": 2, "state": {"scroll": 0}})

    def test_clipping_example_scroll_input(self):
        example = Path(__file__).resolve().parent.parent / "examples/clipping.nix"
        self.assertEqual(self._input_evaluate(f"import {example} {{ hidden = true; maxFrames = 4; }}"),
                         {"frames": 4, "state": {"scroll": 18}})
