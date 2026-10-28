#pragma once

#include "commands.hh"

namespace nixray {

class Assets;

// activeTexture, when set, names a render texture currently being painted;
// stamping it into itself would be an undefined OpenGL write/read cycle.
Command textureCommand(nix::EvalState & state, nix::PosIdx pos, nix::Value & value,
                       const Assets * assets, const std::string * activeTexture = nullptr);

} // namespace nixray
