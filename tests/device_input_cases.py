"""Immutable device snapshots with deterministic hotplug and touch fixtures."""

import os
from pathlib import Path
from unittest.mock import patch


PAYLOAD = "{ gamepads = frame.gamepads; touches = frame.touches; gesture = frame.gesture; }"
ZERO_GESTURE = {"detected": 0, "holdDuration": 0, "dragVector": {"x": 0, "y": 0}, "dragAngle": 0,
                "pinchVector": {"x": 0, "y": 0}, "pinchAngle": 0}
LIB = Path(__file__).resolve().parent.parent / "lib"


class DeviceInputCases:
    def _device_preload(self):
        if not self.input_library:
            self.skipTest("pass --input-library to enable device fixture tests")
        library = Path(self.input_library).resolve()
        self.assertTrue(library.is_file(), f"missing input fixture: {library}")
        return str(library) + (" " + os.environ["LD_PRELOAD"] if os.environ.get("LD_PRELOAD") else "")

    def _device_evaluate(self, expression, *, mode="standard"):
        return self.evaluate(expression, env={"LD_PRELOAD": self._device_preload(), "NIXRAY_TEST_DEVICE_INPUT": mode})

    def _device_frames(self, value=PAYLOAD, *, frames=5, config="", mode="standard"):
        return self._device_evaluate(f'''builtins.raylib {{ hidden = true; fps = 0; maxFrames = {frames}; state = []; {config} }}
          (frame: {{ commands = []; state = frame.state ++ [ ({value}) ]; }})''', mode=mode)["state"]

    def test_device_input_empty_snapshots(self):
        self.assertEqual(self._device_frames(frames=2, mode="off"),
                         [{"gamepads": [], "touches": [], "gesture": ZERO_GESTURE}] * 2)

    def test_device_input_hotplug_slot_ids(self):
        self.assertEqual(self._device_frames("map (pad: pad.id) frame.gamepads"), [[0, 3], [0, 2], [2], [], [0]])

    def test_device_input_names_are_copied_and_unicode_preserved(self):
        self.assertEqual(self._device_frames("map (pad: pad.name) frame.gamepads", frames=2),
                         [["Pad 0 frame 0 Ω", "Pad 3 frame 0 Ω"], ["Pad 0 frame 1 Ω", "Pad 2 frame 1 Ω"]])

    def test_device_input_axes_and_native_trigger_range(self):
        self.assertEqual(self._device_frames("map (pad: pad.axes) frame.gamepads"), [
            [[0.25, -0.5, 0, 1, -1, 0.75], [-1, 0.5, -0.25, 0, 1, -1, 0.125, -0.125]],
            [[-0.75, 0.5], []], [[0, 0.25, -0.25]], [], [[0, 0, 0, 0, -1, -1]],
        ])

    def test_device_input_button_down_lists(self):
        self.assertEqual(self._device_frames("map (pad: pad.buttonsDown) frame.gamepads"),
                         [[[1, 7, 31], [17]], [[1], [12]], [[]], [], [[7]]])

    def test_device_input_button_edges_are_per_pad(self):
        self.assertEqual(self._device_frames("map (pad: { pressed = pad.buttonsPressed; released = pad.buttonsReleased; }) frame.gamepads", frames=3), [
            [{"pressed": [1, 7, 31], "released": []}, {"pressed": [17], "released": []}],
            [{"pressed": [], "released": [7, 31]}, {"pressed": [12], "released": []}],
            [{"pressed": [], "released": [12]}],
        ])

    def test_device_input_gamepad_lookup_is_by_id_not_list_index(self):
        self.assertEqual(self._device_frames(f'''let ray = import {LIB}; pad = ray.gamepad frame 3;
          in if pad == null then null else pad.id'''), [3, None, None, None, None])

    def test_device_input_gamepad_helpers_survive_disconnect_and_reconnect(self):
        values = self._device_frames(f'''let ray = import {LIB}; pad = ray.gamepad frame 0; in {{
          available = pad != null;
          down = ray.gamepadButtonDown pad ray.gamepadButtons.rightFaceDown;
          pressed = ray.gamepadButtonPressed pad ray.gamepadButtons.rightFaceDown;
          released = ray.gamepadButtonReleased pad ray.gamepadButtons.rightFaceDown;
          axis = ray.gamepadAxis pad ray.gamepadAxes.leftX;
        }}''')
        self.assertEqual(values, [
            {"available": True, "down": True, "pressed": True, "released": False, "axis": 0.25},
            {"available": True, "down": False, "pressed": False, "released": True, "axis": -0.75},
            {"available": False, "down": False, "pressed": False, "released": False, "axis": 0},
            {"available": False, "down": False, "pressed": False, "released": False, "axis": 0},
            {"available": True, "down": True, "pressed": True, "released": False, "axis": 0},
        ])

    def test_device_input_missing_axis_helpers_return_neutral(self):
        self.assertEqual(self._device_frames(f'''let ray = import {LIB}; pad = ray.gamepad frame 2; in [
          (ray.gamepadAxis pad (-1)) (ray.gamepadAxis pad 0) (ray.gamepadAxis pad 7) (ray.gamepadAxis pad 8)
        ]''', frames=3), [[0, 0, 0, 0]] * 3)

    def test_device_input_constants_and_helpers_are_plain_nix(self):
        result = self.evaluate(f'''let ray = import {LIB}; frame = {{ gamepads = []; gesture.detected = 0; }}; in {{
          buttons = builtins.attrValues ray.gamepadButtons;
          axes = builtins.attrValues ray.gamepadAxes;
          gestures = builtins.attrValues ray.gestures;
          absent = ray.gamepad frame 0;
          neutral = ray.gamepadAxis null 0;
          noButton = ray.gamepadButtonDown null 7;
          none = ray.gestureDetected frame ray.gestures.none;
          noTap = ray.gestureDetected frame ray.gestures.tap;
        }}''', env={"DISPLAY": "", "WAYLAND_DISPLAY": ""})
        self.assertEqual(sorted(result.pop("buttons")), list(range(18)))
        self.assertEqual(sorted(result.pop("axes")), list(range(6)))
        self.assertEqual(sorted(result.pop("gestures")), [0, 1, 2, 4, 8, 16, 32, 64, 128, 256, 512])
        self.assertEqual(result, {"absent": None, "neutral": 0, "noButton": False, "none": True, "noTap": False})

    def test_device_input_touches_keep_ids_positions_and_native_order(self):
        self.assertEqual(self._device_frames("frame.touches"), [
            [{"id": 41, "x": 10.25, "y": 20.5}, {"id": 99, "x": 100.5, "y": 80.25}],
            [{"id": 99, "x": 101.5, "y": 81.25}, {"id": 41, "x": 12.25, "y": 22.5}],
            [{"id": 41, "x": 14.25, "y": 24.5}], [], [{"id": 202, "x": 30, "y": 40}],
        ])

    def test_device_input_all_native_gesture_codes(self):
        self.assertEqual(self._device_frames("frame.gesture.detected", frames=11), [1, 4, 8, 512, 32, 2, 16, 64, 128, 256, 0])

    def test_device_input_gesture_metrics_and_hold_seconds(self):
        values = self._device_frames("frame.gesture", frames=4)
        self.assertEqual(values[0], ZERO_GESTURE | {"detected": 1})
        self.assertEqual(values[1], ZERO_GESTURE | {"detected": 4, "holdDuration": 2.5})
        self.assertEqual(values[2], ZERO_GESTURE | {"detected": 8, "dragVector": {"x": 0.25, "y": -0.5}, "dragAngle": 90})
        self.assertEqual(values[3], {"detected": 512, "holdDuration": 0, "dragVector": {"x": 0.25, "y": -0.5},
                                     "dragAngle": 90, "pinchVector": {"x": 0.75, "y": 0.125}, "pinchAngle": 315})

    def test_device_input_gesture_metrics_can_outlive_detected_gesture(self):
        values = self._device_frames("frame.gesture", frames=11)
        self.assertEqual(values[-1], values[3] | {"detected": 0})

    def test_device_input_gesture_selection(self):
        self.assertEqual(self._device_frames("frame.gesture.detected", frames=11, config="gestures = [ 8 512 ];"),
                         [0, 0, 8, 512, 0, 0, 0, 0, 0, 0, 0])

    def test_device_input_gesture_duplicates_and_none_are_valid(self):
        self.assertEqual(self._device_frames("frame.gesture.detected", frames=4, config="gestures = [ 0 1 1 8 ];"), [1, 0, 8, 0])

    def test_device_input_disabled_detection_keeps_native_metrics(self):
        values = self._device_frames("frame.gesture", frames=4, config="gestures = [];")
        self.assertTrue(all(value["detected"] == 0 for value in values))
        self.assertEqual(values[1]["holdDuration"], 2.5)
        self.assertEqual(values[3]["pinchVector"], {"x": 0.75, "y": 0.125})

    def test_device_input_gesture_flags_reset_between_runs(self):
        self.assertEqual(self._device_evaluate('''let
          run = config: builtins.raylib ({ hidden = true; fps = 0; maxFrames = 1; } // config)
            (frame: { commands = []; state = frame.gesture.detected; });
          first = run { gestures = []; };
          second = builtins.seq first (run {});
          third = builtins.seq second (run { gestures = [8]; });
        in builtins.seq third [ first.state second.state third.state ]'''), [0, 1, 0])

    def test_device_input_invalid_gesture_config(self):
        for value, error in (("{}", "expected a list"), ("true", "expected a list"),
                             ("[ 1.5 ]", "expected an integer"), ("[ true ]", "expected an integer"),
                             ('[ "tap" ]', "expected an integer"), ("[ 3 ]", "unknown gesture code '3'"),
                             ("[ (-1) ]", "integer in"), ("[ 1024 ]", "integer in")):
            with self.subTest(value=value):
                self.evaluate(f"builtins.raylib {{ gestures = {value}; }} (_: {{ commands = []; }})", error=error,
                              env={"DISPLAY": "", "WAYLAND_DISPLAY": ""})

    def test_device_input_snapshot_types(self):
        self.assertEqual(self._device_frames('''{
          pad = builtins.typeOf (builtins.head frame.gamepads);
          axis = builtins.typeOf (builtins.head (builtins.head frame.gamepads).axes);
          button = builtins.typeOf (builtins.head (builtins.head frame.gamepads).buttonsDown);
          touch = builtins.typeOf (builtins.head frame.touches).x;
          id = builtins.typeOf (builtins.head frame.touches).id;
          hold = builtins.typeOf frame.gesture.holdDuration;
          fields = builtins.length (builtins.attrNames frame);
        }''', frames=1), [{"pad": "set", "axis": "float", "button": "int", "touch": "float", "id": "int", "hold": "float", "fields": 24}])

    def test_device_input_ignored_fields_still_poll_once(self):
        # The native fixture aborts on duplicate, missing or out-of-bounds queries.
        self.assertEqual(self._device_evaluate('''builtins.raylib { hidden = true; fps = 0; maxFrames = 5; }
          (_: { commands = []; state = 42; })'''), {"frames": 5, "state": 42})

    def test_device_input_retained_closure_uses_old_snapshot(self):
        value = self._device_evaluate(f'''builtins.raylib {{ hidden = true; fps = 0; maxFrames = 4; }} (frame: {{ commands = [];
          state = if frame.frame == 0 then (_: {PAYLOAD}) else if frame.frame == 3 then frame.state null else frame.state;
        }})''')["state"]
        self.assertEqual(value, self._device_frames(frames=1)[0])

    def test_device_input_retained_values_survive_window_close(self):
        value = self._device_evaluate(f'''let result = builtins.raylib {{ hidden = true; fps = 0; maxFrames = 1; }}
          (frame: {{ commands = []; state = _: {PAYLOAD}; }}); in result.state null''')
        self.assertEqual(value, self._device_frames(frames=1)[0])

    def test_device_input_axis_count_caps_and_null_name(self):
        pads = self._device_frames("frame.gamepads", frames=1, mode="bounds")[0]
        self.assertEqual([(pad["id"], pad["name"], len(pad["axes"])) for pad in pads], [(0, "", 8), (3, "Bounds pad", 0)])
        self.assertEqual(pads[0]["buttonsDown"], [0, 31])

    def test_device_input_negative_counts_become_empty(self):
        values = self._device_frames(frames=2, mode="bounds")
        self.assertEqual(values[1]["gamepads"][0]["axes"], [])
        self.assertEqual(values[1]["touches"], [])

    def test_device_input_nonfinite_axes_are_neutral_finite_values_preserved(self):
        self.assertEqual(self._device_frames("(builtins.head frame.gamepads).axes", frames=1, mode="bounds")[0],
                         [0, 0, 0, 1.25, -1.25, 0.5, 0, -1])

    def test_device_input_touch_count_caps_and_numeric_sanitization(self):
        touches = self._device_frames("frame.touches", frames=1, mode="bounds")[0]
        self.assertEqual(len(touches), 10)
        self.assertEqual(touches[:2], [{"id": -1, "x": 0, "y": 0}, {"id": 1, "x": 0, "y": -2.5}])
        self.assertEqual(touches[-1], {"id": 9, "x": 9.25, "y": -9.5})

    def test_device_input_nonfinite_gesture_metrics_are_zero(self):
        self.assertEqual(self._device_frames("frame.gesture", frames=1, mode="bounds"), [ZERO_GESTURE | {"detected": 4}])

    def test_device_input_drives_real_framebuffer(self):
        with patch.dict(os.environ, {"LD_PRELOAD": self._device_preload(), "NIXRAY_TEST_DEVICE_INPUT": "standard"}):
            pixels = self._capture(f'''let ray = import {LIB}; pad = ray.gamepad frame 3;
            in [ (ray.clear ray.colors.black)
              (ray.rectangle {{ x = 4; y = 4; width = if ray.gamepadButtonDown pad ray.gamepadButtons.rightThumb then 8 else 0;
                height = 4; color = [255 0 0 255]; }})
              (ray.pixel {{ x = builtins.floor ((ray.gamepadAxis pad ray.gamepadAxes.leftX + 1) * 5) + 16;
                y = 12; color = [255 255 255 255]; }})
              (ray.pixel {{ x = builtins.floor (builtins.head frame.touches).x; y = builtins.floor (builtins.head frame.touches).y;
                color = [0 255 0 255]; }})
              (ray.pixel {{ x = 20; y = 10; color = if ray.gestureDetected frame ray.gestures.tap then [255 255 0 255] else [0 0 0 255]; }})
            ]''')
        self.assert_pixel(pixels, 5, 5, (255, 0, 0))
        self.assert_pixel(pixels, 16, 12, (255, 255, 255))
        self.assert_pixel(pixels, 10, 20, (0, 255, 0))
        self.assert_pixel(pixels, 20, 10, (255, 255, 0))

    def test_device_input_example_without_devices(self):
        example = LIB.parent / "examples/devices.nix"
        self.assertEqual(self._device_evaluate(f"import {example} {{ hidden = true; maxFrames = 2; }}", mode="off"),
                         {"frames": 2, "state": {"x": 200, "y": 280, "warm": False}})

    def test_device_input_example_with_hotplug_touch_and_gestures(self):
        example = LIB.parent / "examples/devices.nix"
        self.assertEqual(self._device_evaluate(f"import {example} {{ hidden = true; maxFrames = 4; }}"),
                         {"frames": 4, "state": {"x": 198, "y": 281, "warm": True}})
