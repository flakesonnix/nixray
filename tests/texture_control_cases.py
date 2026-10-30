"""Sampler settings, wrapped crops and nine-patch panels on images and FBOs."""

import json
import os
from pathlib import Path
import struct
import zlib


COLORS = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0), (255, 255, 255),
          (255, 0, 255), (0, 255, 255), (255, 128, 0), (128, 128, 128)]
BORDERS = "{ left = 1; top = 2; right = 3; bottom = 1; }"


class TextureControlCases:
    def _panel_images(self):
        panel = self.asset_directory / "panel.png"
        atlas = self.asset_directory / "panel-atlas.png"
        if not panel.exists():
            def chunk(tag, data):
                return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))

            def write(path, pixels):
                h, w = len(pixels), len(pixels[0])
                path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
                    + chunk(b"IDAT", zlib.compress(b"".join(b"\0" + b"".join(bytes((*color, 255)) for color in row) for row in pixels)))
                    + chunk(b"IEND", b""))

            rows = [[COLORS[(0 if y < 2 else 1 if y < 5 else 2) * 3 + (0 if x < 1 else 1 if x < 5 else 2)]
                     for x in range(8)] for y in range(6)]
            write(panel, rows)
            write(atlas, [[(7, 11, 13)] * 10] + [[(7, 11, 13), *row, (7, 11, 13)] for row in rows] + [[(7, 11, 13)] * 10])
        return json.dumps(str(panel)), json.dumps(str(atlas))

    def _sampler(self, options="", *, target=False):
        if target:
            assets = f"{{ renderTextures.tex = {{ width = 2; height = 2; {options} }}; }}"
            colors = (COLORS[0], COLORS[1], COLORS[2], COLORS[3])
            draw = " ".join(f'{{ op = "pixel"; x = {i % 2}; y = {i // 2}; color = [{r} {g} {b} 255]; }}'
                            for i, (r, g, b) in enumerate(colors))
            prefix = f'{{ op = "paint"; texture = "tex"; commands = [ {draw} ]; }}'
        else:
            assets = f"{{ textures.tex = {{ path = {self.pattern_path}; {options} }}; }}"
            prefix = ""
        return assets, prefix

    def _sample_pixels(self, options="", attributes="", *, target=False):
        assets, prefix = self._sampler(options, target=target)
        return self._capture(f'''[ {{ op = "clear"; color = [0 0 0 255]; }} {prefix}
          {{ op = "texture"; texture = "tex"; x = 4; y = 4; {attributes} }} ]''', assets=assets)

    def _panel_setup(self, *, target=False, options="", atlas=False):
        panel, sheet = self._panel_images()
        if not target:
            return f"{{ textures.panel = {{ path = {sheet if atlas else panel}; {options} }}; }}", ""
        shift = 1 if atlas else 0
        draw = " ".join(f'{{ op = "rectangle"; x = {x + shift}; y = {y + shift}; width = {w}; height = {h}; color = [{r} {g} {b} 255]; }}'
            for row, (y, h) in enumerate(((0, 2), (2, 3), (5, 1)))
            for col, (x, w) in enumerate(((0, 1), (1, 4), (5, 3)))
            for r, g, b in (COLORS[row * 3 + col],))
        clear = '{ op = "clear"; color = [7 11 13 255]; }' if atlas else ""
        return f"{{ renderTextures.panel = {{ width = {8 + shift * 2}; height = {6 + shift * 2}; {options} }}; }}", f'{{ op = "paint"; texture = "panel"; commands = [ {clear} {draw} ]; }}'

    def _panel_command(self, attributes="", *, borders=BORDERS, width=20, height=18, x=4, y=4):
        return f'''{{ op = "textureNPatch"; texture = "panel"; x = {x}; y = {y}; width = {width}; height = {height};
          borders = {borders}; {attributes} }}'''

    def _panel_pixels(self, attributes="", *, target=False, options="", atlas=False, **kwargs):
        assets, prefix = self._panel_setup(target=target, options=options, atlas=atlas)
        return self._capture(f'''[ {{ op = "clear"; color = [0 0 0 255]; }} {prefix}
          {self._panel_command(attributes, **kwargs)} ]''', assets=assets)

    def test_texture_control_path_and_structured_defaults(self):
        commands = '[ { op = "clear"; color = [0 0 0 255]; } { op = "texture"; texture = "tex"; x = 4; y = 4; scale = 4; } ]'
        plain = self._capture(commands, assets=f"{{ textures.tex = {self.pattern_path}; }}")
        structured = self._capture(commands, assets=f"{{ textures.tex = {{ path = {self.pattern_path}; }}; }}")
        self.assertEqual(plain, structured)

    def test_texture_control_bilinear_pixels_images_and_targets(self):
        for target in (False, True):
            with self.subTest(target=target):
                pixels = self._sample_pixels('filter = "bilinear"; wrap = "clamp";', "scale = 4;", target=target)
                for y in range(8):
                    for x in range(8):
                        fx, fy = min(1, max(0, (x + 0.5) / 4 - 0.5)), min(1, max(0, (y + 0.5) / 4 - 0.5))
                        weights = ((1-fx)*(1-fy), fx*(1-fy), (1-fx)*fy, fx*fy)
                        expected = tuple(round(sum(c[k] * w for c, w in zip((COLORS[0], COLORS[1], COLORS[2], COLORS[3]), weights))) for k in range(3))
                        self.assert_pixel(pixels, 4 + x, 4 + y, expected, tolerance=1)

    def test_texture_control_point_pixels(self):
        for target in (False, True):
            pixels = self._sample_pixels('filter = "point";', "scale = 4;", target=target)
            for y in range(8):
                for x in range(8):
                    self.assert_pixel(pixels, 4 + x, 4 + y, COLORS[(y // 4) * 2 + x // 4])

    def test_texture_control_repeat_and_mirror_pixels(self):
        for target in (False, True):
            for wrap in ("repeat", "mirrorRepeat"):
                for flip_x, flip_y in ((False, False), (True, False), (False, True), (True, True)):
                    with self.subTest(target=target, wrap=wrap, flip_x=flip_x, flip_y=flip_y):
                        pixels = self._sample_pixels(f'wrap = "{wrap}";', f'''source = {{ x = 1; y = 1; width = 6; height = 6; }};
                          flipX = {str(flip_x).lower()}; flipY = {str(flip_y).lower()};''', target=target)
                        def index(i):
                            return i % 2 if wrap == "repeat" else (i % 4 if i % 4 < 2 else 3 - i % 4)
                        for y in range(6):
                            for x in range(6):
                                sx, sy = 1 + (5-x if flip_x else x), 1 + (5-y if flip_y else y)
                                self.assert_pixel(pixels, 4 + x, 4 + y, COLORS[index(sy) * 2 + index(sx)])

    def test_texture_control_clamp_and_legacy_bounds_remain_strict(self):
        for options in ('wrap = "clamp";', 'filter = "bilinear";', ''):
            for target in (False, True):
                assets, prefix = self._sampler(options, target=target)
                self.evaluate(f'''builtins.raylib {{ hidden = true; fps = 0; maxFrames = 1; assets = {assets}; }} (_: {{
                  commands = [ {prefix} {{ op = "texture"; texture = "tex"; x = 0; y = 0;
                    source = {{ x = 0; y = 0; width = 3; height = 2; }}; }} ]; }})''', error="source rectangle exceeds")

    def test_texture_control_invalid_asset_options(self):
        for group, base in (("textures", f"path = {self.pattern_path};"), ("renderTextures", "width = 2; height = 2;")):
            for attributes, error in (('filter = "cubic";', "unknown texture filter"), ('filter = true;', "expected a string"),
                                      ('wrap = "border";', "unknown texture wrap"), ('wrap = 1;', "expected a string"),
                                      ('typo = 1;', "unknown attribute 'typo'")):
                with self.subTest(group=group, attributes=attributes):
                    self.evaluate(f'''builtins.raylib {{ assets.{group}.tex = {{ {base} {attributes} }}; }}
                      (_: {{ commands = []; }})''', error=error)
        self.evaluate('builtins.raylib { assets.textures.tex = { filter = "point"; }; } (_: { commands = []; })', error="missing attribute 'path'")

    def test_texture_control_sampler_settings_are_per_asset(self):
        pixels = self._capture('''[ { op = "clear"; color = [0 0 0 255]; }
          { op = "texture"; texture = "smooth"; x = 0; y = 0; scale = 4; }
          { op = "texture"; texture = "sharp"; x = 8; y = 0; scale = 4; }
        ]''', assets=f'''{{ textures = {{ smooth = {{ path = {self.pattern_path}; filter = "bilinear"; wrap = "clamp"; }};
          sharp = {{ path = {self.pattern_path}; filter = "point"; }}; }}; }}''')
        self.assert_pixel(pixels, 11, 3, COLORS[0])
        self.assertNotEqual(pixels[3 * 32 + 3], COLORS[0])

    def test_texture_control_structured_store_paths(self):
        result = self.evaluate(f'''let p = builtins.path {{ path = builtins.toPath {self.pattern_path}; name = "filtered.png"; }};
        in builtins.raylib {{ hidden = true; fps = 0; maxFrames = 1;
          assets.textures.tex = {{ path = "${{p}}"; filter = "bilinear"; wrap = "clamp"; }};
        }} (_: {{ commands = [ {{ op = "texture"; texture = "tex"; x = 0; y = 0; }} ]; }})''', flags=["--read-write-mode"])
        self.assertEqual(result["frames"], 1)

    def test_texture_control_repaint_preserves_wrapping_and_updates_content(self):
        pixels = self._capture('''let color = if frame.frame == 0 then [255 0 0 255] else [255 255 255 255];
        in [ { op = "clear"; color = [0 0 0 255]; }
          { op = "paint"; texture = "tex"; commands = [ { op = "clear"; inherit color; } ]; }
          { op = "texture"; texture = "tex"; x = 4; y = 4;
            source = { x = 0; y = 0; width = 4; height = 4; }; }
        ]''', assets='{ renderTextures.tex = { width = 2; height = 2; filter = "bilinear"; wrap = "repeat"; }; }', frames=2)
        self.assertTrue(all(pixels[y * 32 + x] == (255, 255, 255) for y in range(4, 8) for x in range(4, 8)))

    def test_texture_control_repeated_crops_retain_scale_guards(self):
        assets, _ = self._sampler('wrap = "repeat";')
        self.evaluate(f'''builtins.raylib {{ hidden = true; fps = 0; maxFrames = 1; assets = {assets}; }}
          (_: {{ commands = [ {{ op = "texture"; texture = "tex"; x = 0; y = 0; scale = 3.0e38;
            source = {{ x = 0; y = 0; width = 4; height = 4; }}; }} ]; }})''', error="scaled texture dimensions")

    def test_texture_control_patch_validation_is_pure(self):
        command = self._panel_command('source = { x = 1; y = 1; width = 8; height = 6; };')
        for flag in ("--pure-eval", "--restrict-eval"):
            self.assertEqual(self.evaluate(f"builtins.raylibValidate [ {command} ]", flags=[flag], env={"DISPLAY": "", "WAYLAND_DISPLAY": ""}), 1)
        library = Path(__file__).resolve().parent.parent / "lib"
        self.assertEqual(self.evaluate(f"let ray = import {library}; in ray.validate [ (ray.textureNPatch {self._panel_command()}) ]"), 1)

    def test_texture_control_patch_required_fields(self):
        command = self._panel_command()
        for field in ("texture", "x", "y", "width", "height", "borders"):
            self.evaluate(f'builtins.raylibValidate [ (builtins.removeAttrs {command} ["{field}"]) ]', error=f"missing attribute '{field}'")
        for field in ("left", "top", "right", "bottom"):
            self.evaluate(f'''builtins.raylibValidate [ ({command} // {{
              borders = builtins.removeAttrs {BORDERS} ["{field}"]; }}) ]''', error=f"missing attribute '{field}'")

    def test_texture_control_patch_rejects_bad_fields(self):
        command = self._panel_command()
        for changes, error in (('width = -1;', "integer in"), ('height = 0.5;', "expected an integer"),
                                ('texture = "";', "texture name must not be empty"), ('borders = [];', "expected a set"),
                                ('rotation = 1.0e100;', "finite number"), ('tint = [];', "color must"),
                                ('origin = {};', "missing attribute 'x'"), ('origin = { x = 3.0e38; y = 3.0e38; };', "texture origin and dimensions"),
                                ('scale = 2;', "unknown attribute 'scale'"), ('flipX = true;', "unknown attribute 'flipX'"),
                                ('layout = "diagonal";', "unknown texture patch layout")):
            self.evaluate(f"builtins.raylibValidate [ ({command} // {{ {changes} }}) ]", error=error)
        for borders, error in (('{ left = -1; top = 0; right = 0; bottom = 0; }', "integer in"),
                                ('{ left = 1; top = 2; right = 3; bottom = 1; typo = 1; }', "unknown attribute 'typo'")):
            self.evaluate(f"builtins.raylibValidate [ {self._panel_command(borders=borders)} ]", error=error)

    def test_texture_control_patch_center_and_bounds(self):
        panel, _ = self._panel_images()
        for borders in ('{ left = 5; right = 3; top = 2; bottom = 1; }', '{ left = 1; right = 3; top = 5; bottom = 1; }',
                        '{ left = 2147483647; right = 2147483647; top = 0; bottom = 0; }'):
            command = self._panel_command(borders=borders)
            self.evaluate(f'''builtins.raylib {{ hidden = true; fps = 0; maxFrames = 1; assets.textures.panel = {panel}; }}
              (_: {{ commands = [ {command} ]; }})''', error="nonempty source center")
            self.evaluate(f"builtins.raylibValidate [ {self._panel_command('source = { x = 0; y = 0; width = 8; height = 6; };', borders=borders)} ]", error="nonempty source center")
        self.evaluate(f'''builtins.raylib {{ hidden = true; fps = 0; maxFrames = 1;
          assets.textures.panel = {{ path = {panel}; wrap = "repeat"; }};
        }} (_: {{ commands = [ {self._panel_command('source = { x = 1; y = 0; width = 8; height = 6; };')} ]; }})''', error="source rectangle exceeds")

    def test_texture_control_patch_source_validation(self):
        for source, error in (("[]", "expected a set"), ("{}", "missing attribute 'x'"),
                              ("{ x = -1; y = 0; width = 8; height = 6; }", "integer in"),
                              ("{ x = 0; y = 0; width = 0; height = 6; }", "integer in"),
                              ("{ x = 0; y = 0; width = 8; height = 6; typo = 1; }", "unknown attribute 'typo'")):
            self.evaluate(f"builtins.raylibValidate [ {self._panel_command(f'source = {source};')} ]", error=error)

    def test_texture_control_patch_fixed_borders_and_upright_targets(self):
        for target in (False, True):
            pixels = self._panel_pixels(target=target)
            for y in range(32):
                for x in range(32):
                    expected = (0, 0, 0)
                    if 4 <= x < 24 and 4 <= y < 22:
                        col = 0 if x < 5 else 1 if x < 21 else 2
                        row = 0 if y < 6 else 1 if y < 21 else 2
                        expected = COLORS[row * 3 + col]
                    self.assert_pixel(pixels, x, y, expected)

    def test_texture_control_patch_cropped_atlas(self):
        self.assertEqual(self._panel_pixels(), self._panel_pixels('source = { x = 1; y = 1; width = 8; height = 6; };', atlas=True))

    def test_texture_control_patch_cropped_render_texture(self):
        self.assertEqual(self._panel_pixels(), self._panel_pixels('source = { x = 1; y = 1; width = 8; height = 6; };', atlas=True, target=True))

    def test_texture_control_patch_bilinear_images_and_targets(self):
        image = self._panel_pixels(options='filter = "bilinear"; wrap = "clamp";')
        target = self._panel_pixels(options='filter = "bilinear"; wrap = "clamp";', target=True)
        self.assertTrue(all(abs(a-b) <= 1 for p, q in zip(image, target) for a, b in zip(p, q)))
        self.assertNotEqual(image[10 * 32 + 5], self._panel_pixels()[10 * 32 + 5])

    def test_texture_control_patch_small_destinations(self):
        for target in (False, True):
            pixels = self._panel_pixels(target=target, width=2, height=2)
            self.assert_pixel(pixels, 4, 4, COLORS[2])
            self.assert_pixel(pixels, 5, 4, COLORS[2])
            self.assert_pixel(pixels, 4, 5, COLORS[8])
            self.assert_pixel(pixels, 5, 5, COLORS[8])
            self.assert_pixel(pixels, 6, 5, (0, 0, 0))

    def test_texture_control_patch_zero_borders_and_zero_size(self):
        zero = '{ left = 0; top = 0; right = 0; bottom = 0; }'
        panel, _ = self._panel_images()
        plain = self._capture('[ { op = "clear"; color = [0 0 0 255]; } { op = "texture"; texture = "panel"; x = 4; y = 4; scale = 2; } ]', assets=f"{{ textures.panel = {panel}; }}")
        self.assertEqual(plain, self._panel_pixels(width=16, height=12, borders=zero))
        self.assertEqual(set(self._panel_pixels(width=0)), {(0, 0, 0)})
        self.assertEqual(set(self._panel_pixels(height=0)), {(0, 0, 0)})

    def test_texture_control_patch_tint_and_alpha(self):
        assets, prefix = self._panel_setup()
        pixels = self._capture(f'[ {{ op = "clear"; color = [0 0 255 255]; }} {prefix} {self._panel_command("tint = [255 0 0 128];")} ]', assets=assets)
        self.assert_pixel(pixels, 10, 10, (128, 0, 127), tolerance=1)
        self.assert_pixel(pixels, 4, 4, (128, 0, 127), tolerance=1)

    def test_texture_control_patch_rotation_and_panel_pivot(self):
        for target in (False, True):
            pixels = self._panel_pixels('rotation = 90; origin = { x = 10; y = 9; };', target=target, x=16, y=16)
            self.assert_pixel(pixels, 24, 6, COLORS[0])
            self.assert_pixel(pixels, 24, 24, COLORS[2])
            self.assert_pixel(pixels, 7, 6, COLORS[6])
            self.assert_pixel(pixels, 7, 24, COLORS[8])

    def test_texture_control_patch_large_compensating_pivot(self):
        for target in (False, True):
            reference = self._panel_pixels(target=target, x=0, y=0)
            actual = self._panel_pixels('origin = { x = 1073741824; y = 1073741824; };',
                                        target=target, x=1073741824, y=1073741824)
            self.assertEqual(actual, reference)

    def test_texture_control_patch_rejects_self_sampling_and_missing_assets(self):
        self.evaluate(f'''builtins.raylib {{ hidden = true; fps = 0; maxFrames = 1; assets.renderTextures.panel = {{ width = 8; height = 6; }}; }}
          (_: {{ commands = [ {{ op = "paint"; texture = "panel"; commands = [ {self._panel_command()} ]; }} ]; }})''', error="into its own paint")
        self.evaluate(f'''builtins.raylib {{ hidden = true; fps = 0; maxFrames = 1; }}
          (_: {{ commands = [ {self._panel_command()} ]; }})''', error="unknown texture 'panel'")

    def test_texture_control_patch_clip_camera_and_blend(self):
        assets, prefix = self._panel_setup(target=True)
        pixels = self._capture(f'''[ {{ op = "clear"; color = [0 0 0 255]; }} {prefix}
          {{ op = "clip"; x = 8; y = 8; width = 8; height = 8; commands = [
            {{ op = "camera2D"; camera = {{ zoom = 2; }}; commands = [ {self._panel_command()} ]; }}
          ]; }} ]''', assets=assets)
        self.assertTrue(any(pixel != (0, 0, 0) for pixel in pixels))
        self.assertTrue(all(pixel == (0, 0, 0) for y in range(32) for x in range(32)
                            for pixel in (pixels[y * 32 + x],) if not (8 <= x < 16 and 8 <= y < 16)))
        blended = self._capture(f'''[ {{ op = "clear"; color = [0 0 255 255]; }} {prefix}
          {{ op = "blend"; mode = "additive"; commands = [ {self._panel_command('tint = [255 0 0 128];')} ]; }} ]''', assets=assets)
        self.assert_pixel(blended, 10, 10, (128, 0, 255), tolerance=1)

    def test_texture_control_patch_camera_transform(self):
        for target in (False, True):
            assets, prefix = self._panel_setup(target=target)
            pixels = self._capture(f'''[ {{ op = "clear"; color = [0 0 0 255]; }} {prefix}
              {{ op = "camera2D"; camera = {{ zoom = 2; offset = {{ x = 4; y = 4; }}; }};
                 commands = [ {self._panel_command(x=1, y=1, width=12, height=10)} ]; }}
            ]''', assets=assets)
            for row, y in enumerate((6, 10, 25)):
                for col, x in enumerate((6, 8, 29)):
                    self.assert_pixel(pixels, x, y, COLORS[row * 3 + col])
            self.assert_pixel(pixels, 5, 5, (0, 0, 0))

    def test_texture_control_patch_shader(self):
        assets, prefix = self._panel_setup()
        shader = Path(__file__).resolve().parent.parent / "examples/shaders/tint.fs"
        assets = f'''({assets} // {{ shaders.fx = {{ fragment = {shader}; uniforms = {{ gain = {{ type = "float"; value = 0.5; }};
          tint = {{ type = "vec3"; value = [1 1 1]; }}; }}; }}; }})'''
        pixels = self._capture(f'''[ {{ op = "clear"; color = [0 0 0 255]; }} {prefix}
          {{ op = "shader"; shader = "fx"; commands = [ {self._panel_command()} ]; }} ]''', assets=assets)
        self.assert_pixel(pixels, 10, 10, (128, 128, 128), tolerance=1)
        self.assert_pixel(pixels, 4, 4, (128, 0, 0), tolerance=1)

    def test_texture_control_patch_into_another_render_texture(self):
        for target in (False, True):
            assets, prefix = self._panel_setup(target=target)
            assets = f'({assets} // {{ renderTextures = ({assets}.renderTextures or {{}}) // {{ canvas = {{ width = 32; height = 32; }}; }}; }})'
            pixels = self._capture(f'''[ {{ op = "clear"; color = [0 0 0 255]; }} {prefix}
              {{ op = "paint"; texture = "canvas"; commands = [ {{ op = "clear"; color = [0 0 0 255]; }} {self._panel_command()} ]; }}
              {{ op = "texture"; texture = "canvas"; x = 0; y = 0; }} ]''', assets=assets)
            self.assertEqual(pixels, self._panel_pixels())

    def test_texture_control_patch_validates_before_render(self):
        if not self.capture_library:
            self.skipTest("pass --capture-library to enable framebuffer tests")
        panel, _ = self._panel_images()
        capture = self.asset_directory / "invalid-patch.ppm"
        capture.unlink(missing_ok=True)
        self.evaluate(f'''builtins.raylib {{ hidden = true; fps = 0; maxFrames = 1; assets.textures.panel = {panel}; }}
          (_: {{ commands = [ {{ op = "clear"; color = [255 0 0 255]; }}
            {self._panel_command(borders='{ left = 8; top = 0; right = 0; bottom = 0; }')} ]; }})''', error="nonempty source center", env={
              "LD_PRELOAD": str(Path(self.capture_library).resolve()) + " " + os.environ.get("LD_PRELOAD", ""),
              "NIXRAY_TEST_CAPTURE": str(capture),
          })
        self.assertFalse(capture.exists())

    def test_texture_control_extreme_wrapped_crops_and_panels(self):
        assets, prefix = self._sampler('wrap = "repeat";', target=True)
        panel, _ = self._panel_images()
        result = self.evaluate(f'''builtins.raylib {{ width = 32; height = 32; hidden = true; fps = 0; maxFrames = 1;
          assets = {assets} // {{ textures.panel = {panel}; }};
        }} (_: {{ commands = [ {prefix}
          {{ op = "texture"; texture = "tex"; x = 0; y = 0; source = {{ x = 2147483647; y = 2147483647; width = 2147483647; height = 2147483647; }}; }}
          {self._panel_command(width=2147483647, height=2147483647)}
        ]; }})''')
        self.assertEqual(result["frames"], 1)

    def test_texture_control_example(self):
        example = Path(__file__).resolve().parent.parent / "examples/textures.nix"
        self.assertEqual(self.evaluate(f"import {example} {{ hidden = true; maxFrames = 2; }}"),
                         {"frames": 2, "state": {"width": 320, "height": 140}})
