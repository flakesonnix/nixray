{ hidden ? false, maxFrames ? 0, output ? "" }:
let
  ray = import ../lib;
  source = ray.genImage {
    kind = "checked"; width = 96; height = 96;
    checksX = 12; checksY = 12;
    color1 = ray.colors.orange; color2 = ray.colors.skyblue;
  };
  edited = ray.imageTransform source [
    { op = "rotateCW"; }
    { op = "colorTint"; color = [255 180 220 220]; }
    { op = "resizeNN"; width = 192; height = 192; }
    { op = "resizeCanvas"; width = 224; height = 224;
      offsetX = 16; offsetY = 16; fill = ray.rgb 20 24 36; }
    { op = "drawRectangle"; x = 104; y = 104; width = 16; height = 16; color = ray.colors.purple; }
  ];
  inverted = ray.imageTransform edited [ { op = "colorInvert"; } ];
  exported = if output == "" then null else ray.exportImage { image = edited; path = output; };
in builtins.seq exported (ray.run {
  inherit hidden maxFrames;
  width = 560; height = 350;
  title = "Immutable CPU images from Nix";
  assets.textures = {
    source.image = source;
    edited.image = edited;
    inverted.image = inverted;
  };
  state = { inverted = false; image = ray.imageInfo edited; inherit exported; };
} (frame:
  let showInverted = if ray.keyPressed frame ray.keys.space then !frame.state.inverted else frame.state.inverted;
  in {
    state = frame.state // { inverted = showInverted; };
    commands = [
      (ray.clear (ray.rgb 32 36 48))
      (ray.text { text = "Generated source"; x = 28; y = 24; size = 22; color = ray.colors.white; })
      (ray.text { text = "Immutable edits"; x = 284; y = 24; size = 22; color = ray.colors.white; })
      (ray.texture { texture = "source"; x = 28; y = 80; scale = 2; })
      (ray.texture { texture = if showInverted then "inverted" else "edited"; x = 284; y = 64; })
      (ray.text { text = "Space: invert the edited copy | Source stays unchanged";
        x = 20; y = 316; size = 18; color = ray.colors.white; })
    ];
  }))
