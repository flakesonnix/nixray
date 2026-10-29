{ hidden ? false, maxFrames ? 0 }:
let
  ray = import ../lib;
  clamp = low: high: x: if x < low then low else if x > high then high else x;
  knots = [ { x = 420; y = 440; } { x = 460; y = 290; }
            { x = 670; y = 460; } { x = 750; y = 290; } ];
  quadratic = [ { x = 35; y = 340; } { x = 170; y = 190; } { x = 350; y = 340; } ];
  cubic = [ { x = 35; y = 480; } { x = 100; y = 360; }
            { x = 270; y = 560; } { x = 350; y = 440; } ];
  label = text: x: y: ray.text { inherit text x y; size = 18; color = ray.colors.gray; };
  guide = points: [ (ray.splineLinear { inherit points; thickness = 1; color = ray.rgb 55 62 75; }) ]
    ++ map (p: ray.circle (p // { radius = 4; color = ray.colors.gray; })) points;
in ray.run {
  inherit hidden maxFrames;
  width = 800; height = 600;
  title = "Nix regular polygons and open splines";
  state = { thickness = 5; guides = true; };
} (frame:
  let
    thickness = clamp 1 20 (frame.state.thickness + frame.mouseWheelY);
    guides = if ray.keyPressed frame ray.keys.space then !frame.state.guides else frame.state.guides;
    rotation = frame.frame - builtins.div frame.frame 360 * 360;
  in {
    state = { inherit thickness guides; };
    commands = [
      (ray.clear (ray.rgb 18 22 33))
      (ray.text { text = "Regular polygons, Bezier connectors and splines";
        x = 24; y = 20; size = 24; color = ray.colors.white; })
      (ray.poly { x = 80; y = 125; sides = 5; radius = 48; inherit rotation; color = ray.colors.skyblue; })
      (ray.polyLines { x = 240; y = 125; sides = 6; radius = 48; inherit rotation; color = ray.colors.green; })
      (ray.polyLinesEx { x = 400; y = 125; sides = 8; radius = 48; inherit rotation thickness; color = ray.colors.orange; })
      (ray.lineBezier { x1 = 530; y1 = 90; x2 = 750; y2 = 180; inherit thickness; color = ray.colors.purple; })
      (label "Filled" 48 190) (label "Outline" 205 190) (label "Thick outline" 340 190)
      (label "Eased connector" 560 210)
    ] ++ (if guides then guide quadratic ++ guide cubic ++ guide knots else []) ++ [
      (ray.splineBezierQuadratic { points = quadratic; inherit thickness; color = ray.colors.skyblue; })
      (ray.splineBezierCubic { points = cubic; inherit thickness; color = ray.colors.purple; })
      (label "Quadratic Bezier" 90 350) (label "Cubic Bezier" 105 520)
      (ray.splineLinear { points = knots; inherit thickness; color = ray.rgb 0 117 44; })
      (ray.splineBasis { points = knots; inherit thickness; color = ray.colors.yellow; })
      (ray.splineCatmullRom { points = knots; inherit thickness; color = ray.colors.orange; })
      (label "Green: linear | Yellow: B-spline" 425 490)
      (label "Orange: Catmull-Rom (middle knots)" 425 515)
      (label "Mouse wheel: thickness | Space: control guides" 24 565)
    ];
  })
