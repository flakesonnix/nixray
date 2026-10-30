#pragma once

#include "commands.hh"
#include <raylib.h>
#include <optional>
#include <string>

namespace nixray {

class Reader;

Camera3D camera3DSpec(const Reader & reader, nix::Value & value);
void validateProjection3D(const Reader & reader, Camera3D camera, double aspect);
Command camera3DCommand(const Reader & reader, Camera3D camera, std::optional<Camera2D> parent,
                        bool clearDepth, bool loaded, std::vector<Command> batch);
bool isShape3D(const std::string & op);
Command shape3DCommand(nix::EvalState & state, nix::PosIdx pos, nix::Value & value, const std::string & op);

} // namespace nixray
