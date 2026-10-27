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
        cls.asset_config = ("{ width = 64; height = 64; hidden = true; fps = 0; "
                            "maxFrames = 2; assets.textures.logo = "
                            + cls.texture_path + "; }")

    def test_texture_assets_load(self):
        self.assertEqual(self.evaluate(
            f"builtins.raylib {self.asset_config} (_: {{ commands = []; }})"
        ), {"frames": 2, "state": None})
