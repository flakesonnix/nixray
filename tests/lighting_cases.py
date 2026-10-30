"""Directional lighting/material schemas and native pixel/state coverage."""

import json
import math
import os
from pathlib import Path
from unittest.mock import patch

from three_d_cases import command, scene, ORTHO, TOP, LIB
from model_cases import model, HALF_POSE


FRONT = "[ { direction = { x = 0; y = 0; z = -1; }; intensity = 0.5; } ]"


def lighting(commands="", *, ambient="[0 0 0]", lights=FRONT):
    return f'{{ op = "lighting"; ambient = {ambient}; lights = {lights}; commands = [ {commands} ]; }}'


def material(commands, attributes="specular = 0;"):
    return f'{{ op = "material"; {attributes} commands = [ {commands} ]; }}'


class LightingCases:
    def _lighting_pixels(self, op="cube", changes=None, *, ambient="[0 0 0]", lights=FRONT,
                         properties="specular = 0;", camera=ORTHO, assets="{}", draw=None):
        draw = command(op, {"color": "[255 255 255 255]"} | (changes or {})) if draw is None else draw
        return self._capture(f'[ {{ op = "clear"; color = [0 0 0 255]; }} {scene(lighting(material(draw, properties), ambient=ambient, lights=lights), camera=camera)} ]', assets=assets)

    def test_lighting_validation_is_pure(self):
        value = scene(lighting(material(command("cube"))))
        for flag in ("--pure-eval", "--restrict-eval"):
            self.assertEqual(self.evaluate(f"builtins.raylibValidate [ {value} ]", flags=[flag], env={"DISPLAY": "", "WAYLAND_DISPLAY": ""}), 1)
        self.assertEqual(self.evaluate(f'''let ray = import {LIB}; in ray.validate [ (ray.camera3D {{ camera = {{}};
          commands = [ (ray.lighting {{ lights = []; commands = [ (ray.material {{ commands = []; }}) ]; }}) ]; }}) ]'''), 1)

    def test_lighting_scope_constraints(self):
        self.evaluate(f"builtins.raylibValidate [ {lighting()} ]", error="requires a camera3D")
        self.evaluate(f"builtins.raylibValidate [ {scene(material(''))} ]", error="requires a lighting scope")
        for value, error in (('{ op = "lighting"; commands = []; }', "missing attribute 'lights'"),
                              ('{ op = "lighting"; lights = []; }', "missing attribute 'commands'"),
                              ('{ op = "lighting"; lights = []; commands = {}; }', "expected a list"),
                              ('{ op = "lighting"; lights = []; commands = []; typo = 1; }', "unknown attribute 'typo'")):
            self.evaluate(f"builtins.raylibValidate [ {scene(value)} ]", error=error)

    def test_lighting_rgb_validation(self):
        for rgb, error in (("{}", "expected a list"), ("[1 1]", "exactly three"), ("[1 1 1 1]", "exactly three"),
                            ("[(-0.1) 0 0]", "finite number"), ("[1.00000001 0 0]", "finite number"), ("[1.0e100 0 0]", "finite number")):
            self.evaluate(f"builtins.raylibValidate [ {scene(lighting(ambient=rgb))} ]", error=error)
            lights = '[ { direction = { x = 0; y = 0; z = -1; }; color = ' + rgb + '; } ]'
            self.evaluate(f"builtins.raylibValidate [ {scene(lighting(lights=lights))} ]", error=error)

    def test_lighting_light_count_and_schema(self):
        for lights, error in (("{}", "expected a list"), ("[ {} ]", "missing attribute 'direction'"),
                               ("[ { direction = {}; } ]", "missing attribute 'x'"),
                               ("[ { direction = { x = 0; y = 0; z = 0; }; } ]", "direction must be nonzero"),
                               ("[ { direction = { x = 0; y = 1.0e100; z = 0; }; } ]", "finite number"),
                               ("[ { direction = { x = 0; y = 1; z = 0; extra = 0; }; } ]", "unknown attribute 'extra'"),
                               ("[ { direction = { x = 0; y = 1; z = 0; }; intensity = -1; } ]", "finite number"),
                               ("[ { direction = { x = 0; y = 1; z = 0; }; intensity = 16.1; } ]", "finite number"),
                               ("builtins.genList (_: { direction = { x = 0; y = 1; z = 0; }; }) 5", "at most four")):
            self.evaluate(f"builtins.raylibValidate [ {scene(lighting(lights=lights))} ]", error=error)
        self.assertEqual(self.evaluate(f"builtins.raylibValidate [ {scene(lighting(lights='builtins.genList (_: { direction = { x = 0; y = 1; z = 0; }; }) 4'))} ]"), 1)

    def test_lighting_material_validation(self):
        for properties, error in (("diffuse = [];", "color must be"), ("specular = -0.1;", "finite number"),
                                  ("specular = 1.1;", "finite number"), ("shininess = 0;", "finite number"),
                                  ("shininess = 257;", "finite number"), ("roughness = 0.5;", "unknown attribute 'roughness'")):
            self.evaluate(f"builtins.raylibValidate [ {scene(lighting(material('', properties)))} ]", error=error)
        self.evaluate(f'''builtins.raylibValidate [ {scene(lighting('{ op = "material"; }'))} ]''', error="missing attribute 'commands'")

    def test_lighting_custom_shader_overlap_is_rejected_purely(self):
        custom = '{ op = "shader"; shader = "unloaded"; commands = [ ' + command("cube") + ' ]; }'
        self.evaluate(f"builtins.raylibValidate [ {scene(lighting(custom))} ]", error="must not overlap")
        outer = '{ op = "shader"; shader = "unloaded"; commands = [ ' + scene(lighting()) + ' ]; }'
        self.evaluate(f"builtins.raylibValidate [ {outer} ]", error="must not overlap")

    def test_lighting_scope_depth_budget(self):
        for count in (61, 62):
            value = scene(lighting(material(command("cube"))))
            expr = f'''let leaf = {value}; wrap = commands: {{ op = "clip"; x = 0; y = 0; width = 32; height = 32; inherit commands; }};
              in builtins.raylibValidate (builtins.foldl' (commands: _: [ (wrap commands) ]) [leaf] (builtins.genList (i: i) {count}))'''
            if count == 61:
                self.assertEqual(self.evaluate(expr), 1)
            else:
                self.evaluate(expr, error="nesting must not exceed 64")

    def test_lighting_ambient_only_pixels(self):
        pixels = self._lighting_pixels(ambient="[0.2 0.4 0.6]", lights="[]")
        self.assert_pixel(pixels, 16, 16, (51, 102, 153), tolerance=1)
        self.assert_pixel(pixels, 0, 0, (0, 0, 0))

    def test_lighting_direction_is_ray_travel_direction(self):
        self.assert_pixel(self._lighting_pixels(), 16, 16, (128, 128, 128), tolerance=1)
        back = "[ { direction = { x = 0; y = 0; z = 1; }; } ]"
        self.assert_pixel(self._lighting_pixels(lights=back), 16, 16, (0, 0, 0))

    def test_lighting_direction_normalization_extremes(self):
        expected = self._lighting_pixels()
        for z in ("-1000", "-1.0e-40", "-3.0e38"):
            self.assertEqual(expected, self._lighting_pixels(lights=f"[ {{ direction = {{ x = 0; y = 0; z = {z}; }}; intensity = 0.5; }} ]"))

    def test_lighting_multiple_colored_lights(self):
        lights = '''[
          { direction = { x = 0; y = 0; z = -1; }; color = [1 0 0]; intensity = 0.25; }
          { direction = { x = 0; y = 0; z = -1; }; color = [0 1 0]; intensity = 0.5; }
          { direction = { x = 0; y = 0; z = -1; }; color = [0 0 1]; intensity = 0.75; }
          { direction = { x = 0; y = 0; z = -1; }; color = [1 1 1]; intensity = 0; }
        ]'''
        self.assert_pixel(self._lighting_pixels(lights=lights), 16, 16, (64, 128, 191), tolerance=1)

    def test_lighting_material_diffuse_tints_color(self):
        pixels = self._lighting_pixels(properties="diffuse = [128 255 64 255]; specular = 0;")
        self.assert_pixel(pixels, 16, 16, (64, 128, 32), tolerance=1)

    def test_lighting_specular_strength_and_orthographic_view(self):
        properties = "diffuse = [0 0 0 255]; specular = 1; shininess = 128;"
        pixels = self._lighting_pixels(properties=properties)
        self.assert_pixel(pixels, 16, 16, (128, 128, 128), tolerance=1)
        self.assert_pixel(pixels, 9, 9, (128, 128, 128), tolerance=1)
        dark = self._lighting_pixels(properties="diffuse = [0 0 0 255]; specular = 0;")
        self.assertEqual(set(dark), {(0, 0, 0)})

    def test_lighting_perspective_view_changes_specular(self):
        pixels = self._lighting_pixels(properties="diffuse = [0 0 0 255]; specular = 1; shininess = 128;", camera="{}")
        self.assertGreater(pixels[16*32 + 16][0], pixels[10*32 + 10][0])

    def test_lighting_sphere_normals_and_shininess(self):
        low = self._lighting_pixels("sphere", properties="diffuse = [0 0 0 255]; specular = 1; shininess = 4;")
        high = self._lighting_pixels("sphere", properties="diffuse = [0 0 0 255]; specular = 1; shininess = 128;")
        self.assertGreater(low[16*32 + 20][0], high[16*32 + 20][0])
        self.assertGreater(high[16*32 + 16][0], high[16*32 + 22][0])

    def test_lighting_plane_world_up_normal(self):
        lights = "[ { direction = { x = 0; y = -1; z = 0; }; intensity = 0.5; } ]"
        self.assert_pixel(self._lighting_pixels("plane", camera=TOP, lights=lights), 16, 16, (128, 128, 128), tolerance=1)

    def test_lighting_nested_materials_restore_parent(self):
        def cube(x):
            return command("cube", {"width": "2", "height": "2", "length": "1", "position": f"{{ x = {x}; y = 0; z = 0; }}", "color": "[255 255 255 255]"})
        red = "diffuse = [255 0 0 255]; specular = 0;"
        blue = "diffuse = [0 0 255 255]; specular = 0;"
        child = material(cube(-2) + material(cube(0), blue) + cube(2), red)
        pixels = self._capture(f'[ {{ op = "clear"; color = [0 0 0 255]; }} {scene(lighting(child, ambient="[1 1 1]", lights="[]"))} ]')
        for x, color in ((8, (255, 0, 0)), (16, (0, 0, 255)), (24, (255, 0, 0))):
            self.assert_pixel(pixels, x, 16, color)

    def test_lighting_material_defaults_do_not_merge_parent(self):
        cube = command("cube", {"color": "[255 255 255 255]"})
        draw = material(material(cube), "diffuse = [255 0 0 255];")
        pixels = self._capture(f'[ {{ op = "clear"; color = [0 0 0 255]; }} {scene(lighting(draw, ambient="[1 1 1]", lights="[]"))} ]')
        self.assert_pixel(pixels, 16, 16, (255, 255, 255))

    def test_lighting_nested_lights_preserve_material(self):
        cube = command("cube", {"color": "[255 255 255 255]"})
        draw = material(lighting(cube, ambient="[0 1 0]", lights="[]"), "diffuse = [128 64 32 255];")
        pixels = self._capture(f'[ {{ op = "clear"; color = [0 0 0 255]; }} {scene(lighting(draw, ambient="[1 0 0]", lights="[]"))} ]')
        self.assert_pixel(pixels, 16, 16, (0, 64, 0))

    def test_lighting_nested_scopes_replace_and_restore(self):
        left = command("cube", {"position": "{ x = -2; y = 0; z = 0; }", "width": "2", "height": "2", "color": "[255 255 255 255]"})
        middle = command("cube", {"width": "2", "height": "2", "color": "[255 255 255 255]"})
        right = command("cube", {"position": "{ x = 2; y = 0; z = 0; }", "width": "2", "height": "2", "color": "[255 255 255 255]"})
        draw = lighting(left + lighting(middle, ambient="[0 1 0]", lights="[]") + right, ambient="[1 0 0]", lights="[]")
        pixels = self._capture(f'[ {{ op = "clear"; color = [0 0 0 255]; }} {scene(draw)} ]')
        self.assert_pixel(pixels, 8, 16, (255, 0, 0))
        self.assert_pixel(pixels, 16, 16, (0, 255, 0))
        self.assert_pixel(pixels, 24, 16, (255, 0, 0))

    def test_lighting_debug_geometry_remains_unlit(self):
        for op in ("cubeWires", "sphereWires", "line3D", "grid", "modelWires"):
            camera = TOP if op == "grid" else ORTHO
            draw = model(op=op) if op == "modelWires" else command(op)
            assets = self._model_assets() if op == "modelWires" else "{}"
            direct = self._capture(f'[ {{ op = "clear"; color = [0 0 0 255]; }} {scene(draw, camera=camera)} ]', assets=assets)
            wrapped = self._capture(f'[ {{ op = "clear"; color = [0 0 0 255]; }} {scene(lighting(material(draw, "diffuse = [0 0 0 0];"), lights="[]"), camera=camera)} ]', assets=assets)
            self.assertEqual(direct, wrapped)

    def test_lighting_unlit_default_and_following_hud_restore(self):
        draw = lighting(material(command("cube")), lights="[]")
        right = command("cube", {"position": "{ x = 3; y = 0; z = 0; }", "width": "1", "height": "1"})
        pixels = self._capture(f'''[ {{ op = "clear"; color = [255 255 255 255]; }} {scene(draw + right)}
          {{ op = "pixel"; x = 0; y = 0; color = [0 255 0 255]; }} ]''')
        self.assert_pixel(pixels, 16, 16, (0, 0, 0))
        self.assert_pixel(pixels, 28, 16, (255, 0, 0))
        self.assert_pixel(pixels, 0, 0, (0, 255, 0))

    def test_lighting_model_world_normal_transform(self):
        draw = model("rotationAxis = { x = 0; y = 1; z = 0; }; rotation = 45;")
        lights = "[ { direction = { x = -1; y = 0; z = 0; }; } ]"
        pixels = self._lighting_pixels(draw=draw, assets=self._model_assets(), lights=lights)
        self.assert_pixel(pixels, 16, 16, (180, 180, 180), tolerance=2)

    def test_lighting_models_and_primitives_do_not_leak_uniforms(self):
        left = "(" + model("scale = 0.5; tint = [255 0 0 255];") + " // { position = { x = -2; y = 0; z = 0; }; })"
        right = "(" + model("scale = 0.5; tint = [0 0 255 255];") + " // { position = { x = 2; y = 0; z = 0; }; })"
        cube = command("cube", {"width": "2", "height": "2", "color": "[255 255 255 255]"})
        pixels = self._lighting_pixels(draw=left + cube + right, ambient="[1 1 1]", lights="[]", assets=self._model_assets())
        self.assert_pixel(pixels, 8, 16, (255, 0, 0))
        self.assert_pixel(pixels, 16, 16, (255, 255, 255))
        self.assert_pixel(pixels, 24, 16, (0, 0, 255))

    def test_lighting_model_missing_normals_uses_flat_faces(self):
        file = self._model_files() / "no-normals.obj"
        assets = f"{{ models.mesh = {json.dumps(str(file))}; }}"
        vertices = "v -2 -1 0\nv 2 -1 0\nv 2 1 0\nv -2 1 0\n"
        for faces in ("f 1 2 3\nf 1 3 4\n", "vn 0 0 1\nf 1//1 2//1 3//1\nf 1 3 4\n"):
            file.write_text(vertices + faces)
            self.assert_pixel(self._lighting_pixels(draw=model(), assets=assets), 16, 16, (128, 128, 128), tolerance=1)
        file.write_text(vertices + "vn 0 1 0\nf 1//1 2//1 3//1\nf 1//1 3//1 4//1\n")
        self.assert_pixel(self._lighting_pixels(draw=model(), assets=assets), 16, 16, (0, 0, 0))

    def test_lighting_model_texture_color_and_alpha(self):
        assets = self._model_assets("textured.glb")
        pixels = self._lighting_pixels(draw=model(), assets=assets)
        self.assertTrue(any(r > 100 and g < 5 and b < 5 for r, g, b in pixels))
        self.assertTrue(any(g > 100 and r < 5 and b < 5 for r, g, b in pixels))
        draw = scene(lighting(material(model(), "diffuse = [255 0 0 128]; specular = 0;")))
        pixels = self._capture(f'[ {{ op = "clear"; color = [0 0 255 255]; }} {draw} ]', assets=self._model_assets())
        self.assert_pixel(pixels, 16, 16, (64, 0, 127), tolerance=1)

    def test_lighting_skeletal_models_keep_pose_and_normals(self):
        draw = model(f"pose = {HALF_POSE};")
        pixels = self._lighting_pixels(draw=draw, assets=self._model_assets("skin.glb", animated=True))
        self.assert_pixel(pixels, 24, 16, (128, 128, 128), tolerance=1)
        self.assert_pixel(pixels, 16, 16, (0, 0, 0))

    def test_lighting_render_texture_matches_window(self):
        child = scene(lighting(material(command("cube", {"color": "[255 255 255 255]"}))))
        direct = self._lighting_pixels()
        painted = self._capture(f'''[ {{ op = "clear"; color = [0 0 0 255]; }}
          {{ op = "paint"; texture = "canvas"; commands = [ {child} ]; }}
          {{ op = "texture"; texture = "canvas"; x = 0; y = 0; }} ]''', assets="{ renderTextures.canvas = { width = 32; height = 32; }; }")
        self.assertEqual(direct, painted)

    def test_lighting_custom_shader_parent_is_suspended_by_paint(self):
        shader = LIB.parent / "examples/shaders/tint.fs"
        assets = f'''{{ renderTextures.canvas = {{ width = 32; height = 32; }};
          shaders.fx = {{ fragment = {shader}; uniforms = {{ gain = {{ type = "float"; value = 0; }};
            tint = {{ type = "vec3"; value = [1 1 1]; }}; }}; }}; }}'''
        child = scene(lighting(material(command("cube", {"color": "[255 255 255 255]"})), ambient="[1 1 1]", lights="[]"))
        pixels = self._capture(f'''[ {{ op = "clear"; color = [0 0 0 255]; }}
          {{ op = "shader"; shader = "fx"; commands = [
            {{ op = "paint"; texture = "canvas"; commands = [ {child} ]; }}
          ]; }} {{ op = "texture"; texture = "canvas"; x = 0; y = 0; }} ]''', assets=assets)
        self.assert_pixel(pixels, 16, 16, (255, 255, 255))

    def test_lighting_camera_uniforms_change_between_frames(self):
        cube = command("cube", {"color": "[255 255 255 255]"})
        properties = "diffuse = [0 0 0 255]; specular = 1; shininess = 128;"
        moving = 'if frame.frame == 0 then { position = { x = 5; y = 0; z = 10; }; } else {}'
        pixels = self._capture(f'[ {{ op = "clear"; color = [0 0 0 255]; }} {scene(lighting(material(cube, properties)), camera=moving)} ]', frames=2)
        self.assertEqual(pixels, self._lighting_pixels(properties=properties, camera="{}"))

    def test_lighting_clips_and_depth_occlusion(self):
        near = command("cube", {"width": "2", "height": "2", "position": "{ x = 0; y = 0; z = 2; }", "color": "[255 0 0 255]"})
        far = command("cube", {"position": "{ x = 0; y = 0; z = -2; }", "color": "[0 0 255 255]"})
        clipped = '{ op = "clip"; x = 16; y = 0; width = 16; height = 32; commands = [ ' + lighting(material(near + far)) + ' ]; }'
        pixels = self._capture(f'[ {{ op = "clear"; color = [0 0 0 255]; }} {scene(clipped)} ]')
        self.assert_pixel(pixels, 17, 16, (128, 0, 0), tolerance=1)
        self.assert_pixel(pixels, 22, 16, (0, 0, 128), tolerance=1)
        self.assert_pixel(pixels, 12, 16, (0, 0, 0))

    def test_lighting_additive_blending(self):
        cube = command("cube", {"color": "[255 255 255 255]"})
        child = lighting(material(cube, "diffuse = [255 0 0 128]; specular = 0;"))
        blend = '{ op = "blend"; mode = "additive"; commands = [ ' + child + ' ]; }'
        pixels = self._capture(f'[ {{ op = "clear"; color = [0 0 255 255]; }} {scene(blend)} ]')
        self.assert_pixel(pixels, 16, 16, (64, 0, 255), tolerance=1)

    def test_lighting_clear_ignores_material_and_lights(self):
        clear = '{ op = "clear"; color = [17 34 51 255]; }'
        pixels = self._capture(f'[ {scene(lighting(material(clear, "diffuse = [0 0 0 0];"), lights="[]"))} ]')
        self.assertEqual(set(pixels), {(17, 34, 51)})

    def test_lighting_large_sphere_batch_transforms_once(self):
        changes = {"position": "{ x = 1; y = 0; z = 0; }", "radius": "1.25", "rings": "128", "slices": "256"}
        pixels = self._lighting_pixels("sphere", changes, properties="diffuse = [0 0 0 255]; specular = 1; shininess = 128;", camera="{}")
        # Compare dense native geometry against analytic ray/sphere lighting.
        # This catches world-position double transforms during automatic flushes.
        def unit(v):
            length = math.sqrt(sum(x*x for x in v))
            return tuple(x/length for x in v)
        for x, y in ((19, 16), (20, 16), (21, 16)):
            ray = unit(((2*(x + 0.5)/32 - 1)*math.tan(math.pi/8), (1 - 2*(y + 0.5)/32)*math.tan(math.pi/8), -1))
            oc = (-1, 0, 10)
            b = sum(a*d for a, d in zip(oc, ray))
            t = -b - math.sqrt(b*b - (sum(a*a for a in oc) - 1.25**2))
            normal = unit(tuple(oc[i] + t*ray[i] for i in range(3)))
            half = unit((-ray[0], -ray[1], 1 - ray[2]))
            intensity = round(127.5 * max(sum(a*b for a, b in zip(normal, half)), 0)**128)
            self.assert_pixel(pixels, x, y, (intensity,)*3, tolerance=3)

    def test_lighting_shader_loaded_once_and_released(self):
        value = scene(lighting(material(command("cube"))))
        self._model_evaluate(f'''builtins.raylib {{ hidden = true; fps = 0; maxFrames = 3; }} (_: {{ commands = [ {value} ]; }})''')
        trace = self._model_trace()
        self.assertEqual(trace.count("load-lighting"), 1)
        self.assertEqual(trace.count("unload-lighting"), 1)
        self.assertEqual(trace[-1], "close")

    def test_lighting_state_failure_releases_shader_without_drawing(self):
        value = scene(lighting(material(command("cube"))))
        self._model_evaluate(f'''builtins.raylib {{ hidden = true; fps = 0; maxFrames = 1; }} (_: {{
          commands = [ {value} ]; state = throw "state failed";
        }})''', error="state failed")
        self.assertEqual(self._model_trace(), ["load-lighting", "unload-lighting", "close"])

    def test_lighting_invalid_batch_cannot_draw(self):
        if not self.capture_library:
            self.skipTest("pass --capture-library for framebuffer validation")
        path = self.asset_directory / "invalid-lighting.ppm"
        path.unlink(missing_ok=True)
        valid = scene(lighting(material(command("cube"))))
        invalid = scene(lighting(material(command("cube"), "shininess = 0;")))
        with patch.dict(os.environ, {"LD_PRELOAD": str(Path(self.capture_library).resolve()), "NIXRAY_TEST_CAPTURE": str(path)}):
            self._model_evaluate(f'''builtins.raylib {{ hidden = true; fps = 0; maxFrames = 1; }}
              (_: {{ commands = [ {valid} {invalid} ]; }})''', error="finite number")
        self.assertFalse(path.exists())
        self.assertEqual(self._model_trace(), ["load-lighting", "unload-lighting", "close"])

    def test_lighting_debug_only_scopes_do_not_compile_shader(self):
        value = scene(lighting(command("grid")))
        self._model_evaluate(f'''builtins.raylib {{ hidden = true; fps = 0; maxFrames = 1; }} (_: {{ commands = [ {value} ]; }})''')
        self.assertEqual(self._model_trace(), ["close"])

    def test_lighting_program_resets_between_windows(self):
        value = scene(lighting(material(command("cube"))))
        self._model_evaluate(f'''let run = _: builtins.raylib {{ hidden = true; fps = 0; maxFrames = 1; }}
          (_: {{ commands = [ {value} ]; }}); first = run null;
        in builtins.seq first (run true)''')
        self.assertEqual(self._model_trace().count("load-lighting"), 2)
        self.assertEqual(self._model_trace().count("unload-lighting"), 2)

    def test_lighting_example(self):
        example = LIB.parent / "examples/lighting.nix"
        self.assertEqual(self._model_evaluate(f"import {example} {{ hidden = true; maxFrames = 2; }}"),
                         {"frames": 2, "state": {"glossy": True, "warm": True}})
