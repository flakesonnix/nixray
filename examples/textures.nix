{ hidden ? false, maxFrames ? 0 }:
let
  ray = import ../lib;
  clamp = low: high: x: if x < low then low else if x > high then high else x;
  tile = [
    (ray.rectangle { x = 0; y = 0; width = 2; height = 2; color = ray.colors.red; })
    (ray.rectangle { x = 2; y = 0; width = 2; height = 2; color = ray.colors.green; })
    (ray.rectangle { x = 0; y = 2; width = 2; height = 2; color = ray.colors.blue; })
    (ray.rectangle { x = 2; y = 2; width = 2; height = 2; color = ray.colors.yellow; })
  ];
  panelColors = [ ray.colors.red ray.colors.green ray.colors.blue ray.colors.yellow
                  ray.colors.gray ray.colors.purple ray.colors.orange ray.colors.white ray.colors.skyblue ];
in ray.run {
  inherit hidden maxFrames;
  width = 800;
  height = 560;
  title = "Nix texture filters, wrapping and nine-patch panels";
  assets.renderTextures = {
    pixel = { width = 4; height = 4; filter = "point"; wrap = "clamp"; };
    smooth = { width = 4; height = 4; filter = "bilinear"; wrap = "clamp"; };
    repeated = { width = 4; height = 4; wrap = "repeat"; };
    mirrored = { width = 4; height = 4; wrap = "mirrorRepeat"; };
    panel = { width = 12; height = 12; };
  };
  state = { width = 320; height = 140; };
} (frame:
  let
    resizing = builtins.elem ray.mouse.left frame.mouseDown;
    width = if resizing then clamp 3 720 (frame.mouseX - 24) else frame.state.width;
    height = if resizing then clamp 3 200 (frame.mouseY - 290) else frame.state.height;
  in {
    state = { inherit width height; };
    commands = (if frame.frame != 0 then [] else
      map (texture: ray.paint { inherit texture; commands = tile; }) [ "pixel" "smooth" "repeated" "mirrored" ]
      ++ [ (ray.paint { texture = "panel"; commands = builtins.genList (i: ray.rectangle {
        x = (i - builtins.div i 3 * 3) * 4; y = builtins.div i 3 * 4; width = 4; height = 4;
        color = builtins.elemAt panelColors i;
      }) 9; }) ]) ++ [
      (ray.clear (ray.rgb 18 22 33))
      (ray.text { text = "Texture filtering, wrapping and nine-patch";
        x = 24; y = 20; size = 24; color = ray.colors.white; })
      (ray.texture { texture = "pixel"; x = 24; y = 70; scale = 32; })
      (ray.texture { texture = "smooth"; x = 200; y = 70; scale = 32; })
      (ray.texture { texture = "repeated"; x = 390; y = 70; scale = 24;
        source = { x = 0; y = 0; width = 8; height = 4; }; })
      (ray.texture { texture = "mirrored"; x = 600; y = 70; scale = 24;
        source = { x = 0; y = 0; width = 8; height = 4; }; })
      (ray.text { text = "Point"; x = 24; y = 215; size = 20; color = ray.colors.gray; })
      (ray.text { text = "Bilinear"; x = 200; y = 215; size = 20; color = ray.colors.gray; })
      (ray.text { text = "Repeat"; x = 390; y = 215; size = 20; color = ray.colors.gray; })
      (ray.text { text = "Mirror repeat"; x = 600; y = 215; size = 20; color = ray.colors.gray; })
      (ray.textureNPatch { texture = "panel"; x = 24; y = 290; inherit width height;
        borders = { left = 4; top = 4; right = 4; bottom = 4; }; })
      (ray.text { text = "Hold left mouse and move to resize the panel (${toString width} x ${toString height})";
        x = 24; y = 525; size = 18; color = ray.colors.gray; })
    ];
  })
