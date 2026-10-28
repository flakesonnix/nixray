"""Real raylib audio on silent fixtures/backends, with native call-order tracing."""

import json
import os
from pathlib import Path
import wave


ACTIONS = '''[
  { op = "playSound"; sound = "click"; }
  { op = "setSoundVolume"; sound = "click"; volume = 0.5; }
  { op = "pauseSound"; sound = "click"; }
  { op = "resumeSound"; sound = "click"; }
  { op = "stopSound"; sound = "click"; }
  { op = "playMusic"; music = "theme"; }
  { op = "setMusicVolume"; music = "theme"; volume = 0.25; }
  { op = "pauseMusic"; music = "theme"; }
  { op = "resumeMusic"; music = "theme"; }
  { op = "seekMusic"; music = "theme"; position = 2.5; }
  { op = "stopMusic"; music = "theme"; }
]'''


class AudioCases:
    def _audio_files(self):
        path = self.asset_directory / "silence.wav"
        if not path.exists():
            with wave.open(str(path), "wb") as output:
                output.setparams((1, 2, 8000, 0, "NONE", "not compressed"))
                output.writeframes(b"\0\0" * 80000)  # Ten seconds, never audible.
        configuration = self.asset_directory / "silent-alsa.conf"
        configuration.write_text('pcm.!default { type null hint.description "nixray silent test device" }\n')
        return json.dumps(str(path)), str(configuration)

    def _audio_assets(self, *, looping=False, extra=""):
        path, _ = self._audio_files()
        return (f"{{ sounds.click = {path}; music.theme = {{ path = {path}; "
                f"looping = {str(looping).lower()}; }}; {extra} }}")

    def _audio_evaluate(self, expression, *, env=None, with_input=False, **kwargs):
        if not self.audio_library:
            self.skipTest("pass --audio-library to enable native audio tests")
        library = Path(self.audio_library).resolve()
        self.assertTrue(library.is_file(), f"missing audio fixture library: {library}")
        _, configuration = self._audio_files()
        destination = self.asset_directory / "audio-trace.txt"
        destination.unlink(missing_ok=True)
        preload = str(library)
        if with_input:
            if not self.input_library:
                self.skipTest("pass --input-library to enable audio example input tests")
            preload += " " + str(Path(self.input_library).resolve())
        if os.environ.get("LD_PRELOAD"):
            preload += " " + os.environ["LD_PRELOAD"]
        return self.evaluate(expression, env={
            "LD_PRELOAD": preload,
            "NIXRAY_TEST_AUDIO_TRACE": str(destination),
            "ALSA_CONFIG_PATH": configuration,
            "PULSE_SERVER": f"unix:{self.asset_directory / 'no-pulse-socket'}",
            "PIPEWIRE_REMOTE": "nixray-no-pipewire",
            "JACK_NO_START_SERVER": "1",
            **(env or {}),
        }, **kwargs)

    def _audio_trace(self):
        path = self.asset_directory / "audio-trace.txt"
        return path.read_text().splitlines() if path.exists() else []

    def _audio_run(self, actions="[]", *, frames=1, state="frame.audio", initial="null", draw="[]",
                   assets=None, enabled=True, **kwargs):
        assets = self._audio_assets() if assets is None else assets
        return self._audio_evaluate(f'''builtins.raylib {{
          width = 32; height = 32; hidden = true; fps = 0; maxFrames = {frames};
          audio = {str(enabled).lower()}; assets = {assets}; state = {initial};
        }} (frame: {{ commands = {draw}; audio = {actions}; state = {state}; }})''', **kwargs)

    def test_audio_validation_is_pure(self):
        for flag in ("--pure-eval", "--restrict-eval"):
            with self.subTest(flag=flag):
                self.assertEqual(self.evaluate(f"builtins.raylibValidateAudio {ACTIONS}", flags=[flag],
                                               env={"DISPLAY": "", "WAYLAND_DISPLAY": ""}), 11)
        self.assertEqual(self.evaluate("builtins.typeOf builtins.raylibValidateAudio"), "lambda")

    def test_audio_helpers(self):
        library = Path(__file__).resolve().parent.parent / "lib"
        self.assertEqual(self.evaluate(f'''let ray = import {library}; in ray.validateAudio [
          (ray.playSound "click") (ray.pauseSound "click") (ray.resumeSound "click") (ray.stopSound "click")
          (ray.setSoundVolume {{ sound = "click"; volume = 0.5; }})
          (ray.playMusic "theme") (ray.pauseMusic "theme") (ray.resumeMusic "theme") (ray.stopMusic "theme")
          (ray.setMusicVolume {{ music = "theme"; volume = 0.5; }})
          (ray.seekMusic {{ music = "theme"; position = 1.25; }})
        ]''', env={"DISPLAY": "", "WAYLAND_DISPLAY": ""}), 11)

    def test_audio_pure_validation_never_probes_device(self):
        for flag in ("--pure-eval", "--restrict-eval"):
            with self.subTest(flag=flag):
                self.assertEqual(self._audio_evaluate(f"builtins.raylibValidateAudio {ACTIONS}", flags=[flag],
                    env={"DISPLAY": "", "WAYLAND_DISPLAY": "", "NIXRAY_TEST_AUDIO_FAIL_INIT": "1"}), 11)
                self.assertEqual(self._audio_trace(), [])

    def test_audio_bad_action_lists(self):
        for actions, error in (
            ("{}", "expected a list"), ("[ {} ]", "missing attribute 'op'"),
            ('[ { op = "unknown"; } ]', "unknown audio operation 'unknown'"),
            ('[ { op = "clear"; color = [0 0 0 255]; } ]', "unknown audio operation 'clear'"),
            ('[ { op = "playSound"; } ]', "missing attribute 'sound'"),
            ('[ { op = "playMusic"; } ]', "missing attribute 'music'"),
            ('[ { op = "playSound"; sound = ""; } ]', "sound name must not be empty"),
            ('[ { op = "playMusic"; music = ""; } ]', "music name must not be empty"),
            ('[ { op = "stopSound"; sound = 1; } ]', "expected a string"),
            ('[ { op = "pauseMusic"; music = "theme"; typo = 1; } ]', "unknown attribute 'typo'"),
            ('[ { op = "playSound"; sound = "click"; commands = []; } ]', "unknown attribute 'commands'"),
            ('[ { op = "setSoundVolume"; sound = "click"; } ]', "missing attribute 'volume'"),
            ('[ { op = "seekMusic"; music = "theme"; } ]', "missing attribute 'position'"),
            ('[ { op = "seekMusic"; music = "theme"; position = -1; } ]', "finite number"),
            ('[ { op = "seekMusic"; music = "theme"; position = 1.0e100; } ]', "finite number"),
        ):
            with self.subTest(actions=actions):
                self.evaluate(f"builtins.raylibValidateAudio {actions}", error=error)
        self.evaluate('builtins.raylibValidate [ { op = "playSound"; sound = "click"; } ]',
                      error="unknown drawing operation 'playSound'")

    def test_audio_volume_validation(self):
        for op, resource in (("setSoundVolume", "sound"), ("setMusicVolume", "music")):
            for value in ("-0.1", "1.01", "1.0e100", "true", '"bad"'):
                with self.subTest(op=op, value=value):
                    self.evaluate(f'''builtins.raylibValidateAudio [ {{
                      op = "{op}"; {resource} = "unloaded"; volume = {value};
                    }} ]''', error="finite number" if value not in ("true", '"bad"') else "expected")
            for value in ("0", "1", "0.5"):
                with self.subTest(op=op, valid=value):
                    self.assertEqual(self.evaluate(f'''builtins.raylibValidateAudio [ {{
                      op = "{op}"; {resource} = "unloaded"; volume = {value};
                    }} ]''', flags=["--pure-eval"]), 1)

    def test_audio_disabled_does_not_touch_device(self):
        result = self._audio_run(assets="{}", enabled=False, frames=2,
                                 env={"NIXRAY_TEST_AUDIO_FAIL_INIT": "1"})
        self.assertEqual(result, {"frames": 2, "state": {"enabled": False, "sounds": {}, "music": {}}})
        self.assertEqual(self._audio_trace(), ["frame", "frame", "window-close"])
        self.assertEqual(self._audio_evaluate('''builtins.raylib {
          hidden = true; fps = 0; maxFrames = 1;
        } (_: { commands = []; })'''), {"frames": 1, "state": None})
        self.assertEqual(self._audio_trace(), ["frame", "window-close"])

    def test_audio_disabled_rejects_assets_and_actions(self):
        for enabled in ("false", "null"):
            if enabled == "null":
                self._audio_evaluate('''builtins.raylib { audio = null; } (_: { commands = []; })''',
                                     error="expected a Boolean")
            else:
                self._audio_run(enabled=False, error="audio assets require config.audio = true")
                self.assertEqual(self._audio_trace(), [])
        self._audio_run('[ { op = "playSound"; sound = "missing"; } ]', enabled=False, assets="{}",
                        error="audio actions require config.audio = true")
        self.assertFalse(any(event.startswith("device-") for event in self._audio_trace()))

    def test_audio_device_opt_in_and_empty_assets(self):
        result = self._audio_run(assets="{}")
        self.assertEqual(result, {"frames": 1, "state": {"enabled": True, "sounds": {}, "music": {}}})
        events = self._audio_trace()
        self.assertEqual(events.count("device-init"), 1)
        self.assertEqual(events.count("device-close"), 1)
        self.assertLess(events.index("device-close"), events.index("window-close"))

    def test_audio_device_initialization_failure(self):
        self._audio_run(env={"NIXRAY_TEST_AUDIO_FAIL_INIT": "1"}, error="could not initialize the audio device")
        events = self._audio_trace()
        self.assertIn("device-init", events)
        self.assertNotIn("device-close", events)
        self.assertNotIn("load-sound", events)
        self.assertIn("window-close", events)

    def test_audio_does_not_take_over_existing_device(self):
        self._audio_run(assets="{}", env={"NIXRAY_TEST_AUDIO_ALREADY_READY": "1"},
                        error="an audio device is already active")
        self.assertEqual(self._audio_trace(), ["device-ready", "window-close"])

    def test_audio_native_wav_assets_and_cleanup_order(self):
        result = self._audio_run(frames=2)
        status = result["state"]
        self.assertEqual(result["frames"], 2)
        self.assertTrue(status["enabled"])
        self.assertEqual(status["sounds"], {"click": {"playing": False}})
        self.assertEqual(status["music"]["theme"], {
            "playing": False, "looping": False, "timePlayed": 0.0, "timeLength": 10.0,
        })
        events = self._audio_trace()
        for event in ("load-sound", "load-music", "unload-sound", "unload-music", "device-init", "device-close"):
            self.assertEqual(events.count(event), 1, events)
        self.assertEqual(events.count("update-music 0"), 2)
        self.assertLess(events.index("unload-sound"), events.index("device-close"))
        self.assertLess(events.index("unload-music"), events.index("device-close"))
        self.assertLess(events.index("device-close"), events.index("window-close"))

    def test_audio_transport_transitions_and_snapshots(self):
        actions = '''if frame.frame == 0 then [
          { op = "playSound"; sound = "click"; } { op = "playMusic"; music = "theme"; }
        ] else if frame.frame == 1 then [
          { op = "pauseSound"; sound = "click"; } { op = "pauseMusic"; music = "theme"; }
        ] else if frame.frame == 2 then [
          { op = "resumeSound"; sound = "click"; } { op = "resumeMusic"; music = "theme"; }
        ] else if frame.frame == 3 then [
          { op = "stopSound"; sound = "click"; } { op = "stopMusic"; music = "theme"; }
        ] else []'''
        result = self._audio_run(actions, frames=5, initial="[]", state="frame.state ++ [ frame.audio ]")
        self.assertEqual(result["frames"], 5)
        states = result["state"]
        self.assertEqual([value["sounds"]["click"]["playing"] for value in states], [False, True, False, True, False])
        self.assertEqual([value["music"]["theme"]["playing"] for value in states], [False, True, False, True, False])
        for value in states:
            music = value["music"]["theme"]
            self.assertIsInstance(music["timePlayed"], float)
            self.assertGreaterEqual(music["timePlayed"], 0)
            self.assertLessEqual(music["timePlayed"], music["timeLength"])

    def test_audio_all_actions_execute_in_list_order(self):
        self._audio_run(ACTIONS)
        events = self._audio_trace()
        controls = [event for event in events if event.startswith(
            ("play-", "pause-", "resume-", "stop-", "sound-volume", "music-volume", "seek-"))]
        self.assertEqual(controls, ["play-sound", "sound-volume 0.5", "pause-sound", "resume-sound", "stop-sound",
                                    "play-music 0", "music-volume 0.25", "pause-music", "resume-music", "seek-music 2.5",
                                    "stop-music"])
        self.assertLess(events.index("stop-music"), events.index("update-music 0"))
        self.assertLess(events.index("update-music 0"), events.index("frame"))

    def test_audio_music_updates_once_per_rendered_frame(self):
        path, _ = self._audio_files()
        self._audio_run(frames=3, assets=self._audio_assets(extra=f"music.other = {path};"))
        events = self._audio_trace()
        self.assertEqual(events.count("load-music"), 2)
        self.assertEqual(events.count("update-music 0"), 3)
        self.assertEqual(events.count("update-music 1"), 3)
        self.assertEqual(events.count("frame"), 3)
        self.assertEqual(events.count("unload-music"), 2)

    def test_audio_music_default_looping_and_optional_action_list(self):
        path, _ = self._audio_files()
        result = self._audio_evaluate(f'''builtins.raylib {{
          hidden = true; fps = 0; maxFrames = 1; audio = true; assets.music.theme = {path};
        }} (frame: {{ commands = []; state = frame.audio; }})''')
        self.assertTrue(result["state"]["music"]["theme"]["looping"])
        self.assertIn("update-music 1", self._audio_trace())

    def test_audio_seek_limits(self):
        for position in (0, 2.5, 10):
            with self.subTest(position=position):
                self._audio_run(f'[ {{ op = "seekMusic"; music = "theme"; position = {position}; }} ]',
                                assets=self._audio_assets(looping=True))
                self.assertIn(f"seek-music {position:g}", self._audio_trace())
        for position in ("10.1", "1.0e30"):
            with self.subTest(position=position):
                self._audio_run(f'[ {{ op = "seekMusic"; music = "theme"; position = {position}; }} ]',
                                error="music seek position must not exceed the track length")
                self.assertFalse(any(event.startswith("seek-music") for event in self._audio_trace()))

    def test_audio_music_frame_count_guard(self):
        self._audio_run(env={"NIXRAY_TEST_AUDIO_OVERSIZE_MUSIC": "1"},
                        error="music frame count must fit signed 32-bit")
        events = self._audio_trace()
        self.assertIn("unload-music", events)
        self.assertLess(events.index("unload-music"), events.index("device-close"))
        self.assertNotIn("frame", events)

    def test_audio_seek_rounding_cannot_overflow_signed_frame_queries(self):
        self._audio_run('''[ {
          op = "seekMusic"; music = "theme"; position = frame.audio.music.theme.timeLength;
        } ]''', env={"NIXRAY_TEST_AUDIO_LIMIT_MUSIC": "1"},
                        error="music seek position must fit native frame coordinates")
        events = self._audio_trace()
        self.assertFalse(any(event.startswith("seek-music") for event in events))
        self.assertNotIn("update-music 0", events)
        self.assertNotIn("frame", events)

    def test_audio_unknown_resources(self):
        for action, error in (
            ('{ op = "playSound"; sound = "missing"; }', "unknown sound 'missing'"),
            ('{ op = "playMusic"; music = "missing"; }', "unknown music 'missing'"),
        ):
            with self.subTest(action=action):
                self._audio_run(f"[ {action} ]", error=error)
                self.assertNotIn("play-sound", self._audio_trace())
                self.assertNotIn("play-music 0", self._audio_trace())

    def test_audio_invalid_asset_specs(self):
        path, _ = self._audio_files()
        for assets, error in (
            ("{ sounds = []; }", "expected a set"),
            ('{ sounds.click = "relative.wav"; }', "asset paths must be"),
            ("{ music.theme = {}; }", "missing attribute 'path'"),
            (f"{{ music.theme = {{ path = {path}; looping = 1; }}; }}", "expected a Boolean"),
            (f"{{ music.theme = {{ path = {path}; typo = 1; }}; }}", "unknown attribute 'typo'"),
            (f'{{ sounds."" = {path}; }}', "asset names must be nonempty"),
        ):
            with self.subTest(assets=assets):
                self._audio_run(assets=assets, error=error)
                self.assertEqual(self._audio_trace(), [])

    def test_audio_bad_files_and_partial_loading_cleanup(self):
        path, _ = self._audio_files()
        bad = self.asset_directory / "bad-audio.wav"
        bad.write_bytes(b"not a WAVE file")
        invalid = json.dumps(str(bad))
        for group, noun, unload in (("sounds", "sound", "unload-sound"), ("music", "music", "unload-music")):
            with self.subTest(group=group):
                self._audio_run(assets=f"{{ {group} = {{ a = {path}; z = {invalid}; }}; }}",
                                error=f"could not load {noun} 'z'")
                events = self._audio_trace()
                self.assertEqual(events.count(unload), 1)
                self.assertLess(events.index(unload), events.index("device-close"))
                self.assertLess(events.index("device-close"), events.index("window-close"))
                self.assertNotIn("frame", events)
        self._audio_run(assets=f'{{ sounds.missing = "{self.asset_directory / "missing.wav"}"; }}',
                        error="could not load sound 'missing'")

    def test_audio_all_validation_finishes_before_playback_or_streaming(self):
        config = f"{{ hidden = true; fps = 0; maxFrames = 1; audio = true; assets = {self._audio_assets()}; }}"
        play = '[ { op = "playSound"; sound = "click"; } ]'
        for output, error in (
            (f'{{ commands = [ {{ op = "invalid-draw"; }} ]; audio = {play}; }}', "unknown drawing operation"),
            (f'{{ commands = []; audio = {play} ++ [ {{ op = "invalid-audio"; }} ]; }}', "unknown audio operation"),
            (f'{{ commands = []; audio = {play}; state = {{ bad = throw "audio state failed"; }}; }}', "audio state failed"),
            (f'{{ commands = []; audio = {play}; close = 1; }}', "expected a Boolean"),
            ('{ commands = []; audio = null; }', "expected a list"),
        ):
            with self.subTest(output=output):
                self._audio_evaluate(f"builtins.raylib {config} (_: {output})", error=error)
                events = self._audio_trace()
                self.assertNotIn("play-sound", events)
                self.assertNotIn("update-music 0", events)
                self.assertNotIn("frame", events)

    def test_audio_snapshots_survive_resource_cleanup(self):
        config = f"{{ hidden = true; fps = 0; maxFrames = 1; audio = true; assets = {self._audio_assets()}; }}"
        result = self._audio_evaluate(f'''let result = builtins.raylib {config}
          (frame: {{ commands = []; state = _: frame.audio; }});
        in result.state null''')
        self.assertTrue(result["enabled"])
        self.assertEqual(result["music"]["theme"]["timeLength"], 10.0)
        self.assertIn("device-close", self._audio_trace())

    def test_audio_callback_exception_and_repeated_windows(self):
        config = f"{{ hidden = true; fps = 0; maxFrames = 1; audio = true; assets = {self._audio_assets()}; }}"
        result = self._audio_evaluate(f'''let
          config = {config};
          failed = builtins.tryEval (builtins.raylib config (_: {{ commands = [];
            audio = [ (throw "audio callback failed") ]; }}));
          total = builtins.foldl' (sum: _: sum + (builtins.raylib config (_: {{
            commands = []; audio = [ {{ op = "playSound"; sound = "click"; }} ];
          }})).frames) 0 [ 1 2 3 ];
        in assert !failed.success; total''')
        self.assertEqual(result, 3)
        events = self._audio_trace()
        self.assertEqual(events.count("device-init"), 4)
        self.assertEqual(events.count("device-close"), 4)
        self.assertEqual(events.count("unload-sound"), 4)
        self.assertEqual(events.count("unload-music"), 4)
        self.assertEqual(events.count("frame"), 3)

    def test_audio_early_close_executes_one_validated_frame(self):
        result = self._audio_evaluate(f'''builtins.raylib {{
          hidden = true; fps = 0; maxFrames = 3; audio = true; assets = {self._audio_assets()};
        }} (_: {{ commands = []; close = true; audio = [
          {{ op = "playSound"; sound = "click"; }} {{ op = "playMusic"; music = "theme"; }}
        ]; }})''')
        self.assertEqual(result, {"frames": 1, "state": None})
        events = self._audio_trace()
        for event in ("play-sound", "play-music 0", "update-music 0", "frame", "device-close"):
            self.assertEqual(events.count(event), 1, events)

    def test_audio_paths_and_store_context(self):
        path, _ = self._audio_files()
        for expression, flags in ((f"builtins.toPath {path}", []),
                                  (f'"${{builtins.path {{ path = builtins.toPath {path}; name = "nixray-silent.wav"; }}}}"',
                                   ["--read-write-mode"])):
            with self.subTest(expression=expression):
                result = self._audio_run(assets=f"{{ sounds.click = {expression}; music.theme = {expression}; }}", flags=flags)
                self.assertEqual(result["state"]["music"]["theme"]["timeLength"], 10.0)

    def test_audio_example(self):
        example = Path(__file__).resolve().parent.parent / "examples/audio.nix"
        path, _ = self._audio_files()
        self.assertEqual(self._audio_evaluate(f'''import {example} {{
          sound = {path}; music = {path}; hidden = true; maxFrames = 2;
        }}'''), {"frames": 2, "state": {"volume": 0.5, "paused": False}})
        events = self._audio_trace()
        self.assertEqual(events.count("play-music 1"), 1)
        self.assertNotIn("play-sound", events)

    def test_audio_example_input_edges(self):
        example = Path(__file__).resolve().parent.parent / "examples/audio.nix"
        path, _ = self._audio_files()
        result = self._audio_evaluate(f'''import {example} {{
          sound = {path}; music = {path}; hidden = true; maxFrames = 6;
        }}''', with_input=True)
        self.assertEqual(result["frames"], 6)
        self.assertAlmostEqual(result["state"]["volume"], 0.4625)
        self.assertTrue(result["state"]["paused"])
        events = self._audio_trace()
        self.assertEqual(events.count("play-sound"), 1)
        self.assertEqual(events.count("play-music 1"), 1)
        self.assertEqual(events.count("pause-music"), 1)
