"""Additional native 3D primitives, safe bases, winding and flat lighting."""

import os
from pathlib import Path

from three_d_cases import scene, ORTHO, TOP, LIB, RED, BLUE, BLACK, ORIGIN
from lighting_cases import lighting, material


def point(x, y, z=0):
    return f'{{ x = {x}; y = {y}; z = {z}; }}'


A, B, C, D = point(-2, -2), point(2, -2), point(-2, 2), point(2, 2)
SHAPES = {
    'circle3D': dict(position=ORIGIN, radius='2', color=RED),
    'triangle3D': dict(v1=A, v2=B, v3=C, color=RED),
    'triangleStrip3D': dict(points=f'[ {A} {B} {C} {D} ]', color=RED),
    'cylinder': dict(position=point(0, -2), radiusTop='2', radiusBottom='2', height='4', color=RED),
    'cylinderWires': dict(position=point(0, -2), radiusTop='2', radiusBottom='2', height='4', color=RED),
    'cylinderEx': dict(start=point(0, -2), end=point(0, 2), startRadius='2', endRadius='2', color=RED),
    'cylinderWiresEx': dict(start=point(0, -2), end=point(0, 2), startRadius='2', endRadius='2', color=RED),
    'capsule': dict(start=point(0, -1), end=point(0, 1), radius='1', color=RED),
    'capsuleWires': dict(start=point(0, -1), end=point(0, 1), radius='1', color=RED),
}
FILLED = ('triangle3D', 'triangleStrip3D', 'cylinder', 'cylinderEx', 'capsule')
WIRES = ('circle3D', 'cylinderWires', 'cylinderWiresEx', 'capsuleWires')
ENDPOINTS = ('cylinderEx', 'cylinderWiresEx', 'capsule', 'capsuleWires')
TESSELLATED = ('cylinder', 'cylinderWires') + ENDPOINTS


def command(op, changes=None, *, remove=()):
    return '{ op = "' + op + '"; ' + ' '.join(f'{k} = {v};' for k, v in (SHAPES[op] | (changes or {})).items() if k not in remove) + ' }'


class ThreeDExtraCases:
    def _extra_3d_pixels(self, op, changes=None, *, camera=ORTHO, lit=False, background=BLACK):
        draw = command(op, changes)
        if lit:
            draw = lighting(material(draw))
        return self._capture(f'[ {{ op = "clear"; color = {background}; }} {scene(draw, camera=camera)} ]')

    def test_extra_3d_pure_and_restricted_validation(self):
        value = scene(lighting(material(' '.join(command(op) for op in SHAPES))))
        for flag in ('--pure-eval', '--restrict-eval'):
            self.assertEqual(self.evaluate(f'builtins.raylibValidate [ {value} ]', flags=[flag], env={'DISPLAY': '', 'WAYLAND_DISPLAY': ''}), 1)

    def test_extra_3d_nix_constructors(self):
        draws = ' '.join(f'(ray.{op} ({command(op)} // {{ op = "ignored"; }}))' for op in SHAPES)
        self.assertEqual(self.evaluate(f'let ray = import {LIB}; in ray.validate [ {scene(draws)} ]'), 1)

    def test_extra_3d_requires_camera(self):
        for op in SHAPES:
            self.evaluate(f'builtins.raylibValidate [ {command(op)} ]', error='requires a camera3D scope')

    def test_extra_3d_required_fields(self):
        for op, fields in SHAPES.items():
            for field in fields:
                self.evaluate(f'builtins.raylibValidate [ {scene(command(op, remove=(field,)))} ]', error=f"missing attribute '{field}'")

    def test_extra_3d_unknown_fields(self):
        for op in SHAPES:
            self.evaluate(f'builtins.raylibValidate [ {scene(command(op, {"typo": "1"}))} ]', error="unknown attribute 'typo'")
        for op in ('cylinder', 'cylinderEx'):
            self.evaluate(f'builtins.raylibValidate [ {scene(command(op, {"rings": "8"}))} ]', error="unknown attribute 'rings'")

    def test_extra_3d_strict_points(self):
        for op, fields in SHAPES.items():
            field = next(iter(fields))
            for value, error in (('{}', "missing attribute 'x'"), (point(0, 0, '1.0e100'), 'finite number'),
                                  ('{ x = 0; y = 0; z = 0; w = 1; }', "unknown attribute 'w'")):
                changes = {field: f'[ {value} {B} {C} ]' if field == 'points' else value}
                self.evaluate(f'builtins.raylibValidate [ {scene(command(op, changes))} ]', error=error)

    def test_extra_3d_negative_and_nonfinite_sizes(self):
        for op, fields in SHAPES.items():
            for field in fields.keys() & {'radius', 'radiusTop', 'radiusBottom', 'height', 'startRadius', 'endRadius'}:
                for value in ('-1', '1.0e100'):
                    self.evaluate(f'builtins.raylibValidate [ {scene(command(op, {field: value}))} ]', error='finite number')

    def test_extra_3d_colors_are_validated(self):
        for op in SHAPES:
            self.evaluate(f'builtins.raylibValidate [ {scene(command(op, {"color": "[]"}))} ]', error='color must be')

    def test_extra_3d_slice_limits_and_defaults(self):
        for op in TESSELLATED:
            for value in ('2', '257', '-1'):
                self.evaluate(f'builtins.raylibValidate [ {scene(command(op, {"slices": value}))} ]', error='integer in')
            self.evaluate(f'builtins.raylibValidate [ {scene(command(op, {"slices": "3.5"}))} ]', error='expected an integer')
            self.assertEqual(self._extra_3d_pixels(op), self._extra_3d_pixels(op, {'slices': '16'}))

    def test_extra_3d_capsule_ring_limits_and_defaults(self):
        for op in ('capsule', 'capsuleWires'):
            for value in ('0', '129'):
                self.evaluate(f'builtins.raylibValidate [ {scene(command(op, {"rings": value}))} ]', error='integer in')
            self.evaluate(f'builtins.raylibValidate [ {scene(command(op, {"rings": "1.5"}))} ]', error='expected an integer')
            self.assertEqual(self._extra_3d_pixels(op), self._extra_3d_pixels(op, {'rings': '8'}))
            self.assertIn((255, 0, 0), self._extra_3d_pixels(op, {'rings': '1', 'slices': '3'}))

    def test_extra_3d_strip_count_limits(self):
        for points, error in (('{}', 'expected a list'), ('[]', '3..4096'), (f'[ {A} {B} ]', '3..4096'),
                                (f'builtins.genList (_: {A}) 4097', '3..4096')):
            self.evaluate(f'builtins.raylibValidate [ {scene(command("triangleStrip3D", {"points": points}))} ]', error=error)
        self.assertEqual(self.evaluate(f'builtins.raylibValidate [ {scene(command("triangleStrip3D", {"points": f"builtins.genList (_: {A}) 4096"}))} ]'), 1)

    def test_extra_3d_circle_axis_validation(self):
        self.evaluate(f'builtins.raylibValidate [ {scene(command("circle3D", {"rotationAxis": ORIGIN}))} ]', error='axis must be nonzero')
        for changes in ({'rotation': '1.0e100'}, {'rotationAxis': point(0, 0, '1.0e100')}):
            self.evaluate(f'builtins.raylibValidate [ {scene(command("circle3D", changes))} ]', error='finite number')
        for axis in (point(0, 0, '3.0e38'), point(0, 0, '1.0e-40')):
            self.assertEqual(self._extra_3d_pixels('circle3D', {'rotationAxis': axis, 'rotation': '30'}),
                             self._extra_3d_pixels('circle3D', {'rotation': '30'}))

    def test_extra_3d_circle_rotation_and_plane(self):
        circle = self._extra_3d_pixels('circle3D')
        self.assertIn((255, 0, 0), circle)
        self.assert_pixel(circle, 16, 16, (0, 0, 0))
        rotated = self._extra_3d_pixels('circle3D', {'rotationAxis': point(1, 0), 'rotation': '90'}, camera=TOP)
        self.assertIn((255, 0, 0), rotated)
        self.assertGreater(rotated.count((255, 0, 0)), 30)
        changes = {'rotationAxis': point(1, 2, 3)}
        self.assertEqual(self._extra_3d_pixels('circle3D', changes | {'rotation': '30'}),
                         self._extra_3d_pixels('circle3D', changes | {'rotation': '390'}))

    def test_extra_3d_native_endpoint_basis_extremes_are_rejected(self):
        for op in ENDPOINTS:
            for start, end in ((ORIGIN, point('1.0e-30', 0)), (ORIGIN, point('1.0e20', 0)),
                               (point('-3.0e38', 0), point('3.0e38', 0))):
                self.evaluate(f'builtins.raylibValidate [ {scene(command(op, {"start": start, "end": end}))} ]', error='endpoint basis')

    def test_extra_3d_geometry_bounds_are_checked(self):
        for op, changes in (('circle3D', {'position': point('3.0e38', 0), 'radius': '3.0e38'}),
                             ('cylinder', {'position': point(0, '3.0e38'), 'height': '3.0e38'}),
                             ('cylinderWires', {'position': point('3.0e38', 0), 'radiusTop': '3.0e38'}),
                             ('cylinderEx', {'startRadius': '3.0e38'}), ('capsule', {'radius': '3.0e38'})):
            self.evaluate(f'builtins.raylibValidate [ {scene(command(op, changes))} ]', error='geometry bounds')

    def test_extra_3d_triangle_winding_is_not_normalized(self):
        pixels = self._extra_3d_pixels('triangle3D')
        self.assert_pixel(pixels, 10, 20, (255, 0, 0))
        self.assert_pixel(pixels, 22, 10, (0, 0, 0))
        self.assertEqual(set(self._extra_3d_pixels('triangle3D', {'v2': C, 'v3': B})), {(0, 0, 0)})

    def test_extra_3d_strip_alternates_native_winding(self):
        pixels = self._extra_3d_pixels('triangleStrip3D')
        self.assertEqual(pixels, [(255, 0, 0) if 8 <= x < 24 and 8 <= y < 24 else (0, 0, 0) for y in range(32) for x in range(32)])
        self.assertEqual(set(self._extra_3d_pixels('triangleStrip3D', {'points': f'[ {B} {A} {D} {C} ]'})), {(0, 0, 0)})

    def test_extra_3d_degenerate_triangles_and_strip_connectors(self):
        self.assertEqual(set(self._extra_3d_pixels('triangle3D', {'v3': B})), {(0, 0, 0)})
        self.assertEqual(self._extra_3d_pixels('triangleStrip3D', {'points': f'[ {A} {B} {C} {C} {D} {D} ]'}),
                         self._extra_3d_pixels('triangle3D'))

    def test_extra_3d_cylinder_base_y_and_closed_caps(self):
        for op in ('cylinder', 'cylinderEx'):
            pixels = self._extra_3d_pixels(op)
            self.assertEqual(pixels, [(255, 0, 0) if 8 <= x < 24 and 8 <= y < 24 else (0, 0, 0) for y in range(32) for x in range(32)])
            cap = self._extra_3d_pixels(op, camera=TOP)
            self.assert_pixel(cap, 16, 16, (255, 0, 0))
            self.assert_pixel(cap, 8, 8, (0, 0, 0))

    def test_extra_3d_cones_allow_either_radius_to_be_zero(self):
        for op, fields in (('cylinder', ('radiusTop', 'radiusBottom')), ('cylinderEx', ('endRadius', 'startRadius'))):
            for field in fields:
                pixels = self._extra_3d_pixels(op, {field: '0'})
                self.assert_pixel(pixels, 16, 16, (255, 0, 0))
                self.assertLess(pixels.count((255, 0, 0)), self._extra_3d_pixels(op).count((255, 0, 0)))

    def test_extra_3d_endpoint_cylinders_follow_all_axes(self):
        for op in ('cylinderEx', 'capsule'):
            for start, end in ((point(-2, 0), point(2, 0)), (point(-1, -1, -1), point(1, 1, 1)),
                               (point(0, 0, -2), point(0, 0, 2))):
                self.assert_pixel(self._extra_3d_pixels(op, {'start': start, 'end': end}), 16, 16, (255, 0, 0))

    def test_extra_3d_capsule_hemispheres_extend_past_endpoints(self):
        pixels = self._extra_3d_pixels('capsule')
        self.assert_pixel(pixels, 16, 9, (255, 0, 0))
        self.assert_pixel(pixels, 16, 22, (255, 0, 0))
        self.assert_pixel(pixels, 16, 16, (255, 0, 0))
        self.assert_pixel(pixels, 8, 16, (0, 0, 0))

    def test_extra_3d_capsule_coincident_endpoints_make_sphere(self):
        for op in ('capsule', 'capsuleWires'):
            pixels = self._extra_3d_pixels(op, {'start': ORIGIN, 'end': ORIGIN, 'radius': '2'})
            self.assertIn((255, 0, 0), pixels)
            self.assertEqual(pixels, self._extra_3d_pixels(op, {'start': ORIGIN, 'end': ORIGIN, 'radius': '2', 'rings': '8', 'slices': '16'}))
            if op == 'capsule':
                self.assert_pixel(pixels, 16, 16, (255, 0, 0))
                self.assert_pixel(pixels, 16, 8, (255, 0, 0))
                self.assert_pixel(pixels, 8, 8, (0, 0, 0))

    def test_extra_3d_zero_sizes_and_collapsed_cylinders_draw_nothing(self):
        for op, changes in (('circle3D', {'radius': '0'}), ('cylinder', {'height': '0'}),
                             ('cylinderWires', {'radiusTop': '0', 'radiusBottom': '0'}),
                             ('cylinderEx', {'start': ORIGIN, 'end': ORIGIN}),
                             ('cylinderWiresEx', {'startRadius': '0', 'endRadius': '0'}),
                             ('capsule', {'radius': '0'}), ('capsuleWires', {'radius': '0'})):
            self.assertEqual(set(self._extra_3d_pixels(op, changes)), {(0, 0, 0)})
            self.evaluate(f'builtins.raylibValidate [ {scene(command(op, changes | {"color": "[]"}))} ]', error='color must be')

    def test_extra_3d_collapsed_cylinder_checks_tessellation(self):
        self.evaluate(f'builtins.raylibValidate [ {scene(command("cylinderEx", {"start": ORIGIN, "end": ORIGIN, "slices": "2"}))} ]', error='integer in')

    def test_extra_3d_endpoint_equality_uses_native_float_rounding(self):
        for op in ENDPOINTS:
            rounded = self._extra_3d_pixels(op, {'start': point(0, 1), 'end': point(0, '1.00000001')})
            self.assertEqual(rounded, self._extra_3d_pixels(op, {'start': point(0, 1), 'end': point(0, 1)}))

    def test_extra_3d_zero_radius_still_checks_native_basis(self):
        for op in ENDPOINTS:
            changes = {'radius': '0'} if op.startswith('capsule') else {'startRadius': '0', 'endRadius': '0'}
            changes |= {'start': ORIGIN, 'end': point('1.0e-30', 0)}
            self.evaluate(f'builtins.raylibValidate [ {scene(command(op, changes))} ]', error='endpoint basis')

    def test_extra_3d_cylinder_minimum_and_maximum_slices_render(self):
        for op in ('cylinder', 'cylinderWires', 'cylinderEx', 'cylinderWiresEx'):
            for slices in ('3', '256'):
                self.assertIn((255, 0, 0), self._extra_3d_pixels(op, {'slices': slices}))

    def test_extra_3d_wire_variants_are_outlines(self):
        for solid, wire in (('cylinder', 'cylinderWires'), ('cylinderEx', 'cylinderWiresEx'), ('capsule', 'capsuleWires')):
            sparse = {'slices': '4'} | ({'rings': '1'} if wire == 'capsuleWires' else {})
            wires = self._extra_3d_pixels(wire, sparse)
            self.assertIn((255, 0, 0), wires)
            self.assertLess(wires.count((255, 0, 0)), self._extra_3d_pixels(solid).count((255, 0, 0)))

    def test_extra_3d_flat_triangle_lighting(self):
        for op in ('triangle3D', 'triangleStrip3D'):
            self.assert_pixel(self._extra_3d_pixels(op, lit=True), 10, 20, (128, 0, 0), tolerance=1)
            self.assertEqual(set(self._lighting_pixels(draw=command(op), lights='[ { direction = { x = 0; y = 0; z = 1; }; } ]')), {(0, 0, 0)})

    def test_extra_3d_curved_solids_use_flat_lighting(self):
        for op in ('cylinder', 'cylinderEx', 'capsule'):
            pixels = self._extra_3d_pixels(op, lit=True)
            self.assertGreater(pixels[16*32 + 16][0], 110)
            self.assertLess(pixels[16*32 + 16][0], 129)
            self.assertNotEqual(pixels, self._extra_3d_pixels(op))

    def test_extra_3d_flat_normals_follow_sloped_world_geometry(self):
        changes = {'v1': point(-1, -2, 1), 'v2': point(1, -2, -1), 'v3': point(-1, 2, 1)}
        draw = command('triangle3D', changes | {'color': '[255 255 255 255]'})
        self.assert_pixel(self._lighting_pixels(draw=draw), 13, 20, (90, 90, 90), tolerance=1)
        side = '[ { direction = { x = -1; y = 0; z = 0; }; intensity = 0.5; } ]'
        self.assert_pixel(self._lighting_pixels(draw=draw, lights=side), 13, 20, (90, 90, 90), tolerance=1)

    def test_extra_3d_lighting_ignores_stale_native_vertex_normals(self):
        preceding = '{ op = "plane"; position = { x = 100; y = 0; z = 0; }; width = 1; length = 1; color = [255 255 255 255]; }'
        for op in FILLED:
            draw = preceding + command(op)
            self.assertEqual(self._lighting_pixels(draw=draw), self._extra_3d_pixels(op, lit=True))

    def test_extra_3d_debug_geometry_remains_unlit(self):
        for op in WIRES:
            draw = lighting(material(command(op), 'diffuse = [0 0 0 0];'), ambient='[0 0 0]', lights='[]')
            pixels = self._capture(f'[ {{ op = "clear"; color = {BLACK}; }} {scene(draw)} ]')
            self.assertEqual(pixels, self._extra_3d_pixels(op))

    def test_extra_3d_material_tint_and_alpha(self):
        draw = material(command('triangleStrip3D', {'color': '[255 255 255 255]'}), 'diffuse = [255 0 0 128]; specular = 0;')
        pixels = self._capture(f'[ {{ op = "clear"; color = {BLUE}; }} {scene(lighting(draw))} ]')
        self.assert_pixel(pixels, 16, 16, (64, 0, 127), tolerance=1)

    def test_extra_3d_mixed_normal_modes_restore_uniforms(self):
        cube = '{ op = "cube"; position = { x = 0; y = 0; z = 2; }; width = 2; height = 2; length = 1; color = [0 255 0 255]; }'
        draw = lighting(material(command('triangleStrip3D') + cube))
        pixels = self._capture(f'[ {{ op = "clear"; color = {BLACK}; }} {scene(draw)} ]')
        self.assert_pixel(pixels, 16, 16, (0, 128, 0), tolerance=1)
        self.assert_pixel(pixels, 10, 20, (128, 0, 0), tolerance=1)

    def test_extra_3d_depth_is_independent_of_order(self):
        near = command('triangleStrip3D', {'points': f'[ {point(-1, -1, 3)} {point(1, -1, 3)} {point(-1, 1, 3)} {point(1, 1, 3)} ]'})
        far = command('cylinder', {'color': BLUE})
        images = [self._capture(f'[ {{ op = "clear"; color = {BLACK}; }} {scene(draw)} ]') for draw in (near + far, far + near)]
        self.assertEqual(*images)
        self.assert_pixel(images[0], 16, 16, (255, 0, 0))
        self.assert_pixel(images[0], 9, 16, (0, 0, 255))

    def test_extra_3d_clipping_and_overlay(self):
        draw = '{ op = "clip"; x = 16; y = 0; width = 16; height = 32; commands = [ ' + command('triangleStrip3D') + ' ]; }'
        pixels = self._capture(f'[ {{ op = "clear"; color = {BLACK}; }} {scene(draw)} {{ op = "pixel"; x = 0; y = 0; color = {BLUE}; }} ]')
        self.assert_pixel(pixels, 12, 16, (0, 0, 0))
        self.assert_pixel(pixels, 20, 16, (255, 0, 0))
        self.assert_pixel(pixels, 0, 0, (0, 0, 255))

    def test_extra_3d_render_texture_matches_window(self):
        for op in SHAPES:
            draw = scene(command(op))
            pixels = self._capture(f'''[ {{ op = "clear"; color = {BLACK}; }}
              {{ op = "paint"; texture = "canvas"; commands = [ {draw} ]; }}
              {{ op = "texture"; texture = "canvas"; x = 0; y = 0; }} ]''', assets='{ renderTextures.canvas = { width = 32; height = 32; }; }')
            self.assertEqual(pixels, self._extra_3d_pixels(op))

    def test_extra_3d_lit_capsule_render_texture(self):
        draw = scene(lighting(material(command('capsule'))))
        pixels = self._capture(f'''[ {{ op = "clear"; color = {BLACK}; }}
          {{ op = "paint"; texture = "canvas"; commands = [ {draw} ]; }}
          {{ op = "texture"; texture = "canvas"; x = 0; y = 0; }} ]''', assets='{ renderTextures.canvas = { width = 32; height = 32; }; }')
        self.assertEqual(pixels, self._extra_3d_pixels('capsule', lit=True))

    def test_extra_3d_fragment_shaders(self):
        shader = LIB.parent / 'examples/shaders/tint.fs'
        assets = f'{{ shaders.fx = {{ fragment = {shader}; uniforms.gain = {{ type = "float"; value = 0; }}; uniforms.tint = {{ type = "vec3"; value = [1 1 1]; }}; }}; }}'
        for op in SHAPES:
            draw = '{ op = "shader"; shader = "fx"; commands = [ ' + command(op) + ' ]; }'
            pixels = self._capture(f'[ {{ op = "clear"; color = [255 255 255 255]; }} {scene(draw)} ]', assets=assets)
            self.assertIn((0, 0, 0), pixels)
            self.assertNotIn((255, 0, 0), pixels)

    def test_extra_3d_additive_blends(self):
        draw = '{ op = "blend"; mode = "additive"; commands = [ ' + command('triangleStrip3D', {'color': '[255 0 0 128]'}) + ' ]; }'
        pixels = self._capture(f'[ {{ op = "clear"; color = {BLUE}; }} {scene(draw)} ]')
        self.assert_pixel(pixels, 16, 16, (128, 0, 255), tolerance=1)

    def test_extra_3d_maximum_capsule_tessellation_and_batch_flushes(self):
        for op in ('capsule', 'capsuleWires'):
            pixels = self._extra_3d_pixels(op, {'slices': '256', 'rings': '128'}, lit=op == 'capsule')
            self.assertGreater(pixels[16*32 + 16][0], 110)
            self.assertEqual(pixels[16*32 + 16][1:], (0, 0))

    def test_extra_3d_maximum_strip_batch(self):
        points = f'[ {A} {B} {C} {D} ] ++ builtins.genList (_: {D}) 4092'
        self.assertEqual(self._extra_3d_pixels('triangleStrip3D', {'points': points}), self._extra_3d_pixels('triangleStrip3D'))

    def test_extra_3d_invalid_later_command_prevents_rendering(self):
        if not self.capture_library:
            self.skipTest('pass --capture-library for framebuffer validation')
        path = self.asset_directory / 'invalid-extra-3d.ppm'
        path.unlink(missing_ok=True)
        draw = scene(command('triangleStrip3D') + command('capsule', {'end': point('1.0e30', 0)}))
        self.evaluate(f'builtins.raylib {{ hidden = true; maxFrames = 1; }} (_: {{ commands = [ {draw} ]; }})', error='endpoint basis',
                      env={'LD_PRELOAD': str(Path(self.capture_library).resolve()) + ' ' + os.environ.get('LD_PRELOAD', ''), 'NIXRAY_TEST_CAPTURE': str(path)})
        self.assertFalse(path.exists())

    def test_extra_3d_invalid_lit_geometry_releases_shader(self):
        draw = scene(lighting(material(command('capsule', {'end': point('1.0e30', 0)}))))
        self._model_evaluate(f'builtins.raylib {{ hidden = true; maxFrames = 1; }} (_: {{ commands = [ {draw} ]; }})', error='endpoint basis')
        self.assertEqual(self._model_trace(), ['load-lighting', 'unload-lighting', 'close'])

    def test_extra_3d_debug_only_does_not_load_lighting(self):
        draw = scene(lighting(' '.join(command(op) for op in WIRES)))
        self._model_evaluate(f'builtins.raylib {{ hidden = true; maxFrames = 1; }} (_: {{ commands = [ {draw} ]; }})')
        self.assertEqual(self._model_trace(), ['close'])

    def test_extra_3d_example(self):
        self.assertEqual(self.evaluate(f'import {LIB.parent / "examples/primitives-3d.nix"} {{ hidden = true; maxFrames = 2; }}'),
                         {'frames': 2, 'state': {'wires': False, 'lit': True, 'slices': 16}})
