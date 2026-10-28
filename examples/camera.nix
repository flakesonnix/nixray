{ hidden ? false, maxFrames ? 0 }:
let
  ray = import ../lib;
  clamp = low: high: value: if value < low then low else if value > high then high else value;
in
ray.run {
  inherit hidden maxFrames;
  width = 640;
  height = 360;
  title = "Nix 2D camera";
  state = { x = 0.0; y = 0.0; zoom = 1.0; rotation = 0.0; };
} (frame:
  let
    down = key: if ray.keyDown frame key then 1 else 0;
    speed = 200.0 * frame.delta / frame.state.zoom;
    x = frame.state.x + speed * (down ray.keys.d - down ray.keys.a);
    y = frame.state.y + speed * (down ray.keys.s - down ray.keys.w);
    zoom = clamp 0.25 4.0 (frame.state.zoom + frame.mouseWheelY * 0.25);
    rawRotation = frame.state.rotation + 60.0 * frame.delta * (down ray.keys.right - down ray.keys.left);
    rotation = rawRotation - builtins.floor (rawRotation / 360.0) * 360.0;
    camera = {
      target = { inherit x y; };
      offset = { x = frame.width / 2.0; y = frame.height / 2.0; };
      inherit zoom rotation;
    };
    mouse = ray.screenToWorld2D camera { x = frame.mouseX; y = frame.mouseY; };
    grid = builtins.concatLists (builtins.genList (index:
      let coordinate = (index - 10) * 50;
      in [
        (ray.line { x1 = coordinate; y1 = -500; x2 = coordinate; y2 = 500; color = ray.colors.gray; })
        (ray.line { x1 = -500; y1 = coordinate; x2 = 500; y2 = coordinate; color = ray.colors.gray; })
      ]) 21);
  in {
    state = { inherit x y zoom rotation; };
    commands = [
      (ray.clear ray.colors.raywhite)
      (ray.clip {
        x = 0; y = 52; width = frame.width; height = frame.height - 52;
        commands = [ (ray.camera2D {
          inherit camera;
          commands = grid ++ [
            (ray.rectangle { x = -60; y = -40; width = 120; height = 80; color = ray.colors.skyblue; })
            (ray.text { text = "World origin"; x = -48; y = -10; size = 16; color = ray.colors.black; })
            (ray.circle { x = builtins.floor mouse.x; y = builtins.floor mouse.y; radius = 8; color = ray.colors.red; })
          ];
        }) ];
      })
      (ray.text { text = "WASD pan | wheel zoom | arrows rotate"; x = 24; y = 18; size = 20; color = ray.colors.blue; })
    ];
  })
