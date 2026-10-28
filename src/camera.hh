#pragma once

#include "commands.hh"
#include <raylib.h>
#include <optional>

namespace nixray {

class Reader;

Camera2D cameraSpec(const Reader & reader, nix::Value & value);
Command cameraCommand(Camera2D camera, std::optional<Camera2D> parent, std::vector<Command> batch);
void worldToScreen2D(nix::EvalState & state, nix::PosIdx pos, nix::Value ** args, nix::Value & out);
void screenToWorld2D(nix::EvalState & state, nix::PosIdx pos, nix::Value ** args, nix::Value & out);

} // namespace nixray
