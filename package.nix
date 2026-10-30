{ lib
, stdenv
, cmake
, pkg-config
, makeWrapper
, writeShellScript
, nixVersions
, nixComponents ? nixVersions.nixComponents_2_34
, boost
, libblake3
, raylib
, glfw
, openssl
, python3
, xvfb-run
, mesa
, dejavu_fonts
, runCommand
}:

let
  synthTones = import ./examples/synth/tones.nix { inherit runCommand; };
  launcher = writeShellScript "nixray-launcher" ''
    set -euo pipefail

    if [ "$#" -eq 0 ]; then
      echo "usage: nixray FILE [nix-instantiate options]" >&2
      exit 2
    fi

    nix="''${NIXRAY_NIX:?NIXRAY_NIX is not set}"
    plugin="''${NIXRAY_PLUGIN:?NIXRAY_PLUGIN is not set}"

    case "''${NIXRAY_GRAPHICS:-mesa}" in
      mesa)
        # Keep the compatible packaged stack as the default.
        mesa="''${NIXRAY_MESA:?NIXRAY_MESA is not set}"
        export LD_LIBRARY_PATH="$mesa/lib''${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
        export LIBGL_DRIVERS_PATH="$mesa/lib/dri"
        export __EGL_VENDOR_LIBRARY_FILENAMES="$mesa/share/glvnd/egl_vendor.d/50_mesa.json"
        export __GLX_VENDOR_LIBRARY_NAME=mesa
        ;;
      system)
        # Leave all inherited graphics settings, including NVIDIA/PRIME, alone.
        ;;
      *)
        echo "nixray: NIXRAY_GRAPHICS must be 'mesa' or 'system'" >&2
        exit 2
        ;;
    esac

    file=$1
    shift

    has_args=false
    for arg in "$@"; do
      case "$arg" in
        --arg|--argstr) has_args=true ;;
      esac
    done

    # nix-instantiate only applies top-level function defaults when an
    # --arg/--argstr is present. Apply an explicit empty argument set otherwise.
    # Read-write mode lets context-bearing asset paths be materialised in the store.
    if [ "$has_args" = true ] || [ "$file" = "-" ] || [ "''${file#-}" != "$file" ]; then
      exec "$nix" --read-write-mode --option plugin-files "$plugin" --eval --strict --json "$file" "$@"
    fi

    case "$file" in
      /*) ;;
      *) file="$PWD/$file" ;;
    esac

    exec "$nix" --read-write-mode --option plugin-files "$plugin" --eval --strict --json \
      --argstr __nixray_file "$file" \
      --expr '{ __nixray_file }: let f = import (builtins.toPath __nixray_file); in if builtins.isFunction f then f {} else f' \
      "$@"
  '';
in
stdenv.mkDerivation {
  pname = "nixray";
  version = "0.1.0";
  src = lib.cleanSourceWith {
    src = ./.;
    filter = path: type:
      !(builtins.elem (baseNameOf path) [ "build" "__pycache__" ])
      && lib.cleanSourceFilter path type;
  };

  nativeBuildInputs = [ cmake pkg-config makeWrapper ];
  # libblake3 and openssl satisfy pkg-config's recursive dependency checks.
  # GLFW also provides current-context GL entry points for shader reflection.
  buildInputs = [ nixComponents.nix-expr boost libblake3 raylib glfw openssl ];
  nativeCheckInputs = [ nixComponents.nix-cli python3 xvfb-run mesa dejavu_fonts ];
  nativeInstallCheckInputs = [ python3 xvfb-run mesa ];
  doCheck = true;
  doInstallCheck = true;

  checkPhase = ''
    runHook preCheck
    export NIXRAY_TEST_FONT=${dejavu_fonts}/share/fonts/truetype/DejaVuSans.ttf
    export NIXRAY_TEST_SYNTH_TONES=${synthTones}
    export HOME="$TMPDIR/home"
    mkdir -p "$HOME"
    export NIX_STATE_DIR="$TMPDIR/nix-state"
    export NIX_STORE_DIR="$TMPDIR/store"
    export NIX_CONFIG="experimental-features = nix-command flakes"
    export XDG_RUNTIME_DIR="$TMPDIR/runtime"
    mkdir -m 700 -p "$XDG_RUNTIME_DIR"
    export LIBGL_ALWAYS_SOFTWARE=1
    export GALLIUM_DRIVER=llvmpipe
    export LIBGL_DRIVERS_PATH=${mesa}/lib/dri
    export LD_LIBRARY_PATH=${lib.makeLibraryPath [ mesa ]}
    export __GLX_VENDOR_LIBRARY_NAME=mesa
    export __EGL_VENDOR_LIBRARY_FILENAMES=${mesa}/share/glvnd/egl_vendor.d/50_mesa.json
    unset WAYLAND_DISPLAY
    export XDG_SESSION_TYPE=x11
    # Repeated windows must not race an X server reset after the last client exits.
    xvfb-run -a -s '-screen 0 800x600x24 -noreset' \
      python3 ../tests/test_plugin.py \
        --nix ${nixComponents.nix-cli}/bin/nix-instantiate \
        --plugin "$PWD/nixray.so" \
        --capture-library "$PWD/nixray-test-capture.so" \
        --input-library "$PWD/nixray-test-input.so" \
        --audio-library "$PWD/nixray-test-audio.so" \
        --window-library "$PWD/nixray-test-window.so" \
        --model-library "$PWD/nixray-test-model.so" \
        --texture-library "$PWD/nixray-test-texture.so"
    runHook postCheck
  '';

  installCheckPhase = ''
    runHook preInstallCheck
    test ! -e "$out/lib/nix/plugins/nixray-test-capture.so"
    test ! -e "$out/lib/nix/plugins/nixray-test-input.so"
    test ! -e "$out/lib/nix/plugins/nixray-test-audio.so"
    test ! -e "$out/lib/nix/plugins/nixray-test-window.so"
    test ! -e "$out/lib/nix/plugins/nixray-test-model.so"
    test ! -e "$out/lib/nix/plugins/nixray-test-texture.so"
    unset WAYLAND_DISPLAY
    export XDG_SESSION_TYPE=x11
    export HOME="$TMPDIR/home"
    mkdir -p "$HOME"
    export NIX_STATE_DIR="$TMPDIR/nix-state"
    export NIX_STORE_DIR="$TMPDIR/store"
    export NIX_CONFIG="experimental-features = nix-command flakes"
    export XDG_RUNTIME_DIR="$TMPDIR/runtime"
    mkdir -m 700 -p "$XDG_RUNTIME_DIR"
    export LIBGL_ALWAYS_SOFTWARE=1
    export GALLIUM_DRIVER=llvmpipe
    export LIBGL_DRIVERS_PATH=${mesa}/lib/dri
    export LD_LIBRARY_PATH=${lib.makeLibraryPath [ mesa ]}
    export __GLX_VENDOR_LIBRARY_NAME=mesa
    export __EGL_VENDOR_LIBRARY_FILENAMES=${mesa}/share/glvnd/egl_vendor.d/50_mesa.json
    cat > "$TMPDIR/auto-call.nix" <<'EOF'
{ value ? 42 }: { inherit value; }
EOF
    auto_output=$("$out/bin/nixray" "$TMPDIR/auto-call.nix")
    printf '%s\n' "$auto_output"
    printf '%s\n' "$auto_output" | grep -q '"value":42'
    direct_output=$("$out/bin/nixray" "$TMPDIR/auto-call.nix" --arg value 7)
    printf '%s\n' "$direct_output"
    printf '%s\n' "$direct_output" | grep -q '"value":7'
    printf 'nixray asset context\n' > "$TMPDIR/context-source.txt"
    cat > "$TMPDIR/store-context.nix" <<'EOF'
{ marker ? "nixray-auto-context" }:
builtins.readFile "''${builtins.path { path = ./context-source.txt; name = marker; }}"
EOF
    context_output=$("$out/bin/nixray" "$TMPDIR/store-context.nix")
    printf '%s\n' "$context_output"
    printf '%s\n' "$context_output" | grep -q 'nixray asset context'
    direct_context=$("$out/bin/nixray" "$TMPDIR/store-context.nix" --argstr marker nixray-direct-context)
    printf '%s\n' "$direct_context"
    printf '%s\n' "$direct_context" | grep -q 'nixray asset context'
    if ! smoke_output=$(xvfb-run -a -s '-screen 0 800x600x24 -noreset' \
      "$out/bin/nixray" ../examples/hello.nix --arg hidden true --arg maxFrames 1 2>&1)
    then
      printf '%s\n' "$smoke_output" >&2
      exit 1
    fi
    printf '%s\n' "$smoke_output"
    printf '%s\n' "$smoke_output" | grep -q '"frames":1'
    cat > "$TMPDIR/builtin.nix" <<'EOF'
builtins.raylib {
  width = 64; height = 64; hidden = true; fps = 0; maxFrames = 2;
  state = 0;
} (frame: {
  commands = [ { op = "clear"; color = [ 0 0 0 255 ]; } ];
  state = frame.state + 1;
})
EOF
    if ! builtin_output=$(xvfb-run -a -s '-screen 0 800x600x24 -noreset' \
      "$out/bin/nixray" "$TMPDIR/builtin.nix" 2>&1)
    then
      printf '%s\n' "$builtin_output" >&2
      exit 1
    fi
    printf '%s\n' "$builtin_output"
    printf '%s\n' "$builtin_output" | grep -q '"frames":2,"state":2'
    if ! lighting_output=$(xvfb-run -a -s '-screen 0 800x600x24 -noreset' \
      "$out/bin/nixray" "$out/share/nixray/examples/lighting.nix" --arg hidden true --arg maxFrames 2 2>&1)
    then
      printf '%s\n' "$lighting_output" >&2
      exit 1
    fi
    printf '%s\n' "$lighting_output"
    printf '%s\n' "$lighting_output" | grep -q '"frames":2,"state":{"glossy":true,"warm":true}'
    image_output=$(env -u DISPLAY -u WAYLAND_DISPLAY "$out/bin/nixray" --expr \
      'builtins.raylibImagePixel (builtins.raylibGenImage { width = 1; height = 1; color = [17 34 51 255]; }) { x = 0; y = 0; }')
    printf '%s\n' "$image_output"
    printf '%s\n' "$image_output" | grep -q '^\[17,34,51,255\]$'
    if ! image_demo=$(xvfb-run -a -s '-screen 0 800x600x24 -noreset' \
      "$out/bin/nixray" "$out/share/nixray/examples/images.nix" --arg hidden true --arg maxFrames 2 2>&1)
    then
      printf '%s\n' "$image_demo" >&2
      exit 1
    fi
    printf '%s\n' "$image_demo"
    printf '%s\n' "$image_demo" | grep -q '"frames":2'
    if ! texture_demo=$(xvfb-run -a -s '-screen 0 800x600x24 -noreset' \
      "$out/bin/nixray" "$out/share/nixray/examples/texture-updates.nix" --arg hidden true --arg maxFrames 2 2>&1)
    then
      printf '%s\n' "$texture_demo" >&2
      exit 1
    fi
    printf '%s\n' "$texture_demo"
    printf '%s\n' "$texture_demo" | grep -q '"frames":2,"state":{"paused":false,"tick":2}'
    if ! drawing_demo=$(xvfb-run -a -s '-screen 0 800x600x24 -noreset' \
      "$out/bin/nixray" "$out/share/nixray/examples/drawing-extra.nix" --arg hidden true --arg maxFrames 2 2>&1)
    then
      printf '%s\n' "$drawing_demo" >&2
      exit 1
    fi
    printf '%s\n' "$drawing_demo"
    printf '%s\n' "$drawing_demo" | grep -q '"frames":2,"state":{"reverse":false,"thickness":4}'
    if ! text_demo=$(xvfb-run -a -s '-screen 0 800x600x24 -noreset' \
      "$out/bin/nixray" "$out/share/nixray/examples/text-layout.nix" --arg hidden true --arg maxFrames 2 2>&1)
    then
      printf '%s\n' "$text_demo" >&2
      exit 1
    fi
    printf '%s\n' "$text_demo"
    printf '%s\n' "$text_demo" | grep -q '"frames":2'
    xvfb-run -a -s '-screen 0 800x600x24 -noreset' \
      python3 ../tests/test_launcher.py --launcher "$out/bin/nixray" --mesa ${mesa}
    runHook postInstallCheck
  '';

  postInstall = ''
    mkdir -p "$out/bin" "$out/share/nixray"
    cp -r ../lib ../examples "$out/share/nixray/"
    install -m755 ${launcher} "$out/bin/nixray"
    wrapProgram "$out/bin/nixray" \
      --set NIXRAY_NIX "${nixComponents.nix-cli}/bin/nix-instantiate" \
      --set NIXRAY_PLUGIN "$out/lib/nix/plugins/nixray.so" \
      --set NIXRAY_MESA "${mesa}"
  '';

  passthru = { inherit nixComponents; };
  meta = {
    description = "A raylib-backed Nix evaluator plugin with an ordered frame loop";
    license = lib.licenses.mit;
    platforms = lib.platforms.linux;
    mainProgram = "nixray";
  };
}
