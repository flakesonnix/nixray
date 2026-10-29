"""Pitch/pan validation and real mixer measurements on isolated silent backends."""

from array import array
import math
from pathlib import Path
import struct
import wave


ROOT = Path(__file__).resolve().parent.parent
CONTROLS = (
    ("setSoundPitch", "sound", "pitch"), ("setMusicPitch", "music", "pitch"),
    ("setSoundPan", "sound", "pan"), ("setMusicPan", "music", "pan"),
)


class AudioControlCases:
    def _control_action(self, op, resource, field, value, name="tone"):
        return f'{{ op = "{op}"; {resource} = "{name}"; {field} = {value}; }}'

    def _control_tone(self):
        path = self.asset_directory / "control-tone.wav"
        if not path.exists():
            # Exactly 440 Hz: 128 samples per period at 56320 Hz, signed PCM16.
            period = struct.pack("<128h", *(round(24576 * (1 - 4 * abs(i / 128 - 0.5))) for i in range(128)))
            with wave.open(str(path), "wb") as output:
                output.setparams((1, 2, 56320, 0, "NONE", "not compressed"))
                output.writeframes(period * 4400)  # Ten seconds, including at 8x pitch.
        return str(path)

    def _capture_audio_controls(self, kind, *, pitch=1, pan=0, repeated=False, actions=None, frames=45):
        tone = self._control_tone()
        capture = self.asset_directory / "controls-mix.f32"
        capture.unlink(missing_ok=True)
        suffix = "Sound" if kind == "sound" else "Music"
        assets = f'{{ sounds.tone = "{tone}"; }}' if kind == "sound" else f'{{ music.tone = "{tone}"; }}'
        if actions is None:
            settings = f'''[
              {{ op = "set{suffix}Pitch"; {kind} = "tone"; pitch = {pitch}; }}
              {{ op = "set{suffix}Pan"; {kind} = "tone"; pan = {pan}; }}
            ]'''
            actions = f'''(if frame.frame == 0 then [
              {{ op = "set{suffix}Volume"; {kind} = "tone"; volume = 0.25; }}
            ] else []) ++ (if frame.frame == 0 || {str(repeated).lower()} then {settings} else [])
            ++ (if frame.frame == 0 then [ {{ op = "play{suffix}"; {kind} = "tone"; }} ] else [])'''
        result = self._audio_evaluate(f'''builtins.raylib {{
          width = 32; height = 32; hidden = true; fps = 60; maxFrames = {frames}; audio = true;
          assets = {assets};
        }} (frame: {{ commands = []; audio = {actions}; }})''', env={"NIXRAY_TEST_AUDIO_CAPTURE": str(capture)})
        self.assertEqual(result["frames"], frames)
        samples = array("f", capture.read_bytes())
        self.assertGreater(len(samples), 10000)
        self.assertTrue(all(math.isfinite(value) for value in samples))
        left, right = samples[::2], samples[1::2]
        return left, right

    def _steady(self, samples):
        return samples[len(samples) // 4:len(samples) * 3 // 4]

    def _rms(self, samples):
        return math.sqrt(sum(value * value for value in samples) / len(samples))

    def _frequency(self, samples):
        return sum(a < 0 <= b for a, b in zip(samples, samples[1:])) * 48000 / len(samples)

    def test_audio_control_ranges_are_pure(self):
        for op, resource, field in CONTROLS:
            values = ("0.125", "0.5", "1", "2", "8") if field == "pitch" else ("-1", "-0.5", "0", "0.5", "1")
            for value in values:
                with self.subTest(op=op, value=value):
                    action = self._control_action(op, resource, field, value)
                    for flag in ("--pure-eval", "--restrict-eval"):
                        self.assertEqual(self._audio_evaluate(f"builtins.raylibValidateAudio [ {action} ]",
                            flags=[flag], env={"DISPLAY": "", "WAYLAND_DISPLAY": ""}), 1)
                        self.assertEqual(self._audio_trace(), [])

    def test_audio_control_rejects_invalid_ranges_and_types(self):
        for op, resource, field in CONTROLS:
            values = ("0", "-1", "0.12499", "8.0001", "1.0e100") if field == "pitch" else ("-1.0001", "1.0001", "1.0e100")
            for value in (*values, "true", "null", '"bad"', "[]"):
                with self.subTest(op=op, value=value):
                    self.evaluate(f"builtins.raylibValidateAudio [ {self._control_action(op, resource, field, value)} ]",
                                  error="finite number" if value in values else "expected")

    def test_audio_control_fields_are_strict(self):
        for op, resource, field in CONTROLS:
            for action, error in (
                (f'{{ op = "{op}"; {field} = 1; }}', f"missing attribute '{resource}'"),
                (f'{{ op = "{op}"; {resource} = "tone"; }}', f"missing attribute '{field}'"),
                (f'{{ op = "{op}"; {resource} = ""; {field} = 1; }}', f"{resource} name must not be empty"),
                (f'{{ op = "{op}"; {resource} = "tone"; {field} = 1; volume = 1; }}', "unknown attribute 'volume'"),
            ):
                with self.subTest(op=op, action=action):
                    self.evaluate(f"builtins.raylibValidateAudio [ {action} ]", error=error)
            self.evaluate(f"builtins.raylibValidate [ {self._control_action(op, resource, field, 1)} ]",
                          error="unknown drawing operation")

    def test_audio_controls_resolve_assets(self):
        for op, resource, field in CONTROLS:
            with self.subTest(op=op):
                self._audio_run(f"[ {self._control_action(op, resource, field, 1, 'missing')} ]",
                                error=f"unknown {resource} 'missing'")
                self.assertFalse(any(event.startswith(("sound-pitch", "music-pitch", "sound-pan", "music-pan"))
                                     for event in self._audio_trace()))

    def test_audio_controls_require_opt_in(self):
        for op, resource, field in CONTROLS:
            with self.subTest(op=op):
                self._audio_run(f"[ {self._control_action(op, resource, field, 1)} ]", assets="{}", enabled=False,
                                error="audio actions require config.audio = true")
                self.assertNotIn("device-init", self._audio_trace())

    def test_audio_control_validation_precedes_every_native_change(self):
        for actions, state, error in (
            ('[ { op = "setSoundPitch"; sound = "click"; pitch = 2; } '
             '{ op = "setMusicPan"; music = "theme"; pan = 2; } ]', "null", "finite number"),
            ('[ { op = "setMusicPan"; music = "theme"; pan = 0.5; } ]',
             '{ fail = throw "control state failed"; }', "control state failed"),
        ):
            with self.subTest(actions=actions):
                self._audio_run(actions, state=state, error=error)
                events = self._audio_trace()
                self.assertFalse(any(event.startswith(("sound-pitch", "music-pan", "update-music")) for event in events))
                self.assertIn("device-close", events)

    def test_audio_sound_pitch_mixer(self):
        self._check_pitch_mixer("sound")

    def test_audio_music_pitch_mixer(self):
        self._check_pitch_mixer("music")

    def _check_pitch_mixer(self, kind):
        for pitch in (0.125, 1, 2, 8):
            with self.subTest(pitch=pitch):
                left, right = self._capture_audio_controls(kind, pitch=pitch, repeated=True)
                steady = self._steady(left)
                self.assertGreater(self._rms(steady), 0.02)
                self.assertAlmostEqual(self._frequency(steady), 440 * pitch, delta=5)
                self.assertLess(max(abs(a - b) for a, b in zip(left, right)), 1e-6)
                self.assertEqual(self._audio_trace().count(f"{kind}-pitch {pitch:g}"), 45)

    def test_audio_sound_pan_mixer(self):
        self._check_pan_mixer("sound")

    def test_audio_music_pan_mixer(self):
        self._check_pan_mixer("music")

    def _check_pan_mixer(self, kind):
        for pan in (-1, -0.5, 0, 0.5, 1):
            with self.subTest(pan=pan):
                left, right = self._capture_audio_controls(kind, pan=pan)
                left_rms, right_rms = self._rms(self._steady(left)), self._rms(self._steady(right))
                if pan == -1:
                    self.assertGreater(left_rms, 0.05)
                    self.assertLess(right_rms, 1e-7)
                elif pan == 1:
                    self.assertGreater(right_rms, 0.05)
                    self.assertLess(left_rms, 1e-7)
                else:
                    self.assertGreater(min(left_rms, right_rms), 0.02)
                    l, r = (1 - pan) / 2, (1 + pan) / 2
                    expected = (l * (3 - l*l)) / (r * (3 - r*r))
                    self.assertAlmostEqual(left_rms / right_rms, expected, delta=0.01)

    def test_audio_live_pitch_pan_changes(self):
        for kind in ("sound", "music"):
            with self.subTest(kind=kind):
                suffix = "Sound" if kind == "sound" else "Music"
                actions = f'''if frame.frame == 0 then [
                  {{ op = "set{suffix}Volume"; {kind} = "tone"; volume = 0.25; }}
                  {{ op = "set{suffix}Pan"; {kind} = "tone"; pan = -1; }}
                  {{ op = "play{suffix}"; {kind} = "tone"; }}
                ] else if frame.frame == 45 then [
                  {{ op = "set{suffix}Pitch"; {kind} = "tone"; pitch = 2; }}
                  {{ op = "set{suffix}Pan"; {kind} = "tone"; pan = 1; }}
                ] else []'''
                left, right = self._capture_audio_controls(kind, actions=actions, frames=90)
                early = slice(len(left) // 8, len(left) * 3 // 8)
                late = slice(len(left) * 5 // 8, len(left) * 7 // 8)
                self.assertAlmostEqual(self._frequency(left[early]), 440, delta=5)
                self.assertAlmostEqual(self._frequency(right[late]), 880, delta=5)
                self.assertLess(self._rms(right[early]), 1e-7)
                self.assertLess(self._rms(left[late]), 1e-7)

    def test_audio_controls_are_per_asset(self):
        tone = self._control_tone()
        capture = self.asset_directory / "independent-controls.f32"
        self._audio_evaluate(f'''builtins.raylib {{
          width = 32; height = 32; hidden = true; fps = 60; maxFrames = 45; audio = true;
          assets = {{ sounds.left = "{tone}"; music.right = "{tone}"; }};
        }} (frame: {{ commands = []; audio = if frame.frame != 0 then [] else [
          {{ op = "setSoundVolume"; sound = "left"; volume = 0.25; }}
          {{ op = "setMusicVolume"; music = "right"; volume = 0.25; }}
          {{ op = "setSoundPan"; sound = "left"; pan = -1; }}
          {{ op = "setMusicPan"; music = "right"; pan = 1; }}
          {{ op = "setMusicPitch"; music = "right"; pitch = 2; }}
          {{ op = "playSound"; sound = "left"; }} {{ op = "playMusic"; music = "right"; }}
        ]; }})''', env={"NIXRAY_TEST_AUDIO_CAPTURE": str(capture)})
        samples = array("f", capture.read_bytes())
        self.assertGreater(len(samples), 10000)
        self.assertAlmostEqual(self._frequency(self._steady(samples[::2])), 440, delta=5)
        self.assertAlmostEqual(self._frequency(self._steady(samples[1::2])), 880, delta=5)

    def test_audio_controls_persist_across_transport(self):
        for kind in ("sound", "music"):
            with self.subTest(kind=kind):
                suffix = "Sound" if kind == "sound" else "Music"
                actions = f'''if frame.frame == 0 then [
                  {{ op = "set{suffix}Volume"; {kind} = "tone"; volume = 0.25; }}
                  {{ op = "set{suffix}Pitch"; {kind} = "tone"; pitch = 2; }}
                  {{ op = "set{suffix}Pan"; {kind} = "tone"; pan = -1; }}
                  {{ op = "play{suffix}"; {kind} = "tone"; }}
                ] else if frame.frame == 20 then [ {{ op = "pause{suffix}"; {kind} = "tone"; }} ]
                else if frame.frame == 30 then [ {{ op = "resume{suffix}"; {kind} = "tone"; }} ]
                else if frame.frame == 50 then [ {{ op = "stop{suffix}"; {kind} = "tone"; }} ]
                else if frame.frame == 60 then [ {{ op = "play{suffix}"; {kind} = "tone"; }} ] else []'''
                left, right = self._capture_audio_controls(kind, actions=actions, frames=90)
                # Cleanup can append a silent device callback after asset unloading.
                # Measure the final audible quarter-second, not that padding.
                last = next((i + 1 for i in range(len(left) - 1, -1, -1) if abs(left[i]) > 1e-6), 0)
                self.assertGreaterEqual(last, 12000)
                first = last - 12000
                tail = left[first:last]
                self.assertGreater(self._rms(tail), 0.05)
                self.assertAlmostEqual(self._frequency(tail), 880, delta=5)
                self.assertLess(self._rms(right[first:last]), 1e-7)
                events = self._audio_trace()
                self.assertEqual(events.count(f"{kind}-pitch 2"), 1)
                self.assertEqual(events.count(f"{kind}-pan -1"), 1)

    def test_audio_control_example_input(self):
        bank = self._synth_bank()
        result = self._audio_evaluate(f'''import {ROOT / 'examples/audio-controls.nix'} {{
          hidden = true; maxFrames = 6; tones = "{bank}";
        }}''', with_input=True)
        self.assertEqual(result["frames"], 6)
        self.assertAlmostEqual(result["state"]["volume"], 0.2125)
        self.assertEqual(result["state"]["pitch"], 1)
        self.assertEqual(result["state"]["pan"], 0)
        self.assertEqual(self._audio_trace().count("play-sound"), 1)

    def test_audio_control_example(self):
        bank = self._synth_bank()
        result = self._audio_evaluate(f'''import {ROOT / 'examples/audio-controls.nix'} {{
          hidden = true; maxFrames = 2; tones = "{bank}";
        }}''')
        self.assertEqual(result, {"frames": 2, "state": {"pitch": 1.0, "pan": 0.0, "volume": 0.25, "paused": False}})
        events = self._audio_trace()
        for event in ("sound-pitch 1", "music-pitch 1", "sound-pan 0", "music-pan 0", "play-music 1"):
            self.assertEqual(events.count(event), 1, events)
