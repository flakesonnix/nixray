cmake_minimum_required(VERSION 3.20)
project(nixray VERSION 0.1.0 LANGUAGES CXX)

find_package(PkgConfig REQUIRED)
# Nix's C++ evaluator API is not ABI-stable. Use the packaged launcher.
pkg_check_modules(NIX REQUIRED IMPORTED_TARGET nix-expr>=2.34 nix-expr<2.35)
pkg_check_modules(RAYLIB REQUIRED IMPORTED_TARGET raylib>=5.5)
pkg_check_modules(GLFW REQUIRED IMPORTED_TARGET glfw3)

add_library(nixray MODULE
    src/plugin.cc
    src/commands.cc
    src/runtime.cc
    src/window.cc
    src/input.cc
    src/assets.cc
    src/texture.cc
    src/text.cc
    src/shapes.cc
    src/curves.cc
    src/clip.cc
    src/blend.cc
    src/camera.cc
    src/collision.cc
    src/render_texture.cc
    src/shader.cc
    src/audio.cc
)
target_compile_features(nixray PRIVATE cxx_std_23)
target_compile_options(nixray PRIVATE -Wall -Wextra)
target_link_libraries(nixray PRIVATE PkgConfig::NIX PkgConfig::RAYLIB PkgConfig::GLFW)
set_target_properties(nixray PROPERTIES PREFIX "")
install(TARGETS nixray LIBRARY DESTINATION lib/nix/plugins)

include(CTest)
if(BUILD_TESTING)
    # These hooks are only preloaded by tests and never installed with the plugin.
    foreach(hook IN ITEMS capture input audio window)
        add_library(nixray-test-${hook} MODULE tests/${hook}.cc)
        target_compile_features(nixray-test-${hook} PRIVATE cxx_std_23)
        target_compile_options(nixray-test-${hook} PRIVATE -Wall -Wextra)
        target_link_libraries(nixray-test-${hook} PRIVATE PkgConfig::RAYLIB ${CMAKE_DL_LIBS})
        set_target_properties(nixray-test-${hook} PROPERTIES PREFIX "")
    endforeach()
endif()
