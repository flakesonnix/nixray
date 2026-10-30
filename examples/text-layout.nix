{ hidden ? false, maxFrames ? 0 }:
let
  ray = import ../lib;
  codepoints = [78 105 120 58 32 228]; # Nix: ä
in ray.run {
  inherit hidden maxFrames;
  width = 800; height = 460;
  title = "Nix text spacing, pivots and Unicode codepoints";
  state = { spacing = 2; rotate = true; };
} (frame:
  let
    rotate = if ray.keyPressed frame ray.keys.space then !frame.state.rotate else frame.state.rotate;
    requested = frame.state.spacing + frame.mouseWheelY;
    spacing = if frame.mouseWheelY == 0 then frame.state.spacing
      else if requested < -12 then -12 else if requested > 24 then 24 else requested;
    metrics = frame.measureText { inherit codepoints spacing; size = 32; };
    origin = { x = metrics.width / 2; y = metrics.height / 2; };
    rotation = if rotate then frame.frame*2 else 0;
    panel = x: ray.rectanglePro { inherit x origin rotation; y = 170;
      width = builtins.ceil metrics.width; height = 32; color = ray.rgb 32 38 54; };
  in {
    state = { inherit spacing rotate metrics; };
    commands = [
      (ray.clear (ray.rgb 18 22 34))
      (ray.text { text = "UTF-8 strings and direct codepoint arrays"; x = 28; y = 24; size = 26; color = ray.colors.white; })
      (ray.text { text = "String"; x = 160; y = 82; size = 22; color = ray.colors.gray; })
      (ray.text { text = "Codepoint array"; x = 490; y = 82; size = 22; color = ray.colors.gray; })
      (panel 210) (panel 590)
      (ray.text { text = "Nix: ä"; x = 210; y = 170; size = 32;
        inherit spacing origin rotation; color = ray.colors.orange; })
      (ray.textCodepoints { inherit codepoints spacing origin rotation; x = 590; y = 170;
        size = 32; color = ray.colors.skyblue; })
      (ray.text { text = "Literal single glyphs: A, ä, newline, U+0000";
        x = 28; y = 280; size = 21; color = ray.colors.white; })
      (ray.textCodepoint { codepoint = 65; x = 90; y = 326; size = 32; color = ray.colors.green; })
      (ray.textCodepoint { codepoint = 228; x = 250; y = 326; size = 32; color = ray.colors.green; })
      (ray.textCodepoint { codepoint = 10; x = 410; y = 326; size = 32; color = ray.colors.purple; })
      (ray.textCodepoint { codepoint = 0; x = 570; y = 326; size = 32; color = ray.colors.purple; })
      (ray.text { text = "Missing glyphs use the default font's fallback; arrays still treat newlines as line breaks.";
        x = 24; y = 382; size = 16; color = ray.colors.gray; })
      (ray.text { text = "Wheel: signed glyph spacing | Space: toggle rotation | Boxes show logical layout";
        x = 24; y = 426; size = 18; color = ray.colors.white; })
    ];
  })
