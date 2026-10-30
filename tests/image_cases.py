"""Immutable CPU images, filesystem boundaries, and native texture uploads."""

import json
from pathlib import Path
import struct
import zlib


LIB = Path(__file__).resolve().parent.parent / "lib"
SOLID = 'builtins.raylibGenImage { width = 2; height = 2; color = [100 150 200 128]; }'


def transform(operations, image=SOLID):
    return f'builtins.raylibImageTransform ({image}) [ {operations} ]'


def pixel(image, x=0, y=0):
    return f'builtins.raylibImagePixel ({image}) {{ x = {x}; y = {y}; }}'


class ImageCases:
    def test_image_registration_and_helpers(self):
        names = ('LoadImage', 'GenImage', 'ImageTransform', 'ImageInfo', 'ImagePixel', 'ExportImage')
        self.assertEqual(self.evaluate('[ ' + ' '.join(f'(builtins.typeOf builtins.raylib{name})' for name in names) + ' ]'), ['lambda']*6)
        self.assertEqual(self.evaluate(f'''let ray = import {LIB}; i = ray.genImage {{ width = 2; height = 3; color = [1 2 3 4]; }};
          in [ (ray.imageInfo i) (ray.imagePixel (ray.imageTransform i []) {{ x = 1; y = 2; }}) ]'''),
                         [{'width': 2, 'height': 3, 'format': 'rgba8'}, [1, 2, 3, 4]])

    def test_image_generation_and_transforms_are_pure_without_display(self):
        for flag in ('--pure-eval', '--restrict-eval'):
            self.assertEqual(self.evaluate(pixel(transform('{ op = "colorInvert"; }')), flags=[flag],
                                           env={'DISPLAY': '', 'WAYLAND_DISPLAY': ''}), [155, 105, 55, 128])

    def test_image_values_are_not_json_handles(self):
        self.evaluate(SOLID, error='cannot convert')
        self.assertEqual(self.evaluate(f'builtins.typeOf ({SOLID})'), 'nixray-image')
        self.assertEqual(self.evaluate(f'builtins.toString ({SOLID})', error='cannot coerce'), None)

    def test_image_wrong_value_types(self):
        for value in ('{}', 'null', '[]', '1', '"image"', '(_: null)'):
            for expression in (f'builtins.raylibImageInfo ({value})', pixel(value), transform('', value)):
                self.evaluate(expression, error='expected a nixray image value')

    def test_image_generator_required_fields(self):
        for value, error in (('{}', "missing attribute 'width'"), ('{ width = 2; }', "missing attribute 'height'"),
                              ('{ width = 2; height = 2; }', "missing attribute 'color'"),
                              ('{ width = 2; height = 2; kind = "random"; }', 'unknown image generator'),
                              ('{ width = 2; height = 2; color = []; }', 'color must be'),
                              ('{ width = 2; height = 2; color = [1 2 3 4]; typo = true; }', "unknown attribute 'typo'")):
            self.evaluate(f'builtins.raylibImageInfo (builtins.raylibGenImage {value})', error=error)

    def test_image_dimension_and_pixel_limits(self):
        for width, height, error in (('0', '2', 'integer in'), ('-1', '2', 'integer in'), ('2.5', '2', 'expected an integer'),
                                    ('16385', '1', 'integer in'), ('2049', '2048', 'at most 4194304')):
            self.evaluate(f'builtins.raylibGenImage {{ width = {width}; height = {height}; color = [0 0 0 0]; }}', error=error)
        self.assertEqual(self.evaluate('builtins.raylibImageInfo (builtins.raylibGenImage { width = 16384; height = 1; color = [0 0 0 0]; })')['width'], 16384)

    def test_image_checked_generator_pixels(self):
        image = 'builtins.raylibGenImage { kind = "checked"; width = 3; height = 2; checksX = 2; checksY = 1; color1 = [255 0 0 255]; color2 = [0 0 255 255]; }'
        self.assertEqual(self.evaluate('[ ' + ' '.join(f'({pixel(image, x, y)})' for y in range(2) for x in range(3)) + ' ]'),
                         [[255, 0, 0, 255]]*2 + [[0, 0, 255, 255]]*3 + [[255, 0, 0, 255]])
        self.evaluate(image.replace('checksX = 2', 'checksX = 0'), error='integer in')

    def test_image_gradient_generators_and_validation(self):
        for kind in ('gradientRadial', 'gradientSquare'):
            image = f'builtins.raylibGenImage {{ kind = "{kind}"; width = 4; height = 4; inner = [255 0 0 255]; outer = [0 0 255 0]; }}'
            self.assertEqual(self.evaluate(pixel(image, 2, 2)), [255, 0, 0, 255])
            self.assertEqual(self.evaluate(pixel(image)), [0, 0, 255, 0])
            for density in ('-0.1', '1', '0.999999999'):
                self.evaluate(image[:-1] + f'density = {density}; }}', error='density')
        linear = 'builtins.raylibGenImage { kind = "gradientLinear"; width = 4; height = 4; direction = 0; start = [255 0 0 255]; end = [0 0 255 255]; }'
        self.assertEqual(self.evaluate(pixel(linear)), [255, 0, 0, 255])
        result = self.evaluate(pixel(linear, 0, 3))
        self.assertTrue(all(abs(a - b) <= 1 for a, b in zip(result, [0, 0, 255, 255])), result)
        self.evaluate(linear.replace('width = 4', 'width = 1'), error='at least 2')
        self.evaluate(linear.replace('direction = 0', 'direction = 361'), error='direction')
        self.evaluate(linear.replace('direction = 0', 'direction = -1'), error='integer in')

    def test_image_transform_list_schema_and_work_limits(self):
        self.evaluate(f'builtins.raylibImageTransform ({SOLID}) {{}}', error='expected a list')
        self.evaluate(f'builtins.raylibImageTransform ({SOLID}) (builtins.genList (_: {{ op = "colorInvert"; }}) 257)', error='at most 256')
        self.evaluate(transform('{ op = "typo"; }'), error='unknown image operation')
        self.evaluate(transform('{ op = "flipHorizontal"; typo = 1; }'), error="unknown attribute 'typo'")
        large = 'builtins.raylibGenImage { width = 2048; height = 2048; color = [0 0 0 0]; }'
        self.evaluate(transform('{ op = "colorInvert"; } { op = "colorInvert"; }', large), error='pixel-work budget')

    def test_image_transforms_never_mutate_shared_input(self):
        self.assertEqual(self.evaluate(f'''let image = {SOLID}; flipped = {transform('{ op = "colorInvert"; }', 'image')};
          tinted = {transform('{ op = "colorTint"; color = [255 0 0 255]; }', 'image')};
          in [ ({pixel('flipped')}) ({pixel('tinted')}) ({pixel('image')}) ]'''),
                         [[155, 105, 55, 128], [100, 0, 0, 128], [100, 150, 200, 128]])

    def test_image_failed_transform_preserves_input(self):
        self.assertEqual(self.evaluate(f'''let image = {SOLID}; failed = builtins.tryEval (builtins.raylibImageTransform image
          [ {{ op = "colorInvert"; }} {{ op = throw "failed operation"; }} ]);
          in assert !failed.success; {pixel('image')}'''), [100, 150, 200, 128])

    def test_image_load_native_png_pixels(self):
        image = f'builtins.raylibLoadImage {self.pattern_path}'
        self.assertEqual(self.evaluate(f'builtins.raylibImageInfo ({image})', env={'DISPLAY': '', 'WAYLAND_DISPLAY': ''}), {'width': 2, 'height': 2, 'format': 'rgba8'})
        self.assertEqual(self.evaluate('[ ' + ' '.join(f'({pixel(image, x, y)})' for y in range(2) for x in range(2)) + ' ]'),
                         [[255, 0, 0, 255], [0, 255, 0, 255], [0, 0, 255, 255], [255, 255, 0, 255]])

    def test_image_load_bad_paths_and_decoding(self):
        for path, error in (('"relative.png"', 'image paths must be'), ('""', 'image paths must be'), ('{}', 'image paths must be'),
                             (self.bad_texture_path, 'could not create or decode image')):
            self.evaluate(f'builtins.raylibLoadImage {path}', error=error)
        no_extension = self.asset_directory / 'extensionless'
        no_extension.write_bytes(b'PNG')
        self.evaluate(f'builtins.raylibLoadImage {json.dumps(str(no_extension))}', error='supported file extension')
        nul = 'builtins.fromJSON ' + json.dumps(json.dumps('/bad\0.png'))
        self.evaluate(f'builtins.raylibLoadImage ({nul})', error='null bytes')

    def test_image_load_respects_nix_access_restrictions(self):
        for flag in ('--pure-eval', '--restrict-eval'):
            self.evaluate(f'builtins.raylibImageInfo (builtins.raylibLoadImage {self.pattern_path})', flags=[flag], error='forbidden')
        folder = str(self.asset_directory)
        self.assertEqual(self.evaluate('builtins.raylibImageInfo (builtins.raylibLoadImage <image-fixtures/pattern.png>)',
                                       flags=['--restrict-eval', '-I', f'image-fixtures={folder}'])['width'], 2)
        link = self.asset_directory / 'escape.png'
        link.symlink_to('/etc/passwd')
        self.evaluate('builtins.raylibLoadImage <image-fixtures/escape.png>',
                      flags=['--restrict-eval', '-I', f'image-fixtures={folder}'], error='forbidden')

    def test_image_load_store_context(self):
        self.assertEqual(self.evaluate(f'''let p = builtins.path {{ path = builtins.toPath {self.pattern_path}; name = "image-input.png"; }};
          ray = import {LIB}; in ray.imageInfo (ray.loadImage "${{p}}")''', flags=['--read-write-mode']),
                         {'width': 2, 'height': 2, 'format': 'rgba8'})

    def test_image_encoded_file_size_limit(self):
        path = self.asset_directory / 'oversize.png'
        with path.open('wb') as file:
            file.truncate(67108865)
        self.evaluate(f'builtins.raylibLoadImage {json.dumps(str(path))}', error='must not exceed 64 MiB')

    def test_image_load_normalizes_grayscale_and_rgb(self):
        def chunk(kind, data):
            return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))
        path = self.asset_directory / 'formats.png'
        for kind, row, expected in ((0, b'\x80', [128, 128, 128, 255]), (2, b'\x01\x02\x03', [1, 2, 3, 255]),
                                    (4, b'\x40\x80', [64, 64, 64, 128])):
            path.write_bytes(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 1, 1, 8, kind, 0, 0, 0))
                             + chunk(b'IDAT', zlib.compress(b'\0' + row)) + chunk(b'IEND', b''))
            self.assertEqual(self.evaluate(pixel(f'builtins.raylibLoadImage {json.dumps(str(path))}')), expected)

    def test_image_pixel_bounds_and_schema(self):
        for point, error in (('{ x = -1; y = 0; }', 'integer in'), ('{ x = 2; y = 0; }', 'integer in'),
                              ('{ x = 0; y = 2; }', 'integer in'), ('{ x = 0.5; y = 0; }', 'expected an integer'),
                              ('{ x = 0; }', "missing attribute 'y'"), ('{ x = 0; y = 0; z = 1; }', "unknown attribute 'z'")):
            self.evaluate(f'builtins.raylibImagePixel ({SOLID}) {point}', error=error)

    def test_image_crop_and_native_nearest_resize(self):
        loaded = f'builtins.raylibLoadImage {self.pattern_path}'
        cropped = transform('{ op = "crop"; x = 1; y = 0; width = 1; height = 2; } { op = "resizeNN"; width = 2; height = 4; }', loaded)
        self.assertEqual(self.evaluate(f'builtins.raylibImageInfo ({cropped})'), {'width': 2, 'height': 4, 'format': 'rgba8'})
        self.assertEqual(self.evaluate(pixel(cropped, 1, 1)), [0, 255, 0, 255])
        self.assertEqual(self.evaluate(pixel(cropped, 1, 3)), [255, 255, 0, 255])
        for attrs, error in (('x = 2; y = 0; width = 1; height = 1;', 'exceeds image bounds'),
                             ('x = 0; y = 0; width = 0; height = 1;', 'integer in'),
                             ('x = -1; y = 0; width = 1; height = 1;', 'integer in')):
            self.evaluate(transform('{ op = "crop"; ' + attrs + ' }'), error=error)

    def test_image_native_bicubic_resize(self):
        resized = transform('{ op = "resize"; width = 7; height = 5; }')
        self.assertEqual(self.evaluate(f'builtins.raylibImageInfo ({resized})')['height'], 5)
        self.assertEqual(self.evaluate(pixel(resized, 3, 2)), [100, 150, 200, 128])
        self.evaluate(transform('{ op = "resizeNN"; width = 0; height = 1; }'), error='integer in')

    def test_image_flips_and_quarter_rotations(self):
        loaded = f'builtins.raylibLoadImage {self.pattern_path}'
        for op, expected in (('flipHorizontal', [0, 255, 0, 255]), ('flipVertical', [0, 0, 255, 255]),
                              ('rotateCW', [0, 0, 255, 255]), ('rotateCCW', [0, 255, 0, 255])):
            self.assertEqual(self.evaluate(pixel(transform('{ op = "' + op + '"; }', loaded))), expected)
        for degrees, expected in ((0, [255, 0, 0, 255]), (90, [0, 0, 255, 255]), (-90, [0, 255, 0, 255]), (180, [255, 255, 0, 255])):
            self.assertEqual(self.evaluate(pixel(transform(f'{{ op = "rotate"; degrees = {degrees}; }}', loaded))), expected)
        narrow = transform('{ op = "crop"; x = 0; y = 0; width = 2; height = 1; } { op = "rotateCW"; }', loaded)
        self.assertEqual(self.evaluate(f'builtins.raylibImageInfo ({narrow})'), {'width': 1, 'height': 2, 'format': 'rgba8'})
        self.assertEqual(self.evaluate(pixel(narrow, 0, 1)), [0, 255, 0, 255])

    def test_image_arbitrary_rotation_and_size_guards(self):
        self.assertEqual(self.evaluate(f'builtins.raylibImageInfo ({transform("{ op = \"rotate\"; degrees = 45; }")})')['width'], 2)
        self.evaluate(transform('{ op = "rotate"; degrees = 360; }'), error='integer in')
        narrow = 'builtins.raylibGenImage { width = 16384; height = 1; color = [0 0 0 0]; }'
        self.evaluate(transform('{ op = "rotate"; degrees = 45; }', narrow), error='at most 4194304')

    def test_image_canvas_safe_clipping_and_same_size_offsets(self):
        loaded = f'builtins.raylibLoadImage {self.pattern_path}'
        for x, y, expected in ((1, 0, [9, 8, 7, 6]), (-1, 0, [0, 255, 0, 255]), (0, -1, [0, 0, 255, 255]),
                                (2147483647, 0, [9, 8, 7, 6]), (-2147483648, 0, [9, 8, 7, 6]), (0, 2147483647, [9, 8, 7, 6])):
            op = f'{{ op = "resizeCanvas"; width = 2; height = 2; offsetX = {x}; offsetY = {y}; fill = [9 8 7 6]; }}'
            self.assertEqual(self.evaluate(pixel(transform(op, loaded))), expected)

    def test_image_color_edits(self):
        for operation, expected in (('{ op = "colorTint"; color = [255 0 128 128]; }', [100, 0, 100, 64]),
                                     ('{ op = "colorInvert"; }', [155, 105, 55, 128]),
                                     ('{ op = "colorBrightness"; value = 100; }', [200, 250, 255, 128]),
                                     ('{ op = "colorContrast"; value = -100; }', [127, 127, 127, 128]),
                                     ('{ op = "colorGrayscale"; }', [140, 140, 140, 128]),
                                     ('{ op = "colorReplace"; color = [100 150 200 128]; replace = [1 2 3 4]; }', [1, 2, 3, 4]),
                                     ('{ op = "alphaPremultiply"; }', [50, 75, 100, 128])):
            self.assertEqual(self.evaluate(pixel(transform(operation))), expected)
        for operation in ('{ op = "colorContrast"; value = 101; }', '{ op = "colorBrightness"; value = 256; }',
                           '{ op = "alphaClear"; color = [0 0 0 0]; threshold = 1.1; }'):
            self.evaluate(transform(operation), error='range' if 'Brightness' not in operation else 'integer in')

    def test_image_alpha_mask_uses_luminance_not_alpha(self):
        mask = 'builtins.raylibGenImage { width = 2; height = 2; color = [255 255 255 0]; }'
        self.assertEqual(self.evaluate(pixel(transform('{ op = "alphaMask"; image = (' + mask + '); }'))), [100, 150, 200, 255])
        self.evaluate(transform('{ op = "alphaMask"; image = (builtins.raylibGenImage { width = 1; height = 1; color = [0 0 0 0]; }); }'), error='must match image dimensions')

    def test_image_alpha_crop_clear_and_drawing(self):
        base = 'builtins.raylibGenImage { width = 4; height = 3; color = [0 0 0 0]; }'
        draw = '{ op = "drawPixel"; x = 2; y = 1; color = [255 0 0 128]; } { op = "alphaCrop"; threshold = 0; }'
        image = transform(draw, base)
        self.assertEqual(self.evaluate(f'builtins.raylibImageInfo ({image})'), {'width': 1, 'height': 1, 'format': 'rgba8'})
        self.assertEqual(self.evaluate(pixel(image)), [255, 0, 0, 128])
        self.assertEqual(self.evaluate(f'builtins.raylibImageInfo ({transform("{ op = \"alphaCrop\"; threshold = 0; }", base)})')['width'], 4)
        self.assertEqual(self.evaluate(pixel(transform('{ op = "alphaClear"; threshold = 0.502; color = [1 2 3 4]; }'))), [1, 2, 3, 4])
        rectangle = transform('{ op = "drawRectangle"; x = 1; y = 0; width = 1; height = 2; color = [1 2 3 4]; }')
        self.assertEqual(self.evaluate(pixel(rectangle, 1, 1)), [1, 2, 3, 4])

    def _image_export_path(self, name='image-output.png'):
        path = self.asset_directory / name
        path.unlink(missing_ok=True)
        return path

    def test_image_export_round_trip_and_metadata(self):
        path = self._image_export_path()
        image = transform('{ op = "flipVertical"; }', f'builtins.raylibLoadImage {self.pattern_path}')
        result = self.evaluate(f'builtins.raylibExportImage {{ image = ({image}); path = {json.dumps(str(path))}; }}', env={'DISPLAY': '', 'WAYLAND_DISPLAY': ''})
        self.assertEqual(result, str(path))
        self.assertEqual(path.read_bytes()[:8], b'\x89PNG\r\n\x1a\n')
        self.assertEqual(path.stat().st_mode & 0o077, 0)
        self.assertEqual(self.evaluate(pixel(f'builtins.raylibLoadImage {json.dumps(str(path))}')), [0, 0, 255, 255])
        self.assertEqual(list(self.asset_directory.glob('.nixray-image-*')), [])

    def test_image_export_preserves_alpha(self):
        path = self._image_export_path()
        result = self.evaluate(f'''let written = builtins.raylibExportImage {{ image = ({SOLID}); path = {json.dumps(str(path))}; }};
          in builtins.raylibImagePixel (builtins.raylibLoadImage written) {{ x = 0; y = 0; }}''')
        self.assertEqual(result, [100, 150, 200, 128])

    def test_image_export_never_overwrites_existing_or_symlink_destinations(self):
        path = self._image_export_path()
        path.write_bytes(b'keep user content')
        symlink = self._image_export_path('linked.png')
        symlink.symlink_to(path)
        for target in (path, symlink):
            self.evaluate(f'builtins.raylibExportImage {{ image = ({SOLID}); path = {json.dumps(str(target))}; }}', error='destination must not exist')
            self.assertEqual(path.read_bytes(), b'keep user content')
            self.assertEqual(list(self.asset_directory.glob('.nixray-image-*')), [])
        self.assertTrue(symlink.is_symlink())

    def test_image_export_rejects_pure_or_restricted_evaluation_before_forcing_arguments(self):
        for flag in ('--pure-eval', '--restrict-eval'):
            self.evaluate('builtins.raylibExportImage (throw "must not force")', flags=[flag], error='requires impure, unrestricted evaluation')

    def test_image_export_path_and_schema_validation(self):
        for path in ('"relative.png"', '"/tmp/image.jpg"', '""', '{}'):
            self.evaluate(f'builtins.raylibExportImage {{ image = ({SOLID}); path = {path}; }}', error='absolute .png' if path != '{}' else 'expected a string')
        self.evaluate(f'builtins.raylibExportImage {{ image = ({SOLID}); }}', error="missing attribute 'path'")
        path = self.asset_directory / 'missing-directory/image.png'
        self.evaluate(f'builtins.raylibExportImage {{ image = ({SOLID}); path = {json.dumps(str(path))}; }}', error='could not create image export temporary')

    def test_image_export_obeys_nix_memoization(self):
        path = self._image_export_path()
        self.assertEqual(self.evaluate(f'''let written = builtins.raylibExportImage {{ image = ({SOLID}); path = {json.dumps(str(path))}; }};
          in [written written]'''), [str(path)]*2)

    def test_image_texture_upload_pixels_and_orientation(self):
        image = transform('{ op = "flipVertical"; }', f'builtins.raylibLoadImage {self.pattern_path}')
        pixels = self._capture('[ { op = "clear"; color = [0 0 0 255]; } { op = "texture"; texture = "cpu"; x = 0; y = 0; scale = 8; } ]',
                               assets='{ textures.cpu = { image = (' + image + '); filter = "point"; }; }')
        for x, y, color in ((4, 4, (0, 0, 255)), (12, 4, (255, 255, 0)), (4, 12, (255, 0, 0)), (12, 12, (0, 255, 0))):
            self.assert_pixel(pixels, x, y, color)

    def test_image_texture_asset_source_schema(self):
        for entry, error in ((f'{{ image = ({SOLID}); path = {self.texture_path}; }}', "exactly one of 'path' or 'image'"),
                               ('{ image = {}; }', 'expected a nixray image value'), ('{ image = null; }', 'expected a nixray image value')):
            self.evaluate(f'builtins.raylib {{ hidden = true; maxFrames = 1; assets.textures.cpu = {entry}; }} (_: {{ commands = []; }})', error=error)

    def test_image_texture_filter_wrap_and_alpha(self):
        pixels = self._capture('''[ { op = "clear"; color = [0 0 255 255]; }
          { op = "texture"; texture = "cpu"; x = 0; y = 0; source = { x = 0; y = 0; width = 4; height = 4; }; scale = 4; } ]''',
          assets='{ textures.cpu = { image = (builtins.raylibGenImage { width = 2; height = 2; color = [255 0 0 128]; }); filter = "bilinear"; wrap = "repeat"; }; }')
        self.assert_pixel(pixels, 8, 8, (128, 0, 127), tolerance=1)

    def test_image_value_survives_window_close_and_can_be_reused(self):
        self.assertEqual(self.evaluate(f'''let image = {SOLID}; run = n: builtins.raylib {{ hidden = true; fps = 0; maxFrames = 1;
          assets.textures.cpu.image = image; }} (_: {{ commands = []; state = _: image; }});
          first = run 1; second = builtins.seq first (run 2);
          in [ (builtins.raylibImageInfo (first.state null)) (builtins.raylibImagePixel (second.state null) {{ x = 0; y = 0; }}) ]'''),
                         [{'width': 2, 'height': 2, 'format': 'rgba8'}, [100, 150, 200, 128]])

    def test_image_gc_pressure_keeps_live_inputs_valid(self):
        self.assertEqual(self.evaluate(f'''let image = {SOLID}; values = builtins.genList (i:
          builtins.head (builtins.raylibImagePixel (builtins.raylibGenImage {{ width = 256; height = 256;
            color = [ (i - (builtins.div i 256)*256) 0 0 255 ]; }}) {{ x = 0; y = 0; }})) 300;
          count = builtins.foldl' (a: b: a + b) 0 values;
          in builtins.seq image (builtins.seq count ({pixel('image')}))'''), [100, 150, 200, 128])

    def test_image_example(self):
        self.assertEqual(self.evaluate(f'import {LIB.parent / "examples/images.nix"} {{ hidden = true; maxFrames = 2; }}'),
                         {'frames': 2, 'state': {'inverted': False, 'exported': None, 'image': {'width': 224, 'height': 224, 'format': 'rgba8'}}})

    def test_image_example_explicit_export(self):
        path = self._image_export_path('demo-output.png')
        result = self.evaluate(f'import {LIB.parent / "examples/images.nix"} {{ hidden = true; maxFrames = 1; output = {json.dumps(str(path))}; }}')
        self.assertEqual(result['state']['exported'], str(path))
        self.assertEqual(self.evaluate(f'builtins.raylibImageInfo (builtins.raylibLoadImage {json.dumps(str(path))})')['width'], 224)
