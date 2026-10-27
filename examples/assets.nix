{ image, font, hidden ? false, maxFrames ? 0 }:
let
  ray = import ../lib;
in
ray.run {
  inherit hidden maxFrames;
  width = 640;
  height = 360;
  title = "Nix textures and fonts";
  assets = {
    textures.logo = image;
    fonts.ui = font;
  };
} (_: {
  commands = [
    (ray.clear ray.colors.raywhite)
    (ray.texture { texture = "logo"; x = 24; y = 24; })
    (ray.text {
      font = "ui"; text = "Custom font + texture, from Nix";
      x = 24; y = 280; size = 24; color = ray.colors.blue;
    })
  ];
})
