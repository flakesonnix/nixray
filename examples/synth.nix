{ hidden ? false
, maxFrames ? 0
, tones ? import ./synth/tones.nix { }
}:
let
  ray = import ../lib;
  instrument = import ./synth/instrument.nix;
in
ray.run {
  inherit hidden maxFrames;
  width = 920;
  height = 520;
  title = "Nix synthesizer";
  audio = true;
  assets.music = builtins.listToAttrs (builtins.concatMap (waveform:
    map (note: {
      name = "${waveform}-${note.name}";
      value = { path = "${tones}/${waveform}-${note.name}.wav"; looping = true; };
    }) instrument.notes
  ) instrument.waveforms);
  state = instrument.initialState;
} instrument.step
