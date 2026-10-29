"""Additional 2D commands: pure validation and native framebuffer coverage."""

import os
from pathlib import Path


RED = "[255 0 0 255]"
GREEN = "[0 255 0 255]"
BLUE = "[0 0 255 255]"
WHITE = "[255 255 255 255]"
RECT = {"x": "4", "y": "4", "width": "24", "height": "24"}
ARC = {"x": "16", "y": "16", "startAngle": "0", "endAngle": "90", "segments": "32", "color": RED}
DRAWINGS = {
    "lineEx": {"x1": "4", "y1": "16", "x2": "28", "y2": "16", "thickness": "6", "color": RED},
    "rectangleGradientV": RECT | {"top": RED, "bottom": BLUE},
    "rectangleGradientH": RECT | {"left": RED, "right": BLUE},
    "rectangleGradientEx": RECT | {"topLeft": RED, "bottomLeft": GREEN, "bottomRight": BLUE, "topRight": WHITE},
    "circleGradient": {"x": "16", "y": "16", "radius": "12", "inner": RED, "outer": BLUE},
    "circleSector": ARC | {"radius": "12"},
    "circleSectorLines": ARC | {"radius": "12"},
    "ring": ARC | {"innerRadius": "6", "outerRadius": "12"},
    "ringLines": ARC | {"innerRadius": "6", "outerRadius": "12"},
}
ARCS = ("circleSector", "circleSectorLines", "ring", "ringLines")
COLOR_FIELDS = {"color", "top", "bottom", "left", "right", "topLeft", "bottomLeft", "bottomRight", "topRight", "inner", "outer"}


class DrawingCases:
    def _drawing_command(self, op, changes=None, *, remove=()):
        fields = DRAWINGS[op] | (changes or {})
        attrs = " ".join(f"{key} = {value};" for key, value in fields.items() if key not in remove)
        return f'{{ op = "{op}"; {attrs} }}'

    def _drawing_pixels(self, op, changes=None, *, background="[0 0 0 255]"):
        return self._capture(f'[ {{ op = "clear"; color = {background}; }} {self._drawing_command(op, changes)} ]')

    def test_drawing_validation_is_pure_and_restricted(self):
        commands = " ".join(self._drawing_command(op) for op in DRAWINGS)
        for flag in ("--pure-eval", "--restrict-eval"):
            self.assertEqual(self.evaluate(f"builtins.raylibValidate [ {commands} ]", flags=[flag],
                                           env={"DISPLAY": "", "WAYLAND_DISPLAY": ""}), 9)

    def test_drawing_helpers(self):
        library = Path(__file__).resolve().parent.parent / "lib"
        calls = " ".join(f'(ray.{op} ({self._drawing_command(op)} // {{ op = "ignored"; }}))' for op in DRAWINGS)
        self.assertEqual(self.evaluate(f"let ray = import {library}; in ray.validate [ {calls} ]",
                                       env={"DISPLAY": "", "WAYLAND_DISPLAY": ""}), 9)

    def test_drawing_required_unknown_and_color_fields(self):
        for op, fields in DRAWINGS.items():
            for field in fields:
                with self.subTest(op=op, field=field):
                    if field != "segments":
                        self.evaluate(f"builtins.raylibValidate [ {self._drawing_command(op, remove=(field,))} ]",
                                      error=f"missing attribute '{field}'")
                    if field in COLOR_FIELDS:
                        for bad, error in (("[]", "color must"), ("[0 0 0]", "color must"),
                                           ("[256 0 0 255]", "integer in"), ('"red"', "expected")):
                            self.evaluate(f"builtins.raylibValidate [ {self._drawing_command(op, {field: bad})} ]",
                                          error=error)
            self.evaluate(f"builtins.raylibValidate [ {self._drawing_command(op, {'typo': '1'})} ]", error="unknown attribute 'typo'")

    def test_drawing_number_validation(self):
        for op, fields in DRAWINGS.items():
            for field in fields.keys() - COLOR_FIELDS - {"segments"}:
                integer = field in {"x", "y", "x1", "y1", "x2", "y2", "width", "height"}
                invalid = (("0.5", "expected an integer"), ("2147483648", "integer in")) if integer else (("1.0e100", "finite number"),)
                for value, error in (*invalid, ("true", "expected")):
                    with self.subTest(op=op, field=field, value=value):
                        self.evaluate(f"builtins.raylibValidate [ {self._drawing_command(op, {field: value})} ]", error=error)
                if field in {"radius", "innerRadius", "outerRadius", "thickness", "width", "height"}:
                    self.evaluate(f"builtins.raylibValidate [ {self._drawing_command(op, {field: '-1'})} ]", error="integer in" if integer else "finite number")

    def test_drawing_ring_radii_checked_before_float_rounding(self):
        for op in ("ring", "ringLines"):
            for inner, outer in (("13", "12"), ("1.000000001", "1")):
                self.evaluate(f"builtins.raylibValidate [ {self._drawing_command(op, {'innerRadius': inner, 'outerRadius': outer})} ]",
                              error="innerRadius must not exceed outerRadius")

    def test_drawing_segments_are_bounded_and_promoted(self):
        for op in ARCS:
            for segments in ("0", "1", "2", "4", "4096"):
                self.assertEqual(self.evaluate(f"builtins.raylibValidate [ {self._drawing_command(op, {'segments': segments, 'endAngle': '360'})} ]", flags=["--pure-eval"]), 1)
            for segments, error in (("-1", "integer in"), ("4097", "integer in"), ("1.5", "expected an integer")):
                self.evaluate(f"builtins.raylibValidate [ {self._drawing_command(op, {'segments': segments})} ]", error=error)
            self.assertEqual(self._drawing_pixels(op, {"segments": "1", "endAngle": "360"}),
                             self._drawing_pixels(op, {"segments": "4", "endAngle": "360"}))
            # A 360-degree double span can round to slightly more than 360 in floats.
            rounded = {"startAngle": "255.999969482421875", "endAngle": "615.999969482421875"}
            self.assertEqual(self._drawing_pixels(op, rounded | {"segments": "1"}),
                             self._drawing_pixels(op, rounded | {"segments": "5"}))

    def test_drawing_arc_span_checked_before_float_rounding(self):
        for op in ARCS:
            for start, end in (("0", "360.000000001"), ("-180", "181"), ("-3.0e38", "3.0e38")):
                self.evaluate(f"builtins.raylibValidate [ {self._drawing_command(op, {'startAngle': start, 'endAngle': end})} ]",
                              error="arc angle span must not exceed 360 degrees")

    def test_drawing_linear_gradient_pixels(self):
        for op in ("rectangleGradientV", "rectangleGradientH"):
            pixels = self._drawing_pixels(op)
            for offset in (0, 5, 12, 23):
                x, y = (8, 4 + offset) if op.endswith("V") else (4 + offset, 8)
                t = (offset + 0.5) / 24
                self.assert_pixel(pixels, x, y, (round(255 * (1 - t)), 0, round(255 * t)), tolerance=1)
            self.assert_pixel(pixels, 3, 8, (0, 0, 0))

    def test_drawing_four_corner_gradient_pixels(self):
        pixels = self._drawing_pixels("rectangleGradientEx")
        for x, y in ((4, 4), (4, 27), (27, 27), (27, 4), (16, 16), (8, 20), (20, 8)):
            fx, fy = (x + 0.5 - 4) / 24, (y + 0.5 - 4) / 24
            # Raylib's quad is two triangles, not a bilinear four-corner blend.
            self.assert_pixel(pixels, x, y, (round(255 * (1 - fy)), round(255 * abs(fy - fx)), round(255 * fx)), tolerance=1)

    def test_drawing_circle_gradient_pixels(self):
        pixels = self._drawing_pixels("circleGradient")
        center, middle, edge = (pixels[16 * 32 + x] for x in (16, 20, 26))
        self.assertGreater(center[0], middle[0])
        self.assertGreater(middle[0], edge[0])
        self.assertLess(center[2], middle[2])
        self.assertLess(middle[2], edge[2])
        self.assertGreater(center[0], 230)
        self.assertGreater(edge[2], 210)
        self.assert_pixel(pixels, 29, 16, (0, 0, 0))

    def test_drawing_thick_line_axis_pixels_and_reversal(self):
        pixels = self._drawing_pixels("lineEx")
        self.assertEqual(pixels, [(255, 0, 0) if 4 <= x < 28 and 13 <= y < 19 else (0, 0, 0)
                                  for y in range(32) for x in range(32)])
        self.assertEqual(pixels, self._drawing_pixels("lineEx", {"x1": "28", "x2": "4"}))
        vertical = self._drawing_pixels("lineEx", {"x1": "16", "y1": "4", "x2": "16", "y2": "28", "thickness": "4"})
        self.assertEqual(vertical, [(255, 0, 0) if 14 <= x < 18 and 4 <= y < 28 else (0, 0, 0)
                                    for y in range(32) for x in range(32)])

    def test_drawing_thick_line_diagonal_and_butt_caps(self):
        pixels = self._drawing_pixels("lineEx", {"y1": "4", "y2": "28", "thickness": "4"})
        for x, y in ((10, 10), (10, 12), (26, 26)):
            self.assert_pixel(pixels, x, y, (255, 0, 0))
        for x, y in ((10, 15), (3, 3), (28, 28)):
            self.assert_pixel(pixels, x, y, (0, 0, 0))

    def test_drawing_sector_clockwise_quadrant(self):
        pixels = self._drawing_pixels("circleSector")
        self.assert_pixel(pixels, 20, 20, (255, 0, 0))
        for x, y in ((20, 12), (12, 20), (12, 12), (27, 27)):
            self.assert_pixel(pixels, x, y, (0, 0, 0))

    def test_drawing_ring_hole_quadrant_and_full_turn(self):
        pixels = self._drawing_pixels("ring")
        self.assert_pixel(pixels, 23, 23, (255, 0, 0))
        for x, y in ((18, 18), (25, 25), (23, 8), (8, 23)):
            self.assert_pixel(pixels, x, y, (0, 0, 0))
        full = self._drawing_pixels("ring", {"endAngle": "360"})
        for x, y in ((24, 16), (16, 24), (8, 16), (16, 8)):
            self.assert_pixel(full, x, y, (255, 0, 0))
        self.assert_pixel(full, 16, 16, (0, 0, 0))

    def test_drawing_arc_outlines_and_radial_caps(self):
        for op, inside in (("circleSectorLines", (20, 20)), ("ringLines", (22, 22))):
            for end in ("90", "360"):
                with self.subTest(op=op, end=end):
                    pixels = self._drawing_pixels(op, {"endAngle": end})
                    self.assertIn((255, 0, 0), pixels)
                    self.assert_pixel(pixels, *inside, (0, 0, 0))
                    self.assertTrue(any(pixels[y * 32 + 24] == (255, 0, 0) for y in (15, 16)), "missing radial cap")

    def test_drawing_zero_inner_radius_matches_sectors(self):
        for ring, sector in (("ring", "circleSector"), ("ringLines", "circleSectorLines")):
            self.assertEqual(self._drawing_pixels(ring, {"innerRadius": "0"}), self._drawing_pixels(sector))

    def test_drawing_arc_normalization_and_reversed_bounds(self):
        for op in ARCS:
            reference = self._drawing_pixels(op)
            for start, end in (("90", "0"), ("-360", "-270"), ("720", "810")):
                self.assertEqual(reference, self._drawing_pixels(op, {"startAngle": start, "endAngle": end}))
            self.assertEqual(self._drawing_pixels(op, {"startAngle": "350", "endAngle": "370"}),
                             self._drawing_pixels(op, {"startAngle": "-10", "endAngle": "10"}))

    def test_drawing_automatic_segments_and_maximum(self):
        for op in ARCS:
            without = self._capture(f'[ {{ op = "clear"; color = [0 0 0 255]; }} {self._drawing_command(op, remove=("segments",))} ]')
            self.assertEqual(without, self._drawing_pixels(op, {"segments": "0"}))
            self.assertIn((255, 0, 0), self._drawing_pixels(op, {"segments": "4096"}))

    def test_drawing_zero_size_noops_still_validate(self):
        for op in DRAWINGS:
            if op == "lineEx":
                changes = {"thickness": "0"}
            elif op.startswith("rectangle"):
                changes = {"width": "0"}
            elif op.startswith("ring"):
                changes = {"innerRadius": "12"}
            else:
                changes = {"radius": "0"}
            self.assertEqual(set(self._drawing_pixels(op, changes)), {(0, 0, 0)})
            self.evaluate(f"builtins.raylibValidate [ {self._drawing_command(op, changes | {'typo': '1'})} ]", error="unknown attribute")
        for op in ARCS:
            self.assertEqual(set(self._drawing_pixels(op, {"endAngle": "0"})), {(0, 0, 0)})
        self.assertEqual(set(self._drawing_pixels("lineEx", {"x2": "4"})), {(0, 0, 0)})

    def test_drawing_alpha(self):
        for op in ("lineEx", "rectangleGradientV", "rectangleGradientH", "rectangleGradientEx", "circleGradient", "circleSector", "ring"):
            changes = {field: "[255 0 0 128]" for field in DRAWINGS[op].keys() & COLOR_FIELDS}
            pixels = self._drawing_pixels(op, changes, background=BLUE)
            x, y = (23, 23) if op == "ring" else (20, 20) if op == "circleSector" else (16, 16)
            self.assert_pixel(pixels, x, y, (128, 0, 127), tolerance=1)

    def test_drawing_clip_and_camera(self):
        commands = " ".join(self._drawing_command(op) for op in DRAWINGS)
        pixels = self._capture(f'''[ {{ op = "clear"; color = [0 0 0 255]; }}
          {{ op = "clip"; x = 8; y = 8; width = 8; height = 8; commands = [
            {{ op = "camera2D"; camera = {{ zoom = 2; }}; commands = [ {commands} ]; }}
          ]; }} ]''')
        self.assertTrue(any(p != (0, 0, 0) for p in pixels))
        for y in range(32):
            for x in range(32):
                if not (8 <= x < 16 and 8 <= y < 16):
                    self.assert_pixel(pixels, x, y, (0, 0, 0))

    def test_drawing_render_texture(self):
        commands = " ".join(self._drawing_command(op) for op in DRAWINGS)
        direct = self._capture(f'[ {{ op = "clear"; color = [0 0 0 255]; }} {commands} ]')
        painted = self._capture(f'''[
          {{ op = "clear"; color = [0 0 0 255]; }}
          {{ op = "paint"; texture = "canvas"; commands = [ {{ op = "clear"; color = [0 0 0 255]; }} {commands} ]; }}
          {{ op = "texture"; texture = "canvas"; x = 0; y = 0; }}
        ]''', assets="{ renderTextures.canvas = { width = 32; height = 32; }; }")
        self.assertTrue(all(abs(a-b) <= 1 for p, q in zip(direct, painted) for a, b in zip(p, q)))

    def test_drawing_shader(self):
        shader = Path(__file__).resolve().parent.parent / "examples/shaders/tint.fs"
        assets = f'{{ shaders.fx = {{ fragment = {shader}; uniforms = {{ gain = {{ type = "float"; value = 0; }}; tint = {{ type = "vec3"; value = [1 1 1]; }}; }}; }}; }}'
        for op in DRAWINGS:
            pixels = self._capture(f'''[ {{ op = "clear"; color = {WHITE}; }}
              {{ op = "shader"; shader = "fx"; commands = [ {self._drawing_command(op)} ]; }} ]''', assets=assets)
            self.assertEqual(set(pixels), {(0, 0, 0), (255, 255, 255)})

    def test_drawing_blend(self):
        commands = " ".join(self._drawing_command(op, {field: "[255 0 0 128]" for field in fields.keys() & COLOR_FIELDS})
                            for op, fields in DRAWINGS.items())
        pixels = self._capture(f'''[ {{ op = "clear"; color = {BLUE}; }}
          {{ op = "blend"; mode = "additive"; commands = [ {commands} ]; }} ]''')
        self.assertTrue(any(p[0] > 0 for p in pixels))
        self.assertTrue(all(p[1] == 0 and p[2] == 255 for p in pixels))

    def test_drawing_batch_validates_before_render(self):
        if not self.capture_library:
            self.skipTest("pass --capture-library to enable framebuffer tests")
        capture = self.asset_directory / "invalid-drawing.ppm"
        capture.unlink(missing_ok=True)
        self.evaluate(f'''builtins.raylib {{ hidden = true; maxFrames = 1; fps = 0; }} (_: {{ commands = [
          {self._drawing_command('rectangleGradientV')}
          {self._drawing_command('circleSector', {'segments': '4097'})}
        ]; }})''', error="integer in", env={
            "LD_PRELOAD": str(Path(self.capture_library).resolve()) + " " + os.environ.get("LD_PRELOAD", ""),
            "NIXRAY_TEST_CAPTURE": str(capture),
        })
        self.assertFalse(capture.exists())

    def test_drawing_extreme_sizes_and_angles(self):
        commands = [self._drawing_command("lineEx", {"x1": "-2147483648", "x2": "2147483647", "thickness": "3.0e38"})]
        for op in ARCS:
            for radius in ("1.0e-40", "3.0e38"):
                changes = {"outerRadius": radius, "innerRadius": "0"} if op.startswith("ring") else {"radius": radius}
                commands.append(self._drawing_command(op, changes | {"segments": "0", "startAngle": "-90", "endAngle": "90"}))
            commands.append(self._drawing_command(op, {"startAngle": "1.0e30", "endAngle": "1.0e30", "segments": "0"}))
        commands.append(self._drawing_command("circleGradient", {"radius": "3.0e38"}))
        result = self.evaluate(f'''builtins.raylib {{ width = 32; height = 32; hidden = true; maxFrames = 1; fps = 0; }}
          (_: {{ commands = [ {' '.join(commands)} ]; }})''')
        self.assertEqual(result["frames"], 1)

    def test_drawing_example(self):
        example = Path(__file__).resolve().parent.parent / "examples/drawing.nix"
        self.assertEqual(self.evaluate(f"import {example} {{ hidden = true; maxFrames = 2; }}"),
                         {"frames": 2, "state": {"sweep": 270}})
