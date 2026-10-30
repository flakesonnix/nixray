{ hidden ? false, maxFrames ? 0 }:
let
  ray = import ../lib;
  reverseList = xs: builtins.foldl' (result: x: [x] ++ result) [] xs;
  rim = [ { x = 80; y = 310; } { x = 80; y = 420; }
          { x = 260; y = 420; } { x = 260; y = 310; } { x = 80; y = 310; } ];
  strip = [ { x = 380; y = 315; } { x = 380; y = 425; }
            { x = 480; y = 295; } { x = 480; y = 405; }
            { x = 580; y = 325; } { x = 580; y = 435; }
            { x = 680; y = 310; } { x = 680; y = 420; } ];
in ray.run {
  inherit hidden maxFrames;
  width = 840; height = 500;
  title = "Nix dashes, rectangle contours and triangle groups";
  state = { thickness = 4; reverse = false; };
} (frame:
  let
    reverse = if ray.keyPressed frame ray.keys.space then !frame.state.reverse else frame.state.reverse;
    requested = frame.state.thickness + frame.mouseWheelY*2;
    thickness = if frame.mouseWheelY == 0 then frame.state.thickness
      else if requested < 0 then 0 else if requested > 24 then 24 else requested;
  in {
    state = { inherit thickness reverse; };
    commands = [
      (ray.clear (ray.rgb 20 24 36))
      (ray.text { text = "Rotated rectangle"; x = 30; y = 26; size = 21; color = ray.colors.white; })
      (ray.text { text = "Inside contour"; x = 320; y = 26; size = 21; color = ray.colors.white; })
      (ray.text { text = "Outside rounded contour"; x = 550; y = 26; size = 21; color = ray.colors.white; })
      (ray.rectanglePro { x = 140; y = 140; width = 132; height = 72;
        origin = { x = 66; y = 36; }; rotation = frame.frame*2; color = ray.colors.orange; })
      (ray.rectangleLines { x = 320; y = 90; width = 170; height = 110; color = ray.colors.gray; })
      (ray.rectangleLinesEx { x = 320; y = 90; width = 170; height = 110; inherit thickness; color = ray.colors.skyblue; })
      (ray.rectangleLines { x = 590; y = 100; width = 150; height = 90; color = ray.colors.gray; })
      (ray.rectangleRoundedLinesEx { x = 590; y = 100; width = 150; height = 90;
        roundness = 0.65; inherit thickness; color = ray.colors.purple; })
      (ray.lineDashed { x1 = 35; y1 = 255; x2 = 805; y2 = 255;
        dashSize = 12; spaceSize = if reverse then 4 else 8; color = ray.colors.skyblue; })
      (ray.triangleFan { points = [ { x = 170; y = 365; } ] ++ (if reverse then reverseList rim else rim); color = ray.colors.blue; })
      (ray.triangleStrip { points = if reverse then reverseList strip else strip; color = ray.colors.green; })
      (ray.text { text = "Triangle fan"; x = 104; y = 445; size = 19; color = ray.colors.white; })
      (ray.text { text = "Triangle strip"; x = 476; y = 445; size = 19; color = ray.colors.white; })
      (ray.text { text = "Wheel: contour thickness | Space: reverse winding and change dash gaps";
        x = 20; y = 478; size = 18; color = ray.colors.white; })
    ];
  })
