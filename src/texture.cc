#include "texture.hh"
#include "assets.hh"
#include "reader.hh"

#include <cmath>
#include <limits>

namespace nixray {

Command textureCommand(EvalState & state, PosIdx pos, Value & value, const Assets * assets)
{
    Reader r(state, pos);
    r.fields(value, {"op", "texture", "x", "y", "tint", "scale", "rotation"});
    auto name = r.string(r.required(value, "texture"));
    if (name.empty()) r.fail("texture name must not be empty");
    int x = r.integerAttr(value, "x"), y = r.integerAttr(value, "y");
    auto * tintValue = r.optional(value, "tint");
    auto tint = tintValue ? r.color(*tintValue) : WHITE;
    auto * scaleValue = r.optional(value, "scale");
    float scale = scaleValue ? r.number(*scaleValue, "scale", 0) : 1.0f;
    if (scale == 0) r.fail("scale must be positive");
    auto * rotationValue = r.optional(value, "rotation");
    float rotation = rotationValue ? r.number(*rotationValue, "rotation") : 0.0f;
    Texture2D texture{};
    if (assets) {
        auto * found = assets->texture(name);
        if (!found) r.fail("unknown texture '" + name + "'");
        texture = *found;
        // Bound the diagonal so rotating a very large quad cannot overflow floats.
        if (std::hypot(static_cast<double>(texture.width) * scale,
                       static_cast<double>(texture.height) * scale) > std::numeric_limits<float>::max())
            r.fail("scaled texture dimensions must fit finite raylib coordinates");
    }
    return [=] { DrawTextureEx(texture, {static_cast<float>(x), static_cast<float>(y)}, rotation, scale, tint); };
}

} // namespace nixray
