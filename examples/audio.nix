{ sound, music, hidden ? false, maxFrames ? 0 }:
let
  ray = import ../lib;
  clamp = low: high: value: if value < low then low else if value > high then high else value;
in
ray.run {
  inherit hidden maxFrames;
  width = 640;
  height = 360;
  title = "Nix sound effects and streamed music";
  audio = true;
  assets = {
    sounds.click = sound;
    music.theme = { path = music; looping = true; };
  };
  state = { volume = 0.5; paused = false; };
} (frame:
  let
    volume = clamp 0.0 1.0 (frame.state.volume + frame.mouseWheelY * 0.05);
    toggle = ray.keyPressed frame ray.keys.enter;
    paused = if toggle then !frame.state.paused else frame.state.paused;
    status = frame.audio.music.theme;
  in {
    state = { inherit volume paused; };
    audio = (if frame.frame == 0 || volume != frame.state.volume then [
      (ray.setSoundVolume { sound = "click"; inherit volume; })
      (ray.setMusicVolume { music = "theme"; inherit volume; })
    ] else []) ++ (if frame.frame == 0 then [ (ray.playMusic "theme") ] else [])
      ++ (if ray.keyPressed frame ray.keys.a then [ (ray.playSound "click") ] else [])
      ++ (if toggle then [ (if paused then ray.pauseMusic "theme" else ray.resumeMusic "theme") ] else []);
    commands = [
      (ray.clear ray.colors.raywhite)
      (ray.text {
        text = "A: sound effect | Enter: pause/resume music";
        x = 24; y = 32; size = 24; color = ray.colors.blue;
      })
      (ray.text {
        text = "Mouse wheel: volume (${toString volume})";
        x = 24; y = 88; size = 24; color = ray.colors.black;
      })
      (ray.text {
        text = "Music: ${if status.playing then "playing" else "paused/stopped"}";
        x = 24; y = 144; size = 24; color = ray.colors.purple;
      })
      (ray.text {
        text = "${toString status.timePlayed} / ${toString status.timeLength} seconds";
        x = 24; y = 200; size = 20; color = ray.colors.black;
      })
    ];
  })
