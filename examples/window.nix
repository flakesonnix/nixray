{ hidden ? false, maxFrames ? 0 }:
let
  ray = import ../lib;
  keys = { f = 70; r = 82; c = 67; t = 84; p = 80; m = 77; };
  text = value: y: ray.text { text = value; x = 24; inherit y; size = 20; color = ray.colors.gray; };
  yes = value: if value then "yes" else "no";
in ray.run {
  inherit hidden maxFrames;
  width = 800; height = 450;
  title = "Nix window controls";
  resizable = true;
  state = { wide = false; };
} (frame:
  let
    window = frame.window;
    pressed = ray.keyPressed frame;
    wide = if pressed ray.keys.space then !frame.state.wide else frame.state.wide;
    nextCursor = if window.cursorMode == "normal" then "hidden"
      else if window.cursorMode == "hidden" then "captured" else "normal";
  in {
    state = { inherit wide; };
    window = (if pressed ray.keys.space then [ (ray.setWindowSize {
      width = if wide then 960 else 800; height = if wide then 540 else 450;
    }) ] else [])
      ++ (if pressed keys.f then [ (ray.setWindowFullscreen (!window.fullscreen)) ] else [])
      ++ (if pressed keys.r then [ (ray.setWindowResizable (!window.resizable)) ] else [])
      ++ (if pressed keys.c then [ (ray.setCursorMode nextCursor) ] else [])
      ++ (if pressed keys.t then [ (ray.setWindowTitle "Nix window - frame ${toString frame.frame}") ] else [])
      ++ (if pressed keys.p then [ (ray.setTargetFPS (if window.targetFPS == 60 then 144 else 60)) ] else [])
      ++ (if pressed keys.m then [ (ray.setWindowPosition { x = 80; y = 80; }) ] else []);
    commands = [
      (ray.clear (ray.rgb 18 22 33))
      (ray.text { text = "Window state and deferred controls"; x = 24; y = 20; size = 26; color = ray.colors.white; })
      (text "Logical: ${toString frame.width} x ${toString frame.height} | Framebuffer: ${toString window.renderWidth} x ${toString window.renderHeight}" 75)
      (text "Position: ${toString window.position.x}, ${toString window.position.y} | Monitor: ${toString window.monitor}" 110)
      (text "DPI: ${toString window.dpiScale.x}, ${toString window.dpiScale.y} | Target FPS: ${toString window.targetFPS}" 145)
      (text "Focused: ${yes window.focused} | Resized: ${yes window.resized} | Resizable: ${yes window.resizable}" 180)
      (text "Fullscreen: ${yes window.fullscreen} | Cursor: ${window.cursorMode}" 215)
      (text "Space: resize | F: fullscreen | R: resizable | C: cursor mode" 280)
      (text "T: title | P: target FPS | M: move to (80, 80) | Esc: quit" 315)
      (text "Window actions apply after drawing; snapshots report later native state." 380)
    ];
  })
