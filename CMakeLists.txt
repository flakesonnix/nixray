cmake_minimum_required(VERSION 3.20)
project(nixray VERSION 0.1.0 LANGUAGES CXX)

find_package(PkgConfig REQUIRED)
# Nix's C++ evaluator API is not ABI-stable. Use the packaged launcher.
pkg_check_modules(NIX REQUIRED IMPORTED_TARGET nix-expr>=2.34 nix-expr<2.35)
pkg_check_modules(RAYLIB REQUIRED IMPORTED_TARGET raylib>=5.5)

add_library(nixray MODULE
    src/plugin.cc
    src/commands.cc
    src/runtime.cc
    src/assets.cc
)
target_compile_features(nixray PRIVATE cxx_std_23)
target_compile_options(nixray PRIVATE -Wall -Wextra)
target_link_libraries(nixray PRIVATE PkgConfig::NIX PkgConfig::RAYLIB)
set_target_properties(nixray PROPERTIES PREFIX "")
install(TARGETS nixray LIBRARY DESTINATION lib/nix/plugins)
