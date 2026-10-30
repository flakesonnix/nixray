{ hidden ? false, maxFrames ? 0 }:
let
  ray = import ../lib;
  point = x: y: z: { inherit x y z; };
  image = ray.imageTransform (ray.genImage {
    kind = "checked"; width = 128; height = 64;
    checksX = 16; checksY = 16;
    color1 = ray.colors.orange; color2 = ray.colors.skyblue;
  }) [ { op = "drawRectangle"; x = 0; y = 0; width = 20; height = 20; color = ray.colors.purple; } ];
  clamp = low: high: n: if n < low then low else if n > high then high else n;
in ray.run {
  inherit hidden maxFrames;
  width = 900; height = 560;
  title = "Nix world-space billboards and live render-texture labels";
  assets = {
    textures.card.image = image;
    renderTextures.label = { width = 256; height = 128; };
  };
  state = { x = 6; z = 10; spin = true; lit = false; flipped = false; };
} (frame:
  let
    x = clamp 1 12 (frame.state.x + (if ray.keyDown frame ray.keys.d then 0.1 else 0)
      - (if ray.keyDown frame ray.keys.a then 0.1 else 0));
    z = clamp 4 16 (frame.state.z + (if ray.keyDown frame ray.keys.s then 0.1 else 0)
      - (if ray.keyDown frame ray.keys.w then 0.1 else 0));
    spin = if ray.keyPressed frame ray.keys.space then !frame.state.spin else frame.state.spin;
    lit = if ray.keyPressed frame 76 then !frame.state.lit else frame.state.lit;
    flipped = if ray.keyPressed frame 70 then !frame.state.flipped else frame.state.flipped;
    cards = [
      (ray.billboard { texture = "card"; position = point (-2.5) 1.7 0; height = 2;
        rotation = if spin then frame.frame else 0; flipX = flipped; })
      (ray.billboard { texture = "label"; position = point 2.5 1.7 0; height = 2; flipX = flipped; })
    ];
  in {
    state = { inherit x z spin lit flipped; };
    commands = [
      (ray.clear (ray.rgb 18 22 33))
      (ray.paint { texture = "label"; commands = [
        (ray.clear (ray.rgb 32 42 62))
        (ray.rectangle { x = 12; y = 12; width = 232; height = 104; color = ray.colors.purple; })
        (ray.text { text = "Live Nix label"; x = 22; y = 24; size = 26; color = ray.colors.white; })
        (ray.text { text = "Frame ${toString frame.frame}"; x = 22; y = 72; size = 22; color = ray.colors.white; })
      ]; })
      (ray.camera3D { camera = { position = point x 5 z; target = point 0 1 0; }; commands = [
        (ray.grid { slices = 14; spacing = 1; })
      ] ++ (if lit then [ (ray.lighting { ambient = [0.2 0.2 0.25]; lights = [
        { direction = point (-1) (-1) (-2); intensity = 0.8; }
      ]; commands = [ (ray.material { specular = 0; commands = cards; }) ]; }) ] else cards) ++ [
        (ray.cube { position = point 0 0.8 1; width = 1.4; height = 1.6; length = 1.4; color = ray.colors.green; })
      ]; })
      (ray.text { text = "Camera-derived 3D billboards | Generated image + live texture";
        x = 24; y = 22; size = 24; color = ray.colors.white; })
      (ray.text { text = "WASD: camera | Space: spin | F: flip UVs | L: flat lighting";
        x = 24; y = 514; size = 22; color = ray.colors.gray; })
    ];
  })
