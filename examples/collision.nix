{ hidden ? false, maxFrames ? 0 }:
let
  ray = import ../lib;
  camera = { offset = { x = 24; y = 56; }; zoom = 1.5; };
  rectangle = { x = 36; y = 48; width = 120; height = 80; };
  circle = { x = 260; y = 88; radius = 40; };
  baseline = { x1 = 16; y1 = 88; x2 = 360; y2 = 88; };
  triangle = { x1 = 30; y1 = 150; x2 = 100; y2 = 150; x3 = 65; y3 = 195; };
  polygon = [ { x = 270; y = 145; } { x = 365; y = 145; } { x = 335; y = 165; }
              { x = 365; y = 195; } { x = 270; y = 195; } ];
in
ray.run {
  inherit hidden maxFrames;
  width = 640;
  height = 360;
  title = "Nix collision and camera-aware picking";
} (frame:
  let
    mouse = ray.screenToWorld2D camera { x = frame.mouseX; y = frame.mouseY; };
    probe = { x = builtins.floor mouse.x - 16; y = builtins.floor mouse.y - 16; width = 32; height = 32; };
    cursor = { x = probe.x + 16; y = probe.y + 16; radius = 12; };
    pointerLine = { x1 = 200; y1 = 180; x2 = cursor.x; y2 = cursor.y; };
    rectangleHit = ray.checkCollisionRecs probe rectangle;
    circleHit = ray.checkCollisionCircles cursor circle;
    circleRectangleHit = ray.checkCollisionCircleRec cursor rectangle;
    hoverRectangle = ray.checkCollisionPointRec mouse rectangle;
    hoverCircle = ray.checkCollisionPointCircle mouse circle;
    hoverTriangle = ray.checkCollisionPointTriangle mouse triangle;
    hoverPolygon = ray.checkCollisionPointPoly mouse polygon;
    hoverLine = ray.checkCollisionPointLine mouse (baseline // { threshold = 3; });
    circleLineHit = ray.checkCollisionCircleLine cursor baseline;
    overlap = ray.getCollisionRec probe rectangle;
    intersection = ray.checkCollisionLines baseline pointerLine;
  in {
    state = { inherit rectangleHit circleHit circleRectangleHit circleLineHit hoverRectangle hoverCircle
                      hoverTriangle hoverPolygon hoverLine overlap intersection; };
    commands = [
      (ray.clear ray.colors.raywhite)
      (ray.text {
        text = "Move mouse: rectangles, circles, triangles, polygons, lines";
        x = 16; y = 16; size = 18; color = ray.colors.black;
      })
      (ray.camera2D {
        inherit camera;
        commands = [
          (ray.rectangle (rectangle // { color = if hoverRectangle then ray.colors.orange else ray.colors.skyblue; }))
          (ray.circle (circle // { color = if hoverCircle then ray.colors.orange else ray.colors.purple; }))
          (ray.triangle (triangle // { color = if hoverTriangle then ray.colors.orange else ray.colors.green; }))
          (ray.line (baseline // { color = if hoverLine then ray.colors.orange else ray.colors.gray; }))
          (ray.line (pointerLine // { color = ray.colors.gray; }))
          (ray.rectangle {
            x = builtins.floor overlap.x; y = builtins.floor overlap.y;
            width = builtins.floor overlap.width; height = builtins.floor overlap.height;
            color = ray.colors.yellow;
          })
          (ray.rectangleLines (probe // { color = if rectangleHit then ray.colors.red else ray.colors.black; }))
          (ray.circleLines (cursor // {
            color = if circleHit || circleRectangleHit || circleLineHit then ray.colors.red else ray.colors.black;
          }))
        ] ++ builtins.genList (i:
          let
            a = builtins.elemAt polygon i;
            b = builtins.elemAt polygon (if i + 1 == builtins.length polygon then 0 else i + 1);
          in ray.line { x1 = a.x; y1 = a.y; x2 = b.x; y2 = b.y;
            color = if hoverPolygon then ray.colors.orange else ray.colors.blue;
          }
        ) (builtins.length polygon) ++ (if intersection == null then [] else [
          (ray.circle {
            x = builtins.floor intersection.x; y = builtins.floor intersection.y;
            radius = 4; color = ray.colors.green;
          })
        ]);
      })
    ];
  })
