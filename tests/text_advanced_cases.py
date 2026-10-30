"""Text transforms, signed tracking, Unicode arrays and retained CPU metrics."""

import os
from pathlib import Path


LIB = Path(__file__).resolve().parent.parent / 'lib'
MODES = {'text': ('text', '"AA"'), 'textCodepoint': ('codepoint', '65'), 'textCodepoints': ('codepoints', '[65 65]')}


def command(op='text', changes=None, *, remove=()):
    field, value = MODES[op]
    fields = {field: value, 'font': '"ui"', 'x': '2', 'y': '2', 'size': '12', 'color': '[255 0 0 255]'} | (changes or {})
    return '{ op = "' + op + '"; ' + ' '.join(f'{k} = {v};' for k, v in fields.items() if k not in remove) + ' }'


class TextAdvancedCases:
    def _advanced_text_assets(self):
        return f'{{ fonts.ui = {self.font_path}; }}'

    def _advanced_text_pixels(self, op='text', changes=None, *, background='[0 0 0 255]'):
        return self._capture(f'[ {{ op = "clear"; color = {background}; }} {command(op, changes)} ]', assets=self._advanced_text_assets())

    def test_advanced_text_pure_validation(self):
        commands = ' '.join(command(op, {'spacing': '-2', 'rotation': '30', 'origin': '{ x = 1.5; y = -2; }'}) for op in MODES)
        for flag in ('--pure-eval', '--restrict-eval'):
            self.assertEqual(self.evaluate(f'builtins.raylibValidate [ {commands} ]', flags=[flag], env={'DISPLAY': '', 'WAYLAND_DISPLAY': ''}), 3)

    def test_advanced_text_nix_constructors(self):
        calls = ' '.join(f'(ray.{op} ({command(op)} // {{ op = "ignored"; }}))' for op in MODES)
        self.assertEqual(self.evaluate(f'let ray = import {LIB}; in ray.validate [ {calls} ]'), 3)

    def test_advanced_text_required_and_unknown_fields(self):
        for op, (source, _) in MODES.items():
            for field in (source, 'x', 'y', 'size', 'color'):
                self.evaluate(f'builtins.raylibValidate [ {command(op, remove=(field,))} ]', error=f"missing attribute '{field}'")
            self.evaluate(f'builtins.raylibValidate [ {command(op, {"typo": "1"})} ]', error="unknown attribute 'typo'")
            wrong = 'text' if op != 'text' else 'codepoints'
            self.evaluate(f'builtins.raylibValidate [ {command(op, {wrong: "[]"})} ]', error=f"unknown attribute '{wrong}'")

    def test_advanced_text_codepoint_scalar_validation(self):
        for scalar, error in (('-1', 'integer in'), ('1114112', 'integer in'), ('55296', 'not surrogates'),
                               ('57343', 'not surrogates'), ('65.5', 'expected an integer'), ('true', 'expected an integer')):
            for op, changes in (('textCodepoint', {'codepoint': scalar}), ('textCodepoints', {'codepoints': f'[ ({scalar}) ]'})):
                self.evaluate(f'builtins.raylibValidate [ {command(op, changes)} ]', error=error)
        for scalar in ('0', '9', '10', '65', '1114111'):
            self.assertEqual(self.evaluate(f'builtins.raylibValidate [ {command("textCodepoint", {"codepoint": scalar})} ]'), 1)

    def test_advanced_text_codepoint_array_bounds(self):
        self.evaluate(f'builtins.raylibValidate [ {command("textCodepoints", {"codepoints": "{}"})} ]', error='expected a list')
        self.evaluate(f'builtins.raylibValidate [ {command("textCodepoints", {"codepoints": "builtins.genList (_: 65) 4097"})} ]', error='at most 4096')
        for points in ('[]', '[65 65]', 'builtins.genList (_: 65) 4096'):
            self.assertEqual(self.evaluate(f'builtins.raylibValidate [ {command("textCodepoints", {"codepoints": points})} ]'), 1)

    def test_advanced_text_spacing_rotation_and_origin_validation(self):
        for op in MODES:
            for changes, error in (({'spacing': 'true'}, 'expected'), ({'spacing': '1.0e100'}, 'finite number'),
                                     ({'rotation': '1.0e100'}, 'finite number'), ({'origin': '{}'}, "missing attribute 'x'"),
                                     ({'origin': '{ x = 0; }'}, "missing attribute 'y'"),
                                     ({'origin': '{ x = 0; y = 0; z = 1; }'}, "unknown attribute 'z'"),
                                     ({'origin': '{ x = 3.0e38; y = 3.0e38; }'}, 'transform bounds must remain finite')):
                self.evaluate(f'builtins.raylibValidate [ {command(op, changes)} ]', error=error)
            self.assertEqual(self.evaluate(f'builtins.raylibValidate [ {command(op, {"rotation": "1.0e38"})} ]'), 1)

    def test_advanced_text_defaults_match_existing_text(self):
        self.assertEqual(self._advanced_text_pixels(), self._advanced_text_pixels('textCodepoints'))
        one = self._advanced_text_pixels('text', {'text': '"A"'})
        self.assertEqual(one, self._advanced_text_pixels('textCodepoint'))
        self.assertEqual(one, self._advanced_text_pixels('textCodepoints', {'codepoints': '[65]'}))

    def test_advanced_text_explicit_default_spacing_and_transform_are_noops(self):
        for op in MODES:
            self.assertEqual(self._advanced_text_pixels(op), self._advanced_text_pixels(op, {'spacing': '1', 'rotation': '0', 'origin': '{ x = 0; y = 0; }'}))

    def test_advanced_text_positive_spacing_moves_second_glyph(self):
        for op in ('text', 'textCodepoints'):
            pixels = self._advanced_text_pixels(op, {'spacing': '4'})
            for x in (3, 13, 18, 29):
                self.assert_pixel(pixels, x, 3, (255, 0, 0))
            for x in (14, 15, 16, 17, 30):
                self.assert_pixel(pixels, x, 3, (0, 0, 0))

    def test_advanced_text_negative_spacing_allows_overlap(self):
        pixels = self._advanced_text_pixels('textCodepoints', {'spacing': '-6', 'color': '[255 0 0 128]'}, background='[0 0 255 255]')
        self.assert_pixel(pixels, 4, 4, (128, 0, 127), tolerance=1)
        self.assert_pixel(pixels, 10, 4, (192, 0, 63), tolerance=1)
        self.assert_pixel(pixels, 18, 4, (128, 0, 127), tolerance=1)

    def test_advanced_text_default_font_minimum_size_and_spacing_remain_unchanged(self):
        for op in MODES:
            small = self._capture(f'[ {{ op = "clear"; color = [0 0 0 255]; }} {command(op, {"size": "1"}, remove=("font",))} ]')
            normal = self._capture(f'[ {{ op = "clear"; color = [0 0 0 255]; }} {command(op, {"size": "10", "spacing": "1"}, remove=("font",))} ]')
            self.assertEqual(small, normal)

    def test_advanced_text_custom_fonts_retain_small_sizes(self):
        small = self._advanced_text_pixels('textCodepoint', {'size': '1'})
        self.assert_pixel(small, 2, 2, (255, 0, 0))
        self.assert_pixel(small, 3, 2, (0, 0, 0))

    def test_advanced_text_rotation_and_pixel_pivot(self):
        for op, changes in (('text', {'text': '"A"'}), ('textCodepoint', {}), ('textCodepoints', {'codepoints': '[65]'})):
            pixels = self._advanced_text_pixels(op, changes | {'x': '16', 'y': '16', 'rotation': '90', 'origin': '{ x = 6; y = 6; }'})
            self.assertEqual(pixels, [(255, 0, 0) if 10 <= x < 22 and 10 <= y < 22 else (0, 0, 0) for y in range(32) for x in range(32)])

    def test_advanced_text_rotation_normalizes_and_origin_can_be_outside(self):
        changes = {'text': '"A"', 'x': '16', 'y': '16', 'origin': '{ x = 6; y = 6; }'}
        self.assertEqual(self._advanced_text_pixels('text', changes | {'rotation': '30'}), self._advanced_text_pixels('text', changes | {'rotation': '390'}))
        moved = self._advanced_text_pixels('textCodepoint', {'origin': '{ x = -4; y = -4; }'})
        self.assert_pixel(moved, 6, 6, (255, 0, 0))
        self.assert_pixel(moved, 5, 6, (0, 0, 0))

    def test_advanced_text_unknown_fonts_still_fail_for_empty_arrays(self):
        self.evaluate(f'''builtins.raylib {{ hidden = true; maxFrames = 1; }} (_: {{ commands = [
          {command('textCodepoints', {'font': '"missing"', 'codepoints': '[]'})} ]; }})''', error="unknown font 'missing'")

    def test_advanced_text_empty_arrays_draw_nothing_but_validate(self):
        self.assertEqual(set(self._advanced_text_pixels('textCodepoints', {'codepoints': '[]'})), {(0, 0, 0)})
        self.evaluate(f'builtins.raylibValidate [ {command("textCodepoints", {"codepoints": "[]", "color": "[]"})} ]', error='color must be')

    def test_advanced_text_unicode_array_matches_utf8(self):
        self.assertEqual(self._advanced_text_pixels('text', {'text': '"λ🙂A"'}),
                         self._advanced_text_pixels('textCodepoints', {'codepoints': '[955 128578 65]'}))

    def test_advanced_text_truetype_unicode_array_and_measurement(self):
        path = self._truetype_path()
        assets = f'{{ fonts.ui = {{ path = {path}; size = 24; codepoints = [63 65 955]; }}; }}'
        text = command('text', {'text': '"λA"', 'size': '20', 'spacing': '2.5'})
        points = command('textCodepoints', {'codepoints': '[955 65]', 'size': '20', 'spacing': '2.5'})
        self.assertEqual(self._capture(f'[ {{ op = "clear"; color = [0 0 0 255]; }} {text} ]', assets=assets),
                         self._capture(f'[ {{ op = "clear"; color = [0 0 0 255]; }} {points} ]', assets=assets))
        result = self.evaluate(f'''builtins.raylib {{ hidden = true; fps = 0; maxFrames = 1; assets = {assets}; }}
          (frame: {{ commands = []; state = [ (frame.measureText {{ text = "λA"; font = "ui"; size = 20; spacing = 2.5; }})
            (frame.measureText {{ codepoints = [955 65]; font = "ui"; size = 20; spacing = 2.5; }}) ]; }})''')['state']
        self.assertEqual(result[0], result[1])

    def test_advanced_text_array_newlines_match_utf8(self):
        changes = {'x': '2', 'y': '0', 'size': '8', 'spacing': '2'}
        self.assertEqual(self._advanced_text_pixels('text', changes | {'text': '"A\nAA"'}),
                         self._advanced_text_pixels('textCodepoints', changes | {'codepoints': '[65 10 65 65]'}))

    def test_advanced_text_single_newline_and_tab_are_literal_glyphs(self):
        one = self._advanced_text_pixels('textCodepoint', {'codepoint': '65'})
        for cp in ('9', '10', '32'):
            self.assertEqual(self._advanced_text_pixels('textCodepoint', {'codepoint': cp}), one) # Tiny font falls back to A.
            self.assertEqual(set(self._advanced_text_pixels('textCodepoints', {'codepoints': f'[{cp}]'})), {(0, 0, 0)})

    def test_advanced_text_zero_scalar_is_not_a_string_terminator(self):
        self.assertEqual(self._advanced_text_pixels('textCodepoint', {'codepoint': '0'}), self._advanced_text_pixels('textCodepoint'))
        self.assertEqual(self._advanced_text_pixels('textCodepoints', {'codepoints': '[0 65]'}), self._advanced_text_pixels())

    def test_advanced_text_spacing_measurements(self):
        for source in ('text = "AA";', 'codepoints = [65 65];'):
            for spacing, width in (('0', 24), ('4', 28), ('-6', 18), ('-20', 4), ('-30', 0)):
                self.assertEqual(self._measure_text('{ font = "ui"; size = 12; ' + source + f' spacing = {spacing}; }}'), {'width': width, 'height': 12})

    def test_advanced_text_array_and_literal_measurements(self):
        for source, expected in (('codepoints = [];', {'width': 0, 'height': 0}),
                                  ('codepoints = [65 10 65 65];', {'width': 25, 'height': 26}),
                                  ('codepoints = [10];', {'width': 0, 'height': 26}),
                                  ('codepoint = 10;', {'width': 12, 'height': 12}),
                                  ('codepoint = 0;', {'width': 12, 'height': 12}),
                                  ('codepoints = [0 65];', {'width': 25, 'height': 12})):
            self.assertEqual(self._measure_text('{ font = "ui"; size = 12; ' + source + ' }'), expected)

    def test_advanced_text_measurement_source_is_unambiguous_and_unrotated(self):
        for options, error in (('{ text = "A"; codepoints = [65]; size = 12; }', 'exactly one'),
                                ('{ codepoint = 65; codepoints = [65]; size = 12; }', 'exactly one'),
                                ('{ text = "A"; size = 12; rotation = 90; }', "unknown attribute 'rotation'"),
                                ('{ text = "A"; size = 12; origin = {}; }', "unknown attribute 'origin'"),
                                ('{ text = "A"; size = 12; spacing = 1.0e100; }', 'finite number'),
                                ('{ codepoints = [55296]; size = 12; }', 'not surrogates')):
            self.evaluate(f'builtins.raylib {self.asset_config} (frame: {{ commands = []; state = frame.measureText {options}; }})', error=error)

    def test_advanced_text_measurement_retains_native_logical_not_ink_rules(self):
        # Native MeasureTextEx combines maximum raw advance and maximum glyph count
        # separately, and clamps a negative result rather than reporting an AABB.
        self.assertEqual(self._measure_text('{ font = "ui"; text = "\n"; size = 12; spacing = -20; }'), {'width': 20, 'height': 26})

    def test_advanced_text_measurements_survive_window_close_and_another_window(self):
        result = self.evaluate(f'''let first = builtins.raylib {{ hidden = true; fps = 0; maxFrames = 1;
          assets.fonts.ui = {self.font_path}; }} (frame: {{ commands = []; state = frame.measureText; }});
          second = builtins.seq first (builtins.raylib {{ hidden = true; fps = 0; maxFrames = 1; }} (_: {{ commands = [];
            state = first.state {{ font = "ui"; codepoints = [65 10 65 65]; size = 12; spacing = 4; }}; }}));
          in [ second.state (first.state {{ font = "ui"; codepoint = 10; size = 12; }}) ]''')
        self.assertEqual(result, [{'width': 28, 'height': 26}, {'width': 12, 'height': 12}])

    def test_advanced_text_measurements_survive_gc(self):
        result = self.evaluate(f'''let first = builtins.raylib {{ hidden = true; fps = 0; maxFrames = 1; assets.fonts.ui = {self.font_path}; }}
          (frame: {{ commands = []; state = frame.measureText; }});
          garbage = builtins.foldl' (a: b: a + b) 0 (builtins.genList (n: n) 100000);
          in builtins.seq first (builtins.seq garbage (first.state {{ font = "ui"; codepoints = [65 65]; size = 12; spacing = 4; }}))''',
          env={'GC_INITIAL_HEAP_SIZE': '1048576'})
        self.assertEqual(result, {'width': 28, 'height': 12})

    def test_advanced_text_runtime_layout_overflow_is_rejected(self):
        for op in ('text', 'textCodepoints'):
            self.evaluate(f'''builtins.raylib {{ hidden = true; maxFrames = 1; assets = {self._advanced_text_assets()}; }}
              (_: {{ commands = [ {command(op, {'spacing': '3.0e38'})} ]; }})''', error='text layout must remain finite')
        self.evaluate(f'''builtins.raylib {self.asset_config} (frame: {{ commands = [];
          state = frame.measureText {{ font = "ui"; text = "AA"; size = 12; spacing = 3.0e38; }}; }})''', error='text layout must remain finite')

    def test_advanced_text_large_transformed_text_survives_batch_flushes(self):
        changes = {'text': 'builtins.concatStringsSep "" (builtins.genList (_: "A") 9000)', 'size': '1', 'x': '16', 'y': '0', 'rotation': '90'}
        maximum = self._advanced_text_pixels('text', changes)
        short = self._advanced_text_pixels('text', changes | {'text': '"AAAAAAAAAAAAAAAAAAAA"'})
        self.assertEqual(maximum, short)

    def test_advanced_text_transforms_restore_following_geometry(self):
        pixels = self._capture(f'''[ {{ op = "clear"; color = [0 0 0 255]; }}
          {command('textCodepoint', {'x': '16', 'y': '16', 'rotation': '90', 'origin': '{ x = 6; y = 6; }'})}
          {{ op = "pixel"; x = 0; y = 0; color = [0 255 0 255]; }} ]''', assets=self._advanced_text_assets())
        self.assert_pixel(pixels, 0, 0, (0, 255, 0))
        self.assert_pixel(pixels, 16, 16, (255, 0, 0))

    def test_advanced_text_camera_and_absolute_clip(self):
        pixels = self._capture(f'''[ {{ op = "clear"; color = [0 0 0 255]; }}
          {{ op = "clip"; x = 8; y = 8; width = 16; height = 16; commands = [
            {{ op = "camera2D"; camera = {{ zoom = 1.5; }}; commands = [
              {command('textCodepoint', {'x': '12', 'y': '12', 'rotation': '30', 'origin': '{ x = 6; y = 6; }'})}
            ]; }} ]; }} ]''', assets=self._advanced_text_assets())
        self.assertTrue(any(p != (0, 0, 0) for p in pixels))
        self.assertTrue(all(pixels[y*32 + x] == (0, 0, 0) for y in range(32) for x in range(32) if not (8 <= x < 24 and 8 <= y < 24)))

    def test_advanced_text_render_target_orientation(self):
        for op in MODES:
            changes = {'x': '16', 'y': '16', 'rotation': '90', 'origin': '{ x = 6; y = 6; }'}
            direct = self._advanced_text_pixels(op, changes)
            assets = f'({self._advanced_text_assets()} // {{ renderTextures.canvas = {{ width = 32; height = 32; }}; }})'
            painted = self._capture(f'''[ {{ op = "clear"; color = [0 0 0 255]; }}
              {{ op = "paint"; texture = "canvas"; commands = [ {command(op, changes)} ]; }}
              {{ op = "texture"; texture = "canvas"; x = 0; y = 0; }} ]''', assets=assets)
            self.assertEqual(direct, painted)

    def test_advanced_text_shader_and_alpha_blending(self):
        shader = LIB.parent / 'examples/shaders/tint.fs'
        assets = f'''({self._advanced_text_assets()} // {{ shaders.fx = {{ fragment = {shader}; uniforms = {{
          gain = {{ type = "float"; value = 0.5; }}; tint = {{ type = "vec3"; value = [1 1 1]; }}; }}; }}; }})'''
        for op in MODES:
            pixels = self._capture(f'''[ {{ op = "clear"; color = [0 0 255 255]; }}
              {{ op = "shader"; shader = "fx"; commands = [ {command(op, {'color': '[255 0 0 128]'})} ]; }} ]''', assets=assets)
            self.assert_pixel(pixels, 4, 4, (64, 0, 127), tolerance=1)

    def test_advanced_text_rejects_3d_context(self):
        for op in MODES:
            self.evaluate(f'builtins.raylibValidate [ {{ op = "camera3D"; camera = {{}}; commands = [ {command(op)} ]; }} ]', error='not supported inside camera3D')

    def test_advanced_text_invalid_later_layout_prevents_rendering(self):
        if not self.capture_library:
            self.skipTest('pass --capture-library for framebuffer validation')
        path = self.asset_directory / 'invalid-advanced-text.ppm'
        path.unlink(missing_ok=True)
        self.evaluate(f'''builtins.raylib {{ hidden = true; fps = 0; maxFrames = 1; assets = {self._advanced_text_assets()}; }}
          (_: {{ commands = [ {command()} {command('textCodepoints', {'spacing': '3.0e38'})} ]; }})''', error='text layout must remain finite',
          env={'LD_PRELOAD': str(Path(self.capture_library).resolve()) + ' ' + os.environ.get('LD_PRELOAD', ''), 'NIXRAY_TEST_CAPTURE': str(path)})
        self.assertFalse(path.exists())

    def test_advanced_text_example(self):
        result = self.evaluate(f'import {LIB.parent / "examples/text-layout.nix"} {{ hidden = true; maxFrames = 2; }}')
        self.assertEqual(result['frames'], 2)
        self.assertEqual(result['state']['spacing'], 2)
        self.assertTrue(result['state']['rotate'])
        self.assertEqual(result['state']['metrics']['height'], 32)
        self.assertGreater(result['state']['metrics']['width'], 0)
