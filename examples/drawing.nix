{ hidden ? false, maxFrames ? 0 }:
let ray = import ../lib;
in ray.run {
  inherit hidden maxFrames;
  width = 800;
  height = 480;
  title = "Nix gradients, thick lines, sectors and rings";
  state = { sweep = 270; };
} (frame:
  let
    sweep = if ray.keyDown frame ray.keys.space then 90 else 270;
    start = frame.frame * 2 - builtins.div (frame.frame * 2) 360 * 360;
  in {
    state = { inherit sweep; };
    commands = [
      (ray.clear (ray.rgb 18 22 33))
      (ray.text { text = "Gradients, thick lines, sectors and rings";
        x = 24; y = 20; size = 24; color = ray.colors.white; })
      (ray.rectangleGradientV { x = 24; y = 70; width = 150; height = 100;
        top = ray.colors.red; bottom = ray.colors.blue; })
      (ray.rectangleGradientH { x = 200; y = 70; width = 150; height = 100;
        left = ray.colors.green; right = ray.colors.purple; })
      (ray.rectangleGradientEx { x = 376; y = 70; width = 150; height = 100;
        topLeft = ray.colors.red; bottomLeft = ray.colors.green;
        bottomRight = ray.colors.blue; topRight = ray.colors.white; })
      (ray.circleGradient { x = 650; y = 120; radius = 60;
        inner = ray.colors.skyblue; outer = ray.colors.blank; })
      (ray.lineEx { x1 = 30; y1 = 210; x2 = 760; y2 = 245; thickness = 10; color = ray.colors.orange; })
      (ray.circleSector { x = 110; y = 345; radius = 65; startAngle = start; endAngle = start + sweep;
        color = ray.colors.skyblue; })
      (ray.circleSectorLines { x = 300; y = 345; radius = 65; startAngle = start; endAngle = start + sweep;
        color = ray.colors.skyblue; })
      (ray.ring { x = 490; y = 345; innerRadius = 35; outerRadius = 65;
        startAngle = start; endAngle = start + sweep; color = ray.colors.purple; })
      (ray.ringLines { x = 680; y = 345; innerRadius = 35; outerRadius = 65;
        startAngle = start; endAngle = start + sweep; color = ray.colors.purple; })
      (ray.text { text = "Hold Space: 90-degree arcs | Release: 270 degrees";
        x = 24; y = 440; size = 20; color = ray.colors.gray; })
    ];
  })
