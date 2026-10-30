"""Bounded dashes, pro rectangles, thick contours and indexed 2D triangles."""

import os
from pathlib import Path


LIB = Path(__file__).resolve().parent.parent / 'lib'
RED = '[255 0 0 255]'
FIELDS = {
    'lineDashed': {'x1': '4', 'y1': '16', 'x2': '28', 'y2': '16', 'dashSize': '4', 'spaceSize': '2', 'color': RED},
    'rectanglePro': {'x': '4', 'y': '4', 'width': '24', 'height': '16', 'color': RED},
    'rectangleLinesEx': {'x': '4', 'y': '4', 'width': '24', 'height': '16', 'thickness': '3', 'color': RED},
    'rectangleRoundedLinesEx': {'x': '8', 'y': '8', 'width': '16', 'height': '12', 'roundness': '1', 'thickness': '3', 'color': RED},
    'triangleFan': {'points': '[ { x = 4; y = 4; } { x = 4; y = 28; } { x = 28; y = 28; } { x = 28; y = 4; } ]', 'color': RED},
    'triangleStrip': {'points': '[ { x = 4; y = 4; } { x = 4; y = 28; } { x = 28; y = 4; } { x = 28; y = 28; } ]', 'color': RED},
}


def command(op, changes=None, *, remove=()):
    fields = FIELDS[op] | (changes or {})
    return '{ op = "' + op + '"; ' + ' '.join(f'{k} = {v};' for k, v in fields.items() if k not in remove) + ' }'


class DrawingExtraCases:
    def _extra_pixels(self, op, changes=None, *, background='[0 0 0 255]'):
        return self._capture(f'[ {{ op = "clear"; color = {background}; }} {command(op, changes)} ]')

    def test_drawing_extra_pure_validation(self):
        commands = ' '.join(command(op) for op in FIELDS)
        for flag in ('--pure-eval', '--restrict-eval'):
            self.assertEqual(self.evaluate(f'builtins.raylibValidate [ {commands} ]', flags=[flag], env={'DISPLAY': '', 'WAYLAND_DISPLAY': ''}), 6)

    def test_drawing_extra_nix_helpers(self):
        commands = ' '.join(f'(ray.{op} ({command(op)} // {{ op = "ignored"; }}))' for op in FIELDS)
        self.assertEqual(self.evaluate(f'let ray = import {LIB}; in ray.validate [ {commands} ]'), 6)

    def test_drawing_extra_required_and_unknown_fields(self):
        for op, fields in FIELDS.items():
            for field in fields:
                self.evaluate(f'builtins.raylibValidate [ {command(op, remove=(field,))} ]', error=f"missing attribute '{field}'")
            self.evaluate(f'builtins.raylibValidate [ {command(op, {"typo": "1"})} ]', error="unknown attribute 'typo'")
            self.evaluate(f'builtins.raylibValidate [ {command(op, {"color": "[]"})} ]', error='color must be')

    def test_drawing_extra_integer_coordinates_and_sizes(self):
        for op, fields in FIELDS.items():
            for field in fields.keys() & {'x', 'y', 'x1', 'y1', 'x2', 'y2', 'width', 'height'}:
                for value, error in (('0.5', 'expected an integer'), ('2147483648', 'integer in')):
                    self.evaluate(f'builtins.raylibValidate [ {command(op, {field: value})} ]', error=error)
            if 'width' in fields:
                self.evaluate(f'builtins.raylibValidate [ {command(op, {"width": "-1"})} ]', error='integer in')

    def test_drawing_extra_dash_parameter_validation(self):
        for field, value, error in (('dashSize', '0', 'integer in'), ('dashSize', '-1', 'integer in'),
                                     ('dashSize', '1.5', 'expected an integer'), ('spaceSize', '-1', 'integer in'),
                                     ('spaceSize', '1.5', 'expected an integer'), ('spaceSize', '2147483648', 'integer in')):
            self.evaluate(f'builtins.raylibValidate [ {command("lineDashed", {field: value})} ]', error=error)

    def test_drawing_extra_dash_work_limit(self):
        base = {'x1': '0', 'y1': '0', 'y2': '0', 'dashSize': '1', 'spaceSize': '1'}
        self.assertEqual(self.evaluate(f'builtins.raylibValidate [ {command("lineDashed", base | {"x2": "131072"})} ]'), 1)
        self.evaluate(f'builtins.raylibValidate [ {command("lineDashed", base | {"x2": "131073"})} ]', error='65536 dashes')
        self.evaluate(f'builtins.raylibValidate [ {command("lineDashed", base | {"x1": "-2147483648", "x2": "2147483647"})} ]', error='65536 dashes')

    def test_drawing_extra_dash_huge_period_avoids_native_integer_overflow(self):
        cmd = command('lineDashed', {'x1': '-2147483648', 'x2': '2147483647', 'dashSize': '2147483647', 'spaceSize': '2147483647'})
        self.assertEqual(self.evaluate(f'builtins.raylib {{ hidden = true; maxFrames = 1; fps = 0; }} (_: {{ commands = [ {cmd} ]; }})')['frames'], 1)

    def test_drawing_extra_maximum_dash_count_survives_native_batch_flushes(self):
        fields = {'x1': '0', 'x2': '131072', 'dashSize': '1', 'spaceSize': '1'}
        maximum = self._extra_pixels('lineDashed', fields)
        reference = self._extra_pixels('lineDashed', fields | {'x2': '32'})
        self.assertEqual(maximum, reference)

    def test_drawing_extra_dash_pixels_and_truncated_last_dash(self):
        actual = self._extra_pixels('lineDashed', {'x2': '25'})
        lines = ' '.join(f'{{ op = "line"; x1 = {a}; y1 = 16; x2 = {b}; y2 = 16; color = {RED}; }}' for a, b in ((4, 8), (10, 14), (16, 20), (22, 25)))
        expected = self._capture(f'[ {{ op = "clear"; color = [0 0 0 255]; }} {lines} ]')
        self.assertEqual(actual, expected)
        self.assert_pixel(actual, 6, 16, (255, 0, 0))
        self.assert_pixel(actual, 9, 16, (0, 0, 0))

    def test_drawing_extra_vertical_dash_pixels(self):
        actual = self._extra_pixels('lineDashed', {'x1': '16', 'x2': '16', 'y1': '4', 'y2': '25'})
        lines = ' '.join(f'{{ op = "line"; x1 = 16; y1 = {a}; x2 = 16; y2 = {b}; color = {RED}; }}' for a, b in ((4, 8), (10, 14), (16, 20), (22, 25)))
        self.assertEqual(actual, self._capture(f'[ {{ op = "clear"; color = [0 0 0 255]; }} {lines} ]'))

    def test_drawing_extra_diagonal_dash_sampling(self):
        pixels = self._extra_pixels('lineDashed', {'x1': '4', 'y1': '4', 'x2': '20', 'y2': '16', 'dashSize': '3', 'spaceSize': '2'})
        self.assertTrue(any(p != (0, 0, 0) for p in pixels))
        self.assert_pixel(pixels, 5, 5, (255, 0, 0))
        self.assert_pixel(pixels, 7, 6, (0, 0, 0))
        self.assert_pixel(pixels, 20, 16, (0, 0, 0))

    def test_drawing_extra_short_dashes_and_zero_gap_are_solid(self):
        for changes in ({'x2': '9', 'dashSize': '2', 'spaceSize': '4'}, {'spaceSize': '0'}):
            fields = FIELDS['lineDashed'] | changes
            reference = '{ op = "line"; ' + ' '.join(f'{k} = {v};' for k, v in fields.items() if k not in ('dashSize', 'spaceSize')) + ' }'
            self.assertEqual(self._extra_pixels('lineDashed', changes),
                             self._capture(f'[ {{ op = "clear"; color = [0 0 0 255]; }} {reference} ]'))

    def test_drawing_extra_dash_pattern_direction_and_period_boundary(self):
        forward = self._extra_pixels('lineDashed', {'x2': '10'}) # Length equals period, not short fallback.
        self.assert_pixel(forward, 6, 16, (255, 0, 0))
        self.assert_pixel(forward, 9, 16, (0, 0, 0))
        reverse = self._extra_pixels('lineDashed', {'x1': '10', 'x2': '4'})
        self.assert_pixel(reverse, 9, 16, (255, 0, 0))
        self.assert_pixel(reverse, 4, 16, (0, 0, 0))

    def test_drawing_extra_rectangle_pro_defaults_and_rotation(self):
        default = self._extra_pixels('rectanglePro')
        plain = self._capture(f'[ {{ op = "clear"; color = [0 0 0 255]; }} {{ op = "rectangle"; x = 4; y = 4; width = 24; height = 16; color = {RED}; }} ]')
        self.assertEqual(default, plain)
        changes = {'x': '16', 'y': '16', 'width': '12', 'height': '8', 'origin': '{ x = 6; y = 4; }', 'rotation': '90'}
        rotated = self._extra_pixels('rectanglePro', changes)
        self.assertEqual(rotated, [(255, 0, 0) if 12 <= x < 20 and 10 <= y < 22 else (0, 0, 0) for y in range(32) for x in range(32)])

    def test_drawing_extra_rectangle_pro_rotation_normalization(self):
        expected = self._extra_pixels('rectanglePro', {'rotation': '30'})
        self.assertEqual(expected, self._extra_pixels('rectanglePro', {'rotation': '390'}))
        self.assertEqual(self.evaluate(f'builtins.raylibValidate [ {command("rectanglePro", {"rotation": "1.0e38"})} ]'), 1)

    def test_drawing_extra_rectangle_pro_origin_and_bounds(self):
        for origin, error in (('{}', "missing attribute 'x'"), ('{ x = 1; }', "missing attribute 'y'"),
                               ('{ x = 0; y = 0; z = 0; }', "unknown attribute 'z'"),
                               ('{ x = 3.0e38; y = 3.0e38; }', 'bounds must remain finite')):
            self.evaluate(f'builtins.raylibValidate [ {command("rectanglePro", {"origin": origin})} ]', error=error)
        self.evaluate(f'builtins.raylibValidate [ {command("rectanglePro", {"rotation": "1.0e100"})} ]', error='finite number')
        shifted = self._extra_pixels('rectanglePro', {'origin': '{ x = -4; y = -4; }'})
        self.assert_pixel(shifted, 8, 8, (255, 0, 0))
        self.assert_pixel(shifted, 7, 8, (0, 0, 0))

    def test_drawing_extra_rectangle_pro_large_compensating_pivot(self):
        reference = self._extra_pixels('rectanglePro', {'x': '0', 'y': '0'})
        actual = self._extra_pixels('rectanglePro', {'x': '1073741824', 'y': '1073741824', 'origin': '{ x = 1073741824; y = 1073741824; }'})
        self.assertEqual(reference, actual)

    def test_drawing_extra_thick_rectangle_stays_inside(self):
        pixels = self._extra_pixels('rectangleLinesEx')
        expected = [(255, 0, 0) if 4 <= x < 28 and 4 <= y < 20 and not (7 <= x < 25 and 7 <= y < 17) else (0, 0, 0)
                    for y in range(32) for x in range(32)]
        self.assertEqual(pixels, expected)

    def test_drawing_extra_consumed_rectangle_interior_fills_once(self):
        plain = self._capture('[ { op = "clear"; color = [0 0 255 255]; } { op = "rectangle"; x = 4; y = 4; width = 24; height = 16; color = [255 0 0 128]; } ]')
        for thickness in ('8', '9', '16', '1.0e38'):
            self.assertEqual(self._extra_pixels('rectangleLinesEx', {'thickness': thickness, 'color': '[255 0 0 128]'}, background='[0 0 255 255]'), plain)

    def test_drawing_extra_fractional_rectangle_stroke_does_not_overlap(self):
        pixels = self._extra_pixels('rectangleLinesEx', {'thickness': '1.5', 'color': '[255 0 0 128]'}, background='[0 0 255 255]')
        self.assertTrue(any(p[0] > 0 for p in pixels))
        self.assertTrue(all(p == (0, 0, 255) or (abs(p[0] - 128) <= 1 and p[1] == 0 and abs(p[2] - 127) <= 1) for p in pixels))

    def test_drawing_extra_outline_parameter_validation(self):
        for op in ('rectangleLinesEx', 'rectangleRoundedLinesEx'):
            for thickness in ('-0.1', '1.0e100'):
                self.evaluate(f'builtins.raylibValidate [ {command(op, {"thickness": thickness})} ]', error='finite number')
        for field, value, error in (('roundness', '1.000000001', 'finite number'), ('segments', '3', '0 (automatic)'),
                                    ('segments', '4097', 'integer in'), ('segments', '4.5', 'expected an integer'),
                                    ('thickness', '2.0e38', 'outline bounds must remain finite')):
            self.evaluate(f'builtins.raylibValidate [ {command("rectangleRoundedLinesEx", {field: value})} ]', error=error)

    def test_drawing_extra_rounded_stroke_is_outward(self):
        pixels = self._extra_pixels('rectangleRoundedLinesEx', {'segments': '32'})
        for x, y in ((16, 6), (6, 14), (16, 21)):
            self.assert_pixel(pixels, x, y, (255, 0, 0))
        for x, y in ((16, 14), (4, 4), (28, 14)):
            self.assert_pixel(pixels, x, y, (0, 0, 0))

    def test_drawing_extra_unrounded_outward_stroke(self):
        pixels = self._extra_pixels('rectangleRoundedLinesEx', {'roundness': '0'})
        self.assertEqual(pixels, [(255, 0, 0) if 5 <= x < 27 and 5 <= y < 23 and not (8 <= x < 24 and 8 <= y < 20) else (0, 0, 0)
                                  for y in range(32) for x in range(32)])

    def test_drawing_extra_unit_rounded_stroke_matches_existing_outline(self):
        fields = 'x = 8; y = 8; width = 16; height = 12; roundness = 1; segments = 8; color = [255 0 0 255];'
        old = self._capture('[ { op = "clear"; color = [0 0 0 255]; } { op = "rectangleRoundedLines"; ' + fields + ' } ]')
        self.assertEqual(old, self._extra_pixels('rectangleRoundedLinesEx', {'thickness': '1', 'segments': '8'}))

    def test_drawing_extra_rounded_sampling_is_bounded(self):
        for segments in ('0', '4', '4096'):
            self.assertIn((255, 0, 0), self._extra_pixels('rectangleRoundedLinesEx', {'segments': segments}))
        for roundness in ('0', '1.0e-40', '1'):
            self.assertEqual(self.evaluate(f'builtins.raylibValidate [ {command("rectangleRoundedLinesEx", {"roundness": roundness, "thickness": "1.0e38"})} ]'), 1)

    def test_drawing_extra_fan_and_strip_point_schema(self):
        for op in ('triangleFan', 'triangleStrip'):
            for points, error in (('{}', 'expected a list'), ('[]', 'between 3 and 4096'),
                                   ('[{} {}]', 'between 3 and 4096'), ('[{} {} {}]', "missing attribute 'x'"),
                                   ('[ { x = 0; y = 0.5; } {} {} ]', 'expected an integer'),
                                   ('[ { x = 2147483648; y = 0; } {} {} ]', 'integer in'),
                                   ('[ { x = 0; y = 0; z = 0; } {} {} ]', "unknown attribute 'z'"),
                                   ('builtins.genList (_: { x = 0; y = 0; }) 4097', 'between 3 and 4096')):
                self.evaluate(f'builtins.raylibValidate [ {command(op, {"points": points})} ]', error=error)
            self.assertEqual(self.evaluate(f'builtins.raylibValidate [ {command(op, {"points": "builtins.genList (_: { x = 0; y = 0; }) 4096"})} ]'), 1)

    def test_drawing_extra_fan_and_strip_fill_same_quad(self):
        expected = [(255, 0, 0) if 4 <= x < 28 and 4 <= y < 28 else (0, 0, 0) for y in range(32) for x in range(32)]
        for op in ('triangleFan', 'triangleStrip'):
            self.assertEqual(self._extra_pixels(op), expected)

    def test_drawing_extra_fan_and_strip_winding_is_normalized(self):
        for op in ('triangleFan', 'triangleStrip'):
            reversed_points = "builtins.foldl' (xs: x: [x] ++ xs) [] " + FIELDS[op]['points']
            self.assertEqual(self._extra_pixels(op), self._extra_pixels(op, {'points': reversed_points}))

    def test_drawing_extra_fan_does_not_implicitly_close_rim(self):
        points = '[ { x = 16; y = 16; } { x = 4; y = 4; } { x = 4; y = 28; } { x = 28; y = 28; } { x = 28; y = 4; } ]'
        open_fan = self._extra_pixels('triangleFan', {'points': points})
        self.assert_pixel(open_fan, 16, 6, (0, 0, 0))
        self.assert_pixel(open_fan, 6, 16, (255, 0, 0))
        closed = self._extra_pixels('triangleFan', {'points': '(' + points + ' ++ [ { x = 4; y = 4; } ])'})
        self.assert_pixel(closed, 16, 6, (255, 0, 0))

    def test_drawing_extra_fan_strip_shared_edges_blend_once(self):
        for op in ('triangleFan', 'triangleStrip'):
            pixels = self._extra_pixels(op, {'color': '[255 0 0 128]'}, background='[0 0 255 255]')
            for x, y in ((8, 8), (16, 16), (20, 20), (8, 24), (24, 8)):
                self.assert_pixel(pixels, x, y, (128, 0, 127), tolerance=1)

    def test_drawing_extra_explicit_overlapping_triangles_are_not_deduplicated(self):
        points = '[ { x = 4; y = 4; } { x = 4; y = 28; } { x = 28; y = 4; } { x = 4; y = 28; } ]'
        pixels = self._extra_pixels('triangleFan', {'points': points, 'color': '[255 0 0 128]'}, background='[0 0 255 255]')
        self.assert_pixel(pixels, 10, 10, (192, 0, 63), tolerance=1)

    def test_drawing_extra_degenerate_geometry_draws_nothing(self):
        for op in FIELDS:
            changes = {'x2': '4'} if op == 'lineDashed' else {'width': '0'} if op.startswith('rectangle') else {'points': '[ { x = 4; y = 4; } { x = 8; y = 8; } { x = 12; y = 12; } ]'}
            self.assertEqual(set(self._extra_pixels(op, changes)), {(0, 0, 0)})
            self.evaluate(f'builtins.raylibValidate [ {command(op, changes | {"color": "[]"})} ]', error='color must be')
        for op in ('rectangleLinesEx', 'rectangleRoundedLinesEx'):
            self.assertEqual(set(self._extra_pixels(op, {'thickness': '0'})), {(0, 0, 0)})

    def test_drawing_extra_clips_and_camera(self):
        commands = ' '.join(command(op) for op in FIELDS)
        pixels = self._capture(f'''[ {{ op = "clear"; color = [0 0 0 255]; }}
          {{ op = "clip"; x = 8; y = 8; width = 16; height = 16; commands = [
            {{ op = "camera2D"; camera = {{ zoom = 1.25; }}; commands = [ {commands} ]; }}
          ]; }} ]''')
        self.assertTrue(any(p != (0, 0, 0) for p in pixels))
        self.assertTrue(all(pixels[y*32 + x] == (0, 0, 0) for y in range(32) for x in range(32) if not (8 <= x < 24 and 8 <= y < 24)))

    def test_drawing_extra_camera_scales_dash_and_gap_lengths(self):
        dashed = command('lineDashed', {'y1': '8', 'y2': '8'})
        actual = self._capture(f'[ {{ op = "clear"; color = [0 0 0 255]; }} {{ op = "camera2D"; camera = {{ zoom = 2; offset = {{ x = 2; y = 2; }}; }}; commands = [ {dashed} ]; }} ]')
        lines = ' '.join(f'{{ op = "line"; x1 = {2 + 2*a}; y1 = 18; x2 = {2 + 2*b}; y2 = 18; color = {RED}; }}' for a, b in ((4, 8), (10, 14), (16, 20), (22, 26)))
        expected = self._capture(f'[ {{ op = "clear"; color = [0 0 0 255]; }} {lines} ]')
        self.assertEqual(actual, expected)

    def test_drawing_extra_render_texture_matches_window(self):
        commands = ' '.join(command(op) for op in FIELDS)
        direct = self._capture(f'[ {{ op = "clear"; color = [0 0 0 255]; }} {commands} ]')
        painted = self._capture(f'''[ {{ op = "clear"; color = [0 0 0 255]; }}
          {{ op = "paint"; texture = "canvas"; commands = [ {{ op = "clear"; color = [0 0 0 255]; }} {commands} ]; }}
          {{ op = "texture"; texture = "canvas"; x = 0; y = 0; }} ]''', assets='{ renderTextures.canvas = { width = 32; height = 32; }; }')
        self.assertEqual(direct, painted)

    def test_drawing_extra_shader_and_additive_blending(self):
        shader = LIB.parent / 'examples/shaders/tint.fs'
        assets = f'{{ shaders.fx = {{ fragment = {shader}; uniforms = {{ gain = {{ type = "float"; value = 0; }}; tint = {{ type = "vec3"; value = [1 1 1]; }}; }}; }}; }}'
        for op in FIELDS:
            shaded = self._capture(f'[ {{ op = "clear"; color = [255 255 255 255]; }} {{ op = "shader"; shader = "fx"; commands = [ {command(op)} ]; }} ]', assets=assets)
            self.assertIn((0, 0, 0), shaded)
            self.assertTrue(set(shaded) <= {(0, 0, 0), (255, 255, 255)})
            additive = self._capture(f'[ {{ op = "clear"; color = [0 0 255 255]; }} {{ op = "blend"; mode = "additive"; commands = [ {command(op, {"color": "[255 0 0 128]"})} ]; }} ]')
            self.assertTrue(any(p[0] > 0 for p in additive))
            self.assertTrue(all(p[1] == 0 and p[2] == 255 for p in additive))

    def test_drawing_extra_rejects_3d_context(self):
        for op in FIELDS:
            self.evaluate(f'builtins.raylibValidate [ {{ op = "camera3D"; camera = {{}}; commands = [ {command(op)} ]; }} ]', error='not supported inside camera3D')

    def test_drawing_extra_invalid_later_command_prevents_drawing(self):
        if not self.capture_library:
            self.skipTest('pass --capture-library for framebuffer validation')
        path = self.asset_directory / 'invalid-drawing-extra.ppm'
        path.unlink(missing_ok=True)
        self.evaluate(f'''builtins.raylib {{ hidden = true; maxFrames = 1; fps = 0; }} (_: {{ commands = [
          {command('rectanglePro')} {command('lineDashed', {'dashSize': '0'})}
        ]; }})''', error='integer in', env={'LD_PRELOAD': str(Path(self.capture_library).resolve()) + ' ' + os.environ.get('LD_PRELOAD', ''), 'NIXRAY_TEST_CAPTURE': str(path)})
        self.assertFalse(path.exists())

    def test_drawing_extra_example(self):
        self.assertEqual(self.evaluate(f'import {LIB.parent / "examples/drawing-extra.nix"} {{ hidden = true; maxFrames = 2; }}'),
                         {'frames': 2, 'state': {'thickness': 4, 'reverse': False}})
