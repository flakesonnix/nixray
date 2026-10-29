#pragma once

#include "commands.hh"
#include <string>

namespace nixray {

// Own the title backing raylib's borrowed pointer, plus requested settings for
// which raylib has no getter. This state outlives the native window.
struct WindowState {
    std::string title;
    int targetFPS;
    std::string cursorMode = "normal";
};

// A null window validates structure only; those actions must never execute.
std::vector<Command> windowCommands(nix::EvalState & state, nix::PosIdx pos, nix::Value & value,
                                    WindowState * window = nullptr);
void windowSnapshot(nix::EvalState & state, const WindowState & window, nix::Value & out);

} // namespace nixray
