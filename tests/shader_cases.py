"""Fragment shaders: typed defaults, native reflection and scoped uniform state."""

from itertools import permutations
import json
import os
from pathlib import Path


FRAGMENT = """#version 330
in vec2 fragTexCoord;
in vec4 fragColor;
uniform sampler2D texture0;
uniform vec4 colDiffuse;
uniform float gain;
uniform int channel;
uniform vec2 offset;
uniform vec3 tint;
uniform vec4 extra;
out vec4 finalColor;
void main() {
    vec4 color = texture(texture0, fragTexCoord) * colDiffuse * fragColor;
    vec3 rgb = color.rgb * tint * gain + vec3(offset, 0.0) + extra.rgb;
    if (channel == 1) rgb = rgb.bgr;
    finalColor = vec4(rgb, color.a * extra.a);
}
"""
INVERSE = """#version 330
in vec2 fragTexCoord;
in vec4 fragColor;
uniform sampler2D texture0;
uniform vec4 colDiffuse;
out vec4 finalColor;
void main() {
    vec4 color = texture(texture0, fragTexCoord) * colDiffuse * fragColor;
    finalColor = vec4(vec3(1.0) - color.rgb, color.a);
}
"""
DEFAULTS = '''{
  gain = { type = "float"; value = 1; };
  channel = { type = "int"; value = 0; };
  offset = { type = "vec2"; value = [ 0 0 ]; };
  tint = { type = "vec3"; value = [ 1 1 1 ]; };
  extra = { type = "vec4"; value = [ 0 0 0 1 ]; };
}'''
RECTANGLE = '{ op = "rectangle"; x = 4; y = 6; width = 8; height = 6; color = [100 120 200 255]; }'


class ShaderCases:
    def _shader_file(self, name, source):
        path = self.asset_directory / name
        path.write_text(source)
        return json.dumps(str(path))

    def _shader_spec(self, *, fragment=None, defaults=DEFAULTS):
        fragment = fragment or self._shader_file("typed.fs", FRAGMENT)
        return f"{{ fragment = {fragment}; uniforms = {defaults}; }}"

    def _shader_assets(self, extra=""):
        inverse = self._shader_file("inverse.fs", INVERSE)
        return (f"{{ shaders.fx = {self._shader_spec()}; "
                f"shaders.inverse = {{ fragment = {inverse}; }}; {extra} }}")

    def _shader_run(self, commands, *, assets=None, **kwargs):
        return self.evaluate(f'''builtins.raylib {{
          width = 32; height = 32; hidden = true; fps = 0; maxFrames = 1;
          assets = {assets or self._shader_assets()};
        }} (_: {{ commands = {commands}; }})''', **kwargs)

    def _shader_pixels(self, uniforms="", commands=None, *, extra_assets=""):
        commands = commands or f"[ {RECTANGLE} ]"
        return self._capture(f'''[
          {{ op = "clear"; color = [0 0 0 255]; }}
          {{ op = "shader"; shader = "fx"; uniforms = {{ {uniforms} }}; commands = {commands}; }}
        ]''', assets=self._shader_assets(extra_assets))

    def test_shader_validation_without_assets_is_pure(self):
        for flag in ("--pure-eval", "--restrict-eval"):
            with self.subTest(flag=flag):
                self.assertEqual(self.evaluate('''builtins.raylibValidate [
                  { op = "shader"; shader = "unloaded";
                    uniforms = { gain = 0.5; channel = 1; tint = [1 0.5 1]; };
                    commands = [ { op = "texture"; texture = "unloaded"; x = 0; y = 0; } ]; }
                ]''', flags=[flag], env={"DISPLAY": "", "WAYLAND_DISPLAY": ""}), 1)

    def test_shader_rejects_bad_commands(self):
        base = '{ op = "shader"; shader = "fx"; commands = []; }'
        for override, error in (
            ('shader = "";', "shader name must not be empty"),
            ("shader = 1;", "expected a string"),
            ("uniforms = [];", "expected a set"),
            ("uniforms.gain = true;", "expected"),
            ('uniforms.gain = "bad";', "expected"),
            ("uniforms.gain = 1.0e100;", "finite number"),
            ("uniforms.tint = [1 2 1.0e100];", "finite number"),
            ("uniforms.tint = [];", "between 2 and 4"),
            ("uniforms.tint = [1];", "between 2 and 4"),
            ("uniforms.tint = [1 2 3 4 5];", "between 2 and 4"),
            ('uniforms."bad.name" = 1;', "GLSL identifiers"),
            ('uniforms."" = 1;', "GLSL identifiers"),
            ("uniforms.gl_test = 1;", "reserved gl_ prefix"),
            ("uniforms.texture0 = 1;", "managed by raylib"),
            ("commands = null;", "expected a list"),
            ('commands = [ { op = "invalid-child"; } ];', "unknown drawing operation"),
            ("typo = true;", "unknown attribute 'typo'"),
        ):
            with self.subTest(override=override):
                self.evaluate(f"builtins.raylibValidate [ ({base} // {{ {override} }}) ]", error=error)
        for field in ("shader", "commands"):
            with self.subTest(missing=field):
                self.evaluate(f'builtins.raylibValidate [ (builtins.removeAttrs {base} [ "{field}" ]) ]',
                              error=f"missing attribute '{field}'")

    def test_shader_asset_specs_and_defaults_validate(self):
        fragment = self._shader_file("typed.fs", FRAGMENT)
        for spec, error in (
            (f"{{ fragment = {fragment}; typo = 1; }}", "unknown attribute 'typo'"),
            ("{}", "missing attribute 'fragment'"),
            ('{ fragment = "relative.fs"; }', "asset paths must be"),
            (f"{{ fragment = {fragment}; uniforms = []; }}", "expected a set"),
            (f'{{ fragment = {fragment}; uniforms.x = {{ type = "bool"; value = 1; }}; }}', "unknown uniform type"),
            (f'{{ fragment = {fragment}; uniforms.x = {{ type = "float"; }}; }}', "missing attribute 'value'"),
            (f'{{ fragment = {fragment}; uniforms.x = {{ value = 1; }}; }}', "missing attribute 'type'"),
            (f'{{ fragment = {fragment}; uniforms.x = {{ type = "float"; value = 1; typo = 0; }}; }}',
             "unknown attribute 'typo'"),
        ):
            with self.subTest(spec=spec):
                self._shader_run("[]", assets=f"{{ shaders.bad = {spec}; }}", error=error)
        for kind, value, error in (
            ("float", "1.0e100", "finite number"),
            ("int", "0.5", "expected an integer"),
            ("int", "2147483648", "integer in"),
            ("int", "-2147483649", "integer in"),
            ("vec2", "[1]", "exactly 2"),
            ("vec3", "[1 2]", "exactly 3"),
            ("vec4", "[1 2 3]", "exactly 4"),
            ("vec4", "[1 2 3 true]", "expected"),
        ):
            with self.subTest(kind=kind, value=value):
                spec = self._shader_spec(defaults=f'{{ x = {{ type = "{kind}"; value = {value}; }}; }}')
                self._shader_run("[]", assets=f"{{ shaders.bad = {spec}; }}", error=error)

    def test_shader_reserved_uniforms_rejected(self):
        for name in ("mvp", "colDiffuse", "texture0", "texture1", "matModel"):
            with self.subTest(name=name):
                spec = self._shader_spec(defaults=f'{{ {name} = {{ type = "float"; value = 1; }}; }}')
                self._shader_run("[]", assets=f"{{ shaders.bad = {spec}; }}", error="managed by raylib")

    def test_shader_load_failure_does_not_accept_default_fallback(self):
        for path in (json.dumps(str(self.asset_directory / "missing.fs")),
                     self._shader_file("empty.fs", ""),
                     self._shader_file("invalid.fs", "#version 330\nthis is not GLSL"),
                     self._shader_file("link-failure.fs", "#version 330\nin vec3 fragColor;\nout vec4 finalColor;\n"
                                       "void main() { finalColor = vec4(fragColor, 1.0); }")):
            with self.subTest(path=path):
                self._shader_run("[]", assets=f"{{ shaders.bad = {{ fragment = {path}; }}; }}",
                                 error="could not load shader 'bad'")

    def test_shader_reflection_checks_native_types_and_active_uniforms(self):
        for defaults, error in (
            ('{ gain = { type = "int"; value = 1; }; }', "incompatible GLSL type"),
            ('{ channel = { type = "float"; value = 1; }; }', "incompatible GLSL type"),
            ('{ tint = { type = "vec4"; value = [1 1 1 1]; }; }', "incompatible GLSL type"),
            ('{ missing = { type = "float"; value = 1; }; }', "missing, optimized out or an array"),
        ):
            with self.subTest(defaults=defaults):
                self._shader_run("[]", assets=f"{{ shaders.bad = {self._shader_spec(defaults=defaults)}; }}", error=error)
        for source, uniform in (
            (INVERSE.replace("out vec4 finalColor;", "uniform float unused;\nout vec4 finalColor;"), "unused"),
            ("#version 330\nuniform float weights[2];\nout vec4 finalColor;\n"
             "void main() { finalColor = vec4(weights[0] + weights[1]); }", "weights"),
        ):
            with self.subTest(uniform=uniform):
                fragment = self._shader_file(f"{uniform}.fs", source)
                spec = self._shader_spec(fragment=fragment,
                                         defaults=f'{{ {uniform} = {{ type = "float"; value = 1; }}; }}')
                self._shader_run("[]", assets=f"{{ shaders.bad = {spec}; }}", error="missing, optimized out or an array")

    def test_shader_uniform_overrides_match_asset_schema(self):
        for uniforms, error in (
            ("missing = 1;", "unknown uniform 'missing'"),
            ("gain = [1 2];", "expected"),
            ("channel = 0.5;", "expected an integer"),
            ("channel = 2147483648;", "integer in"),
            ("channel = -2147483649;", "integer in"),
            ("offset = [1 2 3];", "exactly 2"),
            ("tint = [1 2];", "exactly 3"),
            ("extra = [1 2 3];", "exactly 4"),
        ):
            with self.subTest(uniforms=uniforms):
                self._shader_run(f'[ {{ op = "shader"; shader = "fx"; uniforms = {{ {uniforms} }}; commands = []; }} ]',
                                 error=error)

    def test_shader_unknown_asset_is_rejected_even_in_empty_clip(self):
        self._shader_run('''[ { op = "clip"; x = 0; y = 0; width = 0; height = 0; commands = [
          { op = "shader"; shader = "missing"; commands = []; }
        ]; } ]''', error="unknown shader 'missing'")
        for command, error in (
            ('{ op = "texture"; texture = "scene"; x = 0; y = 0; }', "into its own paint"),
            ('{ op = "paint"; texture = "other"; commands = []; }', "paint must not nest"),
        ):
            with self.subTest(paint_child=command):
                self.evaluate(f'''builtins.raylibValidate [
                  {{ op = "paint"; texture = "scene"; commands = [
                    {{ op = "shader"; shader = "unloaded"; commands = [ {command} ]; }}
                  ]; }}
                ]''', error=error)

    def test_shader_all_uniform_types_pixels(self):
        for uniforms, expected in (
            ("", (100, 120, 200)),
            ("gain = 0.5;", (50, 60, 100)),
            ("channel = 1;", (200, 120, 100)),
            ("offset = [0.2 0.1];", (151, 146, 200)),
            ("tint = [1 0.5 0.25];", (100, 60, 50)),
            ("extra = [0.1 0.2 0.0 1];", (126, 171, 200)),
            ("gain = 0.5; channel = 1; tint = [1 0 0];", (0, 0, 50)),
        ):
            with self.subTest(uniforms=uniforms):
                pixels = self._shader_pixels(uniforms)
                self.assert_pixel(pixels, 5, 7, expected, tolerance=1)
                self.assert_pixel(pixels, 3, 7, (0, 0, 0))

    def test_shader_integer_extremes(self):
        for channel in (-2147483648, 2147483647):
            with self.subTest(channel=channel):
                self.assert_pixel(self._shader_pixels(f"channel = {channel};"), 5, 7, (100, 120, 200))

    def test_shader_nested_same_program_restores_uniforms_and_default_shader(self):
        pixels = self._capture('''[
          { op = "clear"; color = [0 0 0 255]; }
          { op = "shader"; shader = "fx"; uniforms.gain = 0.5; commands = [
            { op = "rectangle"; x = 2; y = 2; width = 4; height = 4; color = [100 120 200 255]; }
            { op = "shader"; shader = "fx"; uniforms.gain = 1; commands = [
              { op = "rectangle"; x = 8; y = 2; width = 4; height = 4; color = [100 120 200 255]; }
            ]; }
            { op = "rectangle"; x = 14; y = 2; width = 4; height = 4; color = [100 120 200 255]; }
            { op = "shader"; shader = "inverse"; commands = [
              { op = "rectangle"; x = 20; y = 2; width = 4; height = 4; color = [100 120 200 255]; }
            ]; }
          ]; }
          { op = "rectangle"; x = 26; y = 2; width = 4; height = 4; color = [100 120 200 255]; }
        ]''', assets=self._shader_assets())
        for x, expected in ((3, (50, 60, 100)), (9, (100, 120, 200)), (15, (50, 60, 100)),
                            (21, (155, 135, 55)), (27, (100, 120, 200))):
            self.assert_pixel(pixels, x, 3, expected, tolerance=1)

    def test_shader_child_uses_asset_defaults_not_parent_overrides(self):
        pixels = self._shader_pixels("tint = [1 0 0];", '''[
          { op = "shader"; shader = "fx"; uniforms.gain = 0.5; commands = [
            { op = "rectangle"; x = 4; y = 6; width = 8; height = 6; color = [100 120 200 255]; }
          ]; }
          { op = "rectangle"; x = 16; y = 6; width = 8; height = 6; color = [100 120 200 255]; }
        ]''')
        self.assert_pixel(pixels, 5, 7, (50, 60, 100), tolerance=1)
        self.assert_pixel(pixels, 17, 7, (100, 0, 0))

    def test_shader_defaults_reset_across_siblings_and_frames(self):
        pixels = self._capture(f'''[
          {{ op = "clear"; color = [0 0 0 255]; }}
          {{ op = "shader"; shader = "fx"; uniforms.gain = 0.25; commands = [ {RECTANGLE} ]; }}
          {{ op = "shader"; shader = "fx";
            uniforms = if frame.frame == 0 then {{ gain = 0.5; }} else {{}};
            commands = [
              {{ op = "rectangle"; x = 16; y = 6; width = 8; height = 6; color = [100 120 200 255]; }}
            ]; }}
        ]''', assets=self._shader_assets(), frames=2)
        self.assert_pixel(pixels, 5, 7, (25, 30, 50), tolerance=1)
        self.assert_pixel(pixels, 17, 7, (100, 120, 200))

    def test_shader_parent_survives_camera_clip_and_blend_scopes(self):
        for wrapper in ('op = "camera2D"; camera = {};',
                        'op = "clip"; x = 0; y = 0; width = 32; height = 32;',
                        'op = "blend"; mode = "alpha";'):
            with self.subTest(wrapper=wrapper):
                pixels = self._shader_pixels("gain = 0.5;", f'''[
                  {{ {wrapper} commands = [
                    {{ op = "shader"; shader = "fx"; uniforms.gain = 1; commands = [ {RECTANGLE} ]; }}
                    {{ op = "rectangle"; x = 16; y = 6; width = 8; height = 6; color = [100 120 200 255]; }}
                  ]; }}
                ]''')
                self.assert_pixel(pixels, 5, 7, (100, 120, 200))
                self.assert_pixel(pixels, 17, 7, (50, 60, 100), tolerance=1)

    def test_shader_camera_clip_blend_combinations_pixels(self):
        wrappers = {
            "shader": 'op = "shader"; shader = "fx"; uniforms.gain = 0.5;',
            "camera": 'op = "camera2D"; camera = { offset = { x = 4; y = 4; }; zoom = 2; };',
            "clip": 'op = "clip"; x = 8; y = 10; width = 4; height = 6;',
        }
        for order in permutations(wrappers):
            with self.subTest(order=order):
                commands = '[ { op = "rectangle"; x = 0; y = 0; width = 16; height = 16; color = [100 120 200 255]; } ]'
                for kind in reversed(order):
                    commands = f"[ {{ {wrappers[kind]} commands = {commands}; }} ]"
                pixels = self._capture(f'''[
                  {{ op = "clear"; color = [20 40 80 255]; }}
                  {{ op = "blend"; mode = "additive"; commands = {commands}; }}
                ]''', assets=self._shader_assets())
                for y in range(32):
                    for x in range(32):
                        expected = (70, 100, 180) if 8 <= x < 12 and 10 <= y < 16 else (20, 40, 80)
                        self.assert_pixel(pixels, x, y, expected, tolerance=1)

    def test_shader_text_and_texture_pixels(self):
        extra = f"textures.logo = {self.texture_path}; fonts.ui = {self.font_path};"
        for command in (
            '{ op = "texture"; texture = "logo"; x = 4; y = 6; scale = 4; tint = [100 120 200 255]; }',
            '{ op = "text"; font = "ui"; text = "A"; x = 4; y = 6; size = 8; color = [100 120 200 255]; }',
        ):
            with self.subTest(command=command):
                pixels = self._shader_pixels("gain = 0.5;", f"[ {command} ]", extra_assets=extra)
                self.assert_pixel(pixels, 5, 7, (50, 60, 100), tolerance=1)

    def test_shader_clear_bypasses_shader_and_preserves_order(self):
        pixels = self._shader_pixels("gain = 0.5;", f'''[
          {{ op = "clip"; x = 4; y = 6; width = 8; height = 6; commands = [
            {RECTANGLE}
            {{ op = "clear"; color = [0 0 255 255]; }}
            {{ op = "rectangle"; x = 4; y = 6; width = 4; height = 6; color = [100 120 200 255]; }}
          ]; }}
        ]''')
        self.assert_pixel(pixels, 5, 7, (50, 60, 100), tolerance=1)
        self.assert_pixel(pixels, 9, 7, (0, 0, 255))
        self.assert_pixel(pixels, 3, 7, (0, 0, 0))

    def test_shader_paint_isolates_default_program_and_restores_parent(self):
        pixels = self._capture('''[
          { op = "clear"; color = [0 0 0 255]; }
          { op = "shader"; shader = "fx"; uniforms.gain = 0.5; commands = [
            { op = "rectangle"; x = 0; y = 0; width = 8; height = 8; color = [100 120 200 255]; }
            { op = "paint"; texture = "scene"; commands = [
              { op = "rectangle"; x = 0; y = 0; width = 16; height = 16; color = [100 120 200 255]; }
            ]; }
            { op = "rectangle"; x = 0; y = 8; width = 8; height = 8; color = [100 120 200 255]; }
          ]; }
          { op = "texture"; texture = "scene"; x = 16; y = 0; }
        ]''', assets=self._shader_assets("renderTextures.scene = { width = 16; height = 16; };"))
        self.assert_pixel(pixels, 4, 4, (50, 60, 100), tolerance=1)
        self.assert_pixel(pixels, 4, 12, (50, 60, 100), tolerance=1)
        self.assert_pixel(pixels, 20, 4, (100, 120, 200))

    def test_shader_inside_paint_restores_unshaded_target(self):
        pixels = self._capture('''[
          { op = "clear"; color = [0 0 0 255]; }
          { op = "shader"; shader = "fx"; uniforms.gain = 0.5; commands = [
            { op = "paint"; texture = "scene"; commands = [
              { op = "shader"; shader = "fx"; uniforms.gain = 0.25; commands = [
                { op = "rectangle"; x = 0; y = 0; width = 8; height = 16; color = [100 120 200 255]; }
              ]; }
              { op = "rectangle"; x = 8; y = 0; width = 8; height = 16; color = [100 120 200 255]; }
            ]; }
          ]; }
          { op = "texture"; texture = "scene"; x = 0; y = 0; }
        ]''', assets=self._shader_assets("renderTextures.scene = { width = 16; height = 16; };"))
        self.assert_pixel(pixels, 4, 4, (25, 30, 50), tolerance=1)
        self.assert_pixel(pixels, 12, 4, (100, 120, 200))

    def test_shader_postprocess_render_texture_orientation(self):
        pixels = self._capture('''[
          { op = "clear"; color = [0 0 0 255]; }
          { op = "paint"; texture = "scene"; commands = [
            { op = "rectangle"; x = 0; y = 0; width = 8; height = 4; color = [200 0 0 255]; }
            { op = "rectangle"; x = 0; y = 4; width = 8; height = 4; color = [0 0 200 255]; }
          ]; }
          { op = "shader"; shader = "fx"; uniforms.gain = 0.5; commands = [
            { op = "texture"; texture = "scene"; x = 4; y = 6; scale = 2; }
          ]; }
        ]''', assets=self._shader_assets("renderTextures.scene = { width = 8; height = 8; };"))
        self.assert_pixel(pixels, 6, 8, (100, 0, 0), tolerance=1)
        self.assert_pixel(pixels, 6, 16, (0, 0, 100), tolerance=1)

    def test_shader_paint_preserves_camera_blend_and_window_clip(self):
        pixels = self._capture('''[
          { op = "clear"; color = [20 40 80 255]; }
          { op = "shader"; shader = "fx"; uniforms.gain = 0.5; commands = [
            { op = "blend"; mode = "additive"; commands = [
              { op = "camera2D"; camera = { offset = { x = 4; y = 4; }; zoom = 2; }; commands = [
                { op = "clip"; x = 8; y = 8; width = 8; height = 8; commands = [
                  { op = "paint"; texture = "scene"; commands = [
                    { op = "rectangle"; x = 0; y = 0; width = 8; height = 8; color = [100 120 200 255]; }
                  ]; }
                  { op = "rectangle"; x = 0; y = 0; width = 16; height = 16; color = [100 120 200 255]; }
                ]; }
              ]; }
            ]; }
          ]; }
          { op = "texture"; texture = "scene"; x = 20; y = 20; }
        ]''', assets=self._shader_assets("renderTextures.scene = { width = 8; height = 8; };"))
        self.assert_pixel(pixels, 10, 10, (70, 100, 180), tolerance=1)
        self.assert_pixel(pixels, 7, 10, (20, 40, 80))
        self.assert_pixel(pixels, 16, 10, (20, 40, 80))
        self.assert_pixel(pixels, 22, 22, (100, 120, 200))

    def test_shader_nesting_and_mixed_scope_limits(self):
        for mixed in (False, True):
            for depth in (64, 65):
                expression = f'''let nested = n: if n == 0 then [] else [ (
                  (if !{str(mixed).lower()} || n - (builtins.div n 3) * 3 == 0 then
                    {{ op = "shader"; shader = "unloaded"; }}
                   else if n - (builtins.div n 3) * 3 == 1 then {{ op = "blend"; mode = "alpha"; }}
                   else {{ op = "camera2D"; camera = {{}}; }}) // {{ commands = nested (n - 1); }}
                ) ]; in builtins.raylibValidate (nested {depth})'''
                with self.subTest(mixed=mixed, depth=depth):
                    if depth == 64:
                        self.assertEqual(self.evaluate(expression, flags=["--pure-eval"]), 1)
                    else:
                        self.evaluate(expression, error="nesting must not exceed 64 levels")

    def test_shader_deep_nesting_pixels(self):
        pixels = self._capture(f'''let nested = n: if n == 0 then [ {RECTANGLE} ] else [ {{
          op = "shader"; shader = "fx"; uniforms.gain = if n == 1 then 0.5 else 1;
          commands = nested (n - 1);
        }} ]; in [ {{ op = "clear"; color = [0 0 0 255]; }} ] ++ nested 64 ++ [
          {{ op = "rectangle"; x = 16; y = 6; width = 8; height = 6; color = [100 120 200 255]; }}
        ]''', assets=self._shader_assets())
        self.assert_pixel(pixels, 5, 7, (50, 60, 100), tolerance=1)
        self.assert_pixel(pixels, 17, 7, (100, 120, 200))

    def test_shader_and_paint_share_nesting_limit(self):
        for depth in (63, 64):
            expression = f'''let nested = n: if n == 0 then [ {{
              op = "paint"; texture = "scene"; commands = [];
            }} ] else [ {{ op = "shader"; shader = "unloaded"; commands = nested (n - 1); }} ];
            in builtins.raylibValidate (nested {depth})'''
            with self.subTest(depth=depth):
                if depth == 63:
                    self.assertEqual(self.evaluate(expression, flags=["--pure-eval"]), 1)
                else:
                    self.evaluate(expression, error="paint nesting must not exceed 64 levels")

    def test_shader_asset_path_values_and_store_context(self):
        path = self._shader_file("typed.fs", FRAGMENT)
        for expression, flags in ((f"builtins.toPath {path}", []),
                                  (f'"${{builtins.path {{ path = builtins.toPath {path}; name = "nixray-shader"; }}}}"',
                                   ["--read-write-mode"])):
            with self.subTest(expression=expression):
                self.assertEqual(self._shader_run('[ { op = "shader"; shader = "fx"; commands = []; } ]',
                    assets=f"{{ shaders.fx = {self._shader_spec(fragment=expression)}; }}", flags=flags),
                    {"frames": 1, "state": None})

    def test_shader_exception_and_partial_loading_cleanup(self):
        bad = self._shader_file("invalid.fs", "#version 330\ninvalid shader")
        assets = self._shader_assets()
        bad_assets = f"({assets} // {{ shaders = {{ a = {self._shader_spec()}; z = {{ fragment = {bad}; }}; }}; }})"
        # Native EvalErrors are not catchable by Nix's tryEval, unlike throw.
        self._shader_run("[]", assets=bad_assets, error="could not load shader 'z'")
        self.assertEqual(self.evaluate(f'''let
          config = {{ hidden = true; fps = 0; maxFrames = 1; assets = {assets}; }};
          failed = builtins.tryEval (builtins.raylib config (_: {{ commands = [
            {{ op = "shader"; shader = "fx"; commands = [ (throw "shader child failed") ]; }}
          ]; }}));
        in assert !failed.success; builtins.raylib config (_: {{ commands = []; }})'''),
          {"frames": 1, "state": None})

    def test_shader_batch_validates_before_drawing(self):
        if not self.capture_library:
            self.skipTest("pass --capture-library to enable framebuffer pixel tests")
        destination = self.asset_directory / "invalid-shader.ppm"
        preload = str(Path(self.capture_library).resolve())
        if os.environ.get("LD_PRELOAD"):
            preload += " " + os.environ["LD_PRELOAD"]
        self._shader_run('''[
          { op = "clear"; color = [255 0 0 255]; }
          { op = "shader"; shader = "fx"; commands = [ { op = "invalid-child"; } ]; }
        ]''', error="unknown drawing operation", env={"LD_PRELOAD": preload, "NIXRAY_TEST_CAPTURE": str(destination)})
        self.assertFalse(destination.exists(), "invalid shader batch reached EndDrawing")

    def test_shader_helper_and_example(self):
        root = Path(__file__).resolve().parent.parent
        self.assertEqual(self.evaluate(f'''let ray = import {root / 'lib'}; in ray.validate [
          (ray.shader {{ shader = "unloaded"; uniforms.gain = 0.5; commands = []; }})
        ]'''), 1)
        self.assertEqual(self.evaluate(f"import {root / 'examples/shader.nix'} {{ hidden = true; maxFrames = 2; }}"),
                         {"frames": 2, "state": {"gain": 1.0}})

    def test_shader_example_wheel_input(self):
        example = Path(__file__).resolve().parent.parent / "examples/shader.nix"
        result = self._input_evaluate(f"import {example} {{ hidden = true; maxFrames = 4; }}")
        self.assertEqual(result["frames"], 4)
        self.assertAlmostEqual(result["state"]["gain"], 0.925)
