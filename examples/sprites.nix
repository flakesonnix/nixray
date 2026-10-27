{ image, frameWidth ? 32, frameHeight ? 32, columns ? 4, hidden ? false, maxFrames ? 0 }:
assert columns > 0 && frameWidth > 0 && frameHeight > 0;
let
  ray = import ../lib;
in
ray.run {
  inherit hidden maxFrames;
  width = 640;
  height = 360;
  fps = 12;
  title = "Nix sprite sheet";
  assets.textures.sheet = image;
} (frame:
  let column = frame.frame - (builtins.div frame.frame columns) * columns;
  in {
    state = column;
    commands = [
      (ray.clear ray.colors.raywhite)
      (ray.texture {
        texture = "sheet"; x = 280; y = 120;
        source = { x = column * frameWidth; y = 0; width = frameWidth; height = frameHeight; };
        scale = 4.0;
        rotation = frame.time * 30.0;
      })
      (ray.text {
        text = "Animated atlas frames, scaled and rotated in Nix";
        x = 24; y = 300; size = 20; color = ray.colors.gray;
      })
    ];
  })
