rec {
  run = builtins.raylib;
  validate = commands: builtins.raylibValidate commands;
  version = builtins.raylibVersion;

  rgba = r: g: b: a: [ r g b a ];
  rgb = r: g: b: rgba r g b 255;
  colors = {
    white = rgb 255 255 255;
    raywhite = rgb 245 245 245;
    black = rgb 0 0 0;
    gray = rgb 130 130 130;
    red = rgb 230 41 55;
    green = rgb 0 228 48;
    blue = rgb 0 121 241;
    skyblue = rgb 102 191 255;
    yellow = rgb 253 249 0;
    orange = rgb 255 161 0;
    purple = rgb 200 122 255;
    blank = rgba 0 0 0 0;
  };
  keys = {
    space = 32;
    a = 65; d = 68; s = 83; w = 87;
    escape = 256; enter = 257;
    right = 262; left = 263; down = 264; up = 265;
  };
  mouse = { left = 0; right = 1; middle = 2; };
  keyDown = frame: key: builtins.elem key frame.keysDown;
  keyPressed = frame: key: builtins.elem key frame.keysPressed;
  keyReleased = frame: key: builtins.elem key frame.keysReleased;
  mouseReleased = frame: button: builtins.elem button frame.mouseReleased;

  clear = color: { op = "clear"; inherit color; };
  clip = args: args // { op = "clip"; };
  text = args: args // { op = "text"; };
  texture = args: args // { op = "texture"; };
  rectangle = args: args // { op = "rectangle"; };
  rectangleLines = args: args // { op = "rectangleLines"; };
  rectangleRounded = args: args // { op = "rectangleRounded"; };
  rectangleRoundedLines = args: args // { op = "rectangleRoundedLines"; };
  circle = args: args // { op = "circle"; };
  circleLines = args: args // { op = "circleLines"; };
  ellipse = args: args // { op = "ellipse"; };
  ellipseLines = args: args // { op = "ellipseLines"; };
  triangle = args: args // { op = "triangle"; };
  triangleLines = args: args // { op = "triangleLines"; };
  line = args: args // { op = "line"; };
  pixel = args: args // { op = "pixel"; };
  fps = x: y: { op = "fps"; inherit x y; };
}
