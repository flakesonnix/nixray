#include "texture.hh"
#include "assets.hh"
#include "reader.hh"

namespace nixray {

Command textureCommand(EvalState & state, PosIdx pos, Value & value, const Assets * assets)
{
    Reader r(state, pos);
    r.fields(value, {"op", "texture", "x", "y", "tint"});
    auto name = r.string(r.required(value, "texture"));
    if (name.empty()) r.fail("texture name must not be empty");
    int x = r.integerAttr(value, "x"), y = r.integerAttr(value, "y");
    auto * tintValue = r.optional(value, "tint");
    auto tint = tintValue ? r.color(*tintValue) : WHITE;
    Texture2D texture{};
    if (assets) {
        auto * found = assets->texture(name);
        if (!found) r.fail("unknown texture '" + name + "'");
        texture = *found;
    }
    return [=] { DrawTexture(texture, x, y, tint); };
}

} // namespace nixray
