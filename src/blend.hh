#pragma once

#include "commands.hh"
#include <raylib.h>

namespace nixray {

class Reader;

BlendMode blendMode(const Reader & reader, nix::Value & value);

// raylib's EndBlendMode resets to alpha instead of restoring a parent mode.
class BlendScope {
    BlendMode parent;

public:
    BlendScope(BlendMode mode, BlendMode parent);
    ~BlendScope();
    BlendScope(const BlendScope &) = delete;
    BlendScope & operator=(const BlendScope &) = delete;
};

Command blendCommand(BlendMode mode, BlendMode parent, std::vector<Command> batch);

} // namespace nixray
