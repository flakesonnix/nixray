{ hidden ? false, maxFrames ? 0, tones ? import ./synth/tones.nix { } }:
let
  ray = import ../lib;
  clamp = low: high: x: if x < low then low else if x > high then high else x;
  direction = frame: plus: minus:
    (if ray.keyDown frame plus then 1 else 0) - (if ray.keyDown frame minus then 1 else 0);
in
ray.run {
  inherit hidden maxFrames;
  width = 800;
  height = 320;
  title = "Nix audio pitch and stereo pan";
  audio = true;
  assets = {
    sounds.note = "${tones}/triangle-c4.wav";
    music.drone = { path = "${tones}/triangle-c4.wav"; looping = true; };
  };
  state = { pitch = 1.0; pan = 0.0; volume = 0.25; paused = false; };
} (frame:
  let
    dt = clamp 0.0 0.1 frame.delta;
    pitch = clamp 0.125 8.0 (frame.state.pitch + dt * direction frame ray.keys.up ray.keys.down);
    pan = clamp (-1.0) 1.0 (frame.state.pan + dt * direction frame ray.keys.right ray.keys.left);
    volume = clamp 0.0 1.0 (frame.state.volume + frame.mouseWheelY * 0.05);
    toggle = ray.keyPressed frame ray.keys.space;
    paused = if toggle then !frame.state.paused else frame.state.paused;
  in {
    state = { inherit pitch pan volume paused; };
    audio = (if frame.frame == 0 || pitch != frame.state.pitch then [
      (ray.setSoundPitch { sound = "note"; inherit pitch; })
      (ray.setMusicPitch { music = "drone"; inherit pitch; })
    ] else []) ++ (if frame.frame == 0 || pan != frame.state.pan then [
      (ray.setSoundPan { sound = "note"; inherit pan; })
      (ray.setMusicPan { music = "drone"; inherit pan; })
    ] else []) ++ (if frame.frame == 0 || volume != frame.state.volume then [
      (ray.setSoundVolume { sound = "note"; inherit volume; })
      (ray.setMusicVolume { music = "drone"; inherit volume; })
    ] else []) ++ (if frame.frame == 0 then [ (ray.playMusic "drone") ] else [])
      ++ (if toggle then [ (if paused then ray.pauseMusic "drone" else ray.resumeMusic "drone") ] else [])
      ++ (if ray.keyPressed frame ray.keys.a then [ (ray.playSound "note") ] else []);
    commands = [
      (ray.clear (ray.rgb 18 22 33))
      (ray.text { text = "AUDIO PITCH + PAN"; x = 24; y = 24; size = 30; color = ray.colors.skyblue; })
      (ray.text { text = "Up/down: pitch | Left/right: pan | Wheel: volume";
        x = 24; y = 80; size = 20; color = ray.colors.white; })
      (ray.text { text = "A: sound effect | Space: pause/resume looping tone";
        x = 24; y = 112; size = 20; color = ray.colors.white; })
      (ray.text { text = "Pitch ${toString pitch}x | Pan ${toString pan} | Volume ${toString volume}";
        x = 24; y = 164; size = 20; color = ray.colors.skyblue; })
      (ray.text { text = "Music: ${if paused then "paused" else "playing"} | Pan: -1 left, 0 center, +1 right";
        x = 24; y = 208; size = 20; color = ray.colors.gray; })
    ];
  })
