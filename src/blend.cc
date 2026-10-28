#include "blend.hh"
#include "reader.hh"

#include <utility>

namespace nixray {

BlendMode blendMode(const Reader & r, Value & value)
{
    auto mode = r.string(value);
    if (mode == "alpha") return BLEND_ALPHA;
    if (mode == "additive") return BLEND_ADDITIVE;
    if (mode == "multiply") return BLEND_MULTIPLIED;
    if (mode == "subtract") return BLEND_SUBTRACT_COLORS;
    r.fail("unknown blend mode '" + mode + "'; expected alpha, additive, multiply or subtract");
}

BlendScope::BlendScope(BlendMode mode, BlendMode parent) : parent(parent)
{
    // Changing modes flushes raylib's pending geometry before changing GL state.
    BeginBlendMode(mode);
}

BlendScope::~BlendScope()
{
    BeginBlendMode(parent);
}

Command blendCommand(BlendMode mode, BlendMode parent, std::vector<Command> batch)
{
    return [mode, parent, batch = std::move(batch)] {
        BlendScope scope(mode, parent);
        for (const auto & command : batch) command();
    };
}

} // namespace nixray
