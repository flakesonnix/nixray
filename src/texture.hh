#pragma once

#include "commands.hh"
#include <raylib.h>

namespace nixray {

class Assets;
class Reader;
struct TextureOptions;

void configureTexture(Texture2D & texture, const TextureOptions & options, const Reader & reader);
void refreshTextureMipmaps(Texture2D texture);
std::vector<Command> textureActions(nix::EvalState & state, nix::PosIdx pos, nix::Value & value,
                                     const Assets * assets = nullptr);

// activeTexture, when set, names a render texture currently being painted;
// stamping it into itself would be an undefined OpenGL write/read cycle.
Command textureCommand(nix::EvalState & state, nix::PosIdx pos, nix::Value & value,
                        const Assets * assets, const std::string * activeTexture = nullptr);
Command texturePatchCommand(nix::EvalState & state, nix::PosIdx pos, nix::Value & value,
                             const Assets * assets, const std::string * activeTexture = nullptr);

} // namespace nixray
