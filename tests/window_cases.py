"""Window snapshots, deferred controls, pure schemas and native lifecycle."""

import os
from pathlib import Path


LIB = Path(__file__).resolve().parent.parent / "lib"
ACTIONS = {
    "setWindowTitle": {"title": '"Changed title"'},
    "setWindowSize": {"width": "96", "height": "80"},
    "setWindowPosition": {"x": "40", "y": "50"},
    "setTargetFPS": {"fps": "120"},
    "setWindowFullscreen": {"enabled": "true"},
    "setWindowResizable": {"enabled": "true"},
    "setCursorMode": {"mode": '"hidden"'},
}


def action(op, changes=None, *, remove=()):
    fields = ACTIONS[op] | (changes or {})
    return '{ op = "' + op + '"; ' + " ".join(f"{k} = {v};" for k, v in fields.items() if k not in remove) + " }"


class WindowCases:
    def _window_preload(self):
        if not self.window_library:
            self.skipTest("pass --window-library to enable window fixture tests")
        library = Path(self.window_library).resolve()
        self.assertTrue(library.is_file(), f"missing window fixture: {library}")
        return str(library) + (" " + os.environ["LD_PRELOAD"] if os.environ.get("LD_PRELOAD") else "")

    def _window_evaluate(self, expression, *, env=None, **kwargs):
        trace = self.asset_directory / "window-trace.txt"
        trace.unlink(missing_ok=True)
        return self.evaluate(expression, env={"LD_PRELOAD": self._window_preload(), "NIXRAY_TEST_WINDOW_TRACE": str(trace), **(env or {})}, **kwargs)

    def _window_trace(self):
        trace = self.asset_directory / "window-trace.txt"
        return trace.read_text().splitlines() if trace.exists() else []

    def _window_frames(self, actions="[]", *, frames=3, value="frame.window", config="", **kwargs):
        result = self._window_evaluate(f'''builtins.raylib {{ width = 64; height = 64; title = "Initial";
          hidden = true; fps = 0; maxFrames = {frames}; state = []; {config}
        }} (frame: {{ commands = []; window = {actions}; state = frame.state ++ [ ({value}) ]; }})''', **kwargs)
        return result["state"] if result is not None else None

    def test_window_control_validation_is_pure(self):
        actions = "[ " + " ".join(action(op) for op in ACTIONS) + " ]"
        for flag in ("--pure-eval", "--restrict-eval"):
            self.assertEqual(self.evaluate(f"builtins.raylibValidateWindow {actions}", flags=[flag], env={"DISPLAY": "", "WAYLAND_DISPLAY": ""}), 7)
        self.assertEqual(self.evaluate("builtins.raylibValidateWindow []"), 0)
        self.assertEqual(self.evaluate("builtins.typeOf builtins.raylibValidateWindow"), "lambda")

    def test_window_control_nix_helpers(self):
        self.assertEqual(self.evaluate(f'''let ray = import {LIB}; in ray.validateWindow [
          (ray.setWindowTitle "New") (ray.setWindowSize {{ width = 64; height = 80; }})
          (ray.setWindowPosition {{ x = -10; y = 20; }}) (ray.setTargetFPS 0)
          (ray.setWindowFullscreen true) (ray.setWindowResizable false) (ray.setCursorMode "captured")
        ]'''), 7)

    def test_window_control_required_fields(self):
        for op, fields in ACTIONS.items():
            for field in fields:
                self.evaluate(f"builtins.raylibValidateWindow [ {action(op, remove=(field,))} ]", error=f"missing attribute '{field}'")
        self.evaluate("builtins.raylibValidateWindow [ {} ]", error="missing attribute 'op'")

    def test_window_control_list_and_entry_schema(self):
        for expression, error in (("{}", "expected a list"), ("[ [] ]", "expected a set"),
                                  ('[ { op = "clear"; } ]', "unknown window operation 'clear'"),
                                  ('[ { op = "setWindowTitle"; title = "x"; commands = []; } ]', "unknown attribute 'commands'")):
            self.evaluate(f"builtins.raylibValidateWindow {expression}", error=error)
        for op in ACTIONS:
            self.evaluate(f"builtins.raylibValidateWindow [ {action(op, {'typo': '1'})} ]", error="unknown attribute 'typo'")

    def test_window_control_integer_bounds(self):
        for op, field in (("setWindowSize", "width"), ("setWindowSize", "height"), ("setWindowPosition", "x"),
                          ("setWindowPosition", "y"), ("setTargetFPS", "fps")):
            self.evaluate(f"builtins.raylibValidateWindow [ {action(op, {field: '1.5'})} ]", error="expected an integer")
        for field in ("width", "height"):
            for value in ("0", "-1", "16385"):
                self.evaluate(f"builtins.raylibValidateWindow [ {action('setWindowSize', {field: value})} ]", error="integer in [1, 16384]")
        for op, field, value in (("setWindowPosition", "x", "2147483648"), ("setWindowPosition", "y", "-2147483649"),
                                 ("setTargetFPS", "fps", "-1"), ("setTargetFPS", "fps", "2147483648")):
            self.evaluate(f"builtins.raylibValidateWindow [ {action(op, {field: value})} ]", error="integer in")
        self.assertEqual(self.evaluate('''builtins.raylibValidateWindow [
          { op = "setWindowSize"; width = 1; height = 16384; }
          { op = "setWindowPosition"; x = -2147483648; y = 2147483647; }
          { op = "setTargetFPS"; fps = 2147483647; }
        ]'''), 3)

    def test_window_control_booleans_strings_and_cursor_modes(self):
        for op in ("setWindowFullscreen", "setWindowResizable"):
            self.evaluate(f"builtins.raylibValidateWindow [ {action(op, {'enabled': '1'})} ]", error="expected a Boolean")
        for op, field in (("setWindowTitle", "title"), ("setCursorMode", "mode")):
            self.evaluate(f"builtins.raylibValidateWindow [ {action(op, {field: 'true'})} ]", error="expected a string")
            nul = r"""builtins.fromJSON ''"a\u0000b"''"""
            self.evaluate(f"builtins.raylibValidateWindow [ {action(op, {field: nul})} ]", error="null bytes")
        self.evaluate('builtins.raylibValidateWindow [ { op = "setCursorMode"; mode = "disabled"; } ]', error="unknown cursor mode 'disabled'")
        self.assertEqual(self.evaluate('''builtins.raylibValidateWindow [
          { op = "setWindowTitle"; title = ""; }
          { op = "setCursorMode"; mode = "normal"; }
          { op = "setCursorMode"; mode = "hidden"; }
          { op = "setCursorMode"; mode = "captured"; }
        ]'''), 4)

    def test_window_control_lists_are_separate_from_drawing_and_audio(self):
        self.evaluate(f"builtins.raylibValidate [ {action('setWindowTitle')} ]", error="unknown drawing operation")
        self.evaluate(f"builtins.raylibValidateAudio [ {action('setWindowTitle')} ]", error="unknown audio operation")

    def test_window_control_initial_snapshot(self):
        self.assertEqual(self._window_frames(frames=1)[0], {
            "title": "Initial", "targetFPS": 0, "position": {"x": 12.5, "y": 34.25},
            "renderWidth": 64, "renderHeight": 64, "dpiScale": {"x": 1.5, "y": 2}, "monitor": 0,
            "fullscreen": False, "resizable": False, "hidden": True, "minimized": False,
            "maximized": False, "focused": True, "resized": False, "cursorMode": "normal", "cursorOnScreen": True,
        })

    def test_window_control_native_state_flags_change_per_frame(self):
        self.assertEqual(self._window_frames(value="{ inherit (frame.window) minimized maximized focused resized cursorOnScreen; }"), [
            {"minimized": False, "maximized": False, "focused": True, "resized": False, "cursorOnScreen": True},
            {"minimized": True, "maximized": False, "focused": False, "resized": True, "cursorOnScreen": False},
            {"minimized": False, "maximized": True, "focused": True, "resized": False, "cursorOnScreen": True},
        ])

    def test_window_control_title_and_fps_affect_later_snapshots(self):
        values = self._window_frames('''if frame.frame == 0 then [
          { op = "setWindowTitle"; title = "Next"; } { op = "setTargetFPS"; fps = 120; }
        ] else []''', value="{ inherit (frame.window) title targetFPS; }")
        self.assertEqual(values, [{"title": "Initial", "targetFPS": 0}, {"title": "Next", "targetFPS": 120}, {"title": "Next", "targetFPS": 120}])

    def test_window_control_actions_follow_drawing_in_list_order(self):
        self._window_frames('''if frame.frame == 0 then [
          { op = "setWindowTitle"; title = "First"; }
          { op = "setWindowPosition"; x = 40; y = 50; }
          { op = "setWindowTitle"; title = "Last"; }
          { op = "setTargetFPS"; fps = 120; }
        ] else []''', frames=2)
        trace = self._window_trace()
        start, end = trace.index("end:0"), trace.index("begin:1")
        self.assertEqual(trace[start + 1:end], ["title:First", "position:40,50", "title:Last", "fps:120"])

    def test_window_control_position_and_resizability(self):
        values = self._window_frames('''if frame.frame == 0 then [
          { op = "setWindowPosition"; x = -10; y = 20; }
          { op = "setWindowResizable"; enabled = true; }
        ] else [ { op = "setWindowResizable"; enabled = false; } ]''',
                                    value="{ inherit (frame.window) position resizable; }")
        self.assertEqual(values, [{"position": {"x": 12.5, "y": 34.25}, "resizable": False},
                                  {"position": {"x": -10, "y": 20}, "resizable": True},
                                  {"position": {"x": -10, "y": 20}, "resizable": False}])

    def test_window_control_fullscreen_is_absolute_and_cleaned_up(self):
        values = self._window_frames('[ { op = "setWindowFullscreen"; enabled = true; } ]', value="frame.window.fullscreen")
        self.assertEqual(values, [False, True, True])
        transitions = [line for line in self._window_trace() if line.startswith("fullscreen-transition:")]
        self.assertEqual(transitions, ["fullscreen-transition:1", "fullscreen-transition:0"])
        self.assertEqual(self._window_trace()[-1], "close")

    def test_window_control_fullscreen_exit_action(self):
        values = self._window_frames('[ { op = "setWindowFullscreen"; enabled = frame.frame == 0; } ]', value="frame.window.fullscreen")
        self.assertEqual(values, [False, True, False])

    def test_window_control_real_fullscreen_round_trip(self):
        values = self.evaluate('''builtins.raylib { width = 64; height = 64; hidden = true; fps = 0; maxFrames = 5; state = []; }
          (frame: { commands = []; state = frame.state ++ [ { width = frame.width; height = frame.height; fullscreen = frame.window.fullscreen; } ];
            window = if frame.frame == 0 then [ { op = "setWindowFullscreen"; enabled = true; } ]
              else if frame.frame == 2 then [ { op = "setWindowFullscreen"; enabled = false; } ] else [];
          })''')["state"]
        self.assertEqual(values[0], {"width": 64, "height": 64, "fullscreen": False})
        self.assertTrue(values[1]["fullscreen"])
        self.assertEqual(values[-1], {"width": 64, "height": 64, "fullscreen": False})

    def test_window_control_real_fullscreen_cleanup_before_new_window(self):
        result = self.evaluate('''let first = builtins.raylib { width = 64; height = 64; hidden = true; fps = 0; maxFrames = 1; }
          (_: { commands = []; window = [ { op = "setWindowFullscreen"; enabled = true; } ]; });
        in builtins.seq first (builtins.raylib { width = 80; height = 72; hidden = true; fps = 0; maxFrames = 1; }
          (frame: { commands = []; state = [ frame.width frame.height frame.window.fullscreen ]; }))''')
        self.assertEqual(result["state"], [80, 72, False])

    def test_window_control_cursor_modes_are_absolute(self):
        modes = self._window_frames('''[ { op = "setCursorMode";
          mode = builtins.elemAt [ "captured" "hidden" "normal" "normal" ] frame.frame; } ]''', frames=4, value="frame.window.cursorMode")
        self.assertEqual(modes, ["normal", "captured", "hidden", "normal"])
        calls = [line for line in self._window_trace() if line.startswith("cursor:")]
        self.assertEqual(calls, ["cursor:normal", "cursor:captured", "cursor:normal", "cursor:hidden", "cursor:normal", "cursor:normal"])

    def test_window_control_resize_preserves_current_framebuffer(self):
        if not self.capture_library:
            self.skipTest("pass --capture-library to enable framebuffer tests")
        capture = self.asset_directory / "resize.ppm"
        self._window_evaluate('''builtins.raylib { width = 32; height = 32; hidden = true; fps = 0; maxFrames = 1; }
          (_: { commands = [ { op = "clear"; color = [17 34 51 255]; } ];
            window = [ { op = "setWindowSize"; width = 64; height = 48; } ]; })''', env={
                "LD_PRELOAD": str(Path(self.capture_library).resolve()) + " " + self._window_preload(),
                "NIXRAY_TEST_CAPTURE": str(capture),
            })
        magic, size, maximum, pixels = capture.read_bytes().split(b"\n", 3)
        self.assertEqual((magic, size, maximum), (b"P6", b"32 32", b"255"))
        self.assertEqual(pixels, bytes((17, 34, 51)) * (32 * 32))
        self.assertLess(self._window_trace().index("end:0"), self._window_trace().index("size:64,48"))

    def test_window_control_resize_updates_native_dimensions(self):
        values = self._window_frames('''if frame.frame == 0 then [ { op = "setWindowSize"; width = 96; height = 80; } ] else []''',
                                    frames=4, value="{ width = frame.width; height = frame.height; renderWidth = frame.window.renderWidth; renderHeight = frame.window.renderHeight; }")
        self.assertEqual(values[0], {"width": 64, "height": 64, "renderWidth": 64, "renderHeight": 64})
        self.assertEqual(values[-1], {"width": 96, "height": 80, "renderWidth": 96, "renderHeight": 80})

    def test_window_control_invalid_batch_never_mutates_or_draws(self):
        self._window_frames('[ { op = "setWindowTitle"; title = "Never"; } { op = "setCursorMode"; mode = "bad"; } ]', frames=1,
                            error="unknown cursor mode")
        self.assertFalse(any(line.startswith(("begin:", "title:Never")) for line in self._window_trace()))

    def test_window_control_bad_drawing_prevents_window_actions(self):
        self._window_evaluate('''builtins.raylib { hidden = true; fps = 0; maxFrames = 1; } (_: {
          commands = [ { op = "unknown"; } ]; window = [ { op = "setWindowTitle"; title = "Never"; } ];
        })''', error="unknown drawing operation")
        self.assertFalse(any(line.startswith(("begin:", "title:Never")) for line in self._window_trace()))

    def test_window_control_bad_state_prevents_window_actions(self):
        self._window_evaluate('''builtins.raylib { hidden = true; fps = 0; maxFrames = 1; } (_: {
          commands = []; window = [ { op = "setWindowTitle"; title = "Never"; } ]; state = { unused = throw "state failure"; };
        })''', error="state failure")
        self.assertFalse(any(line.startswith(("begin:", "title:Never")) for line in self._window_trace()))

    def test_window_control_bad_audio_prevents_window_actions(self):
        self._window_evaluate('''builtins.raylib { hidden = true; fps = 0; maxFrames = 1; } (_: {
          commands = []; audio = [ { op = "unknown"; } ]; window = [ { op = "setWindowTitle"; title = "Never"; } ];
        })''', error="unknown audio operation")
        self.assertNotIn("title:Never", self._window_trace())

    def test_window_control_bad_window_prevents_valid_audio(self):
        assets = self._audio_assets()
        self._audio_evaluate(f'''builtins.raylib {{ hidden = true; fps = 0; maxFrames = 1; audio = true; assets = {assets}; }} (_: {{
          commands = []; audio = [ {{ op = "playSound"; sound = "click"; }} ];
          window = [ {{ op = "setTargetFPS"; fps = -1; }} ];
        }})''', error="integer in")
        self.assertNotIn("play-sound", self._audio_trace())

    def test_window_control_close_frame_still_runs_actions(self):
        result = self._window_evaluate('''builtins.raylib { hidden = true; fps = 0; maxFrames = 10; } (_: {
          commands = []; window = [ { op = "setWindowTitle"; title = "Final"; } ]; close = true;
        })''')
        self.assertEqual(result["frames"], 1)
        trace = self._window_trace()
        self.assertLess(trace.index("end:0"), trace.index("title:Final"))
        self.assertLess(trace.index("title:Final"), trace.index("close"))

    def test_window_control_snapshot_retained_across_mutation_and_close(self):
        result = self._window_evaluate('''let result = builtins.raylib { hidden = true; fps = 0; maxFrames = 2; title = "Original"; }
          (frame: { commands = []; window = [ { op = "setWindowTitle"; title = "Changed"; } ];
            state = if frame.frame == 0 then (_: frame.window) else frame.state;
          }); in result.state null''')
        self.assertEqual(result["title"], "Original")
        self.assertTrue(result["focused"])

    def test_window_control_title_storage_outlives_action_lists(self):
        result = self._window_evaluate('''builtins.raylib { hidden = true; fps = 0; maxFrames = 5; } (frame: {
          commands = []; state = frame.window.title;
          window = if frame.frame == 0 then [ { op = "setWindowTitle"; title = builtins.concatStringsSep "" (builtins.genList (_: "title-") 100); } ] else [];
        })''')
        self.assertEqual(result["state"], "title-" * 100)

    def test_window_control_empty_titles_and_repeated_windows(self):
        result = self._window_evaluate('''let
          first = builtins.raylib { hidden = true; fps = 0; maxFrames = 1; title = ""; }
            (_: { commands = []; window = [ { op = "setWindowFullscreen"; enabled = true; } ]; });
        in builtins.seq first (builtins.raylib { hidden = true; fps = 0; maxFrames = 1; title = ""; }
          (frame: { commands = []; state = { inherit (frame.window) title fullscreen cursorMode targetFPS; }; }))''')
        self.assertEqual(result["state"], {"title": "", "fullscreen": False, "cursorMode": "normal", "targetFPS": 0})

    def test_window_control_exception_cleanup_exits_fullscreen(self):
        self.assertEqual(self._window_evaluate('''let failed = builtins.tryEval (builtins.raylib {
          hidden = true; fps = 0; maxFrames = 2;
        } (frame: if frame.frame == 1 then throw "later failure" else {
          commands = []; window = [ { op = "setWindowFullscreen"; enabled = true; } ];
        })); in assert !failed.success;
          builtins.raylib { hidden = true; fps = 0; maxFrames = 1; }
            (frame: { commands = []; state = frame.window.fullscreen; })''')["state"], False)

    def test_window_control_nonfinite_vectors_do_not_poison_json(self):
        values = self._window_frames(frames=1, env={"NIXRAY_TEST_WINDOW_NONFINITE": "1"})
        self.assertEqual(values[0]["position"], {"x": 0, "y": 0})
        self.assertEqual(values[0]["dpiScale"], {"x": 0, "y": 0})

    def test_window_control_example(self):
        example = LIB.parent / "examples/window.nix"
        self.assertEqual(self.evaluate(f"import {example} {{ hidden = true; maxFrames = 2; }}"),
                         {"frames": 2, "state": {"wide": False}})

    def test_window_control_example_keyboard_actions(self):
        example = LIB.parent / "examples/window.nix"
        self.assertEqual(self._window_evaluate(f"import {example} {{ hidden = true; maxFrames = 5; }}",
                                               env={"NIXRAY_TEST_WINDOW_INPUT": "1"}),
                         {"frames": 5, "state": {"wide": False}})
        trace = self._window_trace()
        for event in ("size:960,540", "size:800,450", "fullscreen:1", "fullscreen:0", "resizable:0",
                      "cursor:hidden", "cursor:captured", "cursor:normal", "title:Nix window - frame 0", "fps:144", "position:80,80"):
            self.assertIn(event, trace)
