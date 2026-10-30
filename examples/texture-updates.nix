{ hidden ? false, maxFrames ? 0, filter ? "trilinear" }:
let
  ray = import ../lib;
  mod = n: d: n - (builtins.div n d)*d;
  source = ray.genImage {
    kind = "checked"; width = 64; height = 64;
    checksX = 2; checksY = 2;
    color1 = ray.colors.orange; color2 = ray.colors.skyblue;
  };
  panel = ray.imageTransform (ray.genImage { width = 16; height = 12; color = ray.colors.skyblue; }) [
    { op = "drawRectangle"; x = 0; y = 0; width = 4; height = 12; color = ray.colors.blue; }
    { op = "drawRectangle"; x = 12; y = 0; width = 4; height = 12; color = ray.colors.orange; }
  ];
in ray.run {
  inherit hidden maxFrames;
  width = 720; height = 430;
  title = "Nix texture uploads, mipmaps and three-patch panels";
  assets = {
    textures = {
      live = { image = source; inherit filter; };
      sharp = { image = source; filter = "point"; };
      bar.image = panel;
      side.image = ray.imageTransform panel [ { op = "rotateCW"; } ];
    };
    renderTextures.preview = { width = 128; height = 64; filter = "trilinear"; };
  };
  state = { paused = false; tick = 0; };
} (frame:
  let
    paused = if ray.keyPressed frame ray.keys.space then !frame.state.paused else frame.state.paused;
    tick = frame.state.tick + (if paused then 0 else 1);
    patch = ray.genImage { width = 8; height = 8;
      color = if mod tick 40 < 20 then ray.colors.purple else ray.colors.green; };
    reset = ray.keyPressed frame 82;
    update = texture: ray.updateTextureRec { inherit texture; image = patch; x = mod (tick*3) 57; y = mod (tick*5) 57; };
  in {
    state = { inherit paused tick; };
    textures = (if reset then [
      (ray.updateTexture { texture = "live"; image = source; })
      (ray.updateTexture { texture = "sharp"; image = source; })
    ] else []) ++ (if paused then [] else [ (update "live") (update "sharp") ]);
    commands = [
      (ray.clear (ray.rgb 22 26 38))
      (ray.text { text = "Point sampling"; x = 28; y = 24; size = 24; color = ray.colors.white; })
      (ray.text { text = "Mipmapped: ${filter}"; x = 324; y = 24; size = 24; color = ray.colors.white; })
      (ray.texture { texture = "sharp"; x = 28; y = 68; width = 256; height = 160; })
      (ray.texture { texture = "live"; x = 324; y = 68; width = 256; height = 160; })
      (ray.texture { texture = "sharp"; x = 600; y = 68; width = 15; height = 15; })
      (ray.texture { texture = "live"; x = 640; y = 68; width = 15; height = 15; })
      (ray.textureNPatch { texture = "bar"; layout = "horizontal"; x = 28; y = 270;
        width = 320; height = 12; borders = { left = 4; right = 4; }; })
      (ray.textureNPatch { texture = "side"; layout = "vertical"; x = 384; y = 258;
        width = 12; height = 120; borders = { top = 4; bottom = 4; }; })
      (ray.paint { texture = "preview"; commands = [
        (ray.texture { texture = "live"; x = 0; y = 0; width = 128; height = 64; })
      ]; })
      (ray.texture { texture = "preview"; x = 452; y = 258; width = 224; height = 112; })
      (ray.text { text = "Space: pause uploads | R: reset | CPU images stay immutable";
        x = 20; y = 398; size = 18; color = ray.colors.white; })
    ];
  })
