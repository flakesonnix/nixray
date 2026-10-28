"""New shape validation and real framebuffer assertions."""

import os
from pathlib import Path


SHAPES = {
    "triangle": "x1 = 4; y1 = 4; x2 = 4; y2 = 28; x3 = 28; y3 = 4;",
    "triangleLines": "x1 = 4; y1 = 4; x2 = 4; y2 = 28; x3 = 28; y3 = 4;",
    "ellipse": "x = 16; y = 16; radiusX = 10.5; radiusY = 5.5;",
    "ellipseLines": "x = 16; y = 16; radiusX = 10; radiusY = 6;",
    "rectangleRounded": "x = 4; y = 4; width = 24; height = 16; roundness = 1;",
    "rectangleRoundedLines": "x = 4; y = 4; width = 24; height = 16; roundness = 1;",
}


class ShapeCases:
    def _shape_pixels(self, op, attributes=None, *, color="[255 0 0 255]", background="[0 0 0 255]"):
        return self._capture(f'''[
          {{ op = "clear"; color = {background}; }}
          {{ op = "{op}"; {attributes if attributes is not None else SHAPES[op]} color = {color}; }}
        ]''')

    def test_shape_validation_is_pure(self):
        commands = " ".join(f'{{ op = "{op}"; {attributes} color = [255 0 0 255]; }}'
                            for op, attributes in SHAPES.items())
        self.assertEqual(self.evaluate(f"builtins.raylibValidate [ {commands} ]", flags=["--pure-eval"],
                                       env={"DISPLAY": "", "WAYLAND_DISPLAY": ""}), 6)

    def test_shape_missing_and_unknown_attributes(self):
        for op, attributes in SHAPES.items():
            with self.subTest(op=op):
                self.evaluate(f'builtins.raylibValidate [ {{ op = "{op}"; color = [0 0 0 255]; }} ]',
                              error="missing attribute")
                self.evaluate(f'builtins.raylibValidate [ {{ op = "{op}"; {attributes} }} ]',
                              error="missing attribute 'color'")
                self.evaluate(f'''builtins.raylibValidate [
                  {{ op = "{op}"; {attributes} color = [0 0 0 255]; typo = 1; }}
                ]''', error="unknown attribute 'typo'")

    def test_bad_shape_numbers(self):
        for op in SHAPES:
            if op.startswith("triangle"):
                bad = (("x1", "2147483648", "integer in"), ("y2", "(-2147483649)", "integer in"),
                       ("x3", "1.5", "expected an integer"))
            elif op.startswith("ellipse"):
                bad = (("radiusX", "(-1)", "finite number"), ("radiusY", "1.0e100", "finite number"),
                       ("radiusX", "true", "expected"), ("x", "0.5", "expected an integer"))
            else:
                bad = (("width", "(-1)", "integer in"), ("height", "1.5", "expected an integer"),
                       ("roundness", "(-0.1)", "finite number"), ("roundness", "1.1", "finite number"),
                       ("roundness", "1.000000001", "finite number"),
                       ("roundness", "1.0e100", "finite number"), ("segments", "(-1)", "integer in"),
                       ("segments", "1", "0 (automatic)"), ("segments", "3", "0 (automatic)"),
                       ("segments", "4097", "integer in"), ("segments", "4.5", "expected an integer"))
            for field, value, error in bad:
                with self.subTest(op=op, field=field, value=value):
                    self.evaluate(f'''builtins.raylibValidate [ ({{ op = "{op}"; {SHAPES[op]}
                      color = [0 0 0 255]; }} // {{ {field} = {value}; }}) ]''', error=error)

    def test_triangle_winding_pixels(self):
        for op in ("triangle", "triangleLines"):
            with self.subTest(op=op):
                forward = self._shape_pixels(op)
                reverse = self._shape_pixels(op, "x1 = 4; y1 = 4; x2 = 28; y2 = 4; x3 = 4; y3 = 28;")
                self.assertEqual(forward, reverse)
                self.assertIn((255, 0, 0), forward)
                self.assert_pixel(forward, 24, 24, (0, 0, 0))
                self.assert_pixel(forward, 10, 10, (255, 0, 0) if op == "triangle" else (0, 0, 0))

    def test_triangle_outline_pixels(self):
        pixels = self._shape_pixels("triangleLines")
        # GL's diamond-exit rule places this vertical edge in column 3.
        self.assert_pixel(pixels, 3, 10, (255, 0, 0))
        self.assert_pixel(pixels, 10, 4, (255, 0, 0))
        self.assert_pixel(pixels, 10, 10, (0, 0, 0))

    def test_ellipse_fill_pixels(self):
        pixels = self._shape_pixels("ellipse")
        for x, y in ((16, 16), (24, 16), (16, 19)):
            self.assert_pixel(pixels, x, y, (255, 0, 0))
        for x, y in ((16, 22), (27, 16), (25, 20), (0, 0)):
            self.assert_pixel(pixels, x, y, (0, 0, 0))

    def test_ellipse_outline_pixels(self):
        pixels = self._shape_pixels("ellipseLines")
        self.assert_pixel(pixels, 16, 16, (0, 0, 0))
        self.assert_pixel(pixels, 25, 16, (255, 0, 0))
        self.assert_pixel(pixels, 16, 10, (255, 0, 0))
        self.assert_pixel(pixels, 28, 16, (0, 0, 0))

    def test_rounded_rectangle_pixels(self):
        for segments in (0, 5, 8, 4096):
            with self.subTest(segments=segments):
                pixels = self._shape_pixels("rectangleRounded", SHAPES["rectangleRounded"] + f" segments = {segments};")
                for x, y in ((16, 12), (16, 4), (4, 12)):
                    self.assert_pixel(pixels, x, y, (255, 0, 0))
                for x, y in ((4, 4), (27, 19), (3, 12)):
                    self.assert_pixel(pixels, x, y, (0, 0, 0))

    def test_rounded_rectangle_outline_pixels(self):
        pixels = self._shape_pixels("rectangleRoundedLines", SHAPES["rectangleRoundedLines"] + " segments = 8;")
        self.assert_pixel(pixels, 16, 12, (0, 0, 0))
        self.assert_pixel(pixels, 4, 4, (0, 0, 0))
        self.assert_pixel(pixels, 16, 3, (255, 0, 0))
        self.assert_pixel(pixels, 28, 12, (255, 0, 0))

    def test_rounded_rectangle_defaults(self):
        for op in ("rectangleRounded", "rectangleRoundedLines"):
            with self.subTest(op=op):
                self.assertEqual(self._shape_pixels(op), self._shape_pixels(op, SHAPES[op] + " segments = 0;"))
        self.assertEqual(self._shape_pixels("rectangleRounded", "x = 4; y = 4; width = 24; height = 16; roundness = 0;"),
                         self._shape_pixels("rectangle", "x = 4; y = 4; width = 24; height = 16;"))

    def test_degenerate_shapes_draw_nothing(self):
        for op in SHAPES:
            if op.startswith("triangle"):
                attributes = "x1 = 4; y1 = 4; x2 = 8; y2 = 8; x3 = 12; y3 = 12;"
            elif op.startswith("ellipse"):
                attributes = "x = 16; y = 16; radiusX = 0; radiusY = 6;"
            else:
                attributes = "x = 4; y = 4; width = 0; height = 16; roundness = 0;"
            with self.subTest(op=op):
                self.assertEqual(set(self._shape_pixels(op, attributes)), {(0, 0, 0)})

    def test_shape_alpha_pixels(self):
        for op in ("triangle", "ellipse", "rectangleRounded"):
            with self.subTest(op=op):
                pixels = self._shape_pixels(op, color="[255 0 0 128]", background="[0 0 255 255]")
                self.assert_pixel(pixels, 12, 12, (128, 0, 127), tolerance=1)

    def test_shape_command_order_pixels(self):
        pixels = self._capture('''[
          { op = "clear"; color = [0 0 0 255]; }
          { op = "rectangleRounded"; x = 4; y = 4; width = 24; height = 24;
            roundness = 0.5; color = [255 0 0 255]; }
          { op = "triangle"; x1 = 4; y1 = 4; x2 = 4; y2 = 28; x3 = 28; y3 = 4; color = [0 255 0 255]; }
          { op = "ellipse"; x = 12; y = 12; radiusX = 4; radiusY = 3; color = [0 0 255 255]; }
        ]''')
        self.assert_pixel(pixels, 12, 12, (0, 0, 255))
        self.assert_pixel(pixels, 8, 8, (0, 255, 0))
        self.assert_pixel(pixels, 24, 24, (255, 0, 0))

    def test_shape_batch_validates_before_drawing(self):
        if not self.capture_library:
            self.skipTest("pass --capture-library to enable framebuffer pixel tests")
        destination = self.asset_directory / "invalid-shapes.ppm"
        preload = str(Path(self.capture_library).resolve())
        if os.environ.get("LD_PRELOAD"):
            preload += " " + os.environ["LD_PRELOAD"]
        self.evaluate('''builtins.raylib { hidden = true; maxFrames = 1; fps = 0; } (_: {
          commands = [
            { op = "ellipse"; x = 16; y = 16; radiusX = 8; radiusY = 4; color = [255 0 0 255]; }
            { op = "rectangleRounded"; x = 0; y = 0; width = 20; height = 20;
              roundness = 2; color = [255 255 255 255]; }
          ];
        })''', error="finite number", env={"LD_PRELOAD": preload, "NIXRAY_TEST_CAPTURE": str(destination)})
        self.assertFalse(destination.exists(), "invalid batch reached EndDrawing")

    def test_extreme_shape_coordinates(self):
        for op in ("rectangleRounded", "rectangleRoundedLines"):
            for roundness in ("1.0e-40", "0.01", "1"):
                with self.subTest(op=op, roundness=roundness):
                    self.evaluate(f'''builtins.raylib {{ hidden = true; maxFrames = 1; fps = 0; }} (_: {{
                      commands = [ {{ op = "{op}"; x = -2147483648; y = -2147483648;
                        width = 2147483647; height = 2147483647; roundness = {roundness}; color = [255 0 0 255]; }} ];
                    }})''')

    def test_shapes_example(self):
        example = Path(__file__).resolve().parent.parent / "examples/shapes.nix"
        self.assertEqual(self.evaluate(f"import {example} {{ hidden = true; maxFrames = 2; }}"),
                         {"frames": 2, "state": None})
