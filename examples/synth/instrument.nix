let
  ray = import ../../lib;
  clamp = low: high: x: if x < low then low else if x > high then high else x;
  abs = x: if x < 0 then -x else x;
  notes = [
    { name = "c4"; label = "C4"; key = 65; keyboard = "A"; frequency = 261.625565; white = 0; black = false; }
    { name = "cs4"; label = "C#"; key = 87; keyboard = "W"; frequency = 277.182631; white = 1; black = true; }
    { name = "d4"; label = "D"; key = 83; keyboard = "S"; frequency = 293.664768; white = 1; black = false; }
    { name = "ds4"; label = "D#"; key = 69; keyboard = "E"; frequency = 311.126984; white = 2; black = true; }
    { name = "e4"; label = "E"; key = 68; keyboard = "D"; frequency = 329.627557; white = 2; black = false; }
    { name = "f4"; label = "F"; key = 70; keyboard = "F"; frequency = 349.228231; white = 3; black = false; }
    { name = "fs4"; label = "F#"; key = 84; keyboard = "T"; frequency = 369.994423; white = 4; black = true; }
    { name = "g4"; label = "G"; key = 71; keyboard = "G"; frequency = 391.995436; white = 4; black = false; }
    { name = "gs4"; label = "G#"; key = 89; keyboard = "Y"; frequency = 415.304698; white = 5; black = true; }
    { name = "a4"; label = "A"; key = 72; keyboard = "H"; frequency = 440.0; white = 5; black = false; }
    { name = "as4"; label = "A#"; key = 85; keyboard = "U"; frequency = 466.163762; white = 6; black = true; }
    { name = "b4"; label = "B"; key = 74; keyboard = "J"; frequency = 493.883301; white = 6; black = false; }
    { name = "c5"; label = "C5"; key = 75; keyboard = "K"; frequency = 523.251131; white = 7; black = false; }
  ];
  waveforms = [ "triangle" "square" "saw" ];
  # One normalized period; the WAV bank and on-screen preview share this math.
  wave = waveform: phase:
    if waveform == "triangle" then 1.0 - 4.0 * abs (phase - 0.5)
    else if waveform == "square" then (if phase < 0.5 then 1.0 else -1.0)
    else if waveform == "saw" then 2.0 * phase - 1.0
    else throw "unknown synth waveform '${waveform}'";
  idle = { gate = false; level = 0.0; };
  initialState = {
    volume = 0.5;
    waveform = "triangle";
    blocked = [];
    voices = builtins.listToAttrs (map (note: { name = note.name; value = idle; }) notes);
  };
  step = frame:
    let
      previous = frame.state;
      panic = ray.keyPressed frame ray.keys.enter;
      waveform = if !(ray.keyPressed frame ray.keys.space) then previous.waveform
        else if previous.waveform == "triangle" then "square"
        else if previous.waveform == "square" then "saw" else "triangle";
      changed = waveform != previous.waveform;
      volume = clamp 0.0 1.0 (previous.volume + frame.mouseWheelY * 0.05);
      # Panic stays silent until held keys have been released.
      blocked = builtins.filter (key: ray.keyDown frame key)
        (if panic then map (note: note.key) notes else previous.blocked);
      dt = clamp 0.0 0.1 frame.delta;
      voices = builtins.listToAttrs (map (note:
        let
          old = if changed then idle else previous.voices.${note.name};
          gate = !panic && ray.keyDown frame note.key && !(builtins.elem note.key blocked);
          level = if panic then 0.0 else clamp 0.0 1.0
            (old.level + (if gate then dt / 0.02 else -dt / 0.15));
        in { name = note.name; value = { inherit gate level; }; }
      ) notes);
      audio = builtins.concatMap (note:
        let
          before = previous.voices.${note.name};
          old = if changed then idle else before;
          voice = voices.${note.name};
          music = "${waveform}-${note.name}";
          active = v: v.gate || v.level > 0.0;
        in (if changed && active before then [ (ray.stopMusic "${previous.waveform}-${note.name}") ] else [])
          ++ (if active voice then [
            # Reserve headroom even when every key is held at maximum volume.
            (ray.setMusicVolume { inherit music; volume = voice.level * volume / 13.0; })
          ] ++ (if voice.gate && !old.gate then [ (ray.playMusic music) ] else [])
          else if active old then [ (ray.stopMusic music) ] else [])
      ) notes;
      keyCommands = note:
        let
          voice = voices.${note.name};
          x = 40 + note.white * 104 - (if note.black then 31 else 0);
          width = if note.black then 62 else 100;
          height = if note.black then 135 else 220;
          color = if voice.gate then ray.colors.skyblue else if voice.level > 0 then ray.colors.orange
            else if note.black then ray.rgb 35 39 52 else ray.colors.raywhite;
          ink = if note.black && !voice.gate && voice.level == 0 then ray.colors.white else ray.colors.black;
        in [
          (ray.rectangle { inherit x width height color; y = 260; })
          (ray.rectangle { x = x + 6; y = 260 + height - 6; width = builtins.floor ((width - 12) * voice.level);
            height = 4; color = ray.colors.blue; })
          (ray.text { text = note.label; x = x + 12; y = 260 + height - 62; size = 18; color = ink; })
          (ray.text { text = note.keyboard; x = x + 12; y = 260 + height - 36; size = 24; color = ink; })
        ];
      previewY = i: 169 - builtins.floor (34 * wave waveform (i / 128.0));
    in {
      state = { inherit volume waveform blocked voices; };
      inherit audio;
      commands = [
        (ray.clear (ray.rgb 18 22 33))
        (ray.text { text = "NIX SYNTH"; x = 40; y = 20; size = 30; color = ray.colors.skyblue; })
        (ray.text { text = "Hold A W S E D F T G Y H U J K - play chords";
          x = 40; y = 64; size = 20; color = ray.colors.white; })
        (ray.text { text = "Space: waveform | Wheel: volume | Enter: all notes off";
          x = 40; y = 94; size = 20; color = ray.colors.gray; })
        (ray.rectangle { x = 40; y = 130; width = 832; height = 80; color = ray.rgb 27 33 47; })
      ] ++ builtins.genList (i: ray.line {
        x1 = 48 + i * 6; y1 = previewY i;
        x2 = 48 + (i + 1) * 6; y2 = previewY (i + 1);
        color = ray.colors.skyblue;
      }) 127 ++ [
        (ray.text { text = "${waveform} | volume ${toString (builtins.floor (volume * 100))}% | attack 20ms / release 150ms";
          x = 40; y = 226; size = 20; color = ray.colors.white; })
      ] ++ builtins.concatMap keyCommands (builtins.filter (note: !note.black) notes)
        ++ builtins.concatMap keyCommands (builtins.filter (note: note.black) notes) ++ [
        (ray.text { text = "13 voices | Nix-generated looping waves | Esc: quit";
          x = 40; y = 494; size = 16; color = ray.colors.gray; })
      ];
    };
in { inherit notes waveforms wave initialState step; }
