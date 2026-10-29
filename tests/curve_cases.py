"""Regular polygons and safely sampled open spline strokes."""

import os
from pathlib import Path


RED = "[255 0 0 255]"
BLACK = "[0 0 0 255]"
POLYGONS = ("poly", "polyLines", "polyLinesEx")
SPLINES = ("splineLinear", "splineBasis", "splineCatmullRom", "splineBezierQuadratic", "splineBezierCubic")
CURVES = ("lineBezier", *SPLINES)


def points(values):
    return "[ " + " ".join(f"{{ x = {x}; y = {y}; }}" for x, y in values) + " ]"


STRAIGHT = {
    "splineLinear": [(4, 16), (16, 16), (28, 16)],
    "splineBasis": [(-20, 16), (4, 16), (28, 16), (52, 16)],
    "splineCatmullRom": [(-20, 16), (4, 16), (28, 16), (52, 16)],
    "splineBezierQuadratic": [(4, 16), (16, 16), (28, 16)],
    "splineBezierCubic": [(4, 16), (12, 16), (20, 16), (28, 16)],
}


class CurveCases:
    def _curve_command(self, op, changes=None, *, remove=()):
        if op in POLYGONS:
            fields = dict(x="16", y="16", sides="4", radius="12", color=RED)
            if op == "polyLinesEx":
                fields["thickness"] = "3"
        elif op == "lineBezier":
            fields = dict(x1="4", y1="16", x2="28", y2="16", thickness="4", color=RED)
        else:
            fields = dict(points=points(STRAIGHT[op]), thickness="4", color=RED)
        fields.update(changes or {})
        return '{ op = "' + op + '"; ' + " ".join(f"{k} = {v};" for k, v in fields.items() if k not in remove) + " }"

    def _curve_pixels(self, op, changes=None, *, background=BLACK):
        return self._capture(f'[ {{ op = "clear"; color = {background}; }} {self._curve_command(op, changes)} ]')

    def test_curves_pure_and_restricted_validation(self):
        commands = " ".join(self._curve_command(op) for op in (*POLYGONS, *CURVES))
        for flag in ("--pure-eval", "--restrict-eval"):
            self.assertEqual(self.evaluate(f"builtins.raylibValidate [ {commands} ]", flags=[flag],
                                           env={"DISPLAY": "", "WAYLAND_DISPLAY": ""}), 9)

    def test_curves_nix_constructors_and_top_level_count(self):
        library = Path(__file__).resolve().parent.parent / "lib"
        commands = " ".join(f"(ray.{op} {self._curve_command(op)})" for op in (*POLYGONS, *CURVES))
        self.assertEqual(self.evaluate(f'''let ray = import {library}; in ray.validate [
          (ray.clip {{ x = 0; y = 0; width = 32; height = 32; commands = [ {commands} ]; }})
        ]'''), 1)
        self.assertEqual(self.evaluate(f'''let ray = import {library}; in ray.run {{ hidden = true; fps = 0; maxFrames = 2; }}
          (_: {{ commands = [ {commands} ]; }})'''), {"frames": 2, "state": None})

    def test_curves_required_fields(self):
        for op in (*POLYGONS, *CURVES):
            fields = ("x", "y", "sides", "radius", "color") if op in POLYGONS else (
                ("x1", "y1", "x2", "y2", "thickness", "color") if op == "lineBezier" else ("points", "thickness", "color"))
            if op == "polyLinesEx":
                fields += ("thickness",)
            for field in fields:
                with self.subTest(op=op, field=field):
                    self.evaluate(f"builtins.raylibValidate [ {self._curve_command(op, remove=(field,))} ]",
                                  error=f"missing attribute '{field}'")

    def test_curves_unknown_fields(self):
        for op in (*POLYGONS, *CURVES):
            self.evaluate(f"builtins.raylibValidate [ {self._curve_command(op, {'typo': '1'})} ]", error="unknown attribute 'typo'")
        for op in ("poly", "polyLines"):
            self.evaluate(f"builtins.raylibValidate [ {self._curve_command(op, {'thickness': '2'})} ]", error="unknown attribute 'thickness'")
        self.evaluate(f"builtins.raylibValidate [ {self._curve_command('splineLinear', {'segments': '24'})} ]", error="unknown attribute 'segments'")

    def test_curves_integer_positions_and_sides(self):
        for op in (*POLYGONS, "lineBezier"):
            field = "x" if op in POLYGONS else "x1"
            for value, error in (("1.5", "expected an integer"), ("2147483648", "integer in"), ("-2147483649", "integer in")):
                self.evaluate(f"builtins.raylibValidate [ {self._curve_command(op, {field: value})} ]", error=error)
        for sides in ("2", "4097", "-1"):
            self.evaluate(f"builtins.raylibValidate [ {self._curve_command('poly', {'sides': sides})} ]", error="integer in [3, 4096]")

    def test_curves_numeric_and_color_validation(self):
        for op in (*POLYGONS, *CURVES):
            field = "radius" if op in POLYGONS else "thickness"
            for number in ("-1", "1.0e100"):
                self.evaluate(f"builtins.raylibValidate [ {self._curve_command(op, {field: number})} ]", error="finite number")
            self.evaluate(f"builtins.raylibValidate [ {self._curve_command(op, {'color': '[]'})} ]", error="color must be")
        self.evaluate(f"builtins.raylibValidate [ {self._curve_command('polyLinesEx', {'thickness': '-0.5'})} ]", error="finite number")
        self.evaluate(f"builtins.raylibValidate [ {self._curve_command('poly', {'rotation': '1.0e100'})} ]", error="finite number")

    def test_curves_point_schema_validation(self):
        for op in SPLINES:
            self.evaluate(f"builtins.raylibValidate [ {self._curve_command(op, {'points': '{}'})} ]", error="expected a list")
            for point, error in (("[]", "expected a set"), ("{}", "missing attribute 'x'"),
                                 ("{ x = 1; }", "missing attribute 'y'"), ("{ x = 0.5; y = 0; }", "expected an integer"),
                                 ("{ x = 2147483648; y = 0; }", "integer in"),
                                 ("{ x = 0; y = 0; typo = 1; }", "unknown attribute 'typo'")):
                changes = {"points": f"[ {point} ] ++ builtins.tail {points(STRAIGHT[op])}"}
                self.evaluate(f"builtins.raylibValidate [ {self._curve_command(op, changes)} ]", error=error)

    def test_curves_point_count_limits(self):
        for op in SPLINES:
            minimum = 2 if op == "splineLinear" else 3 if op == "splineBezierQuadratic" else 4
            for count in (0, minimum - 1, 4097):
                expression = f"builtins.genList (_: {{ x = 0; y = 0; }}) {count}"
                self.evaluate(f"builtins.raylibValidate [ {self._curve_command(op, {'points': expression})} ]", error=f"between {minimum} and 4096 points")

    def test_curves_bezier_requires_complete_spans(self):
        for op, counts in (("splineBezierQuadratic", (4, 6)), ("splineBezierCubic", (5, 6, 8))):
            for count in counts:
                changes = {"points": f"builtins.genList (i: {{ x = i; y = 0; }}) {count}"}
                self.evaluate(f"builtins.raylibValidate [ {self._curve_command(op, changes)} ]", error="complete spans")

    def test_curves_segment_limits(self):
        for op in CURVES:
            if op == "splineLinear":
                continue
            for segments, error in (("0", "integer in [1, 4096]"), ("4097", "integer in [1, 4096]"),
                                    ("-1", "integer in [1, 4096]"), ("1.5", "expected an integer")):
                self.evaluate(f"builtins.raylibValidate [ {self._curve_command(op, {'segments': segments})} ]", error=error)

    def test_curves_total_sampling_budget(self):
        for op in ("splineBasis", "splineCatmullRom", "splineBezierQuadratic", "splineBezierCubic"):
            count = 20 if op in ("splineBasis", "splineCatmullRom") else 35 if op == "splineBezierQuadratic" else 52
            changes = {"segments": "4096", "points": f"builtins.genList (i: {{ x = i; y = 16; }}) {count}"}
            self.evaluate(f"builtins.raylibValidate [ {self._curve_command(op, changes)} ]", error="65536 intervals")
            self.evaluate(f"builtins.raylibValidate [ {self._curve_command(op, changes | {'thickness': '0'})} ]", error="65536 intervals")
            changes["points"] = f"builtins.genList (i: {{ x = i; y = 16; }}) {count - (1 if count == 20 else 2 if count == 35 else 3)}"
            self.assertEqual(self.evaluate(f"builtins.raylibValidate [ {self._curve_command(op, changes)} ]"), 1)

    def test_curves_maximum_point_lists(self):
        for op in SPLINES:
            changes = {"points": "builtins.genList (i: { x = i; y = 16; }) " + ("4095" if op == "splineBezierQuadratic" else "4096")}
            if op != "splineLinear":
                changes["segments"] = "1"
            self.assertEqual(self.evaluate(f"builtins.raylibValidate [ {self._curve_command(op, changes)} ]"), 1)

    def test_curves_regular_polygon_fill_and_rotation(self):
        reference = self._curve_pixels("poly", {"sides": "3"})
        rotated = self._curve_pixels("poly", {"sides": "3", "rotation": "90"})
        self.assert_pixel(reference, 16, 16, (255, 0, 0))
        self.assert_pixel(reference, 25, 16, (255, 0, 0))
        self.assert_pixel(reference, 16, 25, (0, 0, 0))
        self.assert_pixel(rotated, 25, 16, (0, 0, 0))
        self.assert_pixel(rotated, 16, 25, (255, 0, 0))

    def test_curves_polygon_rotation_normalization(self):
        for op in POLYGONS:
            reference = self._curve_pixels(op, {"rotation": "15"})
            for rotation in ("375", "-345", "735.0"):
                self.assertEqual(reference, self._curve_pixels(op, {"rotation": rotation}))

    def test_curves_polygon_outlines_and_saturation(self):
        for op in ("polyLines", "polyLinesEx"):
            pixels = self._curve_pixels(op)
            self.assertIn((255, 0, 0), pixels)
            self.assert_pixel(pixels, 16, 16, (0, 0, 0))
            self.assert_pixel(pixels, 2, 16, (0, 0, 0))
        fill = self._curve_pixels("poly")
        for thickness in ("12", "30", "3.0e38"):
            self.assertEqual(fill, self._curve_pixels("polyLinesEx", {"thickness": thickness}))
        self.assert_pixel(self._curve_pixels("polyLinesEx"), 24, 16, (255, 0, 0))

    def test_curves_straight_strokes_and_butt_caps(self):
        expected = [(255, 0, 0) if 4 <= x < 28 and 14 <= y < 18 else (0, 0, 0) for y in range(32) for x in range(32)]
        for op in CURVES:
            with self.subTest(op=op):
                self.assertEqual(expected, self._curve_pixels(op))

    def test_curves_linear_miter_joins_and_reversal(self):
        values = [(4, 24), (16, 8), (28, 24)]
        reference = self._curve_pixels("splineLinear", {"points": points(values)})
        self.assertEqual(reference, self._curve_pixels("splineLinear", {"points": points(values[::-1])}))
        self.assert_pixel(reference, 16, 8, (255, 0, 0))
        self.assert_pixel(reference, 16, 3, (0, 0, 0))

    def test_curves_quadratic_shape(self):
        pixels = self._curve_pixels("splineBezierQuadratic", {"points": points([(4, 24), (16, 0), (28, 24)])})
        self.assert_pixel(pixels, 16, 12, (255, 0, 0))
        self.assert_pixel(pixels, 16, 20, (0, 0, 0))
        self.assert_pixel(pixels, 16, 2, (0, 0, 0))

    def test_curves_cubic_shape(self):
        pixels = self._curve_pixels("splineBezierCubic", {"points": points([(4, 24), (4, 0), (28, 0), (28, 24)])})
        self.assert_pixel(pixels, 16, 6, (255, 0, 0))
        self.assert_pixel(pixels, 16, 18, (0, 0, 0))

    def test_curves_basis_does_not_interpolate_control_endpoints(self):
        pixels = self._curve_pixels("splineBasis", {"points": points([(0, 28), (0, 4), (32, 4), (32, 28)])})
        self.assert_pixel(pixels, 16, 5, (255, 0, 0))
        self.assert_pixel(pixels, 6, 8, (255, 0, 0))
        self.assert_pixel(pixels, 16, 12, (0, 0, 0))
        self.assert_pixel(pixels, 0, 28, (0, 0, 0))

    def test_curves_catmull_rom_endpoint_and_tangent_controls(self):
        pixels = self._curve_pixels("splineCatmullRom", {"points": points([(0, 88), (4, 24), (28, 24), (32, 88)])})
        self.assert_pixel(pixels, 16, 16, (255, 0, 0))
        self.assert_pixel(pixels, 16, 24, (0, 0, 0))
        self.assert_pixel(pixels, 5, 23, (255, 0, 0))

    def test_curves_connector_easing_and_sampling(self):
        changes = dict(x1="4", y1="4", x2="28", y2="28", thickness="3")
        pixels = self._curve_pixels("lineBezier", changes)
        self.assert_pixel(pixels, 10, 5, (255, 0, 0))
        self.assert_pixel(pixels, 22, 26, (255, 0, 0))
        self.assert_pixel(pixels, 10, 10, (0, 0, 0))
        self.assert_pixel(self._curve_pixels("lineBezier", changes | {"segments": "1"}), 10, 10, (255, 0, 0))
        self.assertEqual(pixels, self._curve_pixels("lineBezier", dict(x1="28", y1="28", x2="4", y2="4", thickness="3")))

    def test_curves_connector_vertical_and_horizontal(self):
        vertical = self._curve_pixels("lineBezier", dict(x1="16", y1="4", x2="16", y2="28"))
        self.assertEqual(vertical, [(255, 0, 0) if 14 <= x < 18 and 4 <= y < 28 else (0, 0, 0) for y in range(32) for x in range(32)])

    def test_curves_complete_multi_span_beziers(self):
        for op, values in (("splineBezierQuadratic", [4, 10, 16, 22, 28]), ("splineBezierCubic", [4, 8, 12, 16, 20, 24, 28])):
            self.assertEqual(self._curve_pixels(op), self._curve_pixels(op, {"points": points([(x, 16) for x in values])}))

    def test_curves_overlapping_spans_and_catmull_endpoint_padding(self):
        for op in ("splineBasis", "splineCatmullRom"):
            self.assertEqual(self._curve_pixels(op), self._curve_pixels(op, {
                "points": points([(x, 16) for x in (-8, 4, 16, 28, 40)]),
            }))
        self.assertEqual(self._curve_pixels("splineCatmullRom"), self._curve_pixels("splineCatmullRom", {
            "points": points([(x, 16) for x in (4, 4, 28, 28)]),
        }))

    def test_curves_default_and_maximum_segments(self):
        for op in CURVES:
            if op != "splineLinear":
                reference = self._curve_pixels(op)
                self.assertEqual(reference, self._curve_pixels(op, {"segments": "24"}))
                self.assertEqual(reference, self._curve_pixels(op, {"segments": "4096"}))
        self.assertIn((255, 0, 0), self._curve_pixels("poly", {"sides": "4096"}))

    def test_curves_zero_sizes_still_validate(self):
        for op in (*POLYGONS, *CURVES):
            changes = {"radius" if op in POLYGONS else "thickness": "0"}
            self.assertEqual(set(self._curve_pixels(op, changes)), {(0, 0, 0)})
            self.evaluate(f"builtins.raylibValidate [ {self._curve_command(op, changes | {'color': '[]'})} ]", error="color must be")
        self.assertEqual(set(self._curve_pixels("polyLinesEx", {"thickness": "0"})), {(0, 0, 0)})
        self.evaluate(f"builtins.raylibValidate [ {self._curve_command('splineBezierCubic', {'thickness': '0', 'points': points([(0, 0)] * 5)})} ]", error="complete spans")

    def test_curves_collapsed_spans_and_float_rounded_points(self):
        for op in SPLINES:
            self.assertEqual(set(self._curve_pixels(op, {"points": points([(16, 16)] * len(STRAIGHT[op]))})), {(0, 0, 0)})
        self.assertEqual(set(self._curve_pixels("lineBezier", {"x2": "4"})), {(0, 0, 0)})
        self.assertEqual(set(self._curve_pixels("lineBezier", dict(x1="1073741824", x2="1073741825"))), {(0, 0, 0)})
        reference = self._curve_pixels("splineLinear")
        self.assertEqual(reference, self._curve_pixels("splineLinear", {"points": points([(4, 16), (4, 16), (16, 16), (16, 16), (28, 16)])}))

    def test_curves_constant_spans_between_nonconstant_spans(self):
        for op, values in (("splineBezierQuadratic", [4, 8, 16, 16, 16, 20, 28]),
                           ("splineBezierCubic", [4, 8, 12, 16, 16, 16, 16, 20, 24, 28])):
            self.assertEqual(self._curve_pixels(op), self._curve_pixels(op, {"points": points([(x, 16) for x in values])}))

    def test_curves_alpha_and_shared_joins(self):
        for op in ("poly", "polyLinesEx", *CURVES):
            changes = {"color": "[255 0 0 128]"}
            if op == "polyLinesEx":
                changes["thickness"] = "12"
            pixels = self._curve_pixels(op, changes, background="[0 0 255 255]")
            self.assert_pixel(pixels, 16, 16, (128, 0, 127), tolerance=1)
        pixels = self._curve_pixels("splineLinear", {"points": points([(4, 24), (16, 8), (28, 24)]), "color": "[255 0 0 128]"}, background="[0 0 255 255]")
        self.assert_pixel(pixels, 16, 8, (128, 0, 127), tolerance=1)

    def test_curves_bounded_miters_and_exact_reversals(self):
        for values in ([(4, 16), (28, 16), (4, 17)], [(4, 16), (28, 16), (4, 16)]):
            pixels = self._curve_pixels("splineLinear", {"points": points(values)})
            self.assertIn((255, 0, 0), pixels)
            for y in (0, 10, 23, 31):
                self.assertTrue(all(pixels[y * 32 + x] == (0, 0, 0) for x in range(32)))

    def test_curves_exact_retrace_preserves_full_width(self):
        self.assertEqual(self._curve_pixels("splineLinear"), self._curve_pixels("splineLinear", {
            "points": points([(4, 16), (28, 16), (4, 16)]),
        }))

    def test_curves_clip_and_camera(self):
        for op in (*POLYGONS, *CURVES):
            pixels = self._capture(f'''[ {{ op = "clear"; color = {BLACK}; }}
              {{ op = "clip"; x = 8; y = 8; width = 8; height = 8; commands = [
                {{ op = "camera2D"; camera = {{ target = {{ x = 16; y = 16; }}; offset = {{ x = 12; y = 12; }}; zoom = 2; }};
                   commands = [ {self._curve_command(op)} ]; }}
              ]; }} ]''')
            # Polygon contours can lie outside this small clip entirely.
            if op not in ("polyLines", "polyLinesEx"):
                self.assertIn((255, 0, 0), pixels)
            self.assertTrue(all(pixels[y * 32 + x] == (0, 0, 0) for y in range(32) for x in range(32)
                                if not (8 <= x < 16 and 8 <= y < 16)))

    def test_curves_camera_transform(self):
        pixels = self._capture(f'''[ {{ op = "clear"; color = {BLACK}; }}
          {{ op = "camera2D"; camera = {{ zoom = 2; offset = {{ x = 2; y = 4; }}; }}; commands = [
            {self._curve_command('splineLinear', {'points': points([(2, 6), (12, 6)]), 'thickness': '2'})}
          ]; }} ]''')
        self.assertEqual(pixels, [(255, 0, 0) if 6 <= x < 26 and 14 <= y < 18 else (0, 0, 0) for y in range(32) for x in range(32)])

    def test_curves_render_textures(self):
        for op in ("poly", "polyLinesEx", *CURVES):
            command = self._curve_command(op)
            pixels = self._capture(f'''[ {{ op = "clear"; color = {BLACK}; }}
              {{ op = "paint"; texture = "canvas"; commands = [ {{ op = "clear"; color = {BLACK}; }} {command} ]; }}
              {{ op = "texture"; texture = "canvas"; x = 0; y = 0; }} ]''', assets="{ renderTextures.canvas = { width = 32; height = 32; }; }")
            self.assertEqual(pixels, self._curve_pixels(op))

    def test_curves_shader_and_state_restoration(self):
        shader = Path(__file__).resolve().parent.parent / "examples/shaders/tint.fs"
        assets = f'''{{ shaders.fx = {{ fragment = {shader}; uniforms = {{ gain = {{ type = "float"; value = 0; }};
          tint = {{ type = "vec3"; value = [1 1 1]; }}; }}; }}; }}'''
        for op in (*POLYGONS, *CURVES):
            pixels = self._capture(f'''[ {{ op = "clear"; color = [255 255 255 255]; }}
              {{ op = "shader"; shader = "fx"; commands = [ {self._curve_command(op)} ]; }}
              {{ op = "rectangle"; x = 0; y = 0; width = 2; height = 2; color = {RED}; }} ]''', assets=assets)
            self.assertIn((0, 0, 0), pixels)
            self.assert_pixel(pixels, 0, 0, (255, 0, 0))
            self.assertEqual(set(pixels), {(0, 0, 0), (255, 0, 0), (255, 255, 255)})

    def test_curves_additive_blend(self):
        for op in ("poly", "polyLinesEx", *CURVES):
            changes = {"color": "[255 0 0 128]"}
            if op == "polyLinesEx":
                changes["thickness"] = "12"
            pixels = self._capture(f'''[ {{ op = "clear"; color = [0 0 255 255]; }}
              {{ op = "blend"; mode = "additive"; commands = [ {self._curve_command(op, changes)} ]; }} ]''')
            self.assert_pixel(pixels, 16, 16, (128, 0, 255), tolerance=1)

    def test_curves_batch_validates_before_drawing(self):
        if not self.capture_library:
            self.skipTest("pass --capture-library to enable framebuffer tests")
        capture = self.asset_directory / "invalid-curves.ppm"
        capture.unlink(missing_ok=True)
        self.evaluate(f'''builtins.raylib {{ hidden = true; fps = 0; maxFrames = 1; }} (_: {{ commands = [
          {self._curve_command('poly')}
          {self._curve_command('splineBezierCubic', {'points': points([(0, 0)] * 5)})}
        ]; }})''', error="complete spans", env={
            "LD_PRELOAD": str(Path(self.capture_library).resolve()) + " " + os.environ.get("LD_PRELOAD", ""),
            "NIXRAY_TEST_CAPTURE": str(capture),
        })
        self.assertFalse(capture.exists())

    def test_curves_extreme_coordinates_and_thickness(self):
        commands = [self._curve_command(op, dict(radius="3.0e38", rotation="-3.0e38")) for op in POLYGONS]
        commands.append(self._curve_command("lineBezier", dict(x1="-2147483648", x2="2147483647", thickness="3.0e38")))
        for op in SPLINES:
            values = [(-2147483648, -2147483648), (2147483647, 2147483647), (-2147483648, 2147483647), (2147483647, -2147483648)]
            commands.append(self._curve_command(op, {"points": points(values[:3] if op == "splineBezierQuadratic" else values), "thickness": "3.0e38"}))
        result = self.evaluate(f'''builtins.raylib {{ hidden = true; width = 32; height = 32; fps = 0; maxFrames = 1; }}
          (_: {{ commands = [ {' '.join(commands)} ]; }})''')
        self.assertEqual(result["frames"], 1)

    def test_curves_subnormal_and_fractional_thickness(self):
        for op in CURVES:
            self.assertEqual(set(self._curve_pixels(op, {"thickness": "1.0e-40"})), {(0, 0, 0)})
            self.assertEqual(self._curve_pixels(op, {"thickness": "3.5"}), self._curve_pixels(op))

    def test_curves_example_wheel_input(self):
        example = Path(__file__).resolve().parent.parent / "examples/curves.nix"
        self.assertEqual(self._input_evaluate(f"import {example} {{ hidden = true; maxFrames = 4; }}"),
                         {"frames": 4, "state": {"thickness": 4.25, "guides": True}})

    def test_curves_example(self):
        example = Path(__file__).resolve().parent.parent / "examples/curves.nix"
        self.assertEqual(self.evaluate(f"import {example} {{ hidden = true; maxFrames = 2; }}"),
                         {"frames": 2, "state": {"thickness": 5, "guides": True}})
