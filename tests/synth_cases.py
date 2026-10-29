"""Nix synth logic, generated PCM, and native playback; no Python in the example."""

from array import array
import math
import os
from pathlib import Path
import struct
import wave


ROOT = Path(__file__).resolve().parent.parent


class SynthCases:
    def _synth_drive(self, steps):
        return self.evaluate(f'''let
          synth = import {ROOT / 'examples/synth/instrument.nix'};
          drive = builtins.foldl' (acc: input:
            let next = synth.step ({{ state = acc.state; keysDown = []; keysPressed = [];
              mouseWheelY = 0.0; delta = 0.01; }} // input);
            in {{ state = next.state; frames = acc.frames ++ [ {{ inherit (next) state audio;
              drawing = builtins.raylibValidate next.commands;
              actions = builtins.raylibValidateAudio next.audio;
            }} ]; }}) {{ state = synth.initialState; frames = []; }};
        in (drive {steps}).frames''', env={"DISPLAY": "", "WAYLAND_DISPLAY": ""})

    def _synth_bank(self):
        bank = os.environ.get("NIXRAY_TEST_SYNTH_TONES")
        if not bank:
            self.skipTest("set NIXRAY_TEST_SYNTH_TONES to the built synth-tones package")
        self.assertTrue(Path(bank).is_dir(), bank)
        return bank

    def test_synth_attack_hold_release_and_polyphony(self):
        frames = self._synth_drive('''[
          { keysDown = [65 87]; } { keysDown = [65 87]; } { keysDown = [65 87]; }
          {} { delta = 0.1; } { delta = 0.1; }
        ]''')
        for name in ("c4", "cs4"):
            self.assertEqual([f["state"]["voices"][name]["gate"] for f in frames], [True, True, True, False, False, False])
            levels = [f["state"]["voices"][name]["level"] for f in frames]
            self.assertEqual(levels[:3], [0.5, 1.0, 1.0])
            self.assertAlmostEqual(levels[3], 1.0 - 0.01 / 0.15)
            self.assertGreater(levels[4], 0)
            self.assertEqual(levels[5], 0)
        plays = [a["music"] for f in frames for a in f["audio"] if a["op"] == "playMusic"]
        stops = [a["music"] for f in frames for a in f["audio"] if a["op"] == "stopMusic"]
        self.assertEqual(plays, ["triangle-c4", "triangle-cs4"])
        self.assertEqual(stops, plays)
        self.assertTrue(all(f["drawing"] > 150 for f in frames))

    def test_synth_retrigger_during_release(self):
        frames = self._synth_drive('[ { keysDown = [65]; } {} { keysDown = [65]; } ]')
        self.assertEqual(sum(a["op"] == "playMusic" for f in frames for a in f["audio"]), 2)
        self.assertFalse(any(a["op"] == "stopMusic" for f in frames for a in f["audio"]))
        self.assertGreater(frames[2]["state"]["voices"]["c4"]["level"], frames[1]["state"]["voices"]["c4"]["level"])

    def test_synth_waveform_switch_stops_previous_voices(self):
        frames = self._synth_drive('''[
          { keysDown = [65]; }
          { keysDown = [65]; keysPressed = [32]; }
          { keysDown = [65]; keysPressed = [32]; }
          { keysDown = [65]; keysPressed = [32]; }
        ]''')
        self.assertEqual([f["state"]["waveform"] for f in frames], ["triangle", "square", "saw", "triangle"])
        for i, waveform in enumerate(("triangle", "square", "saw")):
            actions = frames[i + 1]["audio"]
            self.assertEqual(actions[0], {"op": "stopMusic", "music": f"{waveform}-c4"})
            self.assertEqual([a["op"] for a in actions], ["stopMusic", "setMusicVolume", "playMusic"])

    def test_synth_panic_waits_for_key_release(self):
        frames = self._synth_drive('''[
          { keysDown = [65 87]; } { keysDown = [65 87]; keysPressed = [257]; }
          { keysDown = [65 87]; } {} { keysDown = [65]; }
        ]''')
        self.assertEqual([a["op"] for a in frames[1]["audio"]], ["stopMusic", "stopMusic"])
        self.assertEqual(frames[1]["state"]["blocked"], [65, 87])
        self.assertEqual(frames[2]["audio"], [])
        self.assertEqual(frames[3]["state"]["blocked"], [])
        self.assertEqual(frames[4]["audio"][-1], {"op": "playMusic", "music": "triangle-c4"})

    def test_synth_volume_and_delta_are_bounded(self):
        frames = self._synth_drive('''[
          { mouseWheelY = -100.0; delta = -1.0; keysDown = [65]; }
          { mouseWheelY = 100.0; delta = 10.0; keysDown = [65]; }
          { delta = 10.0; } { delta = 10.0; }
        ]''')
        self.assertEqual([f["state"]["volume"] for f in frames], [0, 1, 1, 1])
        self.assertEqual(frames[0]["state"]["voices"]["c4"]["level"], 0)
        self.assertEqual(frames[1]["state"]["voices"]["c4"]["level"], 1)
        self.assertEqual(frames[3]["state"]["voices"]["c4"]["level"], 0)
        for frame in frames:
            for action in frame["audio"]:
                if action["op"] == "setMusicVolume":
                    self.assertGreaterEqual(action["volume"], 0)
                    self.assertLessEqual(action["volume"], 1 / 13)

    def test_synth_idle_has_no_audio_actions(self):
        frames = self._synth_drive('[ {} {} ]')
        self.assertTrue(all(f["audio"] == [] for f in frames))
        self.assertTrue(all(not v["gate"] and v["level"] == 0 for v in frames[-1]["state"]["voices"].values()))

    def test_synth_keyboard_framebuffer(self):
        if not self.capture_library:
            self.skipTest("pass --capture-library to enable framebuffer tests")
        destination = self.asset_directory / "synth.ppm"
        for phase, expected in (("idle", (245, 245, 245)), ("held", (102, 191, 255)), ("release", (255, 161, 0))):
            with self.subTest(phase=phase):
                destination.unlink(missing_ok=True)
                self.evaluate(f'''let
                  synth = import {ROOT / 'examples/synth/instrument.nix'};
                  frame = {{ state = synth.initialState; keysDown = []; keysPressed = [];
                    mouseWheelY = 0.0; delta = 0.01; }};
                  held = synth.step (frame // {{ keysDown = [65 87]; }});
                  result = if "{phase}" == "held" then held else synth.step
                    (frame // {{ state = if "{phase}" == "release" then held.state else synth.initialState; }});
                in builtins.raylib {{ width = 920; height = 520; hidden = true; fps = 0; maxFrames = 1; }}
                  (_: {{ inherit (result) commands; }})''', env={
                    "LD_PRELOAD": str(Path(self.capture_library).resolve()) + " " + os.environ.get("LD_PRELOAD", ""),
                    "NIXRAY_TEST_CAPTURE": str(destination),
                })
                magic, dimensions, maximum, pixels = destination.read_bytes().split(b"\n", 3)
                self.assertEqual((magic, dimensions, maximum), (b"P6", b"920 520", b"255"))
                self.assertEqual(len(pixels), 920 * 520 * 3)
                for x, y, color in ((5, 5, (18, 22, 33)), (50, 275, expected),
                                    (125, 275, (35, 39, 52) if phase == "idle" else expected),
                                    (200, 275, (245, 245, 245))):
                    offset = (y * 920 + x) * 3
                    self.assertEqual(tuple(pixels[offset:offset + 3]), color, (x, y))

    def test_synth_generated_wavs(self):
        bank = Path(self._synth_bank())
        notes = self.evaluate(f"(import {ROOT / 'examples/synth/instrument.nix'}).notes")
        self.assertEqual(len(list(bank.glob("*.wav"))), 39)
        shapes = set()
        for waveform in ("triangle", "square", "saw"):
            for note in notes:
                with self.subTest(waveform=waveform, note=note["name"]):
                    with wave.open(str(bank / f'{waveform}-{note["name"]}.wav'), "rb") as source:
                        self.assertEqual((source.getnchannels(), source.getsampwidth(), source.getnframes()), (1, 2, 32768))
                        self.assertLess(abs(source.getframerate() / 128 - note["frequency"]), 0.004)
                        pcm = source.readframes(source.getnframes())
                    self.assertEqual(pcm, pcm[:256] * 256)
                    samples = struct.unpack("<32768h", pcm)
                    self.assertGreaterEqual(min(samples), -24576)
                    self.assertLessEqual(max(samples), 24576)
                    self.assertGreater(max(samples) - min(samples), 46000)
                    self.assertAlmostEqual(sum(samples[:128]) / 128, 0, delta=256)
                    shapes.add(pcm[:256])
        self.assertEqual(len(shapes), 3)

    def test_synth_native_mixer_contains_oscillating_audio(self):
        bank = self._synth_bank()
        capture = self.asset_directory / "synth-mix.f32"
        for waveform in ("triangle", "square", "saw"):
            with self.subTest(waveform=waveform):
                capture.unlink(missing_ok=True)
                self._audio_evaluate(f'''let synth = import {ROOT / 'examples/synth/instrument.nix'};
                in builtins.raylib {{
                  width = 32; height = 32; hidden = true; fps = 60; maxFrames = 45; audio = true;
                  assets.music."{waveform}-c4" = {{ path = "{bank}/{waveform}-c4.wav"; looping = true; }};
                  state = synth.initialState // {{ waveform = "{waveform}"; }};
                }} (frame: synth.step (frame // {{ keysDown = [65]; keysPressed = []; mouseWheelY = 0.0; }}))''',
                    env={"NIXRAY_TEST_AUDIO_CAPTURE": str(capture)})
                samples = array("f", capture.read_bytes())
                self.assertGreater(len(samples), 10000, "no sustained mixer output")
                self.assertTrue(all(math.isfinite(value) for value in samples))
                channel = samples[::2]
                # Loading/playing can succeed while an unsupported WAV yields DC.
                # Require both polarities, AC energy, and many complete cycles.
                self.assertLess(min(channel), -0.005)
                self.assertGreater(max(channel), 0.005)
                self.assertLess(max(abs(value) for value in channel), 0.05)
                mean = sum(channel) / len(channel)
                rms = math.sqrt(sum((value - mean) ** 2 for value in channel) / len(channel))
                self.assertGreater(rms, 0.005)
                crossings = sum(a < 0 <= b for a, b in zip(channel, channel[1:]))
                self.assertGreater(crossings, 80)

    def test_synth_example_native_bank_and_cleanup(self):
        bank = self._synth_bank()
        result = self._audio_evaluate(f'''import {ROOT / 'examples/synth.nix'} {{
          hidden = true; maxFrames = 2; tones = "{bank}";
        }}''')
        self.assertEqual(result["frames"], 2)
        self.assertEqual(result["state"]["waveform"], "triangle")
        self.assertEqual(result["state"]["volume"], 0.5)
        events = self._audio_trace()
        self.assertEqual(events.count("load-music"), 39)
        self.assertEqual(events.count("update-music 1"), 78)
        self.assertEqual(events.count("unload-music"), 39)
        self.assertNotIn("play-music 1", events)
        self.assertLess(max(i for i, event in enumerate(events) if event == "unload-music"), events.index("device-close"))

    def test_synth_example_keyboard_and_release(self):
        bank = self._synth_bank()
        result = self._audio_evaluate(f'''import {ROOT / 'examples/synth.nix'} {{
          hidden = true; maxFrames = 18; tones = "{bank}";
        }}''', with_input=True)
        self.assertEqual(result["frames"], 18)
        self.assertAlmostEqual(result["state"]["volume"], 0.4625)
        self.assertTrue(all(v["level"] == 0 and not v["gate"] for v in result["state"]["voices"].values()))
        events = self._audio_trace()
        self.assertEqual(events.count("play-music 1"), 1)
        self.assertEqual(events.count("stop-music"), 1)
        self.assertEqual(events.count("update-music 1"), 39 * 18)
