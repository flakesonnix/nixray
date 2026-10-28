{ hidden ? false, maxFrames ? 0 }:
let
  ray = import ../lib;
  cells = 24;
in
ray.run {
  inherit hidden maxFrames;
  width = 640;
  height = 360;
  title = "Nix render textures";
  state = 0;
  assets.renderTextures.mural = { width = 48; height = 48; };
} (frame:
  let
    step = frame.frame - (builtins.div frame.frame cells) * cells;
    panel = {
      x = 15; y = 23; width = 386; height = 386; color = ray.colors.gray;
    };
  in {
    state = frame.frame + 1;
    close = frame.frame + 1 >= cells;
    commands = [
      (ray.clear ray.colors.raywhite)
      # One square per frame accumulates into the textured mural.
      (ray.paint {
        texture = "mural";
        clear = false;
        commands = [ (ray.rectangle {
          x = step * 2; y = step * 2; width = 2; height = 2;
          color = if step < cells / 2 then ray.colors.blue else ray.colors.purple;
        }) ];
      })
      # The same GPU texture backs two stamps; the right one mirrors it.
      (ray.texture { texture = "mural"; x = 16; y = 24; scale = 8; })
      (ray.texture { texture = "mural"; x = 240; y = 24; scale = 8; flipX = true; })
      (ray.rectangleLines panel)
      (ray.rectangleLines (panel // { x = 239; }))
      (ray.text {
        text = "Paint once per frame, stamp twice with mirroring";
        x = 16; y = 316; size = 20; color = ray.colors.blue;
      })
    ];
  })
