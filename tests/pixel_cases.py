"""Read back real evaluator-driven frames without adding production builtins."""

import os
from pathlib import Path

MIRROR_CASES = (
    ("flipX = false; flipY = false;", [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0)]),
    ("flipX = true;", [(0, 255, 0), (255, 0, 0), (255, 255, 0), (0, 0, 255)]),
    ("flipY = true;", [(0, 0, 255), (255, 255, 0), (255, 0, 0), (0, 255, 0)]),
    ("flipX = true; flipY = true;", [(255, 255, 0), (0, 0, 255), (0, 255, 0), (255, 0, 0)]),
)


class PixelCases:
    def _capture(self, commands, *, assets="{}"):
        if not self.capture_library:
            self.skipTest("pass --capture-library to enable framebuffer pixel tests")
        library = Path(self.capture_library).resolve()
        self.assertTrue(library.is_file(), f"missing capture library: {library}")
        destination = self.asset_directory / "frame.ppm"
        destination.unlink(missing_ok=True)
        preload = str(library)
        if os.environ.get("LD_PRELOAD"):
            preload += " " + os.environ["LD_PRELOAD"]
        result = self.evaluate(f'''builtins.raylib {{
          width = 32; height = 32; hidden = true; fps = 0; maxFrames = 1;
          assets = {assets};
        }} (frame: {{ commands = {commands}; }})''', env={
            "LD_PRELOAD": preload, "NIXRAY_TEST_CAPTURE": str(destination),
        })
        self.assertEqual(result, {"frames": 1, "state": None})
        self.assertTrue(destination.is_file(), "capture hook did not write the framebuffer")
        magic, dimensions, maximum, data = destination.read_bytes().split(b"\n", 3)
        self.assertEqual((magic, dimensions, maximum), (b"P6", b"32 32", b"255"))
        self.assertEqual(len(data), 32 * 32 * 3)
        return [tuple(data[i:i + 3]) for i in range(0, len(data), 3)]

    def assert_pixel(self, pixels, x, y, expected, *, tolerance=0):
        actual = pixels[y * 32 + x]
        self.assertTrue(all(abs(a - b) <= tolerance for a, b in zip(actual, expected)),
                        f"pixel ({x}, {y}): expected {expected}, got {actual}")

    def test_clear_pixels(self):
        pixels = self._capture('[ { op = "clear"; color = [ 17 34 51 255 ]; } ]')
        self.assertEqual(set(pixels), {(17, 34, 51)})

    def test_rectangle_pixels_and_order(self):
        pixels = self._capture('''[
          { op = "clear"; color = [0 0 0 255]; }
          { op = "rectangle"; x = 2; y = 3; width = 4; height = 5; color = [255 0 0 255]; }
          { op = "rectangle"; x = 4; y = 5; width = 2; height = 2; color = [0 255 0 255]; }
        ]''')
        self.assert_pixel(pixels, 3, 4, (255, 0, 0))
        self.assert_pixel(pixels, 4, 5, (0, 255, 0))
        self.assert_pixel(pixels, 1, 3, (0, 0, 0))
        self.assert_pixel(pixels, 3, 8, (0, 0, 0))

    def _texture_pixels(self, attributes="", *, image=None):
        return self._capture(f'''[
          {{ op = "clear"; color = [0 0 0 255]; }}
          {{ op = "texture"; texture = "pattern"; x = 10; y = 10; {attributes} }}
        ]''', assets=f"{{ textures.pattern = {image or self.pattern_path}; }}")

    def test_texture_native_pixels(self):
        pixels = self._texture_pixels()
        for x, y, color in (
            (10, 10, (255, 0, 0)), (11, 10, (0, 255, 0)),
            (10, 11, (0, 0, 255)), (11, 11, (255, 255, 0)),
            (9, 10, (0, 0, 0)), (12, 10, (0, 0, 0)),
        ):
            self.assert_pixel(pixels, x, y, color)

    def test_texture_scaled_pixels(self):
        pixels = self._texture_pixels("scale = 2;")
        colors = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0)]
        for dy in range(4):
            for dx in range(4):
                self.assert_pixel(pixels, 10 + dx, 10 + dy, colors[(dy // 2) * 2 + dx // 2])
        self.assert_pixel(pixels, 14, 10, (0, 0, 0))

    def test_texture_cropped_pixels(self):
        pixels = self._texture_pixels("source = { x = 1; y = 0; width = 1; height = 2; }; scale = 3;")
        for dy in range(6):
            for dx in range(3):
                self.assert_pixel(pixels, 10 + dx, 10 + dy, (0, 255, 0) if dy < 3 else (255, 255, 0))
        self.assert_pixel(pixels, 13, 10, (0, 0, 0))
        self.assert_pixel(pixels, 10, 16, (0, 0, 0))

    def test_texture_rotated_pixels(self):
        for rotation, points in (
            (90, [(8, 10), (8, 12), (6, 10), (6, 12)]),
            (-90, [(10, 8), (10, 6), (12, 8), (12, 6)]),
        ):
            with self.subTest(rotation=rotation):
                pixels = self._texture_pixels(f"scale = 2; rotation = {rotation};")
                for (x, y), color in zip(points, [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0)]):
                    self.assert_pixel(pixels, x, y, color)

    def test_texture_cropped_rotated_pixels(self):
        pixels = self._texture_pixels(
            "source = { x = 1; y = 0; width = 1; height = 2; }; scale = 2; rotation = 90;"
        )
        self.assert_pixel(pixels, 8, 10, (0, 255, 0))
        self.assert_pixel(pixels, 6, 10, (255, 255, 0))
        self.assert_pixel(pixels, 8, 12, (0, 0, 0))

    def test_texture_origin_offset_pixels(self):
        for origin in ("2", "1.75"):
            with self.subTest(origin=origin):
                pixels = self._texture_pixels(f"scale = 2; origin = {{ x = {origin}; y = {origin}; }};")
                for x, y, color in (
                    (8, 8, (255, 0, 0)), (10, 8, (0, 255, 0)),
                    (8, 10, (0, 0, 255)), (10, 10, (255, 255, 0)),
                    (7, 8, (0, 0, 0)), (12, 8, (0, 0, 0)),
                ):
                    self.assert_pixel(pixels, x, y, color)

    def test_texture_center_rotation_pixels(self):
        pixels = self._texture_pixels("scale = 2; rotation = 90; origin = { x = 2; y = 2; };")
        for (x, y), color in zip(
            [(10, 8), (10, 10), (8, 8), (8, 10)],
            [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0)],
        ):
            self.assert_pixel(pixels, x, y, color)

    def test_texture_external_origin_pixels(self):
        pixels = self._texture_pixels("origin = { x = -1; y = -1; };")
        self.assert_pixel(pixels, 11, 11, (255, 0, 0))
        self.assert_pixel(pixels, 12, 12, (255, 255, 0))
        self.assert_pixel(pixels, 10, 10, (0, 0, 0))

    def test_texture_zero_origin_compatibility(self):
        self.assertEqual(self._texture_pixels("scale = 2; rotation = -90;"),
                         self._texture_pixels("scale = 2; rotation = -90; origin = { x = 0; y = 0; };"))

    def test_texture_mirrored_pixels(self):
        for attributes, colors in MIRROR_CASES:
            with self.subTest(attributes=attributes):
                pixels = self._texture_pixels("scale = 2; " + attributes)
                for (x, y), color in zip([(10, 10), (12, 10), (10, 12), (12, 12)], colors):
                    self.assert_pixel(pixels, x, y, color)
                self.assert_pixel(pixels, 9, 10, (0, 0, 0))
                self.assert_pixel(pixels, 14, 10, (0, 0, 0))

    def test_texture_mirrored_atlas_pixels(self):
        for attributes, colors in MIRROR_CASES:
            with self.subTest(attributes=attributes):
                pixels = self._texture_pixels(
                    "source = { x = 1; y = 1; width = 2; height = 2; }; scale = 2; " + attributes,
                    image=self.atlas_path,
                )
                for (x, y), color in zip([(10, 10), (12, 10), (10, 12), (12, 12)], colors):
                    self.assert_pixel(pixels, x, y, color)

    def test_texture_mirrored_pivot_rotation_pixels(self):
        for rotation, points in (
            (90, [(10, 8), (10, 10), (8, 8), (8, 10)]),
            (-90, [(8, 10), (8, 8), (10, 10), (10, 8)]),
        ):
            for attributes, colors in MIRROR_CASES:
                with self.subTest(rotation=rotation, attributes=attributes):
                    pixels = self._texture_pixels(
                        "source = { x = 1; y = 1; width = 2; height = 2; }; "
                        f"scale = 2; rotation = {rotation}; origin = {{ x = 2; y = 2; }}; " + attributes,
                        image=self.atlas_path,
                    )
                    for (x, y), color in zip(points, colors):
                        self.assert_pixel(pixels, x, y, color)
                    self.assert_pixel(pixels, 7, 8, (0, 0, 0))
                    self.assert_pixel(pixels, 12, 8, (0, 0, 0))

    def test_texture_false_flip_compatibility(self):
        attributes = "scale = 2; rotation = 90; origin = { x = 2; y = 2; };"
        self.assertEqual(self._texture_pixels(attributes),
                         self._texture_pixels(attributes + "flipX = false; flipY = false;"))

    def test_texture_tint_pixels(self):
        pixels = self._texture_pixels("tint = [80 120 200 255];")
        for x, y, color in (
            (10, 10, (80, 0, 0)), (11, 10, (0, 120, 0)),
            (10, 11, (0, 0, 200)), (11, 11, (80, 120, 0)),
        ):
            self.assert_pixel(pixels, x, y, color)

    def test_texture_alpha_pixels(self):
        pixels = self._capture('''[
          { op = "clear"; color = [0 0 255 255]; }
          { op = "texture"; texture = "white"; x = 10; y = 10; tint = [255 0 0 128]; }
        ]''', assets=f"{{ textures.white = {self.texture_path}; }}")
        # Allow one quantization step across GL implementations, not a broad image tolerance.
        self.assert_pixel(pixels, 10, 10, (128, 0, 127), tolerance=1)
        self.assert_pixel(pixels, 9, 10, (0, 0, 255))

    def test_circle_pixels(self):
        pixels = self._capture('''[
          { op = "clear"; color = [0 0 0 255]; }
          { op = "circle"; x = 16; y = 16; radius = 4; color = [255 0 0 255]; }
        ]''')
        self.assert_pixel(pixels, 16, 16, (255, 0, 0))
        self.assert_pixel(pixels, 0, 0, (0, 0, 0))

    def test_custom_font_pixels(self):
        pixels = self._capture('''[
          { op = "clear"; color = [0 0 0 255]; }
          { op = "text"; font = "ui"; text = "A"; x = 4; y = 4; size = 12; color = [255 255 255 255]; }
        ]''', assets=f"{{ fonts.ui = {self.font_path}; }}")
        self.assert_pixel(pixels, 4, 4, (255, 255, 255))
        self.assert_pixel(pixels, 15, 15, (255, 255, 255))
        self.assert_pixel(pixels, 16, 4, (0, 0, 0))
        self.assert_pixel(pixels, 4, 16, (0, 0, 0))

    def test_measured_text_layout_pixels(self):
        pixels = self._capture('''let
          measured = frame.measureText { font = "ui"; text = "AA"; size = 12; };
          x = builtins.floor ((frame.width - measured.width) / 2);
        in [
          { op = "clear"; color = [0 0 0 255]; }
          { op = "text"; font = "ui"; text = "AA"; inherit x; y = 4; size = 12; color = [255 255 255 255]; }
        ]''', assets=f"{{ fonts.ui = {{ path = {self.font_path}; }}; }}")
        self.assert_pixel(pixels, 2, 4, (0, 0, 0))
        self.assert_pixel(pixels, 3, 4, (255, 255, 255))
        self.assert_pixel(pixels, 15, 4, (0, 0, 0))
        self.assert_pixel(pixels, 16, 4, (255, 255, 255))
        self.assert_pixel(pixels, 27, 15, (255, 255, 255))
        self.assert_pixel(pixels, 28, 15, (0, 0, 0))

    def test_truetype_unicode_glyph_pixels(self):
        path = self._truetype_path()

        def render(text, specification):
            return self._capture(f'''[
              {{ op = "clear"; color = [0 0 0 255]; }}
              {{ op = "text"; font = "ui"; text = "{text}"; x = 4; y = 4; size = 20; color = [255 255 255 255]; }}
            ]''', assets=f"{{ fonts.ui = {specification}; }}")

        self.assertEqual(render("λ", path), render("?", path))
        configured = f"{{ path = {path}; size = 32; codepoints = [ 63 955 ]; }}"
        glyph = render("λ", configured)
        self.assertNotEqual(glyph, render("?", configured))
        self.assertIn((255, 255, 255), glyph)
        self.assertNotEqual(glyph, render("λ", f"{{ path = {path}; size = 48; codepoints = [ 63 955 ]; }}"))
