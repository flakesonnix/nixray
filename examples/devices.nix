{ hidden ? false, maxFrames ? 0 }:
let
  ray = import ../lib;
  clamp = low: high: x: if x < low then low else if x > high then high else x;
  text = value: x: y: ray.text { text = value; inherit x y; size = 18; color = ray.colors.gray; };
  gestureName = code:
    let names = builtins.filter (name: ray.gestures.${name} == code) (builtins.attrNames ray.gestures);
    in if names == [] then toString code else builtins.head names;
in ray.run {
  inherit hidden maxFrames;
  width = 800; height = 600;
  title = "Nix gamepad, touch and gesture snapshots";
  state = { x = 200; y = 280; warm = false; };
} (frame:
  let
    pad = if frame.gamepads == [] then null else builtins.head frame.gamepads;
    x = clamp 40 360 (frame.state.x + 4 * ray.gamepadAxis pad ray.gamepadAxes.leftX
      + (if ray.keyDown frame ray.keys.right then 3 else 0) - (if ray.keyDown frame ray.keys.left then 3 else 0));
    y = clamp 130 430 (frame.state.y + 4 * ray.gamepadAxis pad ray.gamepadAxes.leftY
      + (if ray.keyDown frame ray.keys.down then 3 else 0) - (if ray.keyDown frame ray.keys.up then 3 else 0));
    warm = if ray.gamepadButtonPressed pad ray.gamepadButtons.rightFaceDown || ray.gestureDetected frame ray.gestures.tap
      then !frame.state.warm else frame.state.warm;
    gesture = frame.gesture;
  in {
    state = { inherit x y warm; };
    commands = [
      (ray.clear (ray.rgb 18 22 33))
      (ray.text { text = "Gamepads, touch and gestures"; x = 24; y = 20; size = 26; color = ray.colors.white; })
      (text (if pad == null then "No gamepad connected - arrows still work"
        else "Slot ${toString pad.id}: ${pad.name}") 24 65)
      (ray.rectangleLines { x = 24; y = 110; width = 352; height = 340; color = ray.colors.gray; })
      (ray.circle { x = builtins.floor x; y = builtins.floor y; radius = 18;
        color = if warm then ray.colors.orange else ray.colors.skyblue; })
      (text "Left stick / arrows: move" 35 465)
      (text "South face button / tap: change color" 35 490)
      (text "Gesture: ${gestureName gesture.detected}" 410 120)
      (text "Hold: ${toString gesture.holdDuration} seconds" 410 150)
      (text "Touch contacts: ${toString (builtins.length frame.touches)}" 410 180)
      (text "Connected pads: ${toString (builtins.length frame.gamepads)}" 410 210)
    ] ++ (if ray.gestureDetected frame ray.gestures.drag then [
      (ray.lineEx { x1 = 580; y1 = 320;
        x2 = builtins.floor (clamp 410 770 (580 + gesture.dragVector.x * 160));
        y2 = builtins.floor (clamp 250 450 (320 + gesture.dragVector.y * 160));
        thickness = 5; color = ray.colors.green; })
    ] else []) ++ builtins.concatLists (map (touch: [
      (ray.circleLines { x = builtins.floor touch.x; y = builtins.floor touch.y; radius = 22; color = ray.colors.yellow; })
      (text "${toString touch.id}" (builtins.floor touch.x + 25) (builtins.floor touch.y))
    ]) frame.touches) ++ [
      (text "Native touch/gesture support depends on the raylib backend." 24 540)
      (text "Desktop mouse gestures can work without a touchscreen." 24 565)
    ];
  })
