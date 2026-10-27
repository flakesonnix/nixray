"""Texture transforms, using the shared asset fixtures from the main suite."""


class TextureCases:
    def _draw_texture(self, attributes, **kwargs):
        return self.evaluate(f'''builtins.raylib {self.asset_config} (_: {{
          commands = [ {{ op = "texture"; texture = "logo"; x = 16; y = 16; {attributes} }} ];
        }})''', **kwargs)

    def test_texture_scale_rotation(self):
        for attributes in (
            "scale = 1; rotation = 0;",
            "scale = 2;",
            "scale = 0.5;",
            "rotation = 90;",
            "rotation = -45.5; scale = 2.5; tint = [ 255 0 0 255 ];",
        ):
            with self.subTest(attributes=attributes):
                self.assertEqual(self._draw_texture(attributes), {"frames": 2, "state": None})

    def test_texture_transform_validation(self):
        self.assertEqual(self.evaluate('''builtins.raylibValidate [
          { op = "texture"; texture = "unloaded"; x = 0; y = 0; scale = 2.5; rotation = -90; }
        ]''', flags=["--pure-eval"], env={"DISPLAY": "", "WAYLAND_DISPLAY": ""}), 1)

    def test_bad_texture_transforms(self):
        for attributes, error in [
            ("scale = 0;", "scale must be positive"),
            ("scale = -1;", "finite number in range"),
            ("scale = 1.0e-100;", "scale must be positive"),
            ("scale = 1.0e100;", "finite number in range"),
            ("scale = true;", "expected"),
            ("rotation = 1.0e100;", "finite number in range"),
            ('rotation = "90";', "expected"),
        ]:
            with self.subTest(attributes=attributes):
                self.evaluate(f'''builtins.raylibValidate [
                  {{ op = "texture"; texture = "logo"; x = 0; y = 0; {attributes} }}
                ]''', error=error)

    def test_texture_transform_overflow(self):
        self.evaluate(f'''builtins.raylib {self.asset_config} (_: {{
          commands = [ {{ op = "texture"; texture = "logo"; x = 0; y = 0; scale = 3.0e38; }} ];
        }})''', error="scaled texture dimensions")

    def test_texture_source(self):
        for attributes in (
            "source = { x = 0; y = 0; width = 2; height = 2; };",
            "source = { x = 1; y = 1; width = 1; height = 1; };",
            "source = { x = 1; y = 0; width = 1; height = 2; }; scale = 4; rotation = 30;",
        ):
            with self.subTest(attributes=attributes):
                self.assertEqual(self._draw_texture(attributes), {"frames": 2, "state": None})

    def test_texture_source_bounds(self):
        for source in (
            "{ x = 2; y = 0; width = 1; height = 1; }",
            "{ x = 0; y = 2; width = 1; height = 1; }",
            "{ x = 1; y = 0; width = 2; height = 1; }",
            "{ x = 2147483647; y = 0; width = 2147483647; height = 1; }",
        ):
            with self.subTest(source=source):
                self._draw_texture(f"source = {source};", error="source rectangle exceeds texture 'logo'")

    def test_bad_texture_sources(self):
        for source, error in [
            ("[]", "expected a set"),
            ("{}", "missing attribute 'x'"),
            ("{ x = -1; y = 0; width = 1; height = 1; }", "'x' must be an integer"),
            ("{ x = 0; y = -1; width = 1; height = 1; }", "'y' must be an integer"),
            ("{ x = 0; y = 0; width = 0; height = 1; }", "'width' must be an integer"),
            ("{ x = 0; y = 0; width = 1; height = -1; }", "'height' must be an integer"),
            ("{ x = 0.5; y = 0; width = 1; height = 1; }", "expected an integer"),
            ("{ x = 0; y = 0; width = 1; height = 1; typo = true; }", "unknown attribute 'typo'"),
        ]:
            with self.subTest(source=source):
                self.evaluate(f'''builtins.raylibValidate [
                  {{ op = "texture"; texture = "logo"; x = 0; y = 0; source = {source}; }}
                ]''', error=error)

    def test_texture_source_validation_without_assets(self):
        self.assertEqual(self.evaluate('''builtins.raylibValidate [
          { op = "texture"; texture = "unloaded"; x = 0; y = 0;
            source = { x = 1000; y = 1000; width = 32; height = 32; }; scale = 2; rotation = 90; }
        ]''', flags=["--pure-eval"], env={"DISPLAY": "", "WAYLAND_DISPLAY": ""}), 1)

    def test_texture_source_scale_overflow(self):
        self.evaluate('''builtins.raylibValidate [
          { op = "texture"; texture = "unloaded"; x = 0; y = 0; scale = 3.0e38;
            source = { x = 0; y = 0; width = 2; height = 2; }; }
        ]''', error="scaled texture dimensions")
