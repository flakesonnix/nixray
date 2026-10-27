#include "texture.hh"
#include "assets.hh"
#include "reader.hh"

#include <cmath>
#include <cstdint>
#include <limits>

namespace nixray {

Command textureCommand(EvalState & state, PosIdx pos, Value & value, const Assets * assets)
{
    Reader r(state, pos);
    r.fields(value, {"op", "texture", "x", "y", "tint", "scale", "rotation", "source"});
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
    }
    int sx = 0, sy = 0, width = texture.width, height = texture.height;
    if (auto * sourceValue = r.optional(value, "source")) {
        r.fields(*sourceValue, {"x", "y", "width", "height"});
        sx = r.integerAttr(*sourceValue, "x", 0);
        sy = r.integerAttr(*sourceValue, "y", 0);
        width = r.integerAttr(*sourceValue, "width", 1);
        height = r.integerAttr(*sourceValue, "height", 1);
        if (assets && (static_cast<int64_t>(sx) + width > texture.width ||
                       static_cast<int64_t>(sy) + height > texture.height))
            r.fail("source rectangle exceeds texture '" + name + "'");
    }
    Rectangle source{static_cast<float>(sx), static_cast<float>(sy),
                     static_cast<float>(width), static_cast<float>(height)};
    // Bound the diagonal so rotating a very large quad cannot overflow floats.
    if (std::hypot(static_cast<double>(source.width) * scale,
                   static_cast<double>(source.height) * scale) > std::numeric_limits<float>::max())
        r.fail("scaled texture dimensions must fit finite raylib coordinates");
    Rectangle destination{static_cast<float>(x), static_cast<float>(y), source.width * scale, source.height * scale};
    return [=] { DrawTexturePro(texture, source, destination, {0, 0}, rotation, tint); };
}

} // namespace nixray
