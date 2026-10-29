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
  height = 620;
  title = "Nix synthesizer";
  audio = true;
  assets.music = instrument.musicAssets tones;
  state = instrument.initialState;
} instrument.step
