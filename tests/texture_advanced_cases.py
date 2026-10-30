"""Real GPU mipmaps/samplers, safe uploads, sizing and three-patch layouts."""

from contextlib import contextmanager
import json
import os
from pathlib import Path
import struct
from unittest.mock import patch
import zlib

from texture_control_cases import COLORS

LIB = Path(__file__).resolve().parent.parent / 'lib'


def cpu(color='[255 0 0 255]', width=2, height=2):
    return f'(builtins.raylibGenImage {{ width = {width}; height = {height}; color = {color}; }})'


def upload(image=None, *, rec=False, x=0, y=0, name='tex'):
    return '{ op = "' + ('updateTextureRec' if rec else 'updateTexture') + f'"; texture = "{name}"; image = {image or cpu()};' + (f' x = {x}; y = {y};' if rec else '') + ' }'


class TextureAdvancedCases:
    @contextmanager
    def _texture_hook(self, caps=''):
        if not self.texture_library:
            self.skipTest('pass --texture-library for native texture tracing')
        trace = self.asset_directory / 'texture-trace.jsonl'
        trace.unlink(missing_ok=True)
        preload = str(Path(self.texture_library).resolve())
        if os.environ.get('LD_PRELOAD'):
            preload += ' ' + os.environ['LD_PRELOAD']
        with patch.dict(os.environ, {'LD_PRELOAD': preload, 'NIXRAY_TEST_TEXTURE_TRACE': str(trace), 'NIXRAY_TEST_TEXTURE_CAPS': caps}):
            yield trace

    def _texture_native(self, expression, *, caps='', error=None):
        with self._texture_hook(caps) as trace:
            value = self.evaluate(expression, error=error)
        return value, [json.loads(line) for line in trace.read_text().splitlines()]

    def _sampler_native(self, options='', *, width=8, height=8, caps='', error=None, frames=1):
        return self._texture_native(f'''builtins.raylib {{ hidden = true; fps = 0; maxFrames = {frames};
          assets.textures.tex = {{ image = {cpu(width=width, height=height)}; {options} }};
        }} (_: {{ commands = []; }})''', caps=caps, error=error)[1]

    def _asset_sampler_events(self, trace, width=8, height=8):
        ids = [event['id'] for event in trace if event['event'] == 'load-image' and event['width'] == width and event['height'] == height]
        self.assertTrue(ids, trace)
        return [event for event in trace if event.get('id') == ids[-1]]

    def _updated_pixels(self, actions, *, assets=None, frames=1, commands=None):
        return self._capture(commands or '[ { op = "clear"; color = [0 0 0 255]; } { op = "texture"; texture = "tex"; x = 0; y = 0; scale = 8; } ]',
                             assets=assets or f'{{ textures.tex.image = {cpu("[0 0 255 255]")}; }}', textures=actions, frames=frames)

    def test_advanced_texture_action_validation_is_pure(self):
        actions = f'[ {upload()} {upload(cpu(width=1, height=1), rec=True, x=2147483647)} ]'
        for flag in ('--pure-eval', '--restrict-eval'):
            self.assertEqual(self.evaluate(f'builtins.raylibValidateTextures {actions}', flags=[flag], env={'DISPLAY': '', 'WAYLAND_DISPLAY': ''}), 2)
        self.assertEqual(self.evaluate(f'''let ray = import {LIB}; in ray.validateTextures [
          (ray.updateTexture {{ texture = "unloaded"; image = {cpu()}; }})
          (ray.updateTextureRec {{ texture = "unloaded"; image = {cpu()}; x = 0; y = 0; }}) ]'''), 2)

    def test_advanced_texture_action_required_fields(self):
        for field in ('op', 'texture', 'image'):
            self.evaluate(f'builtins.raylibValidateTextures [ (builtins.removeAttrs {upload()} ["{field}"]) ]', error=f"missing attribute '{field}'")
        for field in ('x', 'y'):
            self.evaluate(f'builtins.raylibValidateTextures [ (builtins.removeAttrs {upload(rec=True)} ["{field}"]) ]', error=f"missing attribute '{field}'")

    def test_advanced_texture_action_schema_and_limits(self):
        self.evaluate('builtins.raylibValidateTextures {}', error='expected a list')
        for changes, error in (('op = "paint";', 'unknown texture action'), ('texture = "";', 'must not be empty'),
                                ('image = {};', 'expected a nixray image'), ('x = 0;', "unknown attribute 'x'")):
            self.evaluate(f'builtins.raylibValidateTextures [ ({upload()} // {{ {changes} }}) ]', error=error)
        for x in ('-1', '0.5'):
            self.evaluate(f'builtins.raylibValidateTextures [ {upload(rec=True, x=x)} ]', error='integer')
        self.evaluate(f'builtins.raylibValidateTextures (builtins.genList (_: {upload()}) 257)', error='at most 256')
        self.evaluate(f'''let image = {cpu(width=2048, height=2048)};
          in builtins.raylibValidateTextures (builtins.genList (_: {upload('image')}) 5)''', error='16777216 pixels')

    def test_advanced_texture_full_upload_pixels(self):
        pixels = self._updated_pixels(f'[ {upload()} ]')
        self.assert_pixel(pixels, 4, 4, (255, 0, 0))
        self.assert_pixel(pixels, 15, 15, (255, 0, 0))
        self.assert_pixel(pixels, 16, 15, (0, 0, 0))

    def test_advanced_texture_partial_upload_bounds_and_order(self):
        pixels = self._updated_pixels(f'[ {upload(cpu("[255 255 255 255]"))} {upload(cpu("[0 255 0 255]", 1, 1), rec=True, x=1, y=0)} ]')
        self.assert_pixel(pixels, 4, 4, (255, 255, 255))
        self.assert_pixel(pixels, 12, 4, (0, 255, 0))
        self.assert_pixel(pixels, 12, 12, (255, 255, 255))

    def test_advanced_texture_uploads_persist_across_frames(self):
        pixels = self._updated_pixels(f'if frame.frame == 0 then [ {upload()} ] else []', frames=2)
        self.assert_pixel(pixels, 4, 4, (255, 0, 0))

    def test_advanced_texture_updates_validate_asset_and_dimensions(self):
        cases = ((upload(name='missing'), 'unknown texture'), (upload(cpu(width=1, height=1)), 'must match texture dimensions'),
                 (upload(rec=True, x=1), 'exceeds texture bounds'), (upload(rec=True, x=2147483647), 'exceeds texture bounds'))
        for action, error in cases:
            self.evaluate(f'''builtins.raylib {{ hidden = true; maxFrames = 1; assets.textures.tex.image = {cpu()}; }}
              (_: {{ commands = []; textures = [ {action} ]; }})''', error=error)
        self.evaluate(f'''builtins.raylib {{ hidden = true; maxFrames = 1; assets.renderTextures.tex = {{ width = 2; height = 2; }}; }}
          (_: {{ commands = []; textures = [ {upload()} ]; }})''', error='cannot target a render texture')

    def test_advanced_texture_uploads_are_not_drawing_or_audio_commands(self):
        self.evaluate(f'builtins.raylibValidate [ {upload()} ]', error='unknown drawing operation')
        self.evaluate(f'builtins.raylibValidateAudio [ {upload()} ]', error='unknown audio operation')

    def test_advanced_texture_uploads_happen_before_begin_and_on_close(self):
        _, trace = self._texture_native(f'''builtins.raylib {{ hidden = true; fps = 0; maxFrames = 9; assets.textures.tex.image = {cpu()}; }}
          (_: {{ commands = []; textures = [ {upload()} ]; close = true; }})''')
        events = [event['event'] for event in trace]
        self.assertEqual(events.count('update'), 1)
        self.assertLess(events.index('update'), events.index('begin'))
        asset = next(event['id'] for event in trace if event['event'] == 'update')
        unload = next(i for i, event in enumerate(trace) if event['event'] == 'unload' and event['id'] == asset)
        self.assertLess(events.index('end'), unload)
        self.assertLess(unload, events.index('close'))

    def test_advanced_texture_invalid_frame_prevents_all_uploads(self):
        for extra, error in (('state = throw "failed state";', 'failed state'),
                              ('audio = [ { op = "invalid"; } ];', 'unknown audio operation'),
                              ('window = [ { op = "invalid"; } ];', 'unknown window operation'),
                              ('close = 1;', 'expected a Boolean')):
            _, trace = self._texture_native(f'''builtins.raylib {{ hidden = true; fps = 0; maxFrames = 1; assets.textures.tex.image = {cpu()}; }}
              (_: {{ commands = []; textures = [ {upload()} ]; {extra} }})''', error=error)
            self.assertFalse(any(event['event'] in ('begin', 'update', 'update-rec') for event in trace), trace)

    def test_advanced_texture_invalid_later_upload_prevents_earlier_upload(self):
        _, trace = self._texture_native(f'''builtins.raylib {{ hidden = true; maxFrames = 1; assets.textures.tex.image = {cpu()}; }}
          (_: {{ commands = []; textures = [ {upload()} {upload(rec=True, x=99)} ]; }})''', error='exceeds texture bounds')
        self.assertFalse(any(event['event'].startswith('update') for event in trace))

    def test_advanced_texture_upload_does_not_mutate_cpu_image(self):
        self.assertEqual(self.evaluate(f'''let source = {cpu("[1 2 3 128]")}; run = builtins.raylib {{ hidden = true; fps = 0;
          maxFrames = 1; assets.textures.tex.image = {cpu()}; }} (_: {{ commands = []; textures = [ {upload('source')} ]; state = _: source; }});
          in builtins.raylibImagePixel (run.state null) {{ x = 0; y = 0; }}'''), [1, 2, 3, 128])

    def test_advanced_texture_rgb_conversion_and_odd_row_alignment(self):
        path = self.asset_directory / 'rgb-update.png'
        def chunk(kind, data):
            return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))
        path.write_bytes(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 3, 2, 8, 2, 0, 0, 0))
                         + chunk(b'IDAT', zlib.compress((b'\0' + b'\0'*9)*2)) + chunk(b'IEND', b''))
        assets = f'{{ textures.tex = {json.dumps(str(path))}; }}'
        with self._texture_hook() as trace:
            pixels = self._updated_pixels(f'[ {upload(cpu("[200 100 50 0]", 1, 2), rec=True, x=1)} ]', assets=assets)
        self.assert_pixel(pixels, 12, 4, (200, 100, 50))
        self.assert_pixel(pixels, 12, 12, (200, 100, 50))
        updates = [json.loads(line) for line in trace.read_text().splitlines() if '"event":"update-rec"' in line]
        self.assertEqual(updates[0]['format'], 4) # Native RGB8, not RGBA8.

    def test_advanced_texture_updates_reject_float_texture_formats(self):
        # HDR file decoding is disabled in this build. Upload a real float GPU
        # texture through the fixture instead of assuming that codec is enabled.
        _, trace = self._texture_native(f'''builtins.raylib {{ hidden = true; maxFrames = 1; assets.textures.tex.image = {cpu()}; }}
          (_: {{ commands = []; textures = [ {upload()} ]; }})''', caps='float-texture', error='require uncompressed byte or packed 16-bit')
        self.assertFalse(any(event['event'].startswith('update') for event in trace))

    def test_advanced_texture_mipmap_counts_include_npot_and_single_pixels(self):
        for width, height, levels in ((8, 8, 4), (9, 3, 4), (1, 1, 1)):
            events = self._asset_sampler_events(self._sampler_native('mipmaps = true;', width=width, height=height), width, height)
            mip = next(event for event in events if event['event'] == 'mipmaps')
            self.assertEqual(mip['levels'], levels)
            self.assertEqual(mip['lastSize'], [1, 1])
            self.assertEqual(mip['lastPixel'], [255, 0, 0, 255])

    def test_advanced_texture_mipmap_filter_parameters(self):
        for name, expected in (('point', 0x2700), ('bilinear', 0x2701), ('trilinear', 0x2703)):
            events = self._asset_sampler_events(self._sampler_native(f'mipmaps = true; filter = "{name}";'))
            final = [event for event in events if event['event'] == 'filter'][-1]
            self.assertEqual(final['min'], expected)
            self.assertEqual(final['levels'], 4)
            self.assertEqual(final['mag'], 0x2600 if name == 'point' else 0x2601)

    def test_advanced_texture_trilinear_implicitly_generates_mipmaps(self):
        events = self._asset_sampler_events(self._sampler_native('filter = "trilinear";'))
        self.assertEqual([event['event'] for event in events][:3], ['load-image', 'mipmaps', 'filter'])
        self.assertEqual([event for event in events if event['event'] == 'filter'][-1]['min'], 0x2703)

    def test_advanced_texture_anisotropy_establishes_trilinear_base(self):
        for amount in (4, 8, 16):
            events = self._asset_sampler_events(self._sampler_native(f'filter = "anisotropic{amount}x";'))
            final = [event for event in events if event['event'] == 'filter'][-1]
            self.assertEqual((final['min'], final['mag'], final['anisotropy']), (0x2703, 0x2601, amount))

    def test_advanced_texture_rejects_incompatible_mipmap_options(self):
        for group, source in (('textures', f'image = {cpu()};'), ('renderTextures', 'width = 2; height = 2;')):
            for options, error in (('filter = "trilinear"; mipmaps = false;', 'require mipmaps'),
                                    ('filter = "anisotropic4x"; mipmaps = false;', 'require mipmaps'),
                                    ('mipmaps = 1;', 'expected a Boolean')):
                self.evaluate(f'builtins.raylib {{ assets.{group}.tex = {{ {source} {options} }}; }} (_: {{ commands = []; }})', error=error)

    def test_advanced_texture_unsupported_capabilities_fail_and_clean_up(self):
        for caps, options, error in (('no-anisotropy', 'filter = "anisotropic4x";', 'unsupported by this driver'),
                                    ('low-anisotropy', 'filter = "anisotropic4x";', 'exceeds driver support'),
                                    ('no-mirror-clamp', 'wrap = "mirrorClamp";', 'unsupported by this driver'),
                                    ('bad-mipmaps', 'filter = "trilinear";', 'complete texture mipmaps')):
            trace = self._sampler_native(options, caps=caps, error=error)
            events = self._asset_sampler_events(trace)
            self.assertEqual(events[-1]['event'], 'unload')
            self.assertFalse(any(event['event'] == 'begin' for event in trace))
            self.assertTrue(any(event['event'] == 'close' for event in trace))

    def test_advanced_texture_mirror_clamp_is_native_but_not_repeat_permission(self):
        events = self._asset_sampler_events(self._sampler_native('wrap = "mirrorClamp";'))
        wrapped = next(event for event in events if event['event'] == 'wrap')
        self.assertEqual((wrapped['wrapS'], wrapped['wrapT']), (0x8742, 0x8742))
        self.evaluate(f'''builtins.raylib {{ hidden = true; maxFrames = 1; assets.textures.tex = {{ image = {cpu()}; wrap = "mirrorClamp"; }}; }}
          (_: {{ commands = [ {{ op = "texture"; texture = "tex"; x = 0; y = 0; source = {{ x = 0; y = 0; width = 4; height = 2; }}; }} ]; }})''', error='source rectangle exceeds')

    def test_advanced_texture_upload_refreshes_real_mipmap_pixels(self):
        _, trace = self._texture_native(f'''builtins.raylib {{ hidden = true; fps = 0; maxFrames = 1;
          assets.textures.tex = {{ image = {cpu(width=8, height=8)}; filter = "trilinear"; }};
        }} (_: {{ commands = []; textures = [ {upload(cpu('[0 0 255 255]', 8, 8))} ]; }})''')
        mips = [event for event in self._asset_sampler_events(trace) if event['event'] == 'mipmaps']
        self.assertEqual([event['lastPixel'] for event in mips], [[255, 0, 0, 255], [0, 0, 255, 255]])

    def test_advanced_texture_partial_upload_refreshes_mipmaps(self):
        _, trace = self._texture_native(f'''builtins.raylib {{ hidden = true; fps = 0; maxFrames = 1;
          assets.textures.tex = {{ image = {cpu('[0 0 0 255]', 8, 8)}; filter = "trilinear"; }};
        }} (_: {{ commands = []; textures = [ {upload(cpu('[255 255 255 255]', 4, 8), rec=True)} ]; }})''')
        mips = [event for event in self._asset_sampler_events(trace) if event['event'] == 'mipmaps']
        self.assertTrue(all(abs(channel - 128) <= 1 for channel in mips[-1]['lastPixel'][:3]))

    def test_advanced_texture_multiple_uploads_regenerate_once_per_texture(self):
        _, trace = self._texture_native(f'''builtins.raylib {{ hidden = true; fps = 0; maxFrames = 1;
          assets.textures.tex = {{ image = {cpu(width=8, height=8)}; filter = "trilinear"; }};
        }} (_: {{ commands = []; textures = [ {upload(cpu('[0 255 0 255]', 8, 8))}
          {upload(cpu('[0 0 255 255]', 8, 8))} ]; }})''')
        events = self._asset_sampler_events(trace)
        self.assertEqual(len([event for event in events if event['event'] == 'mipmaps']), 2) # Initial + one refresh.
        self.assertEqual([event for event in events if event['event'] == 'mipmaps'][-1]['lastPixel'], [0, 0, 255, 255])

    def test_advanced_texture_render_target_mipmaps_refresh_after_each_paint(self):
        _, trace = self._texture_native('''builtins.raylib { hidden = true; fps = 0; maxFrames = 2;
          assets.renderTextures.tex = { width = 8; height = 8; filter = "trilinear"; };
        } (frame: { commands = [ { op = "paint"; texture = "tex"; commands = [
          { op = "clear"; color = if frame.frame == 0 then [255 0 0 255] else [0 255 0 255]; }
        ]; } ]; })''')
        mips = [event for event in trace if event['event'] == 'mipmaps' and event['levels'] == 4]
        self.assertEqual([event['lastPixel'] for event in mips], [[0, 0, 0, 0], [255, 0, 0, 255], [0, 255, 0, 255]])

    def test_advanced_texture_trilinear_minification_pixels(self):
        assets = '''{ textures.tex = { image = (builtins.raylibGenImage { kind = "checked";
          width = 16; height = 16; checksX = 1; checksY = 1; color1 = [255 0 0 255]; color2 = [0 0 255 255]; }); filter = "trilinear"; }; }'''
        pixels = self._capture('[ { op = "clear"; color = [0 0 0 255]; } { op = "texture"; texture = "tex"; x = 4; y = 4; width = 1; height = 1; } ]', assets=assets)
        self.assert_pixel(pixels, 4, 4, (128, 0, 128), tolerance=1)

    def test_advanced_texture_mipmapped_targets_keep_upright_stamps(self):
        image = self._sample_pixels('filter = "trilinear";', 'width = 12; height = 8;')
        target = self._sample_pixels('filter = "trilinear";', 'width = 12; height = 8;', target=True)
        self.assertTrue(all(abs(a - b) <= 1 for p, q in zip(image, target) for a, b in zip(p, q)))

    def test_advanced_texture_explicit_size_validation_is_pure(self):
        command = '{ op = "texture"; texture = "unloaded"; x = 0; y = 0; width = 12; height = 8; }'
        self.assertEqual(self.evaluate(f'builtins.raylibValidate [ {command} ]', flags=['--pure-eval']), 1)
        for changes, error in (('scale = 2;', 'mutually exclusive'), ('height = -1;', 'integer in'),
                                ('width = 0.5;', 'expected an integer')):
            self.evaluate(f'builtins.raylibValidate [ ({command} // {{ {changes} }}) ]', error=error)
        for field in ('width', 'height'):
            self.evaluate(f'builtins.raylibValidate [ (builtins.removeAttrs {command} ["{field}"]) ]', error=f"missing attribute '{field}'")

    def test_advanced_texture_nonuniform_size_and_fbo_orientation(self):
        for target in (False, True):
            assets, prefix = self._sampler(target=target)
            pixels = self._capture(f'[ {{ op = "clear"; color = [0 0 0 255]; }} {prefix} {{ op = "texture"; texture = "tex"; x = 4; y = 4; width = 12; height = 8; }} ]', assets=assets)
            for x, y, color in ((6, 6, COLORS[0]), (12, 6, COLORS[1]), (6, 10, COLORS[2]), (12, 10, COLORS[3])):
                self.assert_pixel(pixels, x, y, color)

    def test_advanced_texture_explicit_size_rotates_about_destination_pivot(self):
        assets, _ = self._sampler()
        pixels = self._capture('''[ { op = "clear"; color = [0 0 0 255]; }
          { op = "texture"; texture = "tex"; x = 16; y = 16; width = 12; height = 8;
            origin = { x = 6; y = 4; }; rotation = 90; flipX = true; } ]''', assets=assets)
        for x, y, color in ((18, 12, COLORS[1]), (18, 20, COLORS[0]), (14, 12, COLORS[3]), (14, 20, COLORS[2])):
            self.assert_pixel(pixels, x, y, color)

    def test_advanced_texture_zero_explicit_size_draws_nothing_but_validates(self):
        assets, _ = self._sampler()
        self.assertEqual(set(self._capture('[ { op = "clear"; color = [0 0 0 255]; } { op = "texture"; texture = "tex"; x = 0; y = 0; width = 0; height = 4; } ]', assets=assets)), {(0, 0, 0)})
        self.evaluate('''builtins.raylib { hidden = true; maxFrames = 1; } (_: {
          commands = [ { op = "texture"; texture = "missing"; x = 0; y = 0; width = 0; height = 0; } ]; })''', error='unknown texture')

    def test_advanced_texture_three_patch_validation(self):
        for layout, borders, width, height in (('horizontal', '{ left = 1; right = 3; }', 20, 6), ('vertical', '{ top = 2; bottom = 1; }', 8, 18)):
            command = self._panel_command(f'layout = "{layout}"; source = {{ x = 0; y = 0; width = 8; height = 6; }};', borders=borders, width=width, height=height)
            for flag in ('--pure-eval', '--restrict-eval'):
                self.assertEqual(self.evaluate(f'builtins.raylibValidate [ {command} ]', flags=[flag]), 1)
            wrong = 'height = 7;' if layout == 'horizontal' else 'width = 9;'
            self.evaluate(f'builtins.raylibValidate [ ({command} // {{ {wrong} }}) ]', error='preserve the untouched source dimension')
        self.evaluate(f'builtins.raylibValidate [ {self._panel_command("layout = \"horizontal\";")} ]', error='unknown attribute')

    def test_advanced_texture_three_patch_native_axis_pixels(self):
        for target in (False, True):
            horizontal = self._panel_pixels('layout = "horizontal";', target=target, width=20, height=6, borders='{ left = 1; right = 3; }')
            vertical = self._panel_pixels('layout = "vertical";', target=target, width=8, height=18, borders='{ top = 2; bottom = 1; }')
            for row, y in enumerate((4, 6, 9)):
                for col, x in enumerate((4, 8, 23)):
                    self.assert_pixel(horizontal, x, y, COLORS[row*3 + col])
            for row, y in enumerate((4, 8, 21)):
                for col, x in enumerate((4, 6, 11)):
                    self.assert_pixel(vertical, x, y, COLORS[row*3 + col])

    def test_advanced_texture_three_patch_crops_and_small_destinations(self):
        for target in (False, True):
            attributes = 'layout = "horizontal"; source = { x = 1; y = 1; width = 8; height = 6; };'
            crop = self._panel_pixels(attributes, target=target, atlas=True, width=2, height=6, borders='{ left = 1; right = 3; }')
            self.assert_pixel(crop, 4, 4, COLORS[2])
            self.assert_pixel(crop, 5, 9, COLORS[8])
            self.assert_pixel(crop, 6, 4, (0, 0, 0))

    def test_advanced_texture_three_patch_rotated_pivot(self):
        for target in (False, True):
            pixels = self._panel_pixels('layout = "horizontal"; rotation = 90; origin = { x = 10; y = 3; };',
                                        target=target, x=16, y=16, width=20, height=6, borders='{ left = 1; right = 3; }')
            self.assert_pixel(pixels, 18, 6, COLORS[0])
            self.assert_pixel(pixels, 13, 24, COLORS[8])

    def test_advanced_texture_example(self):
        self.assertEqual(self.evaluate(f'import {LIB.parent / "examples/texture-updates.nix"} {{ hidden = true; maxFrames = 2; }}'),
                         {'frames': 2, 'state': {'paused': False, 'tick': 2}})

    def test_advanced_texture_example_anisotropy(self):
        self.assertEqual(self.evaluate(f'import {LIB.parent / "examples/texture-updates.nix"} {{ hidden = true; maxFrames = 2; filter = "anisotropic16x"; }}'),
                         {'frames': 2, 'state': {'paused': False, 'tick': 2}})
