"""Scoped native blending, batch ordering, and isolated render-target state."""

from itertools import permutations
import os
from pathlib import Path


MODES = ("alpha", "additive", "multiply", "subtract")
BACKGROUND = (20, 40, 80)
SOURCE = (100, 120, 200)


def nix_color(channels):
    return "[ " + " ".join(str(channel) for channel in channels) + " ]"


def rectangle(x, y, width, height, color):
    return (f'{{ op = "rectangle"; x = {x}; y = {y}; width = {width}; height = {height}; '
            f'color = {nix_color(color)}; }}')


def blend_rgb(mode, source=SOURCE, destination=BACKGROUND, alpha=128):
    """raylib's GL factors/equations, using normalized source alpha."""
    a = alpha / 255
    if mode == "alpha":
        channels = [s * a + d * (1 - a) for s, d in zip(source, destination)]
    elif mode == "additive":
        channels = [s * a + d for s, d in zip(source, destination)]
    elif mode == "multiply":
        channels = [s * d / 255 + d * (1 - a) for s, d in zip(source, destination)]
    else:
        channels = [s - d for s, d in zip(source, destination)]
    return tuple(max(0, min(255, round(channel))) for channel in channels)


class BlendCases:
    def _blend_pixels(self, mode, commands=None, *, alpha=128, assets="{}"):
        if commands is None:
            commands = f"[ {rectangle(4, 6, 8, 6, (*SOURCE, alpha))} ]"
        return self._capture(f'''[
          {{ op = "clear"; color = {nix_color((*BACKGROUND, 255))}; }}
          {{ op = "blend"; mode = "{mode}"; commands = {commands}; }}
        ]''', assets=assets)

    def test_blend_validation_is_pure(self):
        for flag in ("--pure-eval", "--restrict-eval"):
            for mode in MODES:
                with self.subTest(flag=flag, mode=mode):
                    self.assertEqual(self.evaluate(f'''builtins.raylibValidate [
                      {{ op = "blend"; mode = "{mode}"; commands = [
                        {{ op = "camera2D"; camera = {{}}; commands = [
                          {{ op = "clip"; x = 0; y = 0; width = 0; height = 0; commands = [
                            {{ op = "texture"; texture = "unloaded"; x = 0; y = 0; }}
                          ]; }}
                        ]; }}
                      ]; }}
                    ]''', flags=[flag], env={"DISPLAY": "", "WAYLAND_DISPLAY": ""}), 1)

    def test_blend_rejects_bad_commands(self):
        base = '{ op = "blend"; mode = "alpha"; commands = []; }'
        for override, error in (
            ('mode = "";', "unknown blend mode"),
            ('mode = "screen";', "unknown blend mode 'screen'"),
            ('mode = "ADDITIVE";', "unknown blend mode 'ADDITIVE'"),
            ('mode = "custom";', "unknown blend mode 'custom'"),
            ("mode = 1;", "expected a string"),
            ("mode = null;", "expected a string"),
            ("commands = null;", "expected a list"),
            ('commands = [ { op = "invalid-child"; } ];', "unknown drawing operation"),
            ('commands = [ { op = "rectangle"; } ];', "missing attribute 'x'"),
            ("typo = true;", "unknown attribute 'typo'"),
        ):
            with self.subTest(override=override):
                self.evaluate(f"builtins.raylibValidate [ ({base} // {{ {override} }}) ]", error=error)
        for field in ("mode", "commands"):
            with self.subTest(missing=field):
                self.evaluate(f'builtins.raylibValidate [ (builtins.removeAttrs {base} [ "{field}" ]) ]',
                              error=f"missing attribute '{field}'")

    def test_blend_children_validate_even_in_invisible_clips(self):
        self.evaluate('''builtins.raylibValidate [
          { op = "clip"; x = 0; y = 0; width = 0; height = 0; commands = [
            { op = "blend"; mode = "unknown"; commands = []; }
          ]; }
        ]''', error="unknown blend mode 'unknown'")
        for command, error in (
            ('{ op = "texture"; texture = "scene"; x = 0; y = 0; }', "into its own paint"),
            ('{ op = "paint"; texture = "other"; commands = []; }', "paint must not nest"),
        ):
            with self.subTest(paint_child=command):
                self.evaluate(f'''builtins.raylibValidate [
                  {{ op = "paint"; texture = "scene"; commands = [
                    {{ op = "blend"; mode = "additive"; commands = [ {command} ]; }}
                  ]; }}
                ]''', error=error)
        for command, error in (
            ('{ op = "texture"; texture = "missing"; x = 0; y = 0; }', "unknown texture 'missing'"),
            ('{ op = "text"; font = "missing"; text = "A"; x = 0; y = 0; size = 12; color = [0 0 0 255]; }',
             "unknown font 'missing'"),
            ('{ op = "paint"; texture = "missing"; commands = []; }', "unknown render texture 'missing'"),
        ):
            with self.subTest(command=command):
                self.evaluate(f'''builtins.raylib {{ hidden = true; fps = 0; maxFrames = 1; }} (_: {{
                  commands = [ {{ op = "clip"; x = 0; y = 0; width = 0; height = 0; commands = [
                    {{ op = "blend"; mode = "additive"; commands = [ {command} ]; }}
                  ]; }} ];
                }})''', error=error)

    def test_blend_nesting_limits(self):
        for mixed in (False, True):
            for depth in (64, 65):
                expression = f'''let nested = n: if n == 0 then [] else [ (
                  (if !{str(mixed).lower()} || n - (builtins.div n 3) * 3 == 0 then
                    {{ op = "blend"; mode = "additive"; }}
                   else if n - (builtins.div n 3) * 3 == 1 then
                    {{ op = "camera2D"; camera = {{}}; }}
                   else {{ op = "clip"; x = 0; y = 0; width = 0; height = 0; }})
                  // {{ commands = nested (n - 1); }}
                ) ]; in builtins.raylibValidate (nested {depth})'''
                with self.subTest(mixed=mixed, depth=depth):
                    if depth == 64:
                        self.assertEqual(self.evaluate(expression, flags=["--pure-eval"]), 1)
                    else:
                        self.evaluate(expression, error="nesting must not exceed 64 levels")

    def test_blend_and_paint_share_nesting_limit(self):
        for depth in (63, 64):
            expression = f'''let nested = n: if n == 0 then [ {{
              op = "paint"; texture = "scene"; commands = [];
            }} ] else [ {{ op = "blend"; mode = "alpha"; commands = nested (n - 1); }} ];
            in builtins.raylibValidate (nested {depth})'''
            with self.subTest(depth=depth):
                if depth == 63:
                    self.assertEqual(self.evaluate(expression, flags=["--pure-eval"]), 1)
                else:
                    self.evaluate(expression, error="paint nesting must not exceed 64 levels")

    def test_blend_helper(self):
        library = Path(__file__).resolve().parent.parent / "lib"
        self.assertEqual(self.evaluate(f'''let ray = import {library}; in ray.validate [
          (ray.blend {{ mode = "additive"; commands = [ (ray.clear ray.colors.red) ]; }})
        ]'''), 1)

    def test_blend_mode_equations_pixels(self):
        for mode in MODES:
            for alpha in (0, 128, 255):
                with self.subTest(mode=mode, alpha=alpha):
                    pixels = self._blend_pixels(mode, alpha=alpha)
                    expected = blend_rgb(mode, alpha=alpha)
                    for y in range(6, 12):
                        for x in range(4, 12):
                            self.assert_pixel(pixels, x, y, expected, tolerance=1)
                    self.assert_pixel(pixels, 3, 6, BACKGROUND)
                    self.assert_pixel(pixels, 12, 11, BACKGROUND)

    def test_blend_alpha_matches_unscoped_drawing(self):
        commands = f"[ {rectangle(4, 6, 8, 6, (*SOURCE, 128))} ]"
        self.assertEqual(self._blend_pixels("alpha", commands), self._capture(f'''[
          {{ op = "clear"; color = {nix_color((*BACKGROUND, 255))}; }}
        ] ++ {commands}'''))

    def test_blend_nested_modes_replace_and_restore(self):
        for parent in MODES:
            for child in MODES:
                with self.subTest(parent=parent, child=child):
                    pixels = self._capture(f'''[
                      {{ op = "clear"; color = {nix_color((*BACKGROUND, 255))}; }}
                      {{ op = "blend"; mode = "{parent}"; commands = [
                        {rectangle(2, 2, 4, 4, (*SOURCE, 128))}
                        {{ op = "blend"; mode = "{child}"; commands = [
                          {rectangle(10, 2, 4, 4, (*SOURCE, 128))}
                        ]; }}
                        {rectangle(18, 2, 4, 4, (*SOURCE, 128))}
                      ]; }}
                      {rectangle(26, 2, 4, 4, (*SOURCE, 128))}
                    ]''')
                    for x, mode in ((3, parent), (11, child), (19, parent), (27, "alpha")):
                        self.assert_pixel(pixels, x, 3, blend_rgb(mode), tolerance=1)
                    self.assert_pixel(pixels, 0, 0, BACKGROUND)

    def test_blend_changes_preserve_batch_order(self):
        pixels = self._capture(f'''[
          {{ op = "clear"; color = [0 0 0 255]; }}
          {rectangle(0, 0, 32, 32, (*BACKGROUND, 255))}
          {{ op = "blend"; mode = "additive"; commands = [
            {rectangle(4, 6, 8, 6, (*SOURCE, 128))}
          ]; }}
          {rectangle(16, 6, 8, 6, (*SOURCE, 128))}
        ]''')
        self.assert_pixel(pixels, 5, 7, blend_rgb("additive"), tolerance=1)
        self.assert_pixel(pixels, 17, 7, blend_rgb("alpha"), tolerance=1)
        self.assert_pixel(pixels, 0, 0, BACKGROUND)

    def test_blend_parent_survives_intervening_scopes(self):
        wrappers = (
            'op = "camera2D"; camera = {};',
            'op = "clip"; x = 0; y = 0; width = 32; height = 32;',
        )
        for wrapper in wrappers:
            with self.subTest(wrapper=wrapper):
                pixels = self._blend_pixels("additive", f'''[
                  {{ {wrapper} commands = [
                    {{ op = "blend"; mode = "alpha"; commands = [
                      {rectangle(4, 6, 8, 6, (*SOURCE, 128))}
                    ]; }}
                    {rectangle(16, 6, 8, 6, (*SOURCE, 128))}
                  ]; }}
                ]''')
                self.assert_pixel(pixels, 5, 7, blend_rgb("alpha"), tolerance=1)
                self.assert_pixel(pixels, 17, 7, blend_rgb("additive"), tolerance=1)

    def test_blend_empty_scopes_preserve_state(self):
        for mode in MODES:
            with self.subTest(mode=mode):
                pixels = self._blend_pixels("additive", f'''[
                  {{ op = "blend"; mode = "{mode}"; commands = []; }}
                  {rectangle(4, 6, 8, 6, (*SOURCE, 128))}
                ]''')
                self.assert_pixel(pixels, 5, 7, blend_rgb("additive"), tolerance=1)

    def test_blend_camera_clip_combinations_pixels(self):
        wrappers = {
            "blend": 'op = "blend"; mode = "additive";',
            "camera": 'op = "camera2D"; camera = { offset = { x = 4; y = 4; }; zoom = 2; };',
            "clip": 'op = "clip"; x = 8; y = 10; width = 4; height = 6;',
        }
        for order in permutations(wrappers):
            with self.subTest(order=order):
                commands = f"[ {rectangle(0, 0, 16, 16, (*SOURCE, 255))} ]"
                for kind in reversed(order):
                    commands = f"[ {{ {wrappers[kind]} commands = {commands}; }} ]"
                pixels = self._capture(f'''[
                  {{ op = "clear"; color = {nix_color((*BACKGROUND, 255))}; }}
                ] ++ {commands}''')
                expected = blend_rgb("additive", alpha=255)
                self.assertEqual(pixels, [expected if 8 <= x < 12 and 10 <= y < 16 else BACKGROUND
                                          for y in range(32) for x in range(32)])

    def test_blend_text_and_texture_pixels(self):
        assets = f"{{ textures.logo = {self.texture_path}; fonts.ui = {self.font_path}; }}"
        for mode in MODES:
            for command in (
                '{ op = "texture"; texture = "logo"; x = 4; y = 6; scale = 4; tint = [100 120 200 128]; }',
                '{ op = "text"; font = "ui"; text = "A"; x = 4; y = 6; size = 8; color = [100 120 200 128]; }',
            ):
                with self.subTest(mode=mode, command=command):
                    pixels = self._blend_pixels(mode, f"[ {command} ]", assets=assets)
                    self.assert_pixel(pixels, 5, 7, blend_rgb(mode), tolerance=1)
                    self.assert_pixel(pixels, 3, 5, BACKGROUND)

    def test_blend_clear_bypasses_blending_and_preserves_order(self):
        cleared = (60, 80, 100)
        for mode in MODES:
            with self.subTest(mode=mode):
                pixels = self._blend_pixels(mode, f'''[
                  {{ op = "clip"; x = 4; y = 6; width = 8; height = 6; commands = [
                    {rectangle(0, 0, 32, 32, (*SOURCE, 128))}
                    {{ op = "clear"; color = {nix_color((*cleared, 255))}; }}
                    {rectangle(4, 6, 4, 6, (*SOURCE, 128))}
                  ]; }}
                ]''')
                self.assert_pixel(pixels, 5, 7, blend_rgb(mode, destination=cleared), tolerance=1)
                self.assert_pixel(pixels, 9, 7, cleared)
                self.assert_pixel(pixels, 3, 7, BACKGROUND)

    def test_blend_paint_isolates_alpha_and_restores_parent(self):
        for mode in MODES:
            with self.subTest(mode=mode):
                pixels = self._blend_pixels(mode, f'''[
                  {rectangle(0, 0, 8, 8, (*SOURCE, 255))}
                  {{ op = "paint"; texture = "scene"; commands = [
                    {{ op = "clear"; color = {nix_color((*BACKGROUND, 255))}; }}
                    {rectangle(0, 0, 16, 16, (*SOURCE, 255))}
                  ]; }}
                  {rectangle(0, 8, 8, 8, (*SOURCE, 255))}
                  {{ op = "blend"; mode = "alpha"; commands = [
                    {{ op = "texture"; texture = "scene"; x = 16; y = 0; }}
                  ]; }}
                ]''', assets="{ renderTextures.scene = { width = 16; height = 16; }; }")
                expected = blend_rgb(mode, alpha=255)
                self.assert_pixel(pixels, 4, 4, expected, tolerance=1)
                self.assert_pixel(pixels, 4, 12, expected, tolerance=1)
                self.assert_pixel(pixels, 20, 4, SOURCE)
                self.assert_pixel(pixels, 20, 12, SOURCE)

    def test_blend_inside_paint_restores_target_alpha(self):
        pixels = self._capture(f'''[
          {{ op = "clear"; color = [0 0 0 255]; }}
          {{ op = "blend"; mode = "multiply"; commands = [
            {{ op = "paint"; texture = "scene"; commands = [
              {{ op = "clear"; color = {nix_color((*BACKGROUND, 255))}; }}
              {{ op = "blend"; mode = "additive"; commands = [
                {rectangle(0, 0, 8, 16, (*SOURCE, 255))}
              ]; }}
              {rectangle(8, 0, 8, 16, (*SOURCE, 255))}
            ]; }}
          ]; }}
          {{ op = "texture"; texture = "scene"; x = 0; y = 0; }}
        ]''', assets="{ renderTextures.scene = { width = 16; height = 16; }; }")
        self.assert_pixel(pixels, 4, 4, blend_rgb("additive", alpha=255))
        self.assert_pixel(pixels, 12, 4, SOURCE)

    def test_blend_render_texture_stamps_use_current_mode(self):
        for mode in MODES:
            with self.subTest(mode=mode):
                pixels = self._blend_pixels(mode, f'''[
                  {{ op = "paint"; texture = "scene"; commands = [
                    {rectangle(0, 0, 8, 8, (*SOURCE, 255))}
                  ]; }}
                  {{ op = "texture"; texture = "scene"; x = 4; y = 6; }}
                ]''', assets="{ renderTextures.scene = { width = 8; height = 8; }; }")
                self.assert_pixel(pixels, 5, 7, blend_rgb(mode, alpha=255), tolerance=1)
                self.assert_pixel(pixels, 3, 5, BACKGROUND)

    def test_blend_render_texture_alpha_uses_native_factors(self):
        a = 128 / 255
        target_alpha = {"alpha": round(255 * (a * a + 1 - a)),
                        "additive": 255, "multiply": 255, "subtract": 0}
        for mode in MODES:
            with self.subTest(mode=mode):
                pixels = self._capture(f'''[
                  {{ op = "clear"; color = [0 0 0 255]; }}
                  {{ op = "paint"; texture = "scene"; commands = [
                    {{ op = "clear"; color = {nix_color((*BACKGROUND, 255))}; }}
                    {{ op = "blend"; mode = "{mode}"; commands = [
                      {rectangle(0, 0, 8, 8, (*SOURCE, 128))}
                    ]; }}
                  ]; }}
                  {{ op = "texture"; texture = "scene"; x = 4; y = 6; }}
                ]''', assets="{ renderTextures.scene = { width = 8; height = 8; }; }")
                # RGBA8 target storage quantizes once before normal-alpha stamping.
                expected = tuple(round(channel * target_alpha[mode] / 255) for channel in blend_rgb(mode))
                self.assert_pixel(pixels, 5, 7, expected, tolerance=1)

    def test_blend_paint_preserves_camera_and_window_clip(self):
        pixels = self._blend_pixels("additive", f'''[
          {{ op = "camera2D"; camera = {{ offset = {{ x = 4; y = 4; }}; zoom = 2; }}; commands = [
            {{ op = "clip"; x = 8; y = 8; width = 8; height = 8; commands = [
              {{ op = "paint"; texture = "scene"; commands = [
                {rectangle(0, 0, 8, 8, (255, 255, 255, 255))}
              ]; }}
              {rectangle(0, 0, 16, 16, (*SOURCE, 255))}
            ]; }}
          ]; }}
          {{ op = "blend"; mode = "alpha"; commands = [
            {{ op = "texture"; texture = "scene"; x = 20; y = 20; }}
          ]; }}
        ]''', assets="{ renderTextures.scene = { width = 8; height = 8; }; }")
        self.assert_pixel(pixels, 10, 10, blend_rgb("additive", alpha=255))
        self.assert_pixel(pixels, 7, 10, BACKGROUND)
        self.assert_pixel(pixels, 16, 10, BACKGROUND)
        self.assert_pixel(pixels, 22, 22, (255, 255, 255))

    def test_blend_deep_nesting_pixels(self):
        pixels = self._capture(f'''let nested = n: if n == 0 then [
          {rectangle(4, 6, 8, 6, (*SOURCE, 128))}
        ] else [ {{ op = "blend";
          mode = if n - (builtins.div n 2) * 2 == 0 then "alpha" else "additive";
          commands = nested (n - 1);
        }} ]; in [ {{ op = "clear"; color = {nix_color((*BACKGROUND, 255))}; }} ] ++ nested 64 ++ [
          {rectangle(16, 6, 8, 6, (*SOURCE, 128))}
        ]''')
        self.assert_pixel(pixels, 5, 7, blend_rgb("additive"), tolerance=1)
        self.assert_pixel(pixels, 17, 7, blend_rgb("alpha"), tolerance=1)

    def test_blend_does_not_leak_between_frames(self):
        for mode in MODES:
            with self.subTest(mode=mode):
                pixels = self._capture(f'''[
                  {{ op = "clear"; color = {nix_color((*BACKGROUND, 255))}; }}
                ] ++ (if frame.frame == 0 then [
                  {{ op = "blend"; mode = "{mode}"; commands = [
                    {rectangle(4, 6, 8, 6, (*SOURCE, 255))}
                  ]; }}
                ] else [ {rectangle(4, 6, 8, 6, (*SOURCE, 128))} ])''', frames=2)
                self.assert_pixel(pixels, 5, 7, blend_rgb("alpha"), tolerance=1)

    def test_blend_batch_validates_before_drawing(self):
        if not self.capture_library:
            self.skipTest("pass --capture-library to enable framebuffer pixel tests")
        destination = self.asset_directory / "invalid-blend.ppm"
        preload = str(Path(self.capture_library).resolve())
        if os.environ.get("LD_PRELOAD"):
            preload += " " + os.environ["LD_PRELOAD"]
        self.evaluate('''builtins.raylib { hidden = true; fps = 0; maxFrames = 1; } (_: {
          commands = [
            { op = "clear"; color = [0 0 255 255]; }
            { op = "blend"; mode = "additive"; commands = [
              { op = "clear"; color = [255 0 0 255]; }
              { op = "invalid-child"; }
            ]; }
          ];
        })''', error="unknown drawing operation", env={"LD_PRELOAD": preload, "NIXRAY_TEST_CAPTURE": str(destination)})
        self.assertFalse(destination.exists(), "invalid blend batch reached EndDrawing")

    def test_blend_exception_cleanup(self):
        self.assertEqual(self.evaluate('''let
          config = { hidden = true; fps = 0; maxFrames = 1; };
          failed = builtins.tryEval (builtins.raylib config (_: { commands = [
            { op = "blend"; mode = "additive"; commands = [ (throw "blend child failed") ]; }
          ]; }));
        in assert !failed.success; builtins.raylib config (_: { commands = [
          { op = "blend"; mode = "multiply"; commands = []; }
        ]; })'''), {"frames": 1, "state": None})

    def test_blend_example(self):
        example = Path(__file__).resolve().parent.parent / "examples/blend.nix"
        self.assertEqual(self.evaluate(f"import {example} {{ hidden = true; maxFrames = 2; }}"),
                         {"frames": 2, "state": {"alpha": 160}})

    def test_blend_example_wheel_input(self):
        example = Path(__file__).resolve().parent.parent / "examples/blend.nix"
        self.assertEqual(self._input_evaluate(f"import {example} {{ hidden = true; maxFrames = 4; }}"),
                         {"frames": 4, "state": {"alpha": 148}})
