#!/usr/bin/env python3
"""Exercise graphics environment selection through the installed launcher."""

import argparse
import json
import os
import subprocess
import unittest


parser = argparse.ArgumentParser()
parser.add_argument("--launcher", required=True)
parser.add_argument("--mesa", required=True)
options, remaining = parser.parse_known_args()
GRAPHICS_VARIABLES = (
    "LD_LIBRARY_PATH", "LIBGL_DRIVERS_PATH", "__EGL_VENDOR_LIBRARY_FILENAMES",
    "__EGL_VENDOR_LIBRARY_DIRS", "__GLX_VENDOR_LIBRARY_NAME",
    "__NV_PRIME_RENDER_OFFLOAD", "LIBGL_ALWAYS_SOFTWARE", "GALLIUM_DRIVER",
)
ENVIRONMENT = "{ " + " ".join(
    f'{name} = builtins.getEnv "{name}";' for name in GRAPHICS_VARIABLES
) + " }"


class LauncherTests(unittest.TestCase):
    def run_launcher(self, expression, *, env=None):
        environment = dict(os.environ)
        for name in (*GRAPHICS_VARIABLES, "NIXRAY_GRAPHICS"):
            environment.pop(name, None)
        environment.update(env or {})
        return subprocess.run(
            [options.launcher, "--expr", expression], env=environment,
            text=True, capture_output=True, timeout=30,
        )

    def evaluate(self, expression=ENVIRONMENT, *, env=None):
        result = self.run_launcher(expression, env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def mesa_environment(self, suffix=""):
        expected = dict.fromkeys(GRAPHICS_VARIABLES, "")
        expected.update({
            "LD_LIBRARY_PATH": options.mesa + "/lib" + suffix,
            "LIBGL_DRIVERS_PATH": options.mesa + "/lib/dri",
            "__EGL_VENDOR_LIBRARY_FILENAMES": options.mesa + "/share/glvnd/egl_vendor.d/50_mesa.json",
            "__GLX_VENDOR_LIBRARY_NAME": "mesa",
        })
        return expected

    def test_default_mesa(self):
        self.assertEqual(self.evaluate(), self.mesa_environment())

    def test_mesa_preserves_library_path_suffix(self):
        self.assertEqual(self.evaluate(env={"LD_LIBRARY_PATH": "/caller/lib:/caller/extra"}),
                         self.mesa_environment(":/caller/lib:/caller/extra"))

    def test_mesa_overrides_driver_selection(self):
        self.assertEqual(self.evaluate(env={
            "LIBGL_DRIVERS_PATH": "/caller/dri",
            "__EGL_VENDOR_LIBRARY_FILENAMES": "/caller/nvidia.json",
            "__GLX_VENDOR_LIBRARY_NAME": "nvidia",
        }), self.mesa_environment())

    def test_usage(self):
        result = subprocess.run([options.launcher], text=True, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 2)
        self.assertIn("usage: nixray", result.stderr)


if __name__ == "__main__":
    unittest.main(argv=[__file__, *remaining], verbosity=2)
