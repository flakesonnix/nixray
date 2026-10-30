{ hidden ? false, maxFrames ? 0 }:
let
  ray = import ../lib;
  clamp = low: high: x: if x < low then low else if x > high then high else x;
  point = x: y: z: { inherit x y z; };
  scene = [
    (ray.plane { position = point 0 (-0.02) 0; width = 14; length = 14; color = ray.rgb 55 62 75; })
    (ray.grid { slices = 14; spacing = 1; })
    (ray.cube { position = point 0 1 0; width = 2; height = 2; length = 2; color = ray.colors.orange; })
    (ray.cubeWires { position = point 0 1 0; width = 2; height = 2; length = 2; color = ray.colors.black; })
    (ray.sphere { position = point 3 1 (-1); radius = 1; rings = 24; slices = 32; color = ray.colors.skyblue; })
    (ray.sphereWires { position = point (-3) 1 0; radius = 1; color = ray.colors.purple; })
    (ray.line3D { start = point 0 0 0; end = point 0 4 0; color = ray.colors.green; })
  ];
in ray.run {
  inherit hidden maxFrames;
  width = 800; height = 600;
  title = "Nix 3D cameras, depth and basic primitives";
  assets.renderTextures.overhead = { width = 240; height = 160; };
  state = { x = 6; z = 8; orthographic = false; };
} (frame:
  let
    x = clamp (-10) 10 (frame.state.x + (if ray.keyDown frame ray.keys.d then 0.1 else 0)
      - (if ray.keyDown frame ray.keys.a then 0.1 else 0));
    z = clamp 4 14 (frame.state.z + (if ray.keyDown frame ray.keys.s then 0.1 else 0)
      - (if ray.keyDown frame ray.keys.w then 0.1 else 0));
    orthographic = if ray.keyPressed frame 80 then !frame.state.orthographic else frame.state.orthographic;
  in {
    state = { inherit x z orthographic; };
    commands = [
      (ray.clear (ray.rgb 18 22 33))
      (ray.paint { texture = "overhead"; commands = [
        (ray.clear (ray.rgb 18 22 33))
        (ray.camera3D { camera = { position = point 0 12 0; target = point 0 0 0; up = point 0 0 (-1);
          projection = "orthographic"; fovy = 16; }; commands = scene; })
      ]; })
      (ray.camera3D { camera = { position = point x 5 z; target = point 0 1 0;
        projection = if orthographic then "orthographic" else "perspective";
        fovy = if orthographic then 12 else 45;
      }; commands = scene; })
      (ray.texture { texture = "overhead"; x = 536; y = 406; })
      (ray.text { text = "3D primitives and depth-tested cameras"; x = 24; y = 20; size = 26; color = ray.colors.white; })
      (ray.text { text = "WASD: move camera | P: perspective / orthographic";
        x = 24; y = 560; size = 18; color = ray.colors.white; })
      (ray.text { text = "Overhead render texture"; x = 536; y = 380; size = 18; color = ray.colors.gray; })
    ];
  })
