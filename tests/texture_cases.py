"""Texture transforms, using the shared asset fixtures from the main suite."""


class TextureCases:
    def _draw_texture(self, attributes):
        return self.evaluate(f'''builtins.raylib {self.asset_config} (_: {{
          commands = [ {{ op = "texture"; texture = "logo"; x = 16; y = 16; {attributes} }} ];
        }})''')

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
