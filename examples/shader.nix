{ hidden ? false, maxFrames ? 0 }:
let
  ray = import ../lib;
  clamp = low: high: value: if value < low then low else if value > high then high else value;
in
ray.run {
  inherit hidden maxFrames;
  width = 640;
  height = 360;
  title = "Nix scoped fragment shader";
  state = { gain = 1.0; };
  assets = {
    renderTextures.scene = { width = 128; height = 96; };
    shaders.tint = {
      fragment = ./shaders/tint.fs;
      uniforms = {
        gain = { type = "float"; value = 1.0; };
        tint = { type = "vec3"; value = [ 1 1 1 ]; };
      };
    };
  };
} (frame:
  let gain = clamp 0.0 2.0 (frame.state.gain + frame.mouseWheelY * 0.1);
  in {
    state = { inherit gain; };
    commands = [
      (ray.clear ray.colors.raywhite)
      (ray.paint {
        texture = "scene";
        commands = [
          (ray.clear ray.colors.skyblue)
          (ray.rectangle { x = 16; y = 16; width = 64; height = 56; color = ray.colors.orange; })
          (ray.circle { x = 88; y = 56; radius = 24; color = ray.colors.purple; })
          (ray.text { text = "Nix"; x = 24; y = 32; size = 24; color = ray.colors.white; })
        ];
      })
      (ray.texture { texture = "scene"; x = 32; y = 96; scale = 2; })
      (ray.shader {
        shader = "tint";
        uniforms = { inherit gain; tint = [ 0.8 0.6 1.0 ]; };
        commands = [ (ray.texture { texture = "scene"; x = 352; y = 96; scale = 2; }) ];
      })
      (ray.text { text = "Original"; x = 32; y = 64; size = 20; color = ray.colors.black; })
      (ray.text { text = "Tint + gain"; x = 352; y = 64; size = 20; color = ray.colors.black; })
      (ray.text {
        text = "Mouse wheel changes gain: ${toString gain}";
        x = 32; y = 312; size = 20; color = ray.colors.black;
      })
    ];
  })
