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
}:

let
  launcher = writeShellScript "nixray-launcher" ''
    set -euo pipefail

    if [ "$#" -eq 0 ]; then
      echo "usage: nixray FILE [nix-instantiate options]" >&2
      exit 2
    fi

    nix="''${NIXRAY_NIX:?NIXRAY_NIX is not set}"
    plugin="''${NIXRAY_PLUGIN:?NIXRAY_PLUGIN is not set}"
    mesa="''${NIXRAY_MESA:?NIXRAY_MESA is not set}"

    # Use the packaged Mesa stack. Mixing a Nix glvnd/GLFW with a system
    # graphics-driver store can leave EGL without a usable vendor/display.
    export LD_LIBRARY_PATH="$mesa/lib''${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
    export LIBGL_DRIVERS_PATH="$mesa/lib/dri"
    export __EGL_VENDOR_LIBRARY_FILENAMES="$mesa/share/glvnd/egl_vendor.d/50_mesa.json"
    export __GLX_VENDOR_LIBRARY_NAME=mesa

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
    if [ "$has_args" = true ] || [ "$file" = "-" ] || [ "''${file#-}" != "$file" ]; then
      exec "$nix" --option plugin-files "$plugin" --eval --strict --json "$file" "$@"
    fi

    case "$file" in
      /*) ;;
      *) file="$PWD/$file" ;;
    esac

    exec "$nix" --option plugin-files "$plugin" --eval --strict --json \
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
  # libblake3, glfw and openssl satisfy pkg-config's recursive dependency checks.
  buildInputs = [ nixComponents.nix-expr boost libblake3 raylib glfw openssl ];
  nativeCheckInputs = [ nixComponents.nix-cli python3 xvfb-run mesa ];
  doCheck = true;

  checkPhase = ''
    runHook preCheck
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
    xvfb-run -a -s '-screen 0 800x600x24' \
      python3 ../tests/test_plugin.py \
        --nix ${nixComponents.nix-cli}/bin/nix-instantiate \
        --plugin "$PWD/nixray.so"
    runHook postCheck
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
