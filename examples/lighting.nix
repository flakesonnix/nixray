{ hidden ? false, maxFrames ? 0 }:
let
  ray = import ../lib;
  point = x: y: z: { inherit x y z; };
in ray.run {
  inherit hidden maxFrames;
  width = 800; height = 520;
  title = "Nix directional lights and Blinn-Phong materials";
  assets.models.pyramid = ./models/pyramid.obj;
  state = { glossy = true; warm = true; };
} (frame:
  let
    glossy = if ray.keyPressed frame ray.keys.space then !frame.state.glossy else frame.state.glossy;
    warm = if ray.keyPressed frame 76 then !frame.state.warm else frame.state.warm;
    specular = if glossy then 0.9 else 0.05;
    shininess = if glossy then 96 else 4;
  in {
    state = { inherit glossy warm; };
    commands = [
      (ray.clear (ray.rgb 18 22 33))
      (ray.camera3D { camera = { position = point 7 5 10; target = point 0 1 0; }; commands = [
        (ray.lighting { ambient = [0.12 0.12 0.15]; lights = [
          { direction = point (-1) (-2) (-2); color = if warm then [1 0.8 0.55] else [0.4 0.65 1]; intensity = 0.8; }
          { direction = point 1 (-0.5) 1; color = [0.35 0.45 1]; intensity = 0.35; }
        ]; commands = [
          (ray.material { diffuse = ray.rgb 90 100 115; specular = 0; commands = [
            (ray.plane { position = point 0 (-0.02) 0; width = 14; length = 14; color = ray.colors.white; })
          ]; })
          (ray.material { diffuse = ray.colors.orange; inherit specular shininess; commands = [
            (ray.cube { position = point (-3) 1 0; width = 2; height = 2; length = 2; color = ray.colors.white; })
          ]; })
          (ray.material { diffuse = ray.colors.skyblue; inherit specular shininess; commands = [
            (ray.sphere { position = point 0 1 0; radius = 1; rings = 32; slices = 48; color = ray.colors.white; })
          ]; })
          (ray.material { diffuse = ray.colors.green; inherit specular shininess; commands = [
            (ray.model { model = "pyramid"; position = point 3 0 0; rotation = frame.frame; })
          ]; })
        ]; })
        (ray.grid { slices = 14; spacing = 1; })
      ]; })
      (ray.text { text = "Directional lighting and scoped materials"; x = 24; y = 20; size = 26; color = ray.colors.white; })
      (ray.text { text = "Space: glossy / matte | L: warm / cool key light";
        x = 24; y = 478; size = 20; color = ray.colors.gray; })
    ];
  })
