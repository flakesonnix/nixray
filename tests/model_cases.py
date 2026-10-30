"""Real OBJ/glTF/GLB rendering, skinning, validation and ownership."""

import base64
import json
import os
from pathlib import Path
import struct
from unittest.mock import patch

from three_d_cases import scene, ORTHO


LIB = Path(__file__).resolve().parent.parent / "lib"
HALF_POSE = "{ animation = 0; frame = builtins.div ((builtins.head frame.models.mesh.animations).frameCount - 1) 2; }"


def model(attributes="", *, op="model", name="mesh"):
    return f'{{ op = "{op}"; model = "{name}"; position = {{ x = 0; y = 0; z = 0; }}; {attributes} }}'


class ModelCases:
    def _model_files(self):
        folder = self.asset_directory / "models"
        folder.mkdir(exist_ok=True)
        obj = folder / "quad file.obj"
        if not obj.exists():
            obj.write_text("v -2 -1 0\nv 2 -1 0\nv 2 1 0\nv -2 1 0\nvn 0 0 1\nf 1//1 2//1 3//1\nf 1//1 3//1 4//1\n")
            (folder / "empty.obj").write_text("# no geometry\n")
            png = Path(json.loads(self.pattern_path)).read_bytes()
            for kind in ("static", "skin", "textured", "material"):
                data = bytearray()
                views, accessors = [], []

                def block(payload):
                    while len(data) % 4:
                        data.append(0)
                    view = len(views)
                    views.append({"buffer": 0, "byteOffset": len(data), "byteLength": len(payload)})
                    data.extend(payload)
                    return view

                def accessor(values, fmt, component, shape, count):
                    index = len(accessors)
                    accessors.append({"bufferView": block(struct.pack("<" + fmt * len(values), *values)),
                                      "componentType": component, "count": count, "type": shape})
                    return index

                width = 1 if kind == "skin" else 2
                positions = accessor([-width, -1, 0, width, -1, 0, width, 1, 0, -width, 1, 0], "f", 5126, "VEC3", 4)
                accessors[positions].update(min=[-width, -1, 0], max=[width, 1, 0])
                indices = accessor([0, 1, 2, 0, 2, 3], "H", 5123, "SCALAR", 6)
                uv = accessor([0, 0, 1, 0, 1, 1, 0, 1], "f", 5126, "VEC2", 4)
                normals = accessor([0, 0, 1] * 4, "f", 5126, "VEC3", 4)
                attributes = {"POSITION": positions, "NORMAL": normals, "TEXCOORD_0": uv}
                document = {"asset": {"version": "2.0"}, "scene": 0, "scenes": [{"nodes": [0]}], "nodes": [{"mesh": 0}],
                            "meshes": [{"primitives": [{"attributes": attributes, "indices": indices}]}],
                            "bufferViews": views, "accessors": accessors}
                if kind == "skin":
                    attributes["JOINTS_0"] = accessor([0] * 16, "B", 5121, "VEC4", 4)
                    attributes["WEIGHTS_0"] = accessor([1, 0, 0, 0] * 4, "f", 5126, "VEC4", 4)
                    bind = accessor([1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1], "f", 5126, "MAT4", 1)
                    times = accessor([0, 1], "f", 5126, "SCALAR", 2)
                    output = accessor([0, 0, 0, 4, 0, 0], "f", 5126, "VEC3", 2)
                    document.update(nodes=[{"name": "Joint"}, {"mesh": 0, "skin": 0}, {"children": [0, 1]}],
                                    scenes=[{"nodes": [2]}], skins=[{"joints": [0], "inverseBindMatrices": bind}],
                                    animations=[{"name": "Slide", "samplers": [{"input": times, "output": output, "interpolation": "LINEAR"}],
                                                 "channels": [{"sampler": 0, "target": {"node": 0, "path": "translation"}}]}])
                if kind == "textured":
                    image = block(png)
                    document.update(images=[{"bufferView": image, "mimeType": "image/png"}], textures=[{"source": 0}],
                                    materials=[{"pbrMetallicRoughness": {"baseColorTexture": {"index": 0}}}])
                    document["meshes"][0]["primitives"][0]["material"] = 0
                if kind == "material":
                    document["materials"] = [{"pbrMetallicRoughness": {"baseColorFactor": [0.5, 1, 1, 1]}}]
                    document["meshes"][0]["primitives"][0]["material"] = 0
                document["buffers"] = [{"byteLength": len(data)}]
                encoded = json.dumps(document).encode()
                encoded += b" " * (-len(encoded) % 4)
                binary = bytes(data) + b"\0" * (-len(data) % 4)
                (folder / f"{kind}.glb").write_bytes(struct.pack("<III", 0x46546C67, 2, 28 + len(encoded) + len(binary))
                    + struct.pack("<II", len(encoded), 0x4E4F534A) + encoded + struct.pack("<II", len(binary), 0x004E4942) + binary)
                document["buffers"][0]["uri"] = "data:application/octet-stream;base64," + base64.b64encode(data).decode()
                (folder / f"{kind}.gltf").write_text(json.dumps(document))
        return folder

    def _model_assets(self, kind="obj", *, animated=False):
        folder = self._model_files()
        path = folder / ("quad file.obj" if kind == "obj" else kind)
        entry = json.dumps(str(path))
        if animated:
            entry = f"{{ path = {entry}; animations = {entry}; }}"
        return f"{{ models.mesh = {entry}; }}"

    def _model_preload(self):
        if not self.model_library:
            self.skipTest("pass --model-library to enable model lifetime tests")
        return str(Path(self.model_library).resolve()) + (" " + os.environ["LD_PRELOAD"] if os.environ.get("LD_PRELOAD") else "")

    def _model_evaluate(self, expression, **kwargs):
        trace = self.asset_directory / "model-trace.txt"
        trace.unlink(missing_ok=True)
        return self.evaluate(expression, env={"LD_PRELOAD": self._model_preload(), "NIXRAY_TEST_MODEL_TRACE": str(trace)}, **kwargs)

    def _model_trace(self):
        return (self.asset_directory / "model-trace.txt").read_text().splitlines()

    def _model_pixels(self, attributes="", *, kind="obj", animated=False, op="model", commands=None, frames=1):
        return self._capture(f'[ {{ op = "clear"; color = [0 0 0 255]; }} {scene(model(attributes, op=op) if commands is None else commands)} ]',
                             assets=self._model_assets(kind, animated=animated), frames=frames)

    def test_model_pure_validation_and_nix_helpers(self):
        for flag in ("--pure-eval", "--restrict-eval"):
            self.assertEqual(self.evaluate(f"builtins.raylibValidate [ {scene(model('pose = { animation = 0; frame = 0; };'))} ]", flags=[flag], env={"DISPLAY": "", "WAYLAND_DISPLAY": ""}), 1)
        self.assertEqual(self.evaluate(f'''let ray = import {LIB}; in ray.validate [ (ray.camera3D {{ camera = {{}}; commands = [
          (ray.model {model()}) (ray.modelWires {model()}) ]; }}) ]'''), 1)

    def test_model_scope_required(self):
        for op in ("model", "modelWires"):
            self.evaluate(f"builtins.raylibValidate [ {model(op=op)} ]", error="requires a camera3D scope")

    def test_model_required_and_unknown_fields(self):
        for field in ("model", "position"):
            self.evaluate(f'''builtins.raylibValidate [ {{ op = "camera3D"; camera = {{}};
              commands = [ (builtins.removeAttrs {model()} ["{field}"]) ]; }} ]''', error=f"missing attribute '{field}'")
        for attributes, error in (("color = [];", "unknown attribute 'color'"), ("scale = 0;", "scale must be positive"),
                                  ("scale = -1;", "finite number"), ("scale = 1.0e-40;", "finite and invertible"),
                                  ("rotationAxis = { x = 0; y = 0; z = 0; };", "axis must be nonzero"),
                                  ("rotation = 1.0e100;", "finite number"), ("tint = [];", "color must be"),
                                  ("pose = {};", "missing attribute 'animation'"), ("pose = { animation = 0; frame = -1; };", "integer in"),
                                  ("pose = { animation = 0; frame = 0.5; };", "expected an integer")):
            self.evaluate(f"builtins.raylibValidate [ {scene(model(attributes))} ]", error=error)

    def test_model_asset_schemas(self):
        path = json.dumps(str(self._model_files() / "quad file.obj"))
        for entry, error in (("[]", "asset paths must be"), ('"relative.obj"', "asset paths must be"),
                              ("{}", "missing attribute 'path'"), (f"{{ path = {path}; typo = 1; }}", "unknown attribute 'typo'")):
            self.evaluate(f"builtins.raylib {{ assets.models.mesh = {entry}; }} (_: {{ commands = []; }})", error=error)

    def test_model_obj_gltf_and_glb_pixels(self):
        expected = [(255, 0, 0) if 8 <= x < 24 and 12 <= y < 20 else (0, 0, 0) for y in range(32) for x in range(32)]
        for kind in ("obj", "static.gltf", "static.glb"):
            self.assertEqual(self._model_pixels("tint = [255 0 0 255];", kind=kind), expected)

    def test_model_imported_texture_and_material_tint(self):
        pixels = self._model_pixels(kind="textured.glb")
        self.assertEqual(set(pixels), {(0, 0, 0), (255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0)})
        pixels = self._model_pixels("tint = [255 0 0 255];", kind="material.glb")
        self.assert_pixel(pixels, 16, 16, (127, 0, 0), tolerance=1)

    def test_model_wireframe_and_fill_state_restore(self):
        wires = self._model_pixels("tint = [255 0 0 255];", op="modelWires")
        filled = self._model_pixels("tint = [255 0 0 255];")
        self.assertIn((255, 0, 0), wires)
        self.assertLess(wires.count((255, 0, 0)), filled.count((255, 0, 0)))
        combined = self._model_pixels(commands=model(op="modelWires") + model("tint = [255 0 0 255];"))
        self.assertEqual(combined.count((255, 0, 0)), filled.count((255, 0, 0)))
        self.assert_pixel(combined, 16, 14, (255, 0, 0))

    def test_model_scale_position_rotation(self):
        pixels = self._model_pixels("scale = 0.5; tint = [255 0 0 255];")
        self.assertEqual(pixels, [(255, 0, 0) if 12 <= x < 20 and 14 <= y < 18 else (0, 0, 0) for y in range(32) for x in range(32)])
        pixels = self._model_pixels("rotationAxis = { x = 0; y = 0; z = 1; }; rotation = 90; tint = [255 0 0 255];")
        self.assertEqual(pixels, [(255, 0, 0) if 12 <= x < 20 and 8 <= y < 24 else (0, 0, 0) for y in range(32) for x in range(32)])
        self.assertEqual(pixels, self._model_pixels("rotationAxis = { x = 0; y = 0; z = 100; }; rotation = 450; tint = [255 0 0 255];"))

    def test_model_metadata(self):
        result = self.evaluate(f'''builtins.raylib {{ hidden = true; fps = 0; maxFrames = 1; assets = {self._model_assets()}; }}
          (frame: {{ commands = []; state = frame.models.mesh; }})''')["state"]
        self.assertEqual(result, {"meshCount": 1, "materialCount": 1, "boneCount": 0, "vertexCount": 6, "triangleCount": 2,
                                  "bounds": {"min": {"x": -2, "y": -1, "z": 0}, "max": {"x": 2, "y": 1, "z": 0}}, "animations": []})

    def test_model_missing_name_and_invalid_pose(self):
        for draw, error in ((model(name="missing"), "unknown model 'missing'"),
                             (model("pose = { animation = 0; frame = 0; };"), "pose is out of bounds")):
            self.evaluate(f'''builtins.raylib {{ hidden = true; fps = 0; maxFrames = 1; assets = {self._model_assets()}; }}
              (_: {{ commands = [ {scene(draw)} ]; }})''', error=error)

    def test_model_skeletal_pose_and_bind_reset(self):
        posed = model(f"pose = {HALF_POSE}; tint = [255 0 0 255];")
        bind = model("tint = [0 0 255 255];")
        first = self._model_pixels(kind="skin.glb", animated=True, commands=posed + bind)
        second = self._model_pixels(kind="skin.glb", animated=True, commands=bind + posed)
        self.assertEqual(first, second)
        self.assert_pixel(first, 16, 16, (0, 0, 255))
        self.assert_pixel(first, 24, 16, (255, 0, 0))

    def test_model_bind_pose_resets_across_frames(self):
        draw = f'''{{ op = "model"; model = "mesh"; position = {{ x = 0; y = 0; z = 0; }};
          tint = [0 0 255 255]; }} // (if frame.frame == 0 then {{ pose = {HALF_POSE}; }} else {{}})'''
        pixels = self._model_pixels(kind="skin.glb", animated=True, commands="(" + draw + ")", frames=2)
        self.assert_pixel(pixels, 16, 16, (0, 0, 255))
        self.assert_pixel(pixels, 24, 16, (0, 0, 0))

    def test_model_pose_bounds_are_checked_before_drawing(self):
        self.evaluate(f'''builtins.raylib {{ hidden = true; fps = 0; maxFrames = 1; assets = {self._model_assets('skin.glb', animated=True)}; }}
          (frame: {{ commands = [ {scene(model('pose = { animation = 0; frame = (builtins.head frame.models.mesh.animations).frameCount; };'))} ]; }})''', error="pose is out of bounds")

    def test_model_models_load_once_cleanup_textures_and_animations(self):
        for kind, animated in (("textured.glb", False), ("skin.glb", True)):
            self._model_evaluate(f'''builtins.raylib {{ hidden = true; fps = 0; maxFrames = 3; assets = {self._model_assets(kind, animated=animated)}; }}
              (_: {{ commands = [ {scene(model())} ]; }})''')
            trace = self._model_trace()
            self.assertEqual(trace.count("load-model"), 1)
            self.assertEqual(trace.count("unload-model"), 1)
            self.assertEqual(trace[-1], "close")
            self.assertIn("unload-animations" if animated else "unload-imported-texture", trace)

    def test_model_partial_load_failure_cleans_up(self):
        folder = self._model_files()
        self._model_evaluate(f'''builtins.raylib {{ hidden = true; fps = 0; maxFrames = 1; assets.models = {{
          a = {json.dumps(str(folder / 'textured.glb'))}; z = {json.dumps(str(folder / 'empty.obj'))};
        }}; }} (_: {{ commands = []; }})''', error="model 'z' contains invalid mesh data")
        self.assertEqual(self._model_trace().count("load-model"), 2)
        self.assertEqual(self._model_trace().count("unload-model"), 2)

    def test_model_animation_failure_cleans_model_and_textures(self):
        folder = self._model_files()
        for animations, error in ((folder / "missing.glb", "could not load model animations"),
                                   (folder / "skin.glb", "skeleton is incompatible")):
            self._model_evaluate(f'''builtins.raylib {{ hidden = true; fps = 0; maxFrames = 1;
              assets.models.mesh = {{ path = {json.dumps(str(folder / 'textured.glb'))}; animations = {json.dumps(str(animations))}; }};
            }} (_: {{ commands = []; }})''', error=error)
            self.assertEqual(self._model_trace()[-1], "close")
            self.assertIn("unload-imported-texture", self._model_trace())

    def test_model_independent_named_resources(self):
        path = json.dumps(str(self._model_files() / "textured.glb"))
        self._model_evaluate(f'''builtins.raylib {{ hidden = true; fps = 0; maxFrames = 1;
          assets.models = {{ first = {path}; second = {path}; }};
        }} (_: {{ commands = []; }})''')
        self.assertEqual(self._model_trace().count("load-model"), 2)
        self.assertEqual(self._model_trace().count("unload-imported-texture"), 2)

    def test_model_callback_exception_cleanup(self):
        result = self._model_evaluate(f'''let failed = builtins.tryEval (builtins.raylib {{ hidden = true; fps = 0; maxFrames = 1;
          assets = {self._model_assets('skin.glb', animated=True)}; }} (_: throw "failed"));
        in assert !failed.success; true''')
        self.assertTrue(result)
        self.assertEqual(self._model_trace()[-1], "close")

    def test_model_shader_override_and_restoration(self):
        shader = LIB.parent / "examples/shaders/tint.fs"
        assets = f'''({self._model_assets()} // {{ shaders.fx = {{ fragment = {shader}; uniforms = {{
          gain = {{ type = "float"; value = 0; }}; tint = {{ type = "vec3"; value = [1 1 1]; }}; }}; }}; }})'''
        shaded = '{ op = "shader"; shader = "fx"; commands = [ ' + model() + ' ]; }'
        right = model("scale = 0.25; tint = [255 0 0 255];") + ' // { position = { x = 3; y = 0; z = 0; }; }'
        pixels = self._capture(f'[ {{ op = "clear"; color = [255 255 255 255]; }} {scene(shaded)} {scene("(" + right + ")")} ]', assets=assets)
        self.assert_pixel(pixels, 16, 16, (0, 0, 0))
        self.assert_pixel(pixels, 28, 16, (255, 0, 0))

    def test_model_render_texture_and_clip(self):
        pixels = self._capture(f'''[ {{ op = "clear"; color = [0 0 0 255]; }}
          {{ op = "paint"; texture = "canvas"; commands = [
            {{ op = "clip"; x = 16; y = 0; width = 16; height = 32; commands = [ {scene(model('tint = [255 0 0 255];'))} ]; }}
          ]; }} {{ op = "texture"; texture = "canvas"; x = 0; y = 0; }} ]''',
          assets=f"({self._model_assets()} // {{ renderTextures.canvas = {{ width = 32; height = 32; }}; }})")
        self.assert_pixel(pixels, 12, 16, (0, 0, 0))
        self.assert_pixel(pixels, 20, 16, (255, 0, 0))

    def test_model_additive_blending(self):
        pixels = self._capture(f'''[ {{ op = "clear"; color = [0 0 255 255]; }}
          {{ op = "blend"; mode = "additive"; commands = [ {scene(model('tint = [255 0 0 128];'))} ]; }} ]''', assets=self._model_assets())
        self.assert_pixel(pixels, 16, 16, (128, 0, 255), tolerance=1)

    def test_model_invalid_pose_prevents_any_framebuffer_output(self):
        if not self.capture_library:
            self.skipTest("pass --capture-library for framebuffer validation")
        path = self.asset_directory / "invalid-model.ppm"
        path.unlink(missing_ok=True)
        with patch.dict(os.environ, {"LD_PRELOAD": str(Path(self.capture_library).resolve()), "NIXRAY_TEST_CAPTURE": str(path)}):
            self._model_evaluate(f'''builtins.raylib {{ hidden = true; fps = 0; maxFrames = 1; assets = {self._model_assets()}; }}
              (_: {{ commands = [ {{ op = "clear"; color = [255 0 0 255]; }}
                {scene(model('pose = { animation = 0; frame = 0; };'))} ]; }})''', error="pose is out of bounds")
        self.assertFalse(path.exists())

    def test_model_metadata_survives_close(self):
        result = self._model_evaluate(f'''let result = builtins.raylib {{ hidden = true; fps = 0; maxFrames = 1;
          assets = {self._model_assets('skin.gltf', animated=True)}; }} (frame: {{ commands = []; state = _: frame.models; }});
        in result.state null''')
        self.assertEqual(result["mesh"]["animations"][0]["name"], "Slide")
        self.assertGreater(result["mesh"]["animations"][0]["frameCount"], 2)

    def test_model_store_context_paths(self):
        path = json.dumps(str(self._model_files()))
        result = self.evaluate(f'''let dir = builtins.path {{ path = builtins.toPath {path}; name = "model-bundle"; }};
        in builtins.raylib {{ hidden = true; fps = 0; maxFrames = 1; assets.models.mesh = "${{dir}}/quad file.obj"; }}
          (_: {{ commands = [ {scene(model())} ]; }})''', flags=["--read-write-mode"])
        self.assertEqual(result["frames"], 1)

    def test_model_example(self):
        example = LIB.parent / "examples/model.nix"
        self.assertEqual(self._model_evaluate(f"import {example} {{ hidden = true; maxFrames = 2; }}"),
                         {"frames": 2, "state": {"tick": 2, "paused": False}})
