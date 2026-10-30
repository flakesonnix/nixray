{ hidden ? false, maxFrames ? 0 }:
let
  ray = import ../lib;
  point = x: y: z: { inherit x y z; };
in ray.run {
  inherit hidden maxFrames;
  width = 900; height = 560;
  title = "Nix 3D circles, triangles, cylinders and capsules";
  state = { wires = false; lit = true; slices = 16; };
} (frame:
  let
    wires = if ray.keyPressed frame ray.keys.w then !frame.state.wires else frame.state.wires;
    lit = if ray.keyPressed frame 76 then !frame.state.lit else frame.state.lit;
    requested = frame.state.slices + (if ray.keyPressed frame ray.keys.up then 1 else 0)
      - (if ray.keyPressed frame ray.keys.down then 1 else 0);
    slices = if requested < 3 then 3 else if requested > 64 then 64 else requested;
    cylinder = if wires then ray.cylinderWires else ray.cylinder;
    cylinderEx = if wires then ray.cylinderWiresEx else ray.cylinderEx;
    capsule = if wires then ray.capsuleWires else ray.capsule;
    shapes = [
      (cylinder { position = point (-4) 0 1; radiusBottom = 0.9; radiusTop = 0;
        height = 2.6; inherit slices; color = ray.colors.orange; })
      (cylinder { position = point (-1.4) 0 1; radiusBottom = 0.8; radiusTop = 0.8;
        height = 2.6; inherit slices; color = ray.colors.skyblue; })
      (cylinderEx { start = point 1 0.6 1; end = point 2 2.6 1;
        startRadius = 0.65; endRadius = 0.3; inherit slices; color = ray.colors.green; })
      (capsule { start = point 3.2 0.7 1; end = point 4.2 2 1;
        radius = 0.65; inherit slices; rings = 8; color = ray.colors.purple; })
      (ray.triangle3D { v1 = point (-4.8) 0 (-2); v2 = point (-3.2) 0 (-2);
        v3 = point (-4) 2 (-2); color = ray.colors.yellow; })
      (ray.triangleStrip3D { points = [ (point (-2) 0 (-2)) (point (-0.8) 0 (-2))
        (point (-2) 1.8 (-2)) (point (-0.8) 1.8 (-2)) (point 0.3 2.6 (-2)) ]; color = ray.colors.red; })
      # Coincident endpoints intentionally select the native sphere case.
      (capsule { start = point 3 1 (-2); end = point 3 1 (-2);
        radius = 0.8; inherit slices; rings = 8; color = ray.colors.skyblue; })
    ];
  in {
    state = { inherit wires lit slices; };
    commands = [
      (ray.clear (ray.rgb 18 22 33))
      (ray.camera3D { camera = { position = point 8 7 14; target = point 0 1 0; }; commands = [
        (ray.grid { slices = 14; spacing = 1; })
        (ray.circle3D { position = point 0.8 2.2 (-2); radius = 0.9;
          rotationAxis = point 0 1 0; rotation = frame.frame*2; color = ray.colors.white; })
      ] ++ (if lit then [ (ray.lighting { ambient = [0.2 0.2 0.25]; lights = [
        { direction = point (-1) (-2) (-3); intensity = 0.8; }
      ]; commands = [ (ray.material { specular = 0.3; shininess = 32; commands = shapes; }) ]; }) ] else shapes); })
      (ray.text { text = "Native 3D primitives | Flat-face lighting"; x = 24; y = 22; size = 28; color = ray.colors.white; })
      (ray.text { text = "W: cylinder/capsule wires | L: lighting | Up/Down: slices (${toString slices})";
        x = 24; y = 514; size = 22; color = ray.colors.gray; })
    ];
  })
