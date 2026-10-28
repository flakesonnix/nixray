"""Named render textures: painting, stamping, persistence and validation."""

import os
from pathlib import Path


def quadrant_paint(quadrant_colors):
    """Paint an 8x8 texture with solid quadrants, plus a solid blue background."""
    return f'''[
      {{ op = "rectangle"; x = 0; y = 0; width = 8; height = 8; color = [0 0 255 255]; }}
      {{ op = "rectangle"; x = 0; y = 0; width = 2; height = 2; color = {quadrant_colors[0]}; }}
      {{ op = "rectangle"; x = 6; y = 0; width = 2; height = 2; color = {quadrant_colors[1]}; }}
      {{ op = "rectangle"; x = 0; y = 6; width = 2; height = 2; color = {quadrant_colors[2]}; }}
      {{ op = "rectangle"; x = 6; y = 6; width = 2; height = 2; color = {quadrant_colors[3]}; }}
    ]'''


QUADRANTS = ((255, 0, 0), (0, 255, 0), (255, 255, 0), (200, 122, 255))
QUADRANT_NIX = tuple(f"[ {r} {g} {b} 255 ]" for r, g, b in QUADRANTS)
# Middle pixel of each 2x2 quadrant after a native (12..19) textured region.
QUADRANT_CENTS = ((13, 13), (18, 13), (13, 18), (18, 18))


class RenderCases:
    def _painted(self, texture, commands, stamps, *, attrs="clear = false;", extra_assets="", frames=1):
        paint = f'{{ op = "paint"; texture = "{texture}"; {attrs} commands = {commands}; }}'
        assets = ('{ renderTextures = { mural = { width = 16; height = 16; }; '
                  f'cloth = {{ width = 8; height = 8; }}; }}; {extra_assets} }}')
        return self._capture(f'''
          [ {{ op = "clear"; color = [0 0 0 255]; }} {paint} ] ++ {stamps}''', assets=assets, frames=frames)

    def _quadrated(self, flip):
        return self._painted("cloth", quadrant_paint(QUADRANT_NIX),
                             f'[ {{ op = "texture"; texture = "cloth"; x = 12; y = 12; {flip} }} ]')

    def test_paint_validation_is_pure(self):
        self.assertEqual(self.evaluate('''builtins.raylibValidate [
          { op = "paint"; texture = "scene"; clear = false; commands = [
            { op = "camera2D"; camera = {}; commands = [
              { op = "clip"; x = 0; y = 0; width = 4; height = 4; commands = [
                { op = "texture"; texture = "unloaded"; x = 0; y = 0; }
              ]; }
            ]; }
          ]; }
        ]''', flags=["--pure-eval"], env={"DISPLAY": "", "WAYLAND_DISPLAY": ""}), 1)

    def test_bad_paint_commands(self):
        base = '{ op = "paint"; texture = "scene"; commands = []; }'
        for command, error in (
            ('{ op = "paint"; commands = []; }', "missing attribute 'texture'"),
            ('{ op = "paint"; texture = "scene"; }', "missing attribute 'commands'"),
            ('{ op = "paint"; texture = ""; commands = []; }', "texture name must not be empty"),
            ('{ op = "paint"; texture = "scene"; commands = null; }', "expected a list"),
            ('{ op = "paint"; texture = "scene"; commands = []; clear = 1; }', "expected a Boolean"),
            ('{ op = "paint"; texture = "scene"; commands = []; typo = true; }', "unknown attribute 'typo'"),
            ('{ op = "paint"; texture = "scene"; commands = [ { op = "invalid-child"; } ]; }',
             "unknown drawing operation"),
            ('{ op = "paint"; texture = "scene"; clear = true; commands = [ { op = "paint"; texture = "scene"; '
             'commands = []; } ]; }', "paint must not nest inside another paint"),
        ):
            with self.subTest(command=command):
                self.evaluate(f"builtins.raylibValidate [ {command} ]", error=error)
        for field in ("texture", "commands"):
            with self.subTest(missing=field):
                self.evaluate(f'''builtins.raylibValidate [ (builtins.removeAttrs
                  {{ op = "paint"; texture = "scene"; commands = []; }} [ "{field}" ]) ]''',
                              error=f"missing attribute '{field}'")

    def test_pure_self_stamp_rejected(self):
        self.evaluate('''builtins.raylibValidate [
          { op = "paint"; texture = "wheel"; commands = [
            { op = "texture"; texture = "wheel"; x = 0; y = 0; }
          ]; }
        ]''', error="cannot stamp texture 'wheel' into its own paint")

    def test_paint_nesting_limit(self):
        for depth in (63, 64):
            expression = f'''let nested = n: if n == 0 then [ {{
              op = "paint"; texture = "scene"; commands = [];
            }} ] else [ {{
              op = "clip"; x = 0; y = 0; width = 0; height = 0; commands = nested (n - 1);
            }} ]; in builtins.raylibValidate (nested {depth})'''
            with self.subTest(depth=depth):
                if depth <= 63:
                    self.assertEqual(self.evaluate(expression, flags=["--pure-eval"]), 1)
                else:
                    self.evaluate(expression, error="paint nesting must not exceed 64 levels")

    def test_render_texture_assets_load(self):
        self.assertEqual(self.evaluate('''builtins.raylib { width = 64; height = 64; hidden = true; fps = 0;
          maxFrames = 2; assets.renderTextures.mural = { width = 16; height = 16;
                                                          }; } (_: { commands = []; })'''),
          {"frames": 2, "state": None})

    def test_bad_render_texture_assets(self):
        for spec, error in (
            ("{ width = 0; height = 16; }", "'width' must be an integer in [1, 16384]"),
            ("{ width = -1; height = 16; }", "'width' must be an integer in [1, 16384]"),
            ("{ width = 16385; height = 16; }", "'width' must be an integer in [1, 16384]"),
            ("{ width = 16.5; height = 16; }", "expected an integer"),
            ("{ height = 16; }", "missing attribute 'width'"),
            ("{ width = 16; height = 0; }", "'height' must be an integer in [1, 16384]"),
            ("{ width = 16; height = 16; typo = true; }", "unknown attribute 'typo'"),
        ):
            with self.subTest(spec=spec):
                self.evaluate(f'''builtins.raylib {{ width = 64; height = 64; hidden = true; fps = 0;
                  maxFrames = 1; assets.renderTextures.bad = {spec}; }} (_: {{ commands = []; }})''', error=error)

    def test_duplicate_render_texture_name(self):
        self.evaluate(f'''builtins.raylib {{ width = 64; height = 64; hidden = true; fps = 0; maxFrames = 1;
          assets = {{ textures.bad = {self.texture_path};
                     renderTextures.bad = {{ width = 16; height = 16; }}; }}; }} (_: {{ commands = []; }})''',
                      error="asset name 'bad' is declared more than once")

    def test_unknown_render_texture(self):
        for command, error in (
            ('{ op = "paint"; texture = "ghost"; commands = []; }', "unknown render texture 'ghost'"),
            ('{ op = "paint"; texture = "logo"; commands = []; }', "texture 'logo' is not a render texture"),
        ):
            with self.subTest(command=command):
                self.evaluate(f'''builtins.raylib {{
                  width = 64; height = 64; hidden = true; fps = 0; maxFrames = 1;
                  assets.textures.logo = {self.texture_path};
                }} (_: {{ commands = [ {command} ]; }})''', error=error)

    def test_render_texture_source_bounds(self):
        self.evaluate('''builtins.raylib { width = 64; height = 64; hidden = true; fps = 0; maxFrames = 1;
          assets.renderTextures.mural.width = 16; assets.renderTextures.mural.height = 16; } (_: {
          commands = [ { op = "texture"; texture = "mural"; x = 0; y = 0;
                         source = { x = 15; y = 0; width = 2; height = 1; }; } ];
        })''', error="source rectangle exceeds texture 'mural'")

    def test_paint_helper(self):
        root = Path(__file__).resolve().parent.parent
        self.assertEqual(self.evaluate(f'''let ray = import {root / 'lib'}; in ray.validate [
          (ray.paint {{ texture = "scene"; commands = [ (ray.clear ray.colors.red) ]; }}) ]'''), 1)

    def test_paint_stamp_upright(self):
        pixels = self._quadrated("")
        for (x, y), color in zip(QUADRANT_CENTS, QUADRANTS):
            self.assert_pixel(pixels, x, y, color)
        # An inverted UV traversal would move the top-left quadrant down.
        self.assert_pixel(pixels, 13, 18, (255, 255, 0))
        self.assert_pixel(pixels, 15, 15, (0, 0, 255))
        self.assert_pixel(pixels, 11, 12, (0, 0, 0))
        self.assert_pixel(pixels, 20, 19, (0, 0, 0))

    def test_paint_stamp_scaled(self):
        pixels = self._painted("mural", '''[
          { op = "rectangle"; x = 0; y = 0; width = 16; height = 16; color = [200 100 50 255]; }
          { op = "rectangle"; x = 2; y = 2; width = 2; height = 2; color = [255 0 0 255]; }
        ]''', '[ { op = "texture"; texture = "mural"; x = 4; y = 4; scale = 4; } ]')
        for y in range(12, 20):
            with self.subTest(y=y):
                self.assert_pixel(pixels, 12, y, (255, 0, 0))
        self.assert_pixel(pixels, 10, 10, (200, 100, 50))
        self.assert_pixel(pixels, 20, 20, (200, 100, 50))
        self.assert_pixel(pixels, 3, 4, (0, 0, 0))

    def test_paint_flipped_stamp_pixels(self):
        mirrored = {
            "": QUADRANTS,
            "flipX = true;": (QUADRANTS[1], QUADRANTS[0], QUADRANTS[3], QUADRANTS[2]),
            "flipY = true;": (QUADRANTS[2], QUADRANTS[3], QUADRANTS[0], QUADRANTS[1]),
            "flipX = true; flipY = true;": (QUADRANTS[3], QUADRANTS[2], QUADRANTS[1], QUADRANTS[0]),
        }
        for flip, colors in mirrored.items():
            with self.subTest(flip=flip):
                pixels = self._quadrated(flip)
                for (x, y), color in zip(QUADRANT_CENTS, colors):
                    self.assert_pixel(pixels, x, y, color)
                self.assert_pixel(pixels, 15, 15, (0, 0, 255))

    def test_paint_crop_pixels(self):
        pixels = self._painted("mural", '''[
          { op = "rectangle"; x = 0; y = 0; width = 16; height = 16; color = [0 0 255 255]; }
          { op = "rectangle"; x = 0; y = 0; width = 4; height = 4; color = [255 0 0 255]; }
        ]''', '''[ { op = "texture"; texture = "mural"; x = 2; y = 2; scale = 2;
                    source = { x = 0; y = 0; width = 6; height = 6; }; } ]''')
        self.assert_pixel(pixels, 6, 6, (255, 0, 0))
        self.assert_pixel(pixels, 9, 9, (255, 0, 0))
        self.assert_pixel(pixels, 11, 11, (0, 0, 255))
        self.assert_pixel(pixels, 12, 6, (0, 0, 255))
        self.assert_pixel(pixels, 14, 14, (0, 0, 0))

    def test_paint_persistence_between_frames(self):
        paint_once = '''let
          paint = [ { op = "paint"; texture = "mural"; commands = [
            { op = "rectangle"; x = 6; y = 6; width = 4; height = 4; color = [255 0 0 255]; }
          ]; } ];
          stamp = [ { op = "texture"; texture = "mural"; x = 8; y = 8; } ];
        in [ { op = "clear"; color = [0 0 0 255]; } ]
          ++ (if frame.frame == 0 then paint else []) ++ stamp'''
        pixels = self._capture(paint_once,
                               assets="{ renderTextures.mural = { width = 16; height = 16; }; }", frames=3)
        self.assert_pixel(pixels, 15, 15, (255, 0, 0))
        self.assert_pixel(pixels, 10, 10, (0, 0, 0))
        # Painting never again must be the only difference with frame 3.
        control = self._capture('''[ { op = "clear"; color = [0 0 0 255]; } ]
          ++ [ { op = "texture"; texture = "mural"; x = 8; y = 8; } ]''',
                               assets="{ renderTextures.mural = { width = 16; height = 16; }; }", frames=3)
        self.assertEqual(set(control), {(0, 0, 0)})

    def test_incremental_paint(self):
        commands = '''[ { op = "rectangle"; x = frame.frame * 5; y = 0; width = 3; height = 3;
                         color = [255 0 0 255]; } ]'''
        pixels = self._painted("mural", commands,
                               '[ { op = "texture"; texture = "mural"; x = 8; y = 8; } ]', frames=3)
        for x in (9, 14, 19):
            with self.subTest(x=x):
                self.assert_pixel(pixels, x, 9, (255, 0, 0))
        self.assert_pixel(pixels, 12, 9, (0, 0, 0))
        self.assert_pixel(pixels, 22, 9, (0, 0, 0))

    def test_paint_clip_texture_space(self):
        pixels = self._painted("mural", '''[
          { op = "rectangle"; x = 0; y = 0; width = 16; height = 16; color = [0 0 255 255]; }
          { op = "clip"; x = 2; y = 2; width = 4; height = 4; commands = [
            { op = "rectangle"; x = 0; y = 0; width = 16; height = 16; color = [255 0 0 255]; }
          ]; }
        ]''', '[ { op = "texture"; texture = "mural"; x = 8; y = 8; } ]')
        # Texture coordinates: the stamp at (8, 8) shows texture (2..5) at (10..13).
        self.assert_pixel(pixels, 10, 10, (255, 0, 0))
        self.assert_pixel(pixels, 13, 13, (255, 0, 0))
        self.assert_pixel(pixels, 9, 9, (0, 0, 255))
        self.assert_pixel(pixels, 14, 14, (0, 0, 255))
        self.assert_pixel(pixels, 10, 8, (0, 0, 255))
        self.assert_pixel(pixels, 18, 18, (0, 0, 255))

    def test_paint_clear_inside_clip(self):
        pixels = self._painted("mural", '''[
          { op = "rectangle"; x = 0; y = 0; width = 16; height = 16; color = [0 0 255 255]; }
          { op = "clip"; x = 0; y = 0; width = 4; height = 4; commands = [
            { op = "clear"; color = [255 0 0 255]; }
          ]; }
        ]''', '[ { op = "texture"; texture = "mural"; x = 8; y = 8; } ]')
        self.assert_pixel(pixels, 8, 8, (255, 0, 0))
        self.assert_pixel(pixels, 11, 11, (255, 0, 0))
        self.assert_pixel(pixels, 12, 8, (0, 0, 255))
        self.assert_pixel(pixels, 8, 12, (0, 0, 255))

    def test_paint_camera_inside_and_outside(self):
        pixels = self._capture('''[
          { op = "clear"; color = [0 0 0 255]; }
          { op = "camera2D"; camera = { offset = { x = 10; y = 10; }; zoom = 1; }; commands = [
            { op = "paint"; texture = "mural"; clear = false; commands = [
              { op = "pixel"; x = 0; y = 0; color = [255 0 0 255]; }
            ]; }
            { op = "pixel"; x = 1; y = 1; color = [0 255 0 255]; }
          ]; }
          { op = "texture"; texture = "mural"; x = 0; y = 0; }
        ]''', assets="{ renderTextures.mural = { width = 16; height = 16; }; }")
        self.assert_pixel(pixels, 0, 0, (255, 0, 0))
        # The camera must survive EndTextureMode for the sibling and later draws.
        self.assert_pixel(pixels, 11, 11, (0, 255, 0))
        self.assert_pixel(pixels, 1, 1, (0, 0, 0))

    def test_paint_inside_window_clip(self):
        pixels = self._capture('''[
          { op = "clear"; color = [0 0 0 255]; }
          { op = "clip"; x = 8; y = 8; width = 4; height = 4; commands = [
            { op = "paint"; texture = "mural"; commands = [
              { op = "rectangle"; x = 0; y = 0; width = 16; height = 16; color = [255 0 0 255]; }
            ]; }
            { op = "texture"; texture = "mural"; x = 0; y = 0; }
          ]; }
        ]''', assets="{ renderTextures.mural = { width = 16; height = 16; }; }")
        self.assert_clip_region(pixels, 8, 8, 12, 12)

    def test_untouched_render_texture_transparent(self):
        pixels = self._capture('''[
          { op = "clear"; color = [255 0 255 255]; }
          { op = "texture"; texture = "mural"; x = 0; y = 0; }
        ]''', assets="{ renderTextures.mural = { width = 16; height = 16; }; }")
        self.assertEqual(set(pixels), {(255, 0, 255)})

    def test_paint_composes_textured_assets(self):
        pixels = self._painted("mural", '''[
          { op = "rectangle"; x = 0; y = 0; width = 16; height = 16; color = [0 0 255 255]; }
          { op = "texture"; texture = "logo"; x = 2; y = 2; }
        ]''', '[ { op = "texture"; texture = "mural"; x = 8; y = 8; scale = 4; } ]',
                              extra_assets=f"textures.logo = {self.texture_path};")
        self.assert_pixel(pixels, 18, 18, (255, 255, 255))
        self.assert_pixel(pixels, 10, 10, (0, 0, 255))
        self.assert_pixel(pixels, 12, 12, (0, 0, 255))
        self.assert_pixel(pixels, 27, 27, (0, 0, 255))

    def test_paint_batch_validates_before_drawing(self):
        if not self.capture_library:
            self.skipTest("pass --capture-library to enable framebuffer pixel tests")
        destination = self.asset_directory / "invalid-paint.ppm"
        preload = str(Path(self.capture_library).resolve())
        if os.environ.get("LD_PRELOAD"):
            preload += " " + os.environ["LD_PRELOAD"]
        self.evaluate('''builtins.raylib { hidden = true; maxFrames = 1; fps = 0;
          assets.renderTextures.mural.width = 8; assets.renderTextures.mural.height = 8; } (_: {
          commands = [ { op = "paint"; texture = "mural"; commands = [
            { op = "clear"; color = [255 0 0 255]; }
            { op = "invalid-child"; }
          ]; } ];
        })''', error="unknown drawing operation", env={"LD_PRELOAD": preload, "NIXRAY_TEST_CAPTURE": str(destination)})
        self.assertFalse(destination.exists(), "invalid paint batch reached EndDrawing")

    def test_paint_exception_cleanup(self):
        self.assertEqual(self.evaluate('''let
          config = { hidden = true; maxFrames = 1; fps = 0;
                     assets.renderTextures.mural = { width = 8; height = 8; }; };
          failed = builtins.tryEval (builtins.raylib config (_: { commands = [
            { op = "paint"; texture = "mural"; commands = [ (throw "paint child failed") ]; }
          ]; }));
        in assert !failed.success; builtins.raylib config (_: { commands = []; })'''),
          {"frames": 1, "state": None})

    def test_render_example(self):
        example = Path(__file__).resolve().parent.parent / "examples/render.nix"
        self.assertEqual(self.evaluate(f"import {example} {{ hidden = true; maxFrames = 2; }}"),
                         {"frames": 2, "state": 2})
        self.assertEqual(self.evaluate(f"import {example} {{ hidden = true; maxFrames = 5; }}"),
                         {"frames": 5, "state": 5})
