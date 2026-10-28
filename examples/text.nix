{ font, hidden ? false, maxFrames ? 0 }:
let
  ray = import ../lib;
  label = { font = "ui"; text = "Nix: ä λ"; size = 32; };
in
ray.run {
  inherit hidden maxFrames;
  width = 640;
  height = 360;
  title = "Nix Unicode text and font metrics";
  assets.fonts.ui = {
    path = font;
    size = 48;
    codepoints = (builtins.genList (n: n + 32) 95) ++ [ 228 955 ];
  };
} (frame:
  let
    measured = frame.measureText label;
    x = builtins.floor ((frame.width - measured.width) / 2);
    y = builtins.floor ((frame.height - measured.height) / 2);
  in {
    state = measured;
    commands = [
      (ray.clear ray.colors.raywhite)
      (ray.rectangle {
        x = x - 8; y = y - 8;
        width = builtins.ceil measured.width + 16;
        height = builtins.ceil measured.height + 16;
        color = ray.colors.skyblue;
      })
      (ray.text (label // { inherit x y; color = ray.colors.black; }))
      (ray.text {
        text = "Explicit glyphs, centered using frame.measureText";
        x = 24; y = 300; size = 20; color = ray.colors.gray;
      })
    ];
  })
