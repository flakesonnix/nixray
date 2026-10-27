{
  description = "Draw raylib windows from Nix expressions";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/566acc07c54dc807f91625bb286cb9b321b5f42a";

  outputs = { self, nixpkgs }:
    let
      systems = [ "x86_64-linux" "aarch64-linux" ];
      eachSystem = nixpkgs.lib.genAttrs systems;
      packageFor = system:
        let pkgs = import nixpkgs { inherit system; };
        in pkgs.callPackage ./package.nix { };
    in {
      packages = eachSystem (system: rec {
        nixray = packageFor system;
        default = nixray;
      });
      apps = eachSystem (system: {
        default = {
          type = "app";
          program = "${self.packages.${system}.nixray}/bin/nixray";
          meta.description = "Open a raylib window from a Nix expression";
        };
      });
      checks = eachSystem (system: {
        integration = self.packages.${system}.nixray;
      });
      devShells = eachSystem (system:
        let pkgs = import nixpkgs { inherit system; };
        in {
          default = pkgs.mkShell {
            inputsFrom = [ self.packages.${system}.nixray ];
            packages = [
              self.packages.${system}.nixray.nixComponents.nix-cli
              pkgs.python3 pkgs.xvfb-run pkgs.mesa pkgs.dejavu_fonts
            ];
            # Make the README's Xvfb test command work out of the box.
            shellHook = ''
              export NIXRAY_TEST_FONT=${pkgs.dejavu_fonts}/share/fonts/truetype/DejaVuSans.ttf
              export XDG_RUNTIME_DIR="''${XDG_RUNTIME_DIR:-/tmp/nixray-runtime-$(id -u)}"
              mkdir -m 700 -p "$XDG_RUNTIME_DIR"
              export LIBGL_ALWAYS_SOFTWARE=1
              export GALLIUM_DRIVER=llvmpipe
              export LIBGL_DRIVERS_PATH=${pkgs.mesa}/lib/dri
              export LD_LIBRARY_PATH=${pkgs.lib.makeLibraryPath [ pkgs.mesa ]}
              export __GLX_VENDOR_LIBRARY_NAME=mesa
              export __EGL_VENDOR_LIBRARY_FILENAMES=${pkgs.mesa}/share/glvnd/egl_vendor.d/50_mesa.json
            '';
          };
        });
      lib = import ./lib;
    };
}
