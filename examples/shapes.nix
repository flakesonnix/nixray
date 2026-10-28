{ hidden ? false, maxFrames ? 0 }:
let
  ray = import ../lib;
in
ray.run {
  inherit hidden maxFrames;
  width = 640;
  height = 360;
  title = "Nix 2D shapes";
} (_: {
  commands = [
    (ray.clear ray.colors.raywhite)
    (ray.triangle {
      x1 = 100; y1 = 40; x2 = 40; y2 = 140; x3 = 160; y3 = 140;
      color = ray.colors.red;
    })
    (ray.triangleLines {
      x1 = 100; y1 = 200; x2 = 160; y2 = 300; x3 = 40; y3 = 300;
      color = ray.colors.red;
    })
    (ray.ellipse { x = 300; y = 90; radiusX = 75; radiusY = 45; color = ray.colors.blue; })
    (ray.ellipseLines { x = 300; y = 250; radiusX = 75; radiusY = 45; color = ray.colors.blue; })
    (ray.rectangleRounded {
      x = 440; y = 40; width = 160; height = 100; roundness = 0.6;
      color = ray.colors.green;
    })
    (ray.rectangleRoundedLines {
      x = 440; y = 200; width = 160; height = 100; roundness = 0.6; segments = 12;
      color = ray.colors.green;
    })
    (ray.text { text = "Filled shapes and one-pixel outlines"; x = 24; y = 330; size = 20; color = ray.colors.gray; })
  ];
})
