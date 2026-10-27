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
      devShells = eachSystem (system:
        let pkgs = import nixpkgs { inherit system; };
        in {
          default = pkgs.mkShell {
            inputsFrom = [ self.packages.${system}.nixray ];
            packages = [
              self.packages.${system}.nixray.nixComponents.nix-cli
              pkgs.python3 pkgs.xvfb-run pkgs.mesa
            ];
          };
        });
      lib = import ./lib;
    };
}
