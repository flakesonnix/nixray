"""Camera-derived textured 3D quads, crops, lighting and finite preparation."""

from three_d_cases import scene, ORTHO, TOP, LIB, BLACK, BLUE, ORIGIN
from lighting_cases import lighting, material
from texture_advanced_cases import cpu, upload


FIELDS = dict(texture='"sprite"', position=ORIGIN, height='4')
COLORS = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0)]
SAMPLES = [(10, 10), (20, 10), (10, 20), (20, 20)]


def billboard(changes=None, *, remove=()):
    return '{ op = "billboard"; ' + ' '.join(f'{k} = {v};' for k, v in (FIELDS | (changes or {})).items() if k not in remove) + ' }'


class BillboardCases:
    def _billboard_assets(self):
        return f'{{ textures.sprite = {self.pattern_path}; }}'

    def _billboard_pixels(self, changes=None, *, camera=ORTHO, assets=None, background=BLACK, lit=False):
        draw = billboard(changes)
        if lit:
            draw = lighting(material(draw))
        return self._capture(f'[ {{ op = "clear"; color = {background}; }} {scene(draw, camera=camera)} ]', assets=assets or self._billboard_assets())

    def _assert_billboard_pattern(self, pixels, colors=COLORS):
        for (x, y), color in zip(SAMPLES, colors):
            self.assert_pixel(pixels, x, y, color)

    def test_billboard_pure_and_restricted_validation(self):
        draw = scene(lighting(material(billboard({'source': '{ x = 2; y = 4; width = 16; height = 8; }', 'rotation': '30', 'flipX': 'true'}))))
        for flag in ('--pure-eval', '--restrict-eval'):
            self.assertEqual(self.evaluate(f'builtins.raylibValidate [ {draw} ]', flags=[flag], env={'DISPLAY': '', 'WAYLAND_DISPLAY': ''}), 1)

    def test_billboard_nix_constructor(self):
        draw = f'(ray.billboard ({billboard()} // {{ op = "ignored"; }}))'
        self.assertEqual(self.evaluate(f'let ray = import {LIB}; in ray.validate [ {scene(draw)} ]'), 1)

    def test_billboard_requires_camera(self):
        self.evaluate(f'builtins.raylibValidate [ {billboard()} ]', error='requires a camera3D scope')

    def test_billboard_required_and_unknown_fields(self):
        for field in FIELDS:
            self.evaluate(f'builtins.raylibValidate [ {scene(billboard(remove=(field,)))} ]', error=f"missing attribute '{field}'")
        for field in ('scale', 'size', 'camera', 'color', 'typo'):
            self.evaluate(f'builtins.raylibValidate [ {scene(billboard({field: "1"}))} ]', error=f"unknown attribute '{field}'")

    def test_billboard_texture_name_validation(self):
        for texture, error in (('""', 'texture name must not be empty'), ('1', 'expected a string')):
            self.evaluate(f'builtins.raylibValidate [ {scene(billboard({"texture": texture}))} ]', error=error)
        self.evaluate(f'builtins.raylib {{ hidden = true; maxFrames = 1; }} (_: {{ commands = [ {scene(billboard())} ]; }})', error="unknown texture 'sprite'")

    def test_billboard_position_up_and_origin_schemas(self):
        for field in ('position', 'up', 'origin'):
            for value, error in (('[]', 'expected a set'), ('{}', "missing attribute 'x'"),
                                  ('{ x = 0; }', "missing attribute 'y'"),
                                  ('{ x = 1.0e100; y = 0; z = 0; }' if field != 'origin' else '{ x = 1.0e100; y = 0; }', 'finite number')):
                self.evaluate(f'builtins.raylibValidate [ {scene(billboard({field: value}))} ]', error=error)
        self.evaluate(f'builtins.raylibValidate [ {scene(billboard({"up": "{ x = 0; y = 1; }"}))} ]', error="missing attribute 'z'")
        self.evaluate(f'builtins.raylibValidate [ {scene(billboard({"origin": "{ x = 0; y = 0; z = 0; }"}))} ]', error="unknown attribute 'z'")

    def test_billboard_numeric_sizes_and_rotation(self):
        for field in ('height', 'width'):
            for value, error in (('-1', 'finite number'), ('1.0e100', 'finite number'), ('true', 'expected')):
                self.evaluate(f'builtins.raylibValidate [ {scene(billboard({field: value}))} ]', error=error)
        self.evaluate(f'builtins.raylibValidate [ {scene(billboard({"rotation": "1.0e100"}))} ]', error='finite number')
        self.assertEqual(self.evaluate(f'builtins.raylibValidate [ {scene(billboard({"width": "2.5", "height": "1.25", "rotation": "1.0e38"}))} ]'), 1)

    def test_billboard_flip_and_tint_validation(self):
        for field in ('flipX', 'flipY'):
            self.evaluate(f'builtins.raylibValidate [ {scene(billboard({field: "1"}))} ]', error='expected a Boolean')
        for tint in ('[]', '[255 255 255 256]'):
            self.evaluate(f'builtins.raylibValidate [ {scene(billboard({"tint": tint}))} ]', error='color must be' if tint == '[]' else 'integer in')

    def test_billboard_source_schema_and_limits(self):
        for source, error in (('{}', "missing attribute 'x'"), ('{ x = 0; y = 0; width = 0; height = 1; }', 'integer in'),
                               ('{ x = -1; y = 0; width = 1; height = 1; }', 'integer in'),
                               ('{ x = 0.5; y = 0; width = 1; height = 1; }', 'expected an integer'),
                               ('{ x = 0; y = 0; width = 1; height = 1; typo = 1; }', "unknown attribute 'typo'")):
            self.evaluate(f'builtins.raylibValidate [ {scene(billboard({"source": source}))} ]', error=error)

    def test_billboard_source_bounds_resolve_at_runtime(self):
        for source in ('{ x = 1; y = 0; width = 2; height = 2; }',
                       '{ x = 2147483647; y = 2147483647; width = 2147483647; height = 2147483647; }'):
            draw = scene(billboard({'source': source, 'flipX': 'true', 'flipY': 'true'}))
            self.assertEqual(self.evaluate(f'builtins.raylibValidate [ {draw} ]'), 1)
            self.evaluate(f'builtins.raylib {{ hidden = true; maxFrames = 1; assets = {self._billboard_assets()}; }} (_: {{ commands = [ {draw} ]; }})', error='source rectangle exceeds')

    def test_billboard_up_must_be_nonzero_and_not_parallel_to_right(self):
        for up, error in ((ORIGIN, 'up must be nonzero'), ('{ x = 1; y = 0; z = 0; }', 'basis must be'),
                           ('{ x = 1; y = 1.0e-30; z = 0; }', 'basis must be')):
            self.evaluate(f'builtins.raylibValidate [ {scene(billboard({"up": up}))} ]', error=error)

    def test_billboard_up_normalizes_extreme_magnitudes(self):
        expected = self._billboard_pixels()
        for y in ('2', '3.0e38', '1.0e-40'):
            self.assertEqual(expected, self._billboard_pixels({'up': f'{{ x = 0; y = {y}; z = 0; }}'}))

    def test_billboard_aspect_overflow_checks_pure_and_loaded_sources(self):
        draw = scene(billboard({'height': '3.0e38', 'source': '{ x = 0; y = 0; width = 2; height = 1; }'}))
        self.evaluate(f'builtins.raylibValidate [ {draw} ]', error='aspect-derived width')
        assets = f'{{ textures.sprite.image = {cpu(width=2, height=1)}; }}'
        self.evaluate(f'builtins.raylib {{ hidden = true; maxFrames = 1; assets = {assets}; }} (_: {{ commands = [ {scene(billboard({"height": "3.0e38"}))} ]; }})', error='aspect-derived width')

    def test_billboard_geometry_overflow_is_rejected_purely(self):
        for changes in ({'width': '3.0e38', 'origin': '{ x = -3.0e38; y = 0; }'},
                         {'width': '3.0e38', 'position': '{ x = 3.0e38; y = 0; z = 0; }'},
                         {'width': '3.0e38', 'height': '3.0e38', 'rotation': '45', 'origin': '{ x = 0; y = 0; }'}):
            self.evaluate(f'builtins.raylibValidate [ {scene(billboard(changes))} ]', error='geometry must remain finite')
        # A long diagonal is not itself an error when every prepared coordinate fits.
        self.assertEqual(self.evaluate(f'builtins.raylibValidate [ {scene(billboard({"width": "3.0e38", "height": "3.0e38", "rotation": "45"}))} ]'), 1)

    def test_billboard_default_center_and_orientation(self):
        pixels = self._billboard_pixels()
        self._assert_billboard_pattern(pixels)
        for x, y in ((7, 16), (24, 16), (16, 7), (16, 24)):
            self.assert_pixel(pixels, x, y, (0, 0, 0))
        self.assertEqual(pixels, self._billboard_pixels({'width': '4', 'origin': '{ x = 2; y = 2; }', 'rotation': '0', 'up': '{ x = 0; y = 1; z = 0; }'}))

    def test_billboard_width_defaults_to_source_aspect(self):
        pixels = self._billboard_pixels({'source': '{ x = 1; y = 0; width = 1; height = 2; }'})
        self.assert_pixel(pixels, 13, 10, (0, 255, 0))
        self.assert_pixel(pixels, 18, 20, (255, 255, 0))
        self.assert_pixel(pixels, 11, 10, (0, 0, 0))
        self.assert_pixel(pixels, 20, 10, (0, 0, 0))

    def test_billboard_full_image_aspect_and_explicit_nonuniform_width(self):
        assets = f'{{ textures.sprite.image = {cpu(width=4, height=2)}; }}'
        pixels = self._billboard_pixels({'height': '2'}, assets=assets)
        self.assert_pixel(pixels, 9, 13, (255, 0, 0))
        self.assert_pixel(pixels, 8, 11, (0, 0, 0))
        wide = self._billboard_pixels({'height': '2', 'width': '6'}, assets=assets)
        self.assert_pixel(wide, 5, 13, (255, 0, 0))

    def test_billboard_crop_matches_uncropped_image(self):
        pixels = self._billboard_pixels({'source': '{ x = 1; y = 1; width = 2; height = 2; }'}, assets=f'{{ textures.sprite = {self.atlas_path}; }}')
        self.assertEqual(pixels, self._billboard_pixels())

    def test_billboard_flips_only_uvs(self):
        for changes, colors in (({'flipX': 'true'}, [COLORS[1], COLORS[0], COLORS[3], COLORS[2]]),
                                 ({'flipY': 'true'}, [COLORS[2], COLORS[3], COLORS[0], COLORS[1]]),
                                 ({'flipX': 'true', 'flipY': 'true'}, list(reversed(COLORS)))):
            self._assert_billboard_pattern(self._billboard_pixels(changes), colors)

    def test_billboard_right_handed_rotation_and_normalization(self):
        pixels = self._billboard_pixels({'rotation': '90'})
        self._assert_billboard_pattern(pixels, [COLORS[1], COLORS[3], COLORS[0], COLORS[2]])
        self.assertEqual(pixels, self._billboard_pixels({'rotation': '450'}))
        self.assertEqual(self._billboard_pixels({'rotation': '30'}), self._billboard_pixels({'rotation': '-330'}))

    def test_billboard_origin_is_world_units_from_bottom_left(self):
        pixels = self._billboard_pixels({'origin': '{ x = 0; y = 0; }'})
        self.assert_pixel(pixels, 18, 2, (255, 0, 0))
        self.assert_pixel(pixels, 28, 2, (0, 255, 0))
        self.assert_pixel(pixels, 18, 12, (0, 0, 255))
        self.assert_pixel(pixels, 15, 2, (0, 0, 0))
        self.assert_pixel(pixels, 18, 16, (0, 0, 0))

    def test_billboard_outside_pivots_are_allowed(self):
        pixels = self._billboard_pixels({'origin': '{ x = -1; y = -1; }'})
        self.assert_pixel(pixels, 21, 2, (255, 0, 0))
        self.assert_pixel(pixels, 19, 2, (0, 0, 0))
        self.assert_pixel(pixels, 21, 12, (0, 0, 0))

    def test_billboard_uses_enclosing_camera_view_right(self):
        side = '{ position = { x = 10; y = 0; z = 0; }; projection = "orthographic"; fovy = 8; }'
        self.assertEqual(self._billboard_pixels(), self._billboard_pixels(camera=side))

    def test_billboard_camera_basis_updates_between_frames(self):
        camera = 'if frame.frame == 0 then ' + ORTHO + ' else { position = { x = 10; y = 0; z = 0; }; projection = "orthographic"; fovy = 8; }'
        pixels = self._capture(f'[ {{ op = "clear"; color = {BLACK}; }} {scene(billboard(), camera=camera)} ]', assets=self._billboard_assets(), frames=2)
        self.assertEqual(pixels, self._billboard_pixels())

    def test_billboard_default_up_is_world_y_not_screen_up(self):
        pitch = '{ position = { x = 0; y = 6; z = 8; }; projection = "orthographic"; fovy = 8; }'
        front, tilted = self._billboard_pixels(), self._billboard_pixels(camera=pitch)
        self.assertLess(sum(p != (0, 0, 0) for p in tilted), sum(p != (0, 0, 0) for p in front))
        self.assertEqual(set(self._billboard_pixels(camera=TOP)), {(0, 0, 0)})

    def test_billboard_camera_roll_can_require_custom_up(self):
        rolled = '{ up = { x = 1; y = 0; z = 0; }; projection = "orthographic"; fovy = 8; }'
        self.evaluate(f'builtins.raylibValidate [ {scene(billboard(), camera=rolled)} ]', error='basis must be')
        self.assertEqual(self._billboard_pixels(), self._billboard_pixels({'up': '{ x = 1; y = 0; z = 0; }'}, camera=rolled))

    def test_billboard_skewed_up_is_preserved_and_reversed_up_can_cull(self):
        self.assertNotEqual(self._billboard_pixels(), self._billboard_pixels({'up': '{ x = 1; y = 1; z = 0; }'}))
        self.assertEqual(set(self._billboard_pixels({'up': '{ x = 0; y = -1; z = 0; }'})), {(0, 0, 0)})

    def test_billboard_render_texture_logical_orientation_and_flips(self):
        assets = f'({self._billboard_assets()} // {{ renderTextures.canvas = {{ width = 2; height = 2; }}; }})'
        paint = '{ op = "paint"; texture = "canvas"; commands = [ { op = "texture"; texture = "sprite"; x = 0; y = 0; } ]; }'
        for changes in ({}, {'flipX': 'true'}, {'flipY': 'true'}, {'flipX': 'true', 'flipY': 'true'}):
            draw = scene(billboard(changes | {'texture': '"canvas"'}))
            pixels = self._capture(f'[ {{ op = "clear"; color = {BLACK}; }} {paint} {draw} ]', assets=assets)
            self.assertEqual(pixels, self._billboard_pixels(changes))

    def test_billboard_render_texture_crop_and_rotation(self):
        assets = f'{{ textures.sprite = {self.atlas_path}; renderTextures.canvas = {{ width = 4; height = 4; }}; }}'
        paint = '{ op = "paint"; texture = "canvas"; commands = [ { op = "texture"; texture = "sprite"; x = 0; y = 0; } ]; }'
        changes = {'source': '{ x = 1; y = 1; width = 2; height = 2; }', 'flipY': 'true', 'rotation': '30'}
        draw = scene(billboard(changes | {'texture': '"canvas"'}))
        pixels = self._capture(f'[ {{ op = "clear"; color = {BLACK}; }} {paint} {draw} ]', assets=assets)
        self.assertEqual(pixels, self._billboard_pixels(changes, assets=f'{{ textures.sprite = {self.atlas_path}; }}'))

    def test_billboard_cannot_read_own_paint_even_with_zero_size(self):
        for height in ('0', '4'):
            draw = '{ op = "paint"; texture = "sprite"; commands = [ ' + scene(billboard({'height': height})) + ' ]; }'
            self.evaluate(f'builtins.raylibValidate [ {draw} ]', error='into its own paint')

    def test_billboard_can_render_into_another_target(self):
        assets = f'({self._billboard_assets()} // {{ renderTextures.canvas = {{ width = 32; height = 32; }}; }})'
        pixels = self._capture(f'''[ {{ op = "clear"; color = {BLACK}; }}
          {{ op = "paint"; texture = "canvas"; commands = [ {scene(billboard())} ]; }}
          {{ op = "texture"; texture = "canvas"; x = 0; y = 0; }} ]''', assets=assets)
        self.assertEqual(pixels, self._billboard_pixels())

    def test_billboard_lit_render_target_matches_window(self):
        assets = f'({self._billboard_assets()} // {{ renderTextures.canvas = {{ width = 32; height = 32; }}; }})'
        draw = scene(lighting(material(billboard())))
        pixels = self._capture(f'''[ {{ op = "clear"; color = {BLACK}; }}
          {{ op = "paint"; texture = "canvas"; commands = [ {draw} ]; }}
          {{ op = "texture"; texture = "canvas"; x = 0; y = 0; }} ]''', assets=assets)
        self.assertEqual(pixels, self._billboard_pixels(lit=True))

    def test_billboard_repeating_crops_honor_asset_wrap(self):
        assets = f'{{ textures.sprite = {{ path = {self.pattern_path}; wrap = "repeat"; }}; }}'
        pixels = self._billboard_pixels({'source': '{ x = 0; y = 0; width = 4; height = 4; }'}, assets=assets)
        for x, color in ((9, COLORS[0]), (13, COLORS[1]), (17, COLORS[0]), (21, COLORS[1])):
            self.assert_pixel(pixels, x, 9, color)

    def test_billboard_texture_uploads_are_visible_in_same_frame(self):
        assets = f'{{ textures.tex.image = {cpu("[0 0 255 255]")}; }}'
        draw = scene(billboard({'texture': '"tex"'}))
        pixels = self._capture(f'[ {{ op = "clear"; color = {BLACK}; }} {draw} ]', assets=assets, textures=f'[ {upload()} ]')
        self.assert_pixel(pixels, 16, 16, (255, 0, 0))

    def test_billboard_trilinear_minification_uses_asset_mipmaps(self):
        assets = '''{ textures.sprite = { image = (builtins.raylibGenImage { kind = "checked";
          width = 16; height = 16; checksX = 1; checksY = 1; color1 = [255 0 0 255]; color2 = [0 0 255 255]; }); filter = "trilinear"; }; }'''
        pixels = self._billboard_pixels({'height': '0.25', 'position': '{ x = 0.125; y = -0.125; z = 0; }'}, assets=assets)
        self.assert_pixel(pixels, 16, 16, (128, 0, 128), tolerance=1)

    def test_billboard_zero_dimensions_draw_nothing_after_validation(self):
        for changes in ({'height': '0'}, {'width': '0'}):
            self.assertEqual(set(self._billboard_pixels(changes)), {(0, 0, 0)})
            self.evaluate(f'builtins.raylibValidate [ {scene(billboard(changes | {"up": ORIGIN}))} ]', error='up must be nonzero')
            draw = scene(billboard(changes | {'texture': '"missing"'}))
            self.evaluate(f'builtins.raylib {{ hidden = true; maxFrames = 1; }} (_: {{ commands = [ {draw} ]; }})', error='unknown texture')

    def test_billboard_tint_and_alpha_blending(self):
        assets = f'{{ textures.sprite.image = {cpu("[255 255 255 255]")}; }}'
        pixels = self._billboard_pixels({'tint': '[128 64 32 128]'}, assets=assets, background=BLUE)
        self.assert_pixel(pixels, 16, 16, (64, 32, 143), tolerance=1)

    def test_billboard_flat_lighting_and_material_texture_product(self):
        self._assert_billboard_pattern(self._billboard_pixels(lit=True), [(128, 0, 0), (0, 128, 0), (0, 0, 128), (128, 128, 0)])

    def test_billboard_material_tint_and_specular(self):
        assets = f'{{ textures.sprite.image = {cpu("[255 255 255 255]")}; }}'
        properties = 'diffuse = [128 64 32 255]; specular = 0;'
        pixels = self._lighting_pixels(draw=billboard(), assets=assets, properties=properties)
        self.assert_pixel(pixels, 16, 16, (64, 32, 16), tolerance=1)
        pixels = self._lighting_pixels(draw=billboard(), assets=assets, properties='diffuse = [0 0 0 255]; specular = 1; shininess = 128;')
        self.assert_pixel(pixels, 16, 16, (128, 128, 128), tolerance=1)

    def test_billboard_flat_lighting_ignores_previous_vertex_normal(self):
        preceding = '{ op = "plane"; position = { x = 100; y = 0; z = 0; }; width = 1; length = 1; color = [255 255 255 255]; }'
        self.assertEqual(self._lighting_pixels(draw=preceding + billboard(), assets=self._billboard_assets()), self._billboard_pixels(lit=True))

    def test_billboard_flat_normals_follow_camera_derived_world_plane(self):
        camera = '{ position = { x = 10; y = 0; z = 0; }; projection = "orthographic"; fovy = 8; }'
        lights = '[ { direction = { x = -1; y = 0; z = 0; }; intensity = 0.5; } ]'
        pixels = self._lighting_pixels(draw=billboard(), assets=self._billboard_assets(), camera=camera, lights=lights)
        self.assertEqual(pixels, self._billboard_pixels(lit=True))

    def test_billboard_fragment_shader_and_restore(self):
        shader = LIB.parent / 'examples/shaders/tint.fs'
        assets = f'({self._billboard_assets()} // {{ shaders.fx = {{ fragment = {shader}; uniforms = {{ gain = {{ type = "float"; value = 0; }}; tint = {{ type = "vec3"; value = [1 1 1]; }}; }}; }}; }})'
        draw = scene('{ op = "shader"; shader = "fx"; commands = [ ' + billboard() + ' ]; }')
        pixels = self._capture(f'[ {{ op = "clear"; color = [255 255 255 255]; }} {draw} {{ op = "pixel"; x = 0; y = 0; color = {BLUE}; }} ]', assets=assets)
        self.assert_pixel(pixels, 16, 16, (0, 0, 0))
        self.assert_pixel(pixels, 0, 0, (0, 0, 255))

    def test_billboard_clipping_and_additive_blend(self):
        draw = '{ op = "clip"; x = 16; y = 0; width = 16; height = 32; commands = [ { op = "blend"; mode = "additive"; commands = [ ' + billboard({'tint': '[255 255 255 128]'}) + ' ]; } ]; }'
        pixels = self._capture(f'[ {{ op = "clear"; color = {BLUE}; }} {scene(draw)} ]', assets=self._billboard_assets())
        self.assert_pixel(pixels, 10, 10, (0, 0, 255))
        self.assert_pixel(pixels, 20, 10, (0, 128, 255), tolerance=1)

    def test_billboard_depth_occlusion_is_independent_of_order(self):
        cube = '{ op = "cube"; position = { x = 0; y = 0; z = 2; }; width = 2; height = 2; length = 1; color = [255 255 255 255]; }'
        images = [self._capture(f'[ {{ op = "clear"; color = {BLACK}; }} {scene(draw)} ]', assets=self._billboard_assets()) for draw in (cube + billboard(), billboard() + cube)]
        self.assertEqual(*images)
        self.assert_pixel(images[0], 16, 16, (255, 255, 255))
        self.assert_pixel(images[0], 10, 10, (255, 0, 0))

    def test_billboard_transparent_pixels_retain_native_depth_writes(self):
        assets = f'{{ textures.sprite.image = {cpu("[255 0 0 0]")}; }}'
        cube = '{ op = "cube"; position = { x = 0; y = 0; z = 0; }; width = 2; height = 2; length = 1; color = [0 255 0 255]; }'
        draw = billboard({'position': '{ x = 0; y = 0; z = 2; }'}) + cube
        pixels = self._capture(f'[ {{ op = "clear"; color = {BLUE}; }} {scene(draw)} ]', assets=assets)
        self.assert_pixel(pixels, 16, 16, (0, 0, 255))

    def test_billboard_large_batches_restore_texture_and_2d_camera(self):
        draw = f'builtins.genList (_: {billboard()}) 9000'
        value = '{ op = "camera3D"; camera = ' + ORTHO + '; commands = ' + draw + '; }'
        pixels = self._capture(f'''[ {{ op = "clear"; color = {BLACK}; }}
          {{ op = "camera2D"; camera = {{ zoom = 2; }}; commands = [ {value}
            {{ op = "pixel"; x = 0; y = 0; color = {BLUE}; }} ]; }} ]''', assets=self._billboard_assets())
        self._assert_billboard_pattern(pixels)
        self.assert_pixel(pixels, 0, 0, (0, 0, 255))

    def test_billboard_invalid_later_geometry_prevents_drawing_and_uploads(self):
        draw = scene(billboard({'texture': '"tex"'}) + billboard({'texture': '"tex"', 'origin': '{ x = -3.0e38; y = 0; }', 'width': '3.0e38'}))
        _, trace = self._texture_native(f'''builtins.raylib {{ hidden = true; maxFrames = 1; assets.textures.tex.image = {cpu()}; }}
          (_: {{ commands = [ {draw} ]; textures = [ {upload()} ]; }})''', error='geometry must remain finite')
        self.assertFalse(any(event['event'] in ('begin', 'update', 'update-rec') for event in trace))

    def test_billboard_invalid_lighting_geometry_releases_shader(self):
        draw = scene(lighting(billboard({'width': '3.0e38', 'origin': '{ x = -3.0e38; y = 0; }'})))
        self._model_evaluate(f'''builtins.raylib {{ hidden = true; maxFrames = 1; assets = {self._billboard_assets()}; }}
          (_: {{ commands = [ {draw} ]; }})''', error='geometry must remain finite')
        self.assertEqual(self._model_trace(), ['load-lighting', 'unload-lighting', 'close'])

    def test_billboard_example(self):
        self.assertEqual(self.evaluate(f'import {LIB.parent / "examples/billboards.nix"} {{ hidden = true; maxFrames = 2; }}'),
                         {'frames': 2, 'state': {'x': 6, 'z': 10, 'spin': True, 'lit': False, 'flipped': False}})

    def test_billboard_example_keyboard_input(self):
        self.assertEqual(self._input_evaluate(f'import {LIB.parent / "examples/billboards.nix"} {{ hidden = true; maxFrames = 2; }}'),
                         {'frames': 2, 'state': {'x': 5.9, 'z': 10, 'spin': True, 'lit': False, 'flipped': False}})
