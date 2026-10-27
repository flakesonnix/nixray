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

  passthru = { inherit nixComponents; };
  meta = {
    description = "A raylib-backed Nix evaluator plugin with an ordered frame loop";
    license = lib.licenses.mit;
    platforms = lib.platforms.linux;
  };
}
