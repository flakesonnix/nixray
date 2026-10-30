"""3D camera validation, native depth, projections and framebuffer targets."""

import os
from pathlib import Path


LIB = Path(__file__).resolve().parent.parent / "lib"
RED, BLUE, GREEN, BLACK = "[255 0 0 255]", "[0 0 255 255]", "[0 255 0 255]", "[0 0 0 255]"
ORIGIN = "{ x = 0; y = 0; z = 0; }"
ORTHO = '{ projection = "orthographic"; fovy = 8; }'
TOP = '{ projection = "orthographic"; fovy = 8; position = { x = 0; y = 10; z = 0; }; up = { x = 0; y = 0; z = -1; }; }'
SHAPES = {
    "cube": dict(position=ORIGIN, width="4", height="4", length="2", color=RED),
    "cubeWires": dict(position=ORIGIN, width="4", height="4", length="2", color=RED),
    "sphere": dict(position=ORIGIN, radius="2", color=RED),
    "sphereWires": dict(position=ORIGIN, radius="2", color=RED),
    "plane": dict(position=ORIGIN, width="4", length="2", color=RED),
    "line3D": dict(start="{ x = -2; y = 0; z = 0; }", end="{ x = 2; y = 0; z = 0; }", color=RED),
    "grid": dict(slices="4", spacing="1"),
}


def command(op, changes=None, *, remove=()):
    return '{ op = "' + op + '"; ' + " ".join(f"{k} = {v};" for k, v in (SHAPES[op] | (changes or {})).items() if k not in remove) + " }"


def scene(commands="", *, camera=ORTHO, clear_depth=None):
    clear = "" if clear_depth is None else f"clearDepth = {str(clear_depth).lower()};"
    return f'{{ op = "camera3D"; camera = {camera}; {clear} commands = [ {commands} ]; }}'


class ThreeDCases:
    def _three_d_pixels(self, op, changes=None, *, camera=ORTHO):
        return self._capture(f'[ {{ op = "clear"; color = {BLACK}; }} {scene(command(op, changes), camera=camera)} ]')

    def test_three_d_pure_and_restricted_validation(self):
        commands = " ".join(command(op) for op in SHAPES)
        for flag in ("--pure-eval", "--restrict-eval"):
            self.assertEqual(self.evaluate(f"builtins.raylibValidate [ {scene(commands)} ]", flags=[flag], env={"DISPLAY": "", "WAYLAND_DISPLAY": ""}), 1)

    def test_three_d_nix_constructors(self):
        commands = " ".join(f"(ray.{op} {command(op)})" for op in SHAPES)
        self.assertEqual(self.evaluate(f'''let ray = import {LIB}; in ray.validate [
          (ray.camera3D {{ camera = {{}}; commands = [ {commands} ]; }})
        ]'''), 1)

    def test_three_d_primitives_require_camera(self):
        for op in SHAPES:
            self.evaluate(f"builtins.raylibValidate [ {command(op)} ]", error="requires a camera3D scope")

    def test_three_d_scope_required_and_unknown_fields(self):
        for value, error in (('{ op = "camera3D"; camera = {}; }', "missing attribute 'commands'"),
                              ('{ op = "camera3D"; commands = []; }', "missing attribute 'camera'"),
                              ('{ op = "camera3D"; camera = {}; commands = []; typo = 1; }', "unknown attribute 'typo'"),
                              ('{ op = "camera3D"; camera = {}; commands = []; clearDepth = 1; }', "expected a Boolean"),
                              ('{ op = "camera3D"; camera = {}; commands = {}; }', "expected a list")):
            self.evaluate(f"builtins.raylibValidate [ {value} ]", error=error)

    def test_three_d_camera_vectors_are_strict_finite_sets(self):
        for field in ("position", "target", "up"):
            for value, error in (("[]", "expected a set"), ("{}", "missing attribute 'x'"),
                                 ("{ x = 0; y = 0; }", "missing attribute 'z'"),
                                 ("{ x = 0; y = 0; z = 1.0e100; }", "finite number"),
                                 ("{ x = 0; y = 1; z = 0; typo = 1; }", "unknown attribute 'typo'")):
                self.evaluate(f"builtins.raylibValidate [ {scene(camera='{ ' + field + ' = ' + value + '; }')} ]", error=error)

    def test_three_d_camera_projection_and_fovy(self):
        for camera, error in (('{ projection = "fishEye"; }', "unknown 3D camera projection"),
                               ('{ projection = 1; }', "expected a string"), ('{ fovY = 45; }', "unknown attribute 'fovY'"),
                               ("{ fovy = 0; }", "fovy must be positive"), ("{ fovy = -1; }", "finite number"),
                               ("{ fovy = 180; }", "below 180"), ("{ fovy = 179.99999999; }", "below 180"),
                               ("{ fovy = 1.0e100; }", "finite number")):
            self.evaluate(f"builtins.raylibValidate [ {scene(camera=camera)} ]", error=error)
        self.assertEqual(self.evaluate(f'''builtins.raylibValidate [ {scene(camera='{ projection = "orthographic"; fovy = 180; }')} ]'''), 1)

    def test_three_d_rejects_degenerate_native_camera_matrices(self):
        for camera in (f"{{ position = {ORIGIN}; }}", "{ up = { x = 0; y = 0; z = 0; }; }",
                       "{ up = { x = 0; y = 0; z = 1; }; }", "{ up = { x = 0; y = 1.0e-40; z = 1; }; }",
                       "{ position = { x = 0; y = 0; z = 3.0e38; }; }",
                       "{ position = { x = 3.0e38; y = 0; z = 10; }; target = { x = 3.0e38; y = 0; z = 0; }; }",
                       "{ position = { x = 0; y = 0; z = 10000000000; }; target = { x = 0; y = 0; z = 10000000001; }; }",
                       "{ position = { x = 0; y = 0; z = 1.0e-40; }; }"):
            self.evaluate(f"builtins.raylibValidate [ {scene(camera=camera)} ]", error="finite and invertible")

    def test_three_d_rejects_unusable_projection_matrices(self):
        for camera in ("{ fovy = 1.0e-40; }", '{ projection = "orthographic"; fovy = 1.0e-40; }',
                       '{ projection = "orthographic"; fovy = 3.0e38; }'):
            self.evaluate(f"builtins.raylibValidate [ {scene(camera=camera)} ]", error="finite and invertible")

    def test_three_d_required_shape_fields(self):
        for op, fields in SHAPES.items():
            for field in fields:
                self.evaluate(f"builtins.raylibValidate [ {scene(command(op, remove=(field,)))} ]", error=f"missing attribute '{field}'")

    def test_three_d_unknown_shape_fields(self):
        for op in SHAPES:
            self.evaluate(f"builtins.raylibValidate [ {scene(command(op, {'typo': '1'}))} ]", error="unknown attribute 'typo'")
        self.evaluate(f"builtins.raylibValidate [ {scene(command('grid', {'color': RED}))} ]", error="unknown attribute 'color'")

    def test_three_d_shape_coordinates_and_dimensions(self):
        for op in ("cube", "cubeWires", "sphere", "sphereWires", "plane"):
            self.evaluate(f"builtins.raylibValidate [ {scene(command(op, {'position': '{ x = 1.0e100; y = 0; z = 0; }'}))} ]", error="finite number")
            field = "radius" if op.startswith("sphere") else "width"
            self.evaluate(f"builtins.raylibValidate [ {scene(command(op, {field: '-1'}))} ]", error="finite number")
            self.evaluate(f"builtins.raylibValidate [ {scene(command(op, {'color': '[]'}))} ]", error="color must be")
        self.assertEqual(self.evaluate(f"builtins.raylibValidate [ {scene(command('cube', {'position': '{ x = 0.25; y = -0.5; z = 0.75; }', 'width': '1.5'}))} ]"), 1)

    def test_three_d_overflowing_geometry_bounds(self):
        for op, changes in (("cube", {"position": "{ x = 3.0e38; y = 0; z = 0; }", "width": "3.0e38"}),
                            ("sphere", {"position": "{ x = 3.0e38; y = 0; z = 0; }", "radius": "3.0e38"}),
                            ("plane", {"position": "{ x = 0; y = 0; z = -3.0e38; }", "length": "3.0e38"}),
                            ("grid", {"slices": "4096", "spacing": "3.0e38"})):
            self.evaluate(f"builtins.raylibValidate [ {scene(command(op, changes))} ]", error="geometry bounds")

    def test_three_d_sphere_tessellation_limits(self):
        for op in ("sphere", "sphereWires"):
            for field, values in (("rings", ("1", "129")), ("slices", ("2", "257"))):
                for value in values:
                    self.evaluate(f"builtins.raylibValidate [ {scene(command(op, {field: value}))} ]", error="integer in")
                self.evaluate(f"builtins.raylibValidate [ {scene(command(op, {field: '4.5'}))} ]", error="expected an integer")
            self.assertEqual(self.evaluate(f"builtins.raylibValidate [ {scene(command(op, {'rings': '128', 'slices': '256'}))} ]"), 1)

    def test_three_d_grid_limits(self):
        for changes, error in (({"slices": "4097"}, "integer in"), ({"slices": "-1"}, "integer in"),
                               ({"slices": "1.5"}, "expected an integer"), ({"spacing": "-1"}, "finite number"),
                               ({"spacing": "1.0e100"}, "finite number")):
            self.evaluate(f"builtins.raylibValidate [ {scene(command('grid', changes))} ]", error=error)

    def test_three_d_mode_restrictions(self):
        for child in (scene(), '{ op = "camera2D"; camera = {}; commands = []; }',
                      '{ op = "paint"; texture = "target"; commands = []; }',
                      '{ op = "rectangle"; x = 0; y = 0; width = 1; height = 1; color = [0 0 0 255]; }'):
            self.evaluate(f"builtins.raylibValidate [ {scene(child)} ]", error="is not supported inside camera3D")

    def test_three_d_shares_scope_nesting_limit(self):
        for count in (63, 64):
            expression = f'''let leaf = {scene()}; wrap = commands: {{ op = "clip"; x = 0; y = 0; width = 32; height = 32; inherit commands; }};
              value = builtins.foldl' (commands: _: [ (wrap commands) ]) [ leaf ] (builtins.genList (i: i) {count});
            in builtins.raylibValidate value'''
            if count == 63:
                self.assertEqual(self.evaluate(expression), 1)
            else:
                self.evaluate(expression, error="nesting must not exceed 64")

    def test_three_d_cube_orthographic_pixels(self):
        self.assertEqual(self._three_d_pixels("cube"), [(255, 0, 0) if 8 <= x < 24 and 8 <= y < 24 else (0, 0, 0)
                                                        for y in range(32) for x in range(32)])

    def test_three_d_cube_wire_pixels(self):
        pixels = self._three_d_pixels("cubeWires")
        self.assertIn((255, 0, 0), pixels)
        self.assert_pixel(pixels, 16, 16, (0, 0, 0))
        self.assertLess(pixels.count((255, 0, 0)), self._three_d_pixels("cube").count((255, 0, 0)))

    def test_three_d_sphere_and_wire_pixels(self):
        filled = self._three_d_pixels("sphere")
        self.assert_pixel(filled, 16, 16, (255, 0, 0))
        self.assert_pixel(filled, 23, 16, (255, 0, 0))
        self.assert_pixel(filled, 8, 8, (0, 0, 0))
        wires = self._three_d_pixels("sphereWires", {"rings": "4", "slices": "8"})
        self.assertIn((255, 0, 0), wires)
        self.assertLess(wires.count((255, 0, 0)), filled.count((255, 0, 0)))

    def test_three_d_plane_xz_pixels(self):
        self.assertEqual(self._three_d_pixels("plane", camera=TOP), [(255, 0, 0) if 8 <= x < 24 and 12 <= y < 20 else (0, 0, 0)
                                                                  for y in range(32) for x in range(32)])

    def test_three_d_line_and_grid_pixels(self):
        pixels = self._three_d_pixels("line3D")
        self.assertTrue(any(pixels[y*32 + 16] == (255, 0, 0) for y in (15, 16)))
        grid = self._three_d_pixels("grid", camera=TOP)
        self.assertTrue(any(r == g == b and r > 0 for r, g, b in grid))
        self.assertEqual(grid, self._three_d_pixels("grid", {"slices": "5"}, camera=TOP))

    def test_three_d_zero_sizes_still_validate(self):
        for op in SHAPES:
            changes = {"radius": "0"} if op.startswith("sphere") else {"spacing": "0"} if op == "grid" else {"end": SHAPES[op]["start"]} if op == "line3D" else {"width": "0"}
            self.assertEqual(set(self._three_d_pixels(op, changes)), {(0, 0, 0)})
            self.evaluate(f"builtins.raylibValidate [ {scene(command(op, changes | {'typo': '1'}))} ]", error="unknown attribute 'typo'")
        for slices in ("0", "1"):
            self.assertEqual(set(self._three_d_pixels("grid", {"slices": slices})), {(0, 0, 0)})

    def test_three_d_camera_defaults_and_perspective(self):
        explicit = '{ position = { x = 0; y = 0; z = 10; }; target = { x = 0; y = 0; z = 0; }; up = { x = 0; y = 1; z = 0; }; fovy = 45; projection = "perspective"; }'
        default = self._three_d_pixels("cube", camera="{}")
        self.assertEqual(default, self._three_d_pixels("cube", camera=explicit))
        near = self._three_d_pixels("cube", {"position": "{ x = 0; y = 0; z = 3; }"}, camera="{}")
        self.assertGreater(near.count((255, 0, 0)), default.count((255, 0, 0)))

    def test_three_d_orthographic_depth_does_not_change_size(self):
        self.assertEqual(self._three_d_pixels("cube"), self._three_d_pixels("cube", {"position": "{ x = 0; y = 0; z = 3; }"}))

    def test_three_d_depth_test_is_independent_of_draw_order(self):
        near = command("cube", {"width": "2", "height": "2", "position": "{ x = 0; y = 0; z = 2; }"})
        far = command("cube", {"color": BLUE, "position": "{ x = 0; y = 0; z = -2; }"})
        images = [self._capture(f'[ {{ op = "clear"; color = {BLACK}; }} {scene(commands)} ]') for commands in (near + far, far + near)]
        self.assertEqual(*images)
        self.assert_pixel(images[0], 16, 16, (255, 0, 0))
        self.assert_pixel(images[0], 9, 9, (0, 0, 255))

    def test_three_d_default_depth_clear_preserves_color(self):
        near = command("cube", {"width": "2", "height": "2", "position": "{ x = 0; y = 0; z = 2; }"})
        far = command("cube", {"color": BLUE, "position": "{ x = 0; y = 0; z = -2; }"})
        for clear, expected in ((None, (0, 0, 255)), (True, (0, 0, 255)), (False, (255, 0, 0))):
            pixels = self._capture(f'[ {{ op = "clear"; color = {GREEN}; }} {scene(near)} {scene(far, clear_depth=clear)} ]')
            self.assert_pixel(pixels, 16, 16, expected)
            self.assert_pixel(pixels, 0, 0, (0, 255, 0))

    def test_three_d_depth_clear_obeys_clip(self):
        near = command("cube", {"position": "{ x = 0; y = 0; z = 2; }"})
        far = command("cube", {"color": BLUE, "position": "{ x = 0; y = 0; z = -2; }"})
        middle = command("cube", {"color": GREEN})
        pixels = self._capture(f'''[ {{ op = "clear"; color = {BLACK}; }} {scene(near)}
          {{ op = "clip"; x = 16; y = 0; width = 16; height = 32; commands = [ {scene(far)} ]; }}
          {scene(middle, clear_depth=False)} ]''')
        self.assert_pixel(pixels, 12, 16, (255, 0, 0))
        self.assert_pixel(pixels, 20, 16, (0, 255, 0))

    def test_three_d_clear_command_resets_depth_within_pass(self):
        near = command("cube", {"position": "{ x = 0; y = 0; z = 2; }"})
        far = command("cube", {"color": BLUE, "position": "{ x = 0; y = 0; z = -2; }"})
        clear = '{ op = "clear"; color = [0 255 0 255]; }'
        pixels = self._capture(f'[ {{ op = "clear"; color = {BLACK}; }} {scene(near + clear + far)} ]')
        self.assert_pixel(pixels, 16, 16, (0, 0, 255))
        self.assert_pixel(pixels, 0, 0, (0, 255, 0))

    def test_three_d_exit_restores_2d_overlay(self):
        pixels = self._capture(f'''[ {{ op = "clear"; color = {BLACK}; }} {scene(command('cube'))}
          {{ op = "rectangle"; x = 12; y = 12; width = 8; height = 8; color = {BLUE}; }} ]''')
        self.assert_pixel(pixels, 16, 16, (0, 0, 255))
        self.assert_pixel(pixels, 9, 9, (255, 0, 0))

    def test_three_d_suspends_and_restores_parent_camera2d(self):
        pixels = self._capture(f'''[ {{ op = "clear"; color = {BLACK}; }}
          {{ op = "camera2D"; camera = {{ zoom = 2; offset = {{ x = 4; y = 4; }}; }}; commands = [
            {scene(command('cube'))} {{ op = "pixel"; x = 1; y = 1; color = {GREEN}; }}
          ]; }} {{ op = "pixel"; x = 1; y = 1; color = {BLUE}; }} ]''')
        self.assert_pixel(pixels, 16, 16, (255, 0, 0))
        self.assert_pixel(pixels, 6, 6, (0, 255, 0))
        self.assert_pixel(pixels, 1, 1, (0, 0, 255))

    def test_three_d_clipping_and_empty_clip_validation(self):
        pixels = self._capture(f'''[ {{ op = "clear"; color = {BLACK}; }}
          {scene('{ op = "clip"; x = 16; y = 0; width = 16; height = 32; commands = [ ' + command('cube') + ' ]; }')} ]''')
        self.assert_pixel(pixels, 12, 16, (0, 0, 0))
        self.assert_pixel(pixels, 20, 16, (255, 0, 0))
        self.evaluate(f'''builtins.raylibValidate [ {{ op = "clip"; x = 0; y = 0; width = 0; height = 0;
          commands = [ {scene(camera='{ up = { x = 0; y = 0; z = 0; }; }')} ]; }} ]''', error="finite and invertible")

    def test_three_d_render_texture_matches_direct(self):
        direct = self._three_d_pixels("cube")
        painted = self._capture(f'''[ {{ op = "clear"; color = {BLACK}; }}
          {{ op = "paint"; texture = "canvas"; commands = [ {{ op = "clear"; color = {BLACK}; }} {scene(command('cube'))} ]; }}
          {{ op = "texture"; texture = "canvas"; x = 0; y = 0; }} ]''', assets="{ renderTextures.canvas = { width = 32; height = 32; }; }")
        self.assertEqual(direct, painted)

    def test_three_d_render_texture_aspect_and_orientation(self):
        top = command("cube", {"width": "2", "height": "1", "position": "{ x = 0; y = 2; z = 0; }"})
        bottom = command("cube", {"width": "2", "height": "1", "position": "{ x = 0; y = -2; z = 0; }", "color": BLUE})
        pixels = self._capture(f'''[ {{ op = "clear"; color = {BLACK}; }}
          {{ op = "paint"; texture = "canvas"; commands = [ {scene(top + bottom)} ]; }}
          {{ op = "texture"; texture = "canvas"; x = 0; y = 8; }} ]''', assets="{ renderTextures.canvas = { width = 32; height = 16; }; }")
        self.assert_pixel(pixels, 16, 11, (255, 0, 0))
        self.assert_pixel(pixels, 16, 19, (0, 0, 255))
        self.assert_pixel(pixels, 10, 11, (0, 0, 0))

    def test_three_d_repainting_can_clear_or_retain_depth(self):
        for clear, expected in ((True, (0, 0, 255)), (False, (255, 0, 0))):
            drawing = f'''let cube = {command('cube')} // {{ color = if frame.frame == 0 then {RED} else {BLUE};
              position = {{ x = 0; y = 0; z = if frame.frame == 0 then 2 else -2; }}; }};
            in [ {{ op = "clear"; color = {BLACK}; }}
              {{ op = "paint"; texture = "canvas"; clear = false; commands = [
                {{ op = "camera3D"; camera = {ORTHO}; clearDepth = {str(clear).lower()}; commands = [ cube ]; }}
              ]; }} {{ op = "texture"; texture = "canvas"; x = 0; y = 0; }} ]'''
            pixels = self._capture(drawing, assets="{ renderTextures.canvas = { width = 32; height = 32; }; }", frames=2)
            self.assert_pixel(pixels, 16, 16, expected)

    def test_three_d_shader_scopes(self):
        shader = LIB.parent / "examples/shaders/tint.fs"
        assets = f'''{{ shaders.fx = {{ fragment = {shader}; uniforms = {{ gain = {{ type = "float"; value = 0; }};
          tint = {{ type = "vec3"; value = [1 1 1]; }}; }}; }}; }}'''
        child = '{ op = "shader"; shader = "fx"; commands = [ ' + command('cube') + ' ]; }'
        pixels = self._capture(f'''[ {{ op = "clear"; color = [255 255 255 255]; }} {scene(child)}
          {{ op = "pixel"; x = 0; y = 0; color = {GREEN}; }} ]''', assets=assets)
        self.assert_pixel(pixels, 16, 16, (0, 0, 0))
        self.assert_pixel(pixels, 1, 1, (255, 255, 255))
        self.assert_pixel(pixels, 0, 0, (0, 255, 0))

    def test_three_d_blend_scopes(self):
        child = '{ op = "blend"; mode = "additive"; commands = [ ' + command('cube', {'color': '[255 0 0 128]'}) + ' ]; }'
        pixels = self._capture(f'[ {{ op = "clear"; color = {BLUE}; }} {scene(child)} ]')
        self.assert_pixel(pixels, 16, 16, (128, 0, 255), tolerance=1)

    def test_three_d_validates_entire_batch_before_render(self):
        if not self.capture_library:
            self.skipTest("pass --capture-library to enable framebuffer tests")
        capture = self.asset_directory / "invalid-3d.ppm"
        capture.unlink(missing_ok=True)
        self.evaluate(f'''builtins.raylib {{ hidden = true; fps = 0; maxFrames = 1; }} (_: {{ commands = [
          {scene(command('cube') + command('sphere', {'rings': '0'}))} ]; }})''', error="integer in", env={
              "LD_PRELOAD": str(Path(self.capture_library).resolve()) + " " + os.environ.get("LD_PRELOAD", ""),
              "NIXRAY_TEST_CAPTURE": str(capture),
          })
        self.assertFalse(capture.exists())

    def test_three_d_maximum_tessellation_renders(self):
        self.assertIn((255, 0, 0), self._three_d_pixels("sphere", {"rings": "128", "slices": "256"}))

    def test_three_d_example(self):
        example = LIB.parent / "examples/three-d.nix"
        self.assertEqual(self.evaluate(f"import {example} {{ hidden = true; maxFrames = 2; }}"),
                         {"frames": 2, "state": {"x": 6, "z": 8, "orthographic": False}})

    def test_three_d_example_keyboard_input(self):
        example = LIB.parent / "examples/three-d.nix"
        self.assertEqual(self._input_evaluate(f"import {example} {{ hidden = true; maxFrames = 4; }}"),
                         {"frames": 4, "state": {"x": 5.9, "z": 8, "orthographic": False}})
