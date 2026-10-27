#pragma once

#include "commands.hh"

namespace nixray {

Command textureCommand(nix::EvalState & state, nix::PosIdx pos, nix::Value & value, const Assets * assets);

} // namespace nixray
