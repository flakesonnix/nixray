"""Read back real evaluator-driven frames without adding production builtins."""

import os
from pathlib import Path


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
        }} (_: {{ commands = {commands}; }})''', env={
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
