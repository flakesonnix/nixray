"""Asset fixtures and evaluator cases, mixed into the main integration suite."""

import json
from pathlib import Path
import struct
import tempfile
import zlib


class AssetCases:
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        preferred = Path("/tmp/opencode")
        directory = tempfile.TemporaryDirectory(
            prefix="nixray-assets-", dir=preferred if preferred.is_dir() else None,
        )
        cls.addClassCleanup(directory.cleanup)
        cls.asset_directory = Path(directory.name)
        texture = cls.asset_directory / "tiny texture.png"

        def chunk(tag, data):
            return (struct.pack(">I", len(data)) + tag + data
                    + struct.pack(">I", zlib.crc32(tag + data)))

        texture.write_bytes(
            b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", 2, 2, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress((b"\0" + b"\xff" * 8) * 2))
            + chunk(b"IEND", b"")
        )
        cls.texture_path = json.dumps(str(texture))
        font = cls.asset_directory / "tiny.fnt"
        font.write_text(
            'info face="nixray-test" size=2\n'
            'common lineHeight=2 base=2 scaleW=2 scaleH=2 pages=1 packed=0\n'
            'page id=0 file="tiny texture.png"\n'
            'chars count=1\n'
            'char id=65 x=0 y=0 width=2 height=2 xoffset=0 yoffset=0 xadvance=2 page=0 chnl=15\n'
        )
        cls.font_path = json.dumps(str(font))
        cls.asset_config = ("{ width = 64; height = 64; hidden = true; fps = 0; "
                            "maxFrames = 2; assets.textures.logo = "
                            + cls.texture_path + "; assets.fonts.ui = " + cls.font_path + "; }")

    def test_texture_assets_load(self):
        self.assertEqual(self.evaluate(
            f"builtins.raylib {self.asset_config} (_: {{ commands = []; }})"
        ), {"frames": 2, "state": None})

    def test_draw_texture(self):
        for tint in ("", "tint = [ 255 0 0 255 ];"):
            with self.subTest(tint=tint):
                self.assertEqual(self.evaluate(f'''builtins.raylib {self.asset_config}
                  (frame: {{
                    commands = [ {{ op = "texture"; texture = "logo"; x = 1; y = 2; {tint} }} ];
                    state = frame.frame;
                  }})'''), {"frames": 2, "state": 1})

    def test_texture_helper(self):
        library = Path(__file__).resolve().parent.parent / "lib"
        self.assertEqual(self.evaluate(f'''builtins.raylib {self.asset_config} (_: {{
          commands = [ ((import {library}).texture {{ texture = "logo"; x = 0; y = 0; }}) ];
        }})'''), {"frames": 2, "state": None})

    def test_texture_validation_without_assets(self):
        self.assertEqual(self.evaluate('''builtins.raylibValidate [
          { op = "texture"; texture = "unloaded"; x = 0; y = 0; }
        ]''', flags=["--pure-eval"], env={"DISPLAY": "", "WAYLAND_DISPLAY": ""}), 1)

    def test_unknown_texture(self):
        self.evaluate(f'''builtins.raylib {self.asset_config} (_: {{
          commands = [ {{ op = "texture"; texture = "missing"; x = 0; y = 0; }} ];
        }})''', error="unknown texture 'missing'")

    def test_bad_texture_commands(self):
        for command, error in [
            ('{ op = "texture"; x = 0; y = 0; }', "missing attribute 'texture'"),
            ('{ op = "texture"; texture = ""; x = 0; y = 0; }', "texture name must not be empty"),
            ('{ op = "texture"; texture = "logo"; x = 0; y = 0; tint = []; }', "color must be"),
        ]:
            with self.subTest(command=command):
                self.evaluate(f"builtins.raylibValidate [ {command} ]", error=error)

    def test_draw_custom_font(self):
        library = Path(__file__).resolve().parent.parent / "lib"
        self.assertEqual(self.evaluate(f'''let ray = import {library}; in
          builtins.raylib {self.asset_config} (_: {{
            commands = [
              (ray.text {{ font = "ui"; text = "A"; x = 0; y = 0; size = 12; color = ray.colors.white; }})
              (ray.text {{ text = "default"; x = 0; y = 16; size = 12; color = ray.colors.white; }})
            ];
          }})'''), {"frames": 2, "state": None})

    def test_font_validation_without_assets(self):
        self.assertEqual(self.evaluate('''builtins.raylibValidate [
          { op = "text"; font = "unloaded"; text = "A"; x = 0; y = 0; size = 12; color = [0 0 0 255]; }
        ]''', flags=["--pure-eval"], env={"DISPLAY": "", "WAYLAND_DISPLAY": ""}), 1)

    def test_unknown_font(self):
        self.evaluate(f'''builtins.raylib {self.asset_config} (_: {{
          commands = [ {{ op = "text"; font = "missing"; text = "A";
                         x = 0; y = 0; size = 12; color = [0 0 0 255]; }} ];
        }})''', error="unknown font 'missing'")

    def test_empty_font_name(self):
        self.evaluate('''builtins.raylibValidate [
          { op = "text"; font = ""; text = "A"; x = 0; y = 0; size = 12; color = [0 0 0 255]; }
        ]''', error="font name must not be empty")
