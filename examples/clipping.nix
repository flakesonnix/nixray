{ hidden ? false, maxFrames ? 0 }:
let
  ray = import ../lib;
  rows = 20;
  rowHeight = 28;
  viewport = { x = 24; y = 64; width = 592; height = 240; };
  clamp = low: high: value: if value < low then low else if value > high then high else value;
in
ray.run {
  inherit hidden maxFrames;
  width = 640;
  height = 360;
  title = "Nix clipped scrolling panel";
  state = { scroll = 0; };
} (frame:
  let
    scroll = clamp 0 (rows * rowHeight - viewport.height)
      (frame.state.scroll - builtins.floor (frame.mouseWheelY * 24));
  in {
    state = { inherit scroll; };
    commands = [
      (ray.clear ray.colors.raywhite)
      (ray.text { text = "Scroll inside a clipped panel"; x = 24; y = 24; size = 24; color = ray.colors.blue; })
      (ray.clip (viewport // {
        commands = builtins.concatLists (builtins.genList (index:
          let y = viewport.y + index * rowHeight - scroll;
          in [
            (ray.rectangle {
              x = viewport.x; inherit y; width = viewport.width; height = rowHeight;
              color = if index - (builtins.div index 2) * 2 == 0 then ray.colors.white else ray.colors.raywhite;
            })
            (ray.text {
              text = "Clipped row ${builtins.toString (index + 1)}";
              x = viewport.x + 8; y = y + 4; size = 20; color = ray.colors.black;
            })
          ]) rows);
      }))
      (ray.rectangleLines (viewport // { color = ray.colors.gray; }))
      (ray.text { text = "This footer is outside the clip"; x = 24; y = 324; size = 20; color = ray.colors.gray; })
    ];
  })
