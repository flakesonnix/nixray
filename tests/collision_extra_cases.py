"""Remaining pure 2D queries: native boundaries, degeneracy, overflow and picking."""

from pathlib import Path


POINT = "{ x = 1; y = 1; }"
TRIANGLE = "{ x1 = 0; y1 = 0; x2 = 8; y2 = 0; x3 = 0; y3 = 8; }"
POLYGON = "[ { x = 0; y = 0; } { x = 8; y = 0; } { x = 8; y = 8; } { x = 0; y = 8; } ]"
LINE = "{ x1 = 0; y1 = 0; x2 = 8; y2 = 0; }"
CIRCLE = "{ x = 4; y = 1; radius = 1; }"
EXTRA_CALLS = {
    "CheckCollisionPointTriangle": (POINT, TRIANGLE),
    "CheckCollisionPointPoly": (POINT, POLYGON),
    "CheckCollisionPointLine": ("{ x = 4; y = 0.5; }", LINE),
    "CheckCollisionCircleLine": (CIRCLE, LINE),
}


class CollisionExtraCases:
    def test_collision_extra_registration_pure_and_restricted(self):
        for name, (a, b) in EXTRA_CALLS.items():
            with self.subTest(name=name):
                for flag in ("--pure-eval", "--restrict-eval"):
                    result = self.evaluate(f"builtins.raylib{name} {a} {b}", flags=[flag],
                                           env={"DISPLAY": "", "WAYLAND_DISPLAY": ""})
                    self.assertIs(result, True)

    def test_collision_extra_helpers_and_lazy_partial_application(self):
        library = Path(__file__).resolve().parent.parent / "lib"
        for name, (a, b) in EXTRA_CALLS.items():
            helper = name[0].lower() + name[1:]
            with self.subTest(name=name):
                self.assertEqual(self._collision_evaluate(f'''[
                  (builtins.typeOf builtins.raylib{name})
                  (builtins.typeOf (builtins.raylib{name} (throw "forced too early")))
                ]'''), ["lambda", "lambda"])
                self.assertTrue(self.evaluate(f"let ray = import {library}; in ray.{helper} {a} {b}",
                                              env={"DISPLAY": "", "WAYLAND_DISPLAY": ""}))

    def test_collision_triangle_strict_edges_and_both_windings(self):
        for triangle in (TRIANGLE, "{ x1 = 0; y1 = 0; x2 = 0; y2 = 8; x3 = 8; y3 = 0; }"):
            with self.subTest(triangle=triangle):
                self.assertEqual(self._collision_evaluate(f'''map
                  (point: builtins.raylibCheckCollisionPointTriangle point {triangle}) [
                    {{ x = 1; y = 1; }} {{ x = 3.5; y = 3.5; }}
                    {{ x = 0; y = 0; }} {{ x = 4; y = 0; }} {{ x = 0; y = 4; }}
                    {{ x = 4; y = 4; }} {{ x = 8; y = 0; }} {{ x = 0; y = 8; }}
                    {{ x = -0.25; y = 1; }} {{ x = 4.25; y = 4; }}
                  ]'''), [True, True, False, False, False, False, False, False, False, False])

    def test_collision_triangle_degenerate_and_underflow(self):
        for triangle in ("{ x1 = 0; y1 = 0; x2 = 4; y2 = 4; x3 = 8; y3 = 8; }",
                         "{ x1 = 1; y1 = 1; x2 = 1; y2 = 1; x3 = 1; y3 = 1; }",
                         "{ x1 = 0; y1 = 0; x2 = 1.0e-30; y2 = 0; x3 = 0; y3 = 1.0e-30; }"):
            with self.subTest(triangle=triangle):
                self.assertFalse(self._collision_evaluate(f"builtins.raylibCheckCollisionPointTriangle {POINT} {triangle}"))

    def test_collision_polygon_native_half_open_boundary(self):
        for polygon in (POLYGON, "[ { x = 0; y = 8; } { x = 8; y = 8; } { x = 8; y = 0; } { x = 0; y = 0; } ]",
                        f"({POLYGON} ++ [ {{ x = 0; y = 0; }} ])"):
            with self.subTest(polygon=polygon):
                self.assertEqual(self._collision_evaluate(f'''map
                  (point: builtins.raylibCheckCollisionPointPoly point {polygon}) [
                    {{ x = 1; y = 1; }} {{ x = 0; y = 0; }} {{ x = 4; y = 0; }} {{ x = 0; y = 4; }}
                    {{ x = 8; y = 4; }} {{ x = 4; y = 8; }} {{ x = 8; y = 8; }} {{ x = -0.25; y = 4; }}
                  ]'''), [True, True, True, True, False, False, False, False])

    def test_collision_polygon_concavity_and_implicit_closure(self):
        self.assertEqual(self._collision_evaluate('''let polygon = [
          { x = -4; y = -4; } { x = 4; y = -4; } { x = 4; y = 0; }
          { x = 0; y = 0; } { x = 0; y = 4; } { x = -4; y = 4; }
        ]; in map (point: builtins.raylibCheckCollisionPointPoly point polygon) [
          { x = -2; y = 2; } { x = 2; y = -2; } { x = 2; y = 2; }
          { x = -4; y = 0; } { x = 0; y = 2; }
        ]'''), [True, True, False, True, False])

    def test_collision_polygon_short_and_degenerate_lists(self):
        for polygon in ("[]", f"[ {POINT} ]", f"[ {POINT} {POINT} ]",
                        "[ { x = 0; y = 0; } { x = 4; y = 0; } { x = 8; y = 0; } ]"):
            with self.subTest(polygon=polygon):
                self.assertFalse(self._collision_evaluate(f"builtins.raylibCheckCollisionPointPoly {POINT} {polygon}"))

    def test_collision_polygon_self_intersection_even_odd(self):
        self.assertEqual(self._collision_evaluate('''let polygon = [
          { x = 0; y = 0; } { x = 8; y = 8; } { x = 0; y = 8; } { x = 8; y = 0; }
        ]; in map (point: builtins.raylibCheckCollisionPointPoly point polygon) [
          { x = 4; y = 1; } { x = 4; y = 7; } { x = 1; y = 4; }
          { x = 7; y = 4; } { x = 4; y = 4; }
        ]'''), [True, True, False, False, False])

    def test_collision_point_line_tolerance_and_endpoints(self):
        for line in (LINE, "{ x1 = 8; y1 = 0; x2 = 0; y2 = 0; }"):
            with self.subTest(line=line):
                self.assertEqual(self._collision_evaluate(f'''map
                  (point: builtins.raylibCheckCollisionPointLine point {line}) [
                    {{ x = 4; y = 0; }} {{ x = 4; y = 0.999; }} {{ x = 4; y = 1; }}
                    {{ x = 4; y = -1; }} {{ x = 0; y = 0.5; }} {{ x = 8; y = -0.5; }}
                    {{ x = -0.001; y = 0; }} {{ x = 8.001; y = 0; }}
                  ]'''), [True, True, False, False, True, True, False, False])
        self.assertEqual(self._collision_evaluate('''map
          (point: builtins.raylibCheckCollisionPointLine point { x1 = 2; y1 = 8; x2 = 2; y2 = 0; threshold = 2; }) [
            { x = 3.5; y = 4; } { x = 4; y = 4; } { x = 2; y = -0.1; }
          ]'''), [True, False, False])

    def test_collision_point_line_native_diagonal_heuristic(self):
        self.assertEqual(self._collision_evaluate('''map
          (point: builtins.raylibCheckCollisionPointLine point { x1 = 0; y1 = 0; x2 = 8; y2 = 8; }) [
            { x = 4; y = 4.5; } { x = 4; y = 5; } { x = 4; y = 5.25; }
          ]'''), [True, False, False])

    def test_collision_point_line_zero_threshold_and_length(self):
        self.assertFalse(self._collision_evaluate(f"builtins.raylibCheckCollisionPointLine {{ x = 4; y = 0; }} ({LINE} // {{ threshold = 0; }})"))
        self.assertFalse(self._collision_evaluate(f"builtins.raylibCheckCollisionPointLine {POINT} {{ x1 = 1; y1 = 1; x2 = 1; y2 = 1; threshold = 10; }}"))

    def test_collision_line_threshold_validation_and_schema_isolation(self):
        for threshold, error in (("-1", "integer in"), ("2147483648", "integer in"), ("0.5", "expected an integer"),
                                 ("true", "expected an integer"), ('"bad"', "expected an integer")):
            with self.subTest(threshold=threshold):
                self._collision_evaluate(f"builtins.raylibCheckCollisionPointLine {POINT} ({LINE} // {{ threshold = {threshold}; }})", error=error)
        self.assertTrue(self._collision_evaluate(f"builtins.raylibCheckCollisionPointLine {POINT} ({LINE} // {{ threshold = 2147483647; }})"))
        self._collision_evaluate(f"builtins.raylibCheckCollisionCircleLine {CIRCLE} ({LINE} // {{ threshold = 1; }})",
                                 error="unknown attribute 'threshold'")
        self._collision_evaluate(f"builtins.raylibCheckCollisionLines {LINE} ({LINE} // {{ threshold = 1; }})",
                                 error="unknown attribute 'threshold'")

    def test_collision_circle_line_tangency_projection_and_reversal(self):
        for line in (LINE, "{ x1 = 8; y1 = 0; x2 = 0; y2 = 0; }"):
            with self.subTest(line=line):
                self.assertEqual(self._collision_evaluate(f'''map
                  (circle: builtins.raylibCheckCollisionCircleLine circle {line}) [
                    {{ x = 4; y = 1; radius = 1; }} {{ x = 4; y = 1.001; radius = 1; }}
                    {{ x = -3; y = 4; radius = 5; }} {{ x = -3.01; y = 4; radius = 5; }}
                    {{ x = 11; y = -4; radius = 5; }} {{ x = 4; y = 0; radius = 0; }}
                    {{ x = 8; y = 0; radius = 0; }} {{ x = 9; y = 0; radius = 0; }}
                  ]'''), [True, False, True, False, True, True, True, False])

    def test_collision_circle_line_zero_length_and_epsilon(self):
        self.assertTrue(self._collision_evaluate("builtins.raylibCheckCollisionCircleLine { x = 3; y = 4; radius = 5; } { x1 = 0; y1 = 0; x2 = 0; y2 = 0; }"))
        self.assertFalse(self._collision_evaluate("builtins.raylibCheckCollisionCircleLine { x = 3.01; y = 4; radius = 5; } { x1 = 0; y1 = 0; x2 = 0; y2 = 0; }"))
        # Tiny segments use the first endpoint instead of projection, per raylib.
        self.assertFalse(self._collision_evaluate("builtins.raylibCheckCollisionCircleLine { x = 0.000000059604644775390625; y = 0; radius = 0; } { x1 = 0; y1 = 0; x2 = 0.000000059604644775390625; y2 = 0; }"))

    def test_collision_circle_line_diagonal_projection(self):
        for line in ("{ x1 = 0; y1 = 0; x2 = 8; y2 = 6; }", "{ x1 = 8; y1 = 6; x2 = 0; y2 = 0; }"):
            with self.subTest(line=line):
                self.assertEqual(self._collision_evaluate(f'''map
                  (circle: builtins.raylibCheckCollisionCircleLine circle {line}) [
                    {{ x = 1; y = 7; radius = 5; }} {{ x = 1; y = 7; radius = 4.999; }}
                    {{ x = 11; y = 10; radius = 5; }} {{ x = 4; y = 3; radius = 0; }}
                  ]'''), [True, False, True, True])

    def test_collision_extra_preserves_native_underflow(self):
        self.assertTrue(self._collision_evaluate(f"builtins.raylibCheckCollisionCircleLine {{ x = 4; y = 1.0e-30; radius = 0; }} {LINE}"))
        self.assertTrue(self._collision_evaluate("builtins.raylibCheckCollisionPointLine { x = 5.0e-31; y = 1.0e-30; } { x1 = 0; y1 = 0; x2 = 1.0e-30; y2 = 0; }"))

    def test_collision_extra_rejects_bad_geometry_and_fields(self):
        for name, (a, b) in EXTRA_CALLS.items():
            with self.subTest(name=name):
                self._collision_evaluate(f"builtins.raylib{name} {{}} {b}", error="missing attribute")
                self._collision_evaluate(f"builtins.raylib{name} ({a} // {{ typo = 1; }}) {b}", error="unknown attribute 'typo'")
                if name == "CheckCollisionPointPoly":
                    for bad, error in (("{}", "expected a list"), ("[{}]", "missing attribute"),
                                       ('[ { x = true; y = 0; } ]', "expected"),
                                       ('[ { x = 0; y = 0; typo = 1; } ]', "unknown attribute"),
                                       ('[ { x = 1.0e100; y = 0; } ]', "finite number")):
                        self._collision_evaluate(f"builtins.raylib{name} {a} {bad}", error=error)
                else:
                    for field in (("x1", "y1", "x2", "y2", "x3", "y3") if name.endswith("Triangle") else ("x1", "y1", "x2", "y2")):
                        self._collision_evaluate(f'builtins.raylib{name} {a} (builtins.removeAttrs {b} ["{field}"])', error=f"missing attribute '{field}'")
                        self._collision_evaluate(f"builtins.raylib{name} {a} ({b} // {{ {field} = 1.0e100; }})", error="finite number")
                    self._collision_evaluate(f"builtins.raylib{name} {a} ({b} // {{ typo = 1; }})", error="unknown attribute 'typo'")
        self._collision_evaluate(f"builtins.raylibCheckCollisionCircleLine ({CIRCLE} // {{ radius = -1; }}) {LINE}", error="finite number")

    def test_collision_extra_rejects_native_overflow(self):
        for name, a, b in (
            ("CheckCollisionPointTriangle", POINT, "{ x1 = 0; y1 = 0; x2 = 1.0e30; y2 = 0; x3 = 0; y3 = 1.0e30; }"),
            ("CheckCollisionPointTriangle", "{ x = 3.0e38; y = 0; }", "{ x1 = 0; y1 = 0; x2 = 1.0e-10; y2 = 0; x3 = 0; y3 = 1.0e-10; }"),
            ("CheckCollisionPointPoly", "{ x = 0; y = 0; }", "[ { x = -3.0e38; y = -1; } { x = 3.0e38; y = 1; } { x = 0; y = -1; } ]"),
            ("CheckCollisionPointPoly", "{ x = 0; y = 0; }", "[ { x = 0; y = -1.0e30; } { x = 1.0e30; y = 1.0e30; } { x = 1.0e30; y = -1.0e30; } ]"),
            ("CheckCollisionPointLine", "{ x = 1.0e30; y = 0; }", "{ x1 = 0; y1 = 0; x2 = 0; y2 = 1.0e30; }"),
            ("CheckCollisionPointLine", POINT, "{ x1 = 0; y1 = 0; x2 = 1.0e30; y2 = 0; threshold = 2147483647; }"),
            ("CheckCollisionCircleLine", CIRCLE, "{ x1 = -3.0e38; y1 = 0; x2 = 3.0e38; y2 = 0; }"),
            ("CheckCollisionCircleLine", CIRCLE, "{ x1 = 0; y1 = 0; x2 = 1.0e30; y2 = 0; }"),
            ("CheckCollisionCircleLine", "{ x = 1.0e30; y = 0; radius = 1; }", LINE),
            ("CheckCollisionCircleLine", "{ x = 1.0e30; y = 0; radius = 1; }", "{ x1 = 0; y1 = 0; x2 = 0; y2 = 0; }"),
        ):
            with self.subTest(name=name, a=a, b=b):
                self._collision_evaluate(f"builtins.raylib{name} {a} {b}", error="collision arithmetic must remain finite")

    def test_collision_extra_large_finite_geometry(self):
        self.assertTrue(self._collision_evaluate("builtins.raylibCheckCollisionPointTriangle { x = 1.0e17; y = 1.0e17; } { x1 = 0; y1 = 0; x2 = 1.0e18; y2 = 0; x3 = 0; y3 = 1.0e18; }"))
        self.assertTrue(self._collision_evaluate("builtins.raylibCheckCollisionCircleLine { x = 0; y = 1.0e18; radius = 1.0e18; } { x1 = -1.0e18; y1 = 0; x2 = 1.0e18; y2 = 0; }"))
        # No straddling edge means native polygon arithmetic never runs.
        self.assertFalse(self._collision_evaluate("builtins.raylibCheckCollisionPointPoly { x = 0; y = 2; } [ { x = -3.0e38; y = 0; } { x = 3.0e38; y = 0; } { x = 0; y = 1; } ]"))

    def test_collision_extra_camera_aware_picking_pixels(self):
        calls = (
            ("CheckCollisionPointTriangle", "{ x1 = 0; y1 = 0; x2 = 8; y2 = 0; x3 = 0; y3 = 8; }"),
            ("CheckCollisionPointPoly", POLYGON),
            ("CheckCollisionPointLine", "{ x1 = 0; y1 = 2; x2 = 8; y2 = 2; threshold = 1; }"),
            ("CheckCollisionCircleLine", "{ x1 = 0; y1 = 2; x2 = 8; y2 = 2; }"),
        )
        for name, shape in calls:
            for mouse_y, hit in ((12, True), (30, False)):
                with self.subTest(name=name, mouse_y=mouse_y):
                    pixels = self._capture(f'''let
                      camera = {{ offset = {{ x = 8; y = 8; }}; zoom = 2; }};
                      world = builtins.raylibScreenToWorld2D camera {{ x = 12; y = {mouse_y}; }};
                      hit = builtins.raylib{name} {'(world // { radius = 0.5; })' if name == 'CheckCollisionCircleLine' else 'world'} {shape};
                    in [ {{ op = "clear"; color = [0 0 0 255]; }}
                      {{ op = "camera2D"; inherit camera; commands = [
                        {{ op = "rectangle"; x = 1; y = 1; width = 3; height = 3;
                           color = if hit then [255 0 0 255] else [0 255 0 255]; }}
                      ]; }} ]''')
                    self.assertEqual(pixels[12 * 32 + 12], (255, 0, 0) if hit else (0, 255, 0))
