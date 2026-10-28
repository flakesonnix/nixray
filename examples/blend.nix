{ hidden ? false, maxFrames ? 0 }:
let
  ray = import ../lib;
  modes = [ "alpha" "additive" "multiply" "subtract" ];
  clamp = low: high: value: if value < low then low else if value > high then high else value;
in
ray.run {
  inherit hidden maxFrames;
  width = 640;
  height = 360;
  title = "Nix scoped blend modes";
  state = { alpha = 160; };
} (frame:
  let
    alpha = clamp 0 255 (frame.state.alpha + builtins.floor (frame.mouseWheelY * 16));
    panel = index:
      let
        mode = builtins.elemAt modes index;
        row = builtins.div index 2;
        column = index - row * 2;
        x = 16 + column * 304;
        y = 60 + row * 136;
      in [
        (ray.clip {
          inherit x y;
          width = 288; height = 120;
          commands = [
            (ray.rectangle { inherit x y; width = 288; height = 120; color = ray.rgb 40 60 80; })
            (ray.rectangle {
              x = x + 32; y = y + 32; width = 224; height = 80; color = ray.rgb 90 110 140;
            })
            (ray.blend {
              inherit mode;
              commands = [
                (ray.circle { x = x + 116; y = y + 72; radius = 36; color = ray.rgba 240 120 80 alpha; })
                (ray.circle { x = x + 168; y = y + 72; radius = 36; color = ray.rgba 80 200 240 alpha; })
              ];
            })
            # Text follows the blend scope, so labels always use normal alpha.
            (ray.text { text = mode; x = x + 12; y = y + 8; size = 18; color = ray.colors.white; })
          ];
        })
      ];
  in {
    state = { inherit alpha; };
    commands = [
      (ray.clear ray.colors.raywhite)
      (ray.text {
        text = "Mouse wheel changes source alpha: ${toString alpha}";
        x = 16; y = 20; size = 20; color = ray.colors.black;
      })
    ] ++ builtins.concatLists (builtins.genList panel 4);
  })
