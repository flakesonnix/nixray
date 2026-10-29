"""Pure native geometry, boundary semantics and camera-aware framebuffer picking."""

from pathlib import Path


RECT = "{ x = 0; y = 0; width = 4; height = 4; }"
CIRCLE = "{ x = 0; y = 0; radius = 2; }"
POINT = "{ x = 0; y = 0; }"
LINE = "{ x1 = 0; y1 = 0; x2 = 4; y2 = 4; }"
CALLS = {
    "CheckCollisionRecs": (RECT, RECT),
    "CheckCollisionCircles": (CIRCLE, CIRCLE),
    "CheckCollisionCircleRec": (CIRCLE, RECT),
    "CheckCollisionPointRec": (POINT, RECT),
    "CheckCollisionPointCircle": (POINT, CIRCLE),
    "CheckCollisionLines": (LINE, "{ x1 = 0; y1 = 4; x2 = 4; y2 = 0; }"),
    "GetCollisionRec": (RECT, RECT),
}


class CollisionCases:
    def _collision_evaluate(self, expression, **kwargs):
        return self.evaluate(expression, flags=["--pure-eval"],
                             env={"DISPLAY": "", "WAYLAND_DISPLAY": ""}, **kwargs)

    def test_collision_registration_and_pure_results(self):
        for name, (a, b) in CALLS.items():
            with self.subTest(name=name):
                expression = f"builtins.raylib{name} {a} {b}"
                expected = True
                if name == "CheckCollisionLines":
                    expected = {"x": 2.0, "y": 2.0}
                elif name == "GetCollisionRec":
                    expected = {"x": 0.0, "y": 0.0, "width": 4.0, "height": 4.0}
                result = self._collision_evaluate(expression)
                self.assertEqual(result, expected)
                if isinstance(result, dict):
                    self.assertTrue(all(isinstance(value, float) for value in result.values()))
                else:
                    self.assertIsInstance(result, bool)

    def test_collision_helpers_and_partial_application(self):
        library = Path(__file__).resolve().parent.parent / "lib"
        for name, (a, b) in CALLS.items():
            helper = name[0].lower() + name[1:]
            with self.subTest(name=name):
                # Neither registration nor partial application may force geometry.
                self.assertEqual(self._collision_evaluate(f'''[
                  (builtins.typeOf builtins.raylib{name})
                  (builtins.typeOf (builtins.raylib{name} (throw "forced too early")))
                ]'''), ["lambda", "lambda"])
                self.assertTrue(self.evaluate(f'''let ray = import {library}; in
                  (ray.{helper} {a} {b}) == (builtins.raylib{name} {a} {b})''',
                  env={"DISPLAY": "", "WAYLAND_DISPLAY": ""}))

    def test_collision_restricted_evaluation(self):
        for name, (a, b) in CALLS.items():
            with self.subTest(name=name):
                expression = f"builtins.raylib{name} {a} {b}"
                self.assertEqual(self.evaluate(expression, flags=["--restrict-eval"],
                                               env={"DISPLAY": "", "WAYLAND_DISPLAY": ""}),
                                 self._collision_evaluate(expression))

    def test_collision_recs_overlap_edges_and_fractional_coordinates(self):
        self.assertEqual(self._collision_evaluate('''let
          check = builtins.raylibCheckCollisionRecs { x = -2.5; y = 1.25; width = 4; height = 3; };
        in map check [
          { x = -1; y = 2; width = 1; height = 1; }
          { x = 1.5; y = 2; width = 2; height = 2; }
          { x = 0; y = 4.25; width = 1; height = 1; }
          { x = 1.25; y = 2; width = 1; height = 1; }
          { x = 20; y = 20; width = 1; height = 1; }
        ]'''), [True, False, False, True, False])

    def test_collision_point_rec_half_open_edges(self):
        self.assertEqual(self._collision_evaluate(f'''let
          check = point: builtins.raylibCheckCollisionPointRec point {RECT};
        in map check [
          {{ x = 0; y = 0; }} {{ x = 3.999; y = 3.999; }}
          {{ x = 4; y = 2; }} {{ x = 2; y = 4; }}
          {{ x = -0.001; y = 2; }} {{ x = 2; y = -0.001; }}
        ]'''), [True, True, False, False, False, False])

    def test_collision_circle_tangency_and_separation(self):
        self.assertEqual(self._collision_evaluate(f'''let
          check = builtins.raylibCheckCollisionCircles {CIRCLE};
        in map check [
          {{ x = 3; y = 4; radius = 3; }}
          {{ x = 3.01; y = 4; radius = 3; }}
          {{ x = 0; y = 0; radius = 0; }}
          {{ x = -3; y = 0; radius = 1; }}
        ]'''), [True, False, True, True])

    def test_collision_point_circle_boundary(self):
        self.assertEqual(self._collision_evaluate('''let
          circle = { x = -1.5; y = 2.5; radius = 5; };
          check = point: builtins.raylibCheckCollisionPointCircle point circle;
        in map check [
          { x = 1.5; y = 6.5; } { x = 1.6; y = 6.5; }
          { x = -1.5; y = 2.5; } { x = -6.5; y = 2.5; }
        ]'''), [True, False, True, True])

    def test_collision_circle_rec_sides_and_corners(self):
        self.assertEqual(self._collision_evaluate(f'''let
          check = circle: builtins.raylibCheckCollisionCircleRec circle {RECT};
        in map check [
          {{ x = 6; y = 2; radius = 2; }}
          {{ x = 6.01; y = 2; radius = 2; }}
          {{ x = -3; y = -4; radius = 5; }}
          {{ x = -3.01; y = -4; radius = 5; }}
          {{ x = 2; y = 2; radius = 0; }}
          {{ x = 4; y = 4; radius = 0; }}
        ]'''), [True, False, True, False, True, True])

    def test_collision_zero_size_native_semantics(self):
        self.assertEqual(self._collision_evaluate(f'''let
          empty = {{ x = 2; y = 2; width = 0; height = 0; }};
          zero = {{ x = 2; y = 2; radius = 0; }};
        in {{
          rectangles = builtins.raylibCheckCollisionRecs empty {RECT};
          pointRec = builtins.raylibCheckCollisionPointRec {{ x = 2; y = 2; }} empty;
          pointCircle = builtins.raylibCheckCollisionPointCircle {{ x = 2; y = 2; }} zero;
          circles = builtins.raylibCheckCollisionCircles zero zero;
          circleRec = builtins.raylibCheckCollisionCircleRec zero empty;
          overlap = builtins.raylibGetCollisionRec empty {RECT};
        }}'''), {"rectangles": True, "pointRec": False, "pointCircle": True,
                 "circles": True, "circleRec": True,
                 "overlap": {"x": 0.0, "y": 0.0, "width": 0.0, "height": 0.0}})

    def test_collision_overlap_rectangle(self):
        self.assertEqual(self._collision_evaluate('''builtins.raylibGetCollisionRec
          { x = -2.5; y = 1.25; width = 4; height = 3; }
          { x = 0.5; y = -1; width = 6; height = 4; }'''),
          {"x": 0.5, "y": 1.25, "width": 1.0, "height": 1.75})

    def test_collision_no_overlap_returns_zero_rectangle(self):
        for other in ("{ x = 4; y = 0; width = 4; height = 4; }",
                      "{ x = 10; y = 10; width = 1; height = 1; }"):
            with self.subTest(other=other):
                self.assertEqual(self._collision_evaluate(f"builtins.raylibGetCollisionRec {RECT} {other}"),
                                 {"x": 0.0, "y": 0.0, "width": 0.0, "height": 0.0})

    def test_collision_symmetry(self):
        for name, a, b in (
            ("CheckCollisionRecs", RECT, "{ x = 2; y = 2; width = 4; height = 4; }"),
            ("GetCollisionRec", RECT, "{ x = 2; y = 2; width = 4; height = 4; }"),
            ("CheckCollisionCircles", CIRCLE, "{ x = 3; y = 0; radius = 1; }"),
            ("CheckCollisionLines", LINE, "{ x1 = 0; y1 = 4; x2 = 4; y2 = 0; }"),
        ):
            with self.subTest(name=name):
                self.assertTrue(self._collision_evaluate(f'''(builtins.raylib{name} {a} {b}) ==
                  (builtins.raylib{name} {b} {a})'''))

    def test_collision_lines_endpoint_vertical_and_reversed(self):
        for a, b, expected in (
            (LINE, "{ x1 = 0; y1 = 4; x2 = 4; y2 = 0; }", {"x": 2.0, "y": 2.0}),
            (LINE, "{ x1 = 4; y1 = 4; x2 = 8; y2 = 0; }", {"x": 4.0, "y": 4.0}),
            ("{ x1 = 2; y1 = -2; x2 = 2; y2 = 6; }",
             "{ x1 = 4; y1 = 1.5; x2 = -4; y2 = 1.5; }", {"x": 2.0, "y": 1.5}),
            ("{ x1 = 4; y1 = 4; x2 = 0; y2 = 0; }",
             "{ x1 = 4; y1 = 0; x2 = 0; y2 = 4; }", {"x": 2.0, "y": 2.0}),
        ):
            with self.subTest(a=a, b=b):
                self.assertEqual(self._collision_evaluate(f"builtins.raylibCheckCollisionLines {a} {b}"), expected)

    def test_collision_lines_miss_parallel_collinear_and_degenerate(self):
        for other in (
            "{ x1 = 0; y1 = 1; x2 = 4; y2 = 5; }",  # Parallel.
            "{ x1 = 1; y1 = 1; x2 = 5; y2 = 5; }",  # Collinear overlap.
            "{ x1 = 4; y1 = 4; x2 = 5; y2 = 5; }",  # Collinear shared endpoint.
            "{ x1 = 2; y1 = 2; x2 = 2; y2 = 2; }",  # Zero-length segment.
            "{ x1 = 5; y1 = 0; x2 = 5; y2 = 6; }",  # Intersection outside first segment.
            "{ x1 = 2; y1 = 5; x2 = 2; y2 = 6; }",  # Intersection outside second segment.
        ):
            with self.subTest(other=other):
                self.assertIsNone(self._collision_evaluate(f"builtins.raylibCheckCollisionLines {LINE} {other}"))

    def test_collision_lines_native_epsilon(self):
        for half_span, expected in (("0.0000000298023223876953125", None),
                                    ("0.000000059604644775390625", {"x": 0.5, "y": 0.0})):
            with self.subTest(half_span=half_span):
                self.assertEqual(self._collision_evaluate(f'''builtins.raylibCheckCollisionLines
                  {{ x1 = 0; y1 = 0; x2 = 1; y2 = 0; }}
                  {{ x1 = 0.5; y1 = -{half_span}; x2 = 0.5; y2 = {half_span}; }}'''), expected)

    def test_collision_rejects_bad_geometry_in_either_argument(self):
        for name, good in CALLS.items():
            for index in (0, 1):
                for bad, error in (("[]", "expected a set"), ("{}", "missing attribute"),
                                   (good[index][:-1] + " typo = 1; }", "unknown attribute 'typo'")):
                    args = list(good)
                    args[index] = bad
                    with self.subTest(name=name, index=index, bad=bad):
                        self._collision_evaluate(f"builtins.raylib{name} {args[0]} {args[1]}", error=error)

    def test_collision_rejects_missing_and_invalid_fields(self):
        for name, first, second, fields in (
            ("CheckCollisionPointRec", POINT, RECT, ("x", "y")),
            ("CheckCollisionRecs", RECT, RECT, ("x", "y", "width", "height")),
            ("CheckCollisionCircles", CIRCLE, CIRCLE, ("x", "y", "radius")),
            ("CheckCollisionLines", LINE, LINE, ("x1", "y1", "x2", "y2")),
        ):
            for field in fields:
                with self.subTest(name=name, field=field, missing=True):
                    self._collision_evaluate(f'''builtins.raylib{name}
                      (builtins.removeAttrs {first} [ "{field}" ]) {second}''',
                      error=f"missing attribute '{field}'")
                for bad, error in (("true", "expected"), ('"bad"', "expected"),
                                   ("1.0e100", "finite number"), ("(-1.0e100)", "finite number")):
                    with self.subTest(name=name, field=field, bad=bad):
                        self._collision_evaluate(f'''builtins.raylib{name}
                          ({first} // {{ {field} = {bad}; }}) {second}''', error=error)
        for field in ("width", "height", "radius"):
            name, first, second = (("CheckCollisionCircles", CIRCLE, CIRCLE) if field == "radius"
                                   else ("CheckCollisionRecs", RECT, RECT))
            with self.subTest(field=field, negative=True):
                self._collision_evaluate(f'''builtins.raylib{name}
                  ({first} // {{ {field} = -0.5; }}) {second}''', error="finite number")

    def test_collision_rejects_native_arithmetic_overflow(self):
        for name, a, b in (
            ("CheckCollisionRecs", "{ x = 3.0e38; y = 0; width = 3.0e38; height = 1; }", RECT),
            ("GetCollisionRec", RECT, "{ x = 0; y = 3.0e38; width = 1; height = 3.0e38; }"),
            ("CheckCollisionPointRec", POINT, "{ x = 3.0e38; y = 0; width = 3.0e38; height = 1; }"),
            ("CheckCollisionPointCircle", "{ x = 1.0e30; y = 0; }", CIRCLE),
            ("CheckCollisionCircles", "{ x = -3.0e38; y = 0; radius = 1; }",
             "{ x = 3.0e38; y = 0; radius = 1; }"),
            ("CheckCollisionCircles", "{ x = 0; y = 0; radius = 1.0e19; }",
             "{ x = 0; y = 0; radius = 1.0e19; }"),
            ("CheckCollisionCircleRec", "{ x = -3.0e38; y = 0; radius = 1; }",
             "{ x = 3.0e38; y = 0; width = 0; height = 0; }"),
            ("CheckCollisionLines", "{ x1 = -3.0e38; y1 = 0; x2 = 3.0e38; y2 = 1; }", LINE),
            ("CheckCollisionLines", "{ x1 = 0; y1 = 0; x2 = 1.0e30; y2 = 1.0e30; }",
             "{ x1 = 0; y1 = 1.0e30; x2 = 1.0e30; y2 = 0; }"),
            ("CheckCollisionLines", "{ x1 = 0; y1 = 0; x2 = 1.0e15; y2 = 1.0e15; }",
             "{ x1 = 0; y1 = 1.0e15; x2 = 1.0e15; y2 = 0; }"),
        ):
            with self.subTest(name=name, a=a, b=b):
                self._collision_evaluate(f"builtins.raylib{name} {a} {b}", error="collision arithmetic must remain finite")
        for name, (a, b) in CALLS.items():
            for index, geometry in enumerate((a, b)):
                if "radius" in geometry:
                    args = [a, b]
                    args[index] = f"({geometry} // {{ radius = 1.0e30; }})"
                    with self.subTest(name=name, index=index, radius=True):
                        self._collision_evaluate(f"builtins.raylib{name} {args[0]} {args[1]}",
                                                 error="collision arithmetic must remain finite")

    def test_collision_large_finite_geometry(self):
        self.assertEqual(self._collision_evaluate('''{
          rect = builtins.raylibCheckCollisionPointRec { x = 3.0e38; y = 0; }
            { x = 2.0e38; y = 0; width = 1.1e38; height = 1; };
          circle = builtins.raylibCheckCollisionCircles { x = 0; y = 0; radius = 1.0e18; }
            { x = 2.0e18; y = 0; radius = 1.0e18; };
        }'''), {"rect": True, "circle": True})

    def test_collision_camera_picking_pixels(self):
        for mouse_x, hit in ((12, True), (20, False)):
            with self.subTest(mouse_x=mouse_x):
                pixels = self._capture(f'''let
                  camera = {{ offset = {{ x = 8; y = 8; }}; zoom = 2; }};
                  world = builtins.raylibScreenToWorld2D camera {{ x = {mouse_x}; y = 12; }};
                  rectangle = {{ x = 1; y = 1; width = 4; height = 3; }};
                  hit = builtins.raylibCheckCollisionPointRec world rectangle;
                in [
                  {{ op = "clear"; color = [0 0 0 255]; }}
                  {{ op = "camera2D"; inherit camera; commands = [
                    (rectangle // {{ op = "rectangle"; color = if hit then [255 0 0 255] else [0 255 0 255]; }})
                  ]; }}
                ]''')
                color = (255, 0, 0) if hit else (0, 255, 0)
                self.assertEqual(pixels, [color if 10 <= x < 18 and 10 <= y < 16 else (0, 0, 0)
                                          for y in range(32) for x in range(32)])

    def test_collision_picking_tracks_each_frame(self):
        self.assertEqual(self.evaluate('''builtins.raylib {
          width = 32; height = 32; hidden = true; fps = 0; maxFrames = 3; state = [];
        } (frame: let
          camera = { offset = { x = 8; y = 8; }; zoom = 2; };
          screen = { x = if frame.frame == 1 then 20 else 12; y = 12; };
          world = builtins.raylibScreenToWorld2D camera screen;
        in { commands = []; state = frame.state ++ [ (builtins.raylibCheckCollisionPointRec
          world { x = 1; y = 1; width = 4; height = 3; }) ]; })'''),
          {"frames": 3, "state": [True, False, True]})

    def test_collision_overlap_drives_drawing_pixels(self):
        pixels = self._capture('''let overlap = builtins.raylibGetCollisionRec
          { x = 4; y = 6; width = 12; height = 10; }
          { x = 8; y = 4; width = 12; height = 8; };
        in [
          { op = "clear"; color = [0 0 0 255]; }
          { op = "rectangle"; x = builtins.floor overlap.x; y = builtins.floor overlap.y;
            width = builtins.floor overlap.width; height = builtins.floor overlap.height; color = [255 0 0 255]; }
        ]''')
        self.assert_clip_region(pixels, 8, 6, 16, 12)

    def test_collision_segment_intersection_drives_drawing_pixels(self):
        pixels = self._capture('''let intersection = builtins.raylibCheckCollisionLines
          { x1 = 4; y1 = 4; x2 = 20; y2 = 20; }
          { x1 = 4; y1 = 20; x2 = 20; y2 = 4; };
        in [ { op = "clear"; color = [0 0 0 255]; } ] ++
          (if intersection == null then [] else [ {
            op = "rectangle"; x = builtins.floor intersection.x; y = builtins.floor intersection.y;
            width = 2; height = 2; color = [255 0 0 255];
          } ])''')
        self.assert_clip_region(pixels, 12, 12, 14, 14)

    def test_collision_example(self):
        example = Path(__file__).resolve().parent.parent / "examples/collision.nix"
        result = self.evaluate(f"import {example} {{ hidden = true; maxFrames = 2; }}")
        self.assertEqual(result["frames"], 2)
        for name in ("rectangleHit", "circleHit", "circleRectangleHit", "circleLineHit", "hoverRectangle", "hoverCircle",
                     "hoverTriangle", "hoverPolygon", "hoverLine"):
            self.assertIsInstance(result["state"][name], bool)
        self.assertEqual(set(result["state"]["overlap"]), {"x", "y", "width", "height"})
