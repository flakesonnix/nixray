{ runCommand ? (import (builtins.getFlake
    "github:NixOS/nixpkgs/566acc07c54dc807f91625bb286cb9b321b5f42a").outPath { }).runCommand
}:
let
  instrument = import ./instrument.nix;
  concat = builtins.concatStringsSep "";
  period = 128;
  cycles = 256;
  frames = period * cycles;
  digits = [ "0" "1" "2" "3" "4" "5" "6" "7" ];
  mod = a: b: a - builtins.div a b * b;
  byte = n: "\\${builtins.elemAt digits (builtins.div n 64)}${builtins.elemAt digits (mod (builtins.div n 8) 8)}${builtins.elemAt digits (mod n 8)}";
  le = count: n: if count == 0 then "" else byte (mod n 256) + le (count - 1) (builtins.div n 256);
  header = rate: "RIFF" + le 4 (36 + frames) + "WAVEfmt " + le 4 16 + le 2 1 + le 2 1
    + le 4 rate + le 4 rate + le 2 1 + le 2 8 + "data" + le 4 frames;
in
runCommand "nixray-synth-tones" { } ''
  mkdir -p "$out"
  ${concat (map (waveform: ''
    # Nix computes every 8-bit PCM sample; shell only writes the binary bytes.
    for ((cycle = 0; cycle < ${toString cycles}; ++cycle)); do
      printf '%b' '${concat (builtins.genList (i:
        byte (128 + builtins.floor (96 * instrument.wave waveform (i / 128.0)))
      ) period)}'
    done > ${waveform}.pcm
    ${concat (map (note: ''
      printf '%b' '${header (builtins.floor (note.frequency * period + 0.5))}' > "$out/${waveform}-${note.name}.wav"
      cat ${waveform}.pcm >> "$out/${waveform}-${note.name}.wav"
    '') instrument.notes)}
  '') instrument.waveforms)}
''
