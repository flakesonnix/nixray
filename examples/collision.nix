{ hidden ? false, maxFrames ? 0 }:
let
  ray = import ../lib;
  camera = { offset = { x = 24; y = 56; }; zoom = 1.5; };
  rectangle = { x = 36; y = 48; width = 120; height = 80; };
  circle = { x = 260; y = 88; radius = 40; };
  baseline = { x1 = 16; y1 = 88; x2 = 360; y2 = 88; };
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
    overlap = ray.getCollisionRec probe rectangle;
    intersection = ray.checkCollisionLines baseline pointerLine;
  in {
    state = { inherit rectangleHit circleHit circleRectangleHit hoverRectangle hoverCircle overlap intersection; };
    commands = [
      (ray.clear ray.colors.raywhite)
      (ray.text {
        text = "Move mouse: picking, overlap and segment intersection";
        x = 16; y = 16; size = 18; color = ray.colors.black;
      })
      (ray.camera2D {
        inherit camera;
        commands = [
          (ray.rectangle (rectangle // { color = if hoverRectangle then ray.colors.orange else ray.colors.skyblue; }))
          (ray.circle (circle // { color = if hoverCircle then ray.colors.orange else ray.colors.purple; }))
          (ray.line (baseline // { color = ray.colors.gray; }))
          (ray.line (pointerLine // { color = ray.colors.gray; }))
          (ray.rectangle {
            x = builtins.floor overlap.x; y = builtins.floor overlap.y;
            width = builtins.floor overlap.width; height = builtins.floor overlap.height;
            color = ray.colors.yellow;
          })
          (ray.rectangleLines (probe // { color = if rectangleHit then ray.colors.red else ray.colors.black; }))
          (ray.circleLines (cursor // {
            color = if circleHit || circleRectangleHit then ray.colors.red else ray.colors.black;
          }))
        ] ++ (if intersection == null then [] else [
          (ray.circle {
            x = builtins.floor intersection.x; y = builtins.floor intersection.y;
            radius = 4; color = ray.colors.green;
          })
        ]);
      })
    ];
  })
