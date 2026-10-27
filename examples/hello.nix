{ hidden ? false, maxFrames ? 0 }:
let
  ray = import ../lib;
in
ray.run {
  inherit hidden maxFrames;
  title = "raylib, from Nix!";
  width = 800;
  height = 450;
  state = { x = 400; y = 225; };
} (frame:
  let
    down = ray.keyDown frame;
    x = frame.state.x + (if down ray.keys.right then 4 else 0)
      - (if down ray.keys.left then 4 else 0);
    y = frame.state.y + (if down ray.keys.down then 4 else 0)
      - (if down ray.keys.up then 4 else 0);
  in {
    state = { inherit x y; };
    commands = [
      (ray.clear ray.colors.raywhite)
      (ray.text {
        text = "Nix is drawing this. Arrow keys move the circle.";
        x = 70; y = 80; size = 20; color = ray.colors.gray;
      })
      (ray.circle { inherit x y; radius = 35; color = ray.colors.blue; })
      (ray.fps 10 10)
    ];
  })
