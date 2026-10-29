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
  octaves = [ 3 4 5 ];
  transpose = octave: note:
    let actual = octave + (if note.name == "c5" then 1 else 0);
    in note // {
      name = builtins.substring 0 (builtins.stringLength note.name - 1) note.name + toString actual;
      label = if note.name == "c4" || note.name == "c5" then "C${toString actual}" else note.label;
      frequency = note.frequency * (if octave == 3 then 0.5 else if octave == 5 then 2.0 else 1.0);
    };
  # Adjacent keyboard ranges share their endpoint C: keep one asset per pitch.
  toneNotes = builtins.attrValues (builtins.listToAttrs (builtins.concatMap (octave:
    map (note: let pitch = transpose octave note; in { name = pitch.name; value = pitch; }) notes
  ) octaves));
  musicAssets = tones: builtins.listToAttrs (builtins.concatMap (waveform:
    map (note: { name = "${waveform}-${note.name}";
      value = { path = "${tones}/${waveform}-${note.name}.wav"; looping = true; };
    }) toneNotes
  ) waveforms);
  pianoY = 340;
  keyBounds = note: {
    x = 40 + note.white * 104 - (if note.black then 31 else 0);
    y = pianoY;
    width = if note.black then 62 else 100;
    height = if note.black then 135 else 220;
  };
  hit = frame: bounds: frame.mouseX >= bounds.x && frame.mouseX < bounds.x + bounds.width
    && frame.mouseY >= bounds.y && frame.mouseY < bounds.y + bounds.height;
  attackControl = { x = 40; y = 292; width = 260; height = 24; low = 0.005; high = 0.5; };
  releaseControl = { x = 370; y = 292; width = 260; height = 24; low = 0.02; high = 1.0; };
  sliderHit = frame: control: hit frame (control // { x = control.x - 9; width = control.width + 18; });
  octaveDown = { x = 700; y = 266; width = 76; height = 50; };
  octaveUp = { x = 790; y = 266; width = 82; height = 50; };
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
    octave = 4;
    attack = 0.02;
    release = 0.15;
    drag = null;
    mouseBlocked = false;
    blocked = [];
    voices = builtins.listToAttrs (map (note: { name = note.name; value = idle; }) notes);
  };
  step = frame:
    let
      previous = frame.state;
      panic = ray.keyPressed frame ray.keys.enter;
      mouseDown = builtins.elem ray.mouse.left frame.mouseDown;
      mousePressed = builtins.elem ray.mouse.left frame.mousePressed;
      drag = if !mouseDown then null else if previous.drag != null then previous.drag
        else if mousePressed && sliderHit frame attackControl then "attack"
        else if mousePressed && sliderHit frame releaseControl then "release"
        else if mousePressed && (hit frame octaveDown || hit frame octaveUp) then "octave" else null;
      sliderValue = control: control.low + clamp 0.0 1.0
        ((frame.mouseX - control.x) / (control.width * 1.0)) * (control.high - control.low);
      attack = if drag == "attack" then sliderValue attackControl else previous.attack;
      release = if drag == "release" then sliderValue releaseControl else previous.release;
      down = ray.keyPressed frame 90 || (mousePressed && previous.drag == null && hit frame octaveDown);
      up = ray.keyPressed frame 88 || (mousePressed && previous.drag == null && hit frame octaveUp);
      octave = clamp 3 5 (previous.octave + (if up then 1 else 0) - (if down then 1 else 0));
      waveform = if !(ray.keyPressed frame ray.keys.space) then previous.waveform
        else if previous.waveform == "triangle" then "square"
        else if previous.waveform == "square" then "saw" else "triangle";
      changed = waveform != previous.waveform || octave != previous.octave;
      volume = clamp 0.0 1.0 (previous.volume + frame.mouseWheelY * 0.05);
      # Panic stays silent until held keys have been released.
      blocked = builtins.filter (key: ray.keyDown frame key)
        (if panic then map (note: note.key) notes else previous.blocked);
      mouseBlocked = mouseDown && (panic || previous.mouseBlocked);
      # Black keys win overlapping hit tests. Dragging a slider never plays notes.
      pointed = builtins.filter (note: hit frame (keyBounds note))
        ((builtins.filter (note: note.black) notes) ++ (builtins.filter (note: !note.black) notes));
      mouseNote = if !mouseDown || mouseBlocked || drag != null || pointed == [] then null
        else (builtins.head pointed).name;
      dt = clamp 0.0 0.1 frame.delta;
      voices = builtins.listToAttrs (map (note:
        let
          old = if changed then idle else previous.voices.${note.name};
          gate = !panic && ((ray.keyDown frame note.key && !(builtins.elem note.key blocked)) || mouseNote == note.name);
          level = if panic then 0.0 else clamp 0.0 1.0
            (old.level + (if gate then dt / attack else -dt / release));
        in { name = note.name; value = { inherit gate level; }; }
      ) notes);
      active = voice: voice.gate || voice.level > 0.0;
      # Stop the whole old range first: its top C may be the new range's bottom C.
      retired = if !changed then [] else builtins.concatMap (note:
        if active previous.voices.${note.name} then [
          (ray.stopMusic "${previous.waveform}-${(transpose previous.octave note).name}")
        ] else []
      ) notes;
      audio = retired ++ builtins.concatMap (note:
        let
          before = previous.voices.${note.name};
          old = if changed then idle else before;
          voice = voices.${note.name};
          music = "${waveform}-${(transpose octave note).name}";
        in if active voice then [
            # Reserve headroom even when every key is held at maximum volume.
            (ray.setMusicVolume { inherit music; volume = voice.level * volume / 13.0; })
          ] ++ (if voice.gate && !old.gate then [ (ray.playMusic music) ] else [])
          else if active old then [ (ray.stopMusic music) ] else []
      ) notes;
      keyCommands = note:
        let
          voice = voices.${note.name};
          bounds = keyBounds note;
          inherit (bounds) x width height;
          color = if voice.gate then ray.colors.skyblue else if voice.level > 0 then ray.colors.orange
            else if note.black then ray.rgb 35 39 52 else ray.colors.raywhite;
          ink = if note.black && !voice.gate && voice.level == 0 then ray.colors.white else ray.colors.black;
        in [
          (ray.rectangle (bounds // { inherit color; }))
          (ray.rectangle { x = x + 6; y = pianoY + height - 6; width = builtins.floor ((width - 12) * voice.level);
            height = 4; color = ray.colors.blue; })
          (ray.text { text = (transpose octave note).label; x = x + 12; y = pianoY + height - 62; size = 18; color = ink; })
          (ray.text { text = note.keyboard; x = x + 12; y = pianoY + height - 36; size = 24; color = ink; })
        ];
      sliderCommands = name: control: value: [
        (ray.text { text = "${name}: ${toString (builtins.floor (value * 1000 + 0.5))} ms";
          x = control.x; y = 266; size = 20; color = ray.colors.white; })
        (ray.rectangle { x = control.x; y = 300; width = control.width; height = 8; color = ray.colors.gray; })
        (ray.circle { x = control.x + builtins.floor (control.width * (value - control.low) / (control.high - control.low));
          y = 304; radius = 9; color = ray.colors.skyblue; })
      ];
      octaveButton = bounds: text: enabled: [
        (ray.rectangle (bounds // { color = if enabled then ray.rgb 35 55 75 else ray.rgb 27 33 47; }))
        (ray.text { inherit text; x = bounds.x + 12; y = bounds.y + 14; size = 20;
          color = if enabled then ray.colors.skyblue else ray.colors.gray; })
      ];
      previewY = i: 169 - builtins.floor (34 * wave waveform (i / 128.0));
    in {
      state = { inherit volume waveform octave attack release drag mouseBlocked blocked voices; };
      inherit audio;
      commands = [
        (ray.clear (ray.rgb 18 22 33))
        (ray.text { text = "NIX SYNTH"; x = 40; y = 20; size = 30; color = ray.colors.skyblue; })
        (ray.text { text = "Hold A W S E D F T G Y H U J K | Click/drag keys";
          x = 40; y = 64; size = 20; color = ray.colors.white; })
        (ray.text { text = "Space: waveform | Wheel: volume | Enter: all notes off";
          x = 40; y = 94; size = 20; color = ray.colors.gray; })
        (ray.rectangle { x = 40; y = 130; width = 832; height = 80; color = ray.rgb 27 33 47; })
      ] ++ builtins.genList (i: ray.line {
        x1 = 48 + i * 6; y1 = previewY i;
        x2 = 48 + (i + 1) * 6; y2 = previewY (i + 1);
        color = ray.colors.skyblue;
      }) 127 ++ [
        (ray.text { text = "${waveform} | volume ${toString (builtins.floor (volume * 100))}% | Z/X: octave ${toString octave}";
          x = 40; y = 226; size = 20; color = ray.colors.white; })
      ] ++ sliderCommands "Attack" attackControl attack ++ sliderCommands "Release" releaseControl release
        ++ octaveButton octaveDown "Z -" (octave > 3) ++ octaveButton octaveUp "X +" (octave < 5)
        ++ builtins.concatMap keyCommands (builtins.filter (note: !note.black) notes)
        ++ builtins.concatMap keyCommands (builtins.filter (note: note.black) notes) ++ [
        (ray.text { text = "13 voices | Nix-generated looping waves | Esc: quit";
          x = 40; y = 590; size = 16; color = ray.colors.gray; })
      ];
    };
in { inherit notes toneNotes musicAssets waveforms octaves transpose wave initialState step; }
