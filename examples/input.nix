{ hidden ? false, maxFrames ? 0 }:
let
  ray = import ../lib;
in
ray.run {
  inherit hidden maxFrames;
  width = 800;
  height = 450;
  title = "Nix input events";
  state = { text = ""; radius = 40.0; warm = false; };
} (frame:
  let
    requested = frame.state.radius + frame.mouseWheelY * 4.0;
    radius = if requested < 5 then 5.0 else if requested > 120 then 120.0 else requested;
    text = if ray.keyPressed frame ray.keys.enter then "" else frame.state.text + frame.textInput;
    released = ray.keyReleased frame ray.keys.a || ray.mouseReleased frame ray.mouse.left;
    warm = if released then !frame.state.warm else frame.state.warm;
  in {
    state = { inherit text radius warm; };
    commands = [
      (ray.clear ray.colors.raywhite)
      (ray.text {
        text = "Type; Enter clears. Wheel changes radius.\nRelease A or the left mouse button to change color.";
        x = 24; y = 24; size = 20; color = ray.colors.gray;
      })
      (ray.text { inherit text; x = 24; y = 100; size = 24; color = ray.colors.blue; })
      (ray.circle {
        x = 400; y = 300; inherit radius;
        color = if warm then ray.colors.orange else ray.colors.blue;
      })
    ];
  })
