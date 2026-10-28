"""Font loading options and text measurement through the real evaluator."""

import json
import os
from pathlib import Path


class TextCases:
    def _measure_text(self, options, *, config=None):
        return self.evaluate(f'''(builtins.raylib {config or self.asset_config} (frame: {{
          commands = []; state = frame.measureText {options};
        }})).state''')

    def _truetype_path(self):
        path = os.environ.get("NIXRAY_TEST_FONT")
        if not path:
            self.skipTest("set NIXRAY_TEST_FONT to exercise TrueType options")
        return json.dumps(path)

    def test_font_path_set_compatibility(self):
        for path in (self.font_path, f"builtins.toPath {self.font_path}"):
            with self.subTest(path=path):
                config = f"({self.asset_config} // {{ assets.fonts.ui = {{ path = {path}; }}; }})"
                self.assertEqual(self._measure_text('{ font = "ui"; text = "AA"; size = 12; }',
                                                    config=config), {"width": 25.0, "height": 12.0})

    def test_font_options_store_context(self):
        directory = json.dumps(str(self.asset_directory))
        self.assertEqual(self.evaluate(f'''let
          source = builtins.path {{ path = builtins.toPath {directory}; name = "nixray-font-options"; }};
        in (builtins.raylib ({self.asset_config} // {{
          assets.fonts.ui = {{ path = "${{source}}/tiny.fnt"; }};
        }}) (frame: {{ commands = []; state = frame.measureText {{ font = "ui"; text = "A"; size = 12; }}; }})).state''',
          flags=["--read-write-mode"]), {"width": 12.0, "height": 12.0})

    def test_truetype_font_options(self):
        path = self._truetype_path()
        for options in ("size = 48;", "codepoints = [ 63 65 228 955 ];",
                        "size = 48; codepoints = [ 63 65 228 955 ];"):
            with self.subTest(options=options):
                config = f"({self.asset_config} // {{ assets.fonts.ui = {{ path = {path}; {options} }}; }})"
                measured = self._measure_text('{ font = "ui"; text = "Aäλ"; size = 24; }', config=config)
                self.assertGreater(measured["width"], 0)
                self.assertEqual(measured["height"], 24.0)

    def test_bad_font_options(self):
        for options, error in (
            ("{}", "missing attribute 'path'"),
            (f"{{ path = {self.font_path}; typo = true; }}", "unknown attribute 'typo'"),
            ('{ path = "relative.ttf"; }', "asset paths must be"),
            ('{ path = 1; }', "asset paths must be"),
            ('{ path = "/font.ttf"; size = 0; }', "'font size' must be"),
            ('{ path = "/font.ttf"; size = 513; }', "'font size' must be"),
            ('{ path = "/font.ttf"; size = 24.5; }', "expected an integer"),
            ('{ path = "/font.ttf"; codepoints = []; }', "between 1 and 4096"),
            ('{ path = "/font.ttf"; codepoints = builtins.genList (x: x + 1) 4097; }', "between 1 and 4096"),
            ('{ path = "/font.ttf"; codepoints = null; }', "expected a list"),
            ('{ path = "/font.ttf"; codepoints = [ 0 ]; }', "'font codepoint' must be"),
            ('{ path = "/font.ttf"; codepoints = [ 1114112 ]; }', "'font codepoint' must be"),
            ('{ path = "/font.ttf"; codepoints = [ 55296 ]; }', "not surrogates"),
            ('{ path = "/font.ttf"; codepoints = [ 57343 ]; }', "not surrogates"),
            ('{ path = "/font.ttf"; codepoints = [ 65 65 ]; }', "duplicates"),
            ('{ path = "/font.ttf"; codepoints = [ true ]; }', "expected an integer"),
            (f"{{ path = {self.font_path}; size = 32; }}", "require a .ttf or .otf font"),
            (f"{{ path = {self.font_path}; codepoints = [ 65 ]; }}", "require a .ttf or .otf font"),
        ):
            with self.subTest(options=options):
                self.evaluate(f'''builtins.raylib ({self.asset_config} // {{ assets.fonts.ui = {options}; }})
                  (_: {{ commands = []; }})''', error=error)

    def test_customized_font_load_failure(self):
        self.evaluate(f'''builtins.raylib ({self.asset_config} // {{
          assets.fonts.ui = {{ path = {self.bad_font_path}; size = 24; codepoints = [ 63 65 ]; }};
        }}) (_: {{ commands = []; }})''', error="could not load font 'ui'")

    def test_measure_custom_font(self):
        for text, size, expected in (
            ('""', 12, {"width": 0.0, "height": 0.0}),
            ('"A"', 12, {"width": 12.0, "height": 12.0}),
            ('"AA"', 12, {"width": 25.0, "height": 12.0}),
            ('"AA"', 1, {"width": 3.0, "height": 1.0}),
            ('"A\\nAA"', 12, {"width": 25.0, "height": 26.0}),
            ('"\\n\\n"', 12, {"width": 0.0, "height": 40.0}),
            ('"λ🙂"', 12, {"width": 25.0, "height": 12.0}),
        ):
            with self.subTest(text=text, size=size):
                self.assertEqual(self._measure_text(f'{{ font = "ui"; text = {text}; size = {size}; }}'), expected)

    def test_measure_default_font(self):
        small = self._measure_text('{ text = "Hello"; size = 1; }')
        normal = self._measure_text('{ text = "Hello"; size = 10; }')
        large = self._measure_text('{ text = "Hello"; size = 20; }')
        self.assertEqual(small, normal)
        self.assertGreater(normal["width"], 0)
        self.assertEqual(normal["height"], 10.0)
        self.assertEqual(large, {"width": normal["width"] * 2, "height": 20.0})
        self.assertEqual(self._measure_text('{ text = ""; size = 20; }'), {"width": 0.0, "height": 0.0})

    def test_bad_text_measurement(self):
        for options, error in (
            ('[]', "expected a set"),
            ('{}', "missing attribute 'text'"),
            ('{ text = "A"; }', "missing attribute 'size'"),
            ('{ text = false; size = 10; }', "expected a string"),
            ('{ text = "A"; size = 0; }', "'size' must be"),
            ('{ text = "A"; size = 1.5; }', "expected an integer"),
            ('{ text = "A"; size = 10; font = ""; }', "font name must not be empty"),
            ('{ text = "A"; size = 10; font = "missing"; }', "unknown font 'missing'"),
            ('{ text = "A"; size = 10; typo = true; }', "unknown attribute 'typo'"),
        ):
            with self.subTest(options=options):
                self.evaluate(f'''builtins.raylib {self.asset_config} (frame: {{
                  commands = []; state = frame.measureText {options};
                }})''', error=error)

    def test_measurement_survives_window(self):
        self.assertEqual(self.evaluate(f'''let
          result = builtins.raylib {self.asset_config} (frame: {{ commands = []; state = frame.measureText; }});
        in result.state {{ font = "ui"; text = "AA"; size = 12; }}'''), {"width": 25.0, "height": 12.0})

    def test_measurement_survives_other_window(self):
        self.assertEqual(self.evaluate(f'''let
          first = builtins.raylib {self.asset_config} (frame: {{ commands = []; state = frame.measureText; }});
          second = builtins.raylib {{ hidden = true; fps = 0; maxFrames = 1; }}
            (frame: {{ commands = []; state = first.state {{ font = "ui"; text = "AA"; size = 12; }}; }});
        in builtins.seq first second.state'''), {"width": 25.0, "height": 12.0})

    def test_measurement_exception_cleanup(self):
        self.assertEqual(self.evaluate(f'''let
          failed = builtins.tryEval (builtins.raylib {self.asset_config} (frame: {{
            commands = []; state = frame.measureText {{ text = throw "measurement failed"; size = 12; }};
          }}));
        in assert !failed.success;
          builtins.raylib {self.asset_config} (_: {{ commands = []; }})'''), {"frames": 2, "state": None})

    def test_measurement_survives_gc(self):
        self.assertEqual(self.evaluate(f'''let
          result = builtins.raylib {self.asset_config} (frame: {{ commands = []; state = frame.measureText; }});
          garbage = builtins.foldl' (sum: n: sum + n) 0 (builtins.genList (n: n) 100000);
        in builtins.seq result (builtins.seq garbage
          (result.state {{ font = "ui"; text = "AA"; size = 12; }}))''',
          env={"GC_INITIAL_HEAP_SIZE": "1048576"}), {"width": 25.0, "height": 12.0})

    def test_text_example(self):
        path = self._truetype_path()
        example = Path(__file__).resolve().parent.parent / "examples/text.nix"
        result = self.evaluate(f'''import {example} {{ font = {path}; hidden = true; maxFrames = 2; }}''')
        self.assertEqual(result["frames"], 2)
        self.assertGreater(result["state"]["width"], 0)
        self.assertEqual(result["state"]["height"], 32.0)
