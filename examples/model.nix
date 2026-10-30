{ hidden ? false, maxFrames ? 0 }:
let
  ray = import ../lib;
  point = x: y: z: { inherit x y z; };
in ray.run {
  inherit hidden maxFrames;
  width = 800; height = 500;
  title = "Nix model assets and skeletal poses";
  assets.models = {
    pyramid = ./models/pyramid.obj;
    actor = { path = ./models/slide.gltf; animations = ./models/slide.gltf; };
  };
  state = { tick = 0; paused = false; };
} (frame:
  let
    paused = if ray.keyPressed frame ray.keys.space then !frame.state.paused else frame.state.paused;
    tick = frame.state.tick + (if paused then 0 else 1);
    count = (builtins.head frame.models.actor.animations).frameCount;
    pose = { animation = 0; frame = tick - builtins.div tick count * count; };
  in {
    state = { inherit tick paused; };
    commands = [
      (ray.clear (ray.rgb 18 22 33))
      (ray.camera3D { camera = { position = point 7 5 10; target = point 0 1 0; }; commands = [
        (ray.grid { slices = 12; spacing = 1; })
        (ray.model { model = "pyramid"; position = point 2 0 (-2); rotation = frame.frame * 2; tint = ray.colors.orange; })
        (ray.model { model = "actor"; position = point (-2) 1 0; inherit pose; tint = ray.colors.skyblue; })
        (ray.modelWires { model = "actor"; position = point (-2) 1 (-3); tint = ray.colors.purple; })
      ]; })
      (ray.text { text = "OBJ model + glTF skeletal pose + bind-pose wireframe"; x = 24; y = 20; size = 24; color = ray.colors.white; })
      (ray.text { text = "Space: pause | Native clip frame ${toString pose.frame} / ${toString count}";
        x = 24; y = 460; size = 20; color = ray.colors.gray; })
    ];
  })
