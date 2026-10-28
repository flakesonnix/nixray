#include "texture.hh"
#include "assets.hh"
#include "reader.hh"

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <limits>
#include <string>

namespace nixray {

Command textureCommand(EvalState & state, PosIdx pos, Value & value, const Assets * assets,
                       const std::string * activeTexture)
{
    Reader r(state, pos);
    r.fields(value, {"op", "texture", "x", "y", "tint", "scale", "rotation", "source", "origin", "flipX", "flipY"});
    auto name = r.string(r.required(value, "texture"));
    if (name.empty()) r.fail("texture name must not be empty");
    if (activeTexture && *activeTexture == name)
        r.fail("cannot stamp texture '" + name + "' into its own paint");
    int x = r.integerAttr(value, "x"), y = r.integerAttr(value, "y");
    auto * tintValue = r.optional(value, "tint");
    auto tint = tintValue ? r.color(*tintValue) : WHITE;
    auto * scaleValue = r.optional(value, "scale");
    float scale = scaleValue ? r.number(*scaleValue, "scale", 0) : 1.0f;
    if (scale == 0) r.fail("scale must be positive");
    auto * rotationValue = r.optional(value, "rotation");
    float rotation = rotationValue ? r.number(*rotationValue, "rotation") : 0.0f;
    bool flipX = r.defaultBool(value, "flipX", false);
    bool flipY = r.defaultBool(value, "flipY", false);
    Vector2 origin{};
    if (auto * originValue = r.optional(value, "origin")) {
        r.fields(*originValue, {"x", "y"});
        origin.x = r.number(r.required(*originValue, "x"), "origin.x");
        origin.y = r.number(r.required(*originValue, "y"), "origin.y");
    }
    Texture2D texture{};
    // Render targets are attached bottom-up relative to their logical image;
    // drawing one requires inverted vertical UV traversal.
    bool rerouted = false;
    if (assets) {
        if (auto * found = assets->texture(name)) texture = *found;
        else if (auto * target = assets->renderTexture(name)) {
            texture = target->texture;
            rerouted = true;
        } else r.fail("unknown texture '" + name + "'");
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
    // Bound the diagonal so rotating a very large quad cannot overflow floats.
    if (std::hypot(static_cast<double>(width) * scale,
                   static_cast<double>(height) * scale) > std::numeric_limits<float>::max())
        r.fail("scaled texture dimensions must fit finite raylib coordinates");
    Rectangle destination{static_cast<float>(x), static_cast<float>(y), width * scale, height * scale};
    // Subtract in double precision before raylib performs the same steps in floats.
    double reachX = std::max(std::abs(static_cast<double>(origin.x)),
                             std::abs(static_cast<double>(destination.width) - origin.x));
    double reachY = std::max(std::abs(static_cast<double>(origin.y)),
                             std::abs(static_cast<double>(destination.height) - origin.y));
    if (std::hypot(reachX, reachY) > std::numeric_limits<float>::max())
        r.fail("texture origin and dimensions must fit finite raylib coordinates");
    int sourceY = sy, sourceHeight = height;
    if (rerouted) {
        // Traverse v bottom-up so logical crops display upright.
        sourceY = texture.height - sy - height;
        if (!flipY) sourceHeight = -height;
    } else if (flipY) sourceHeight = -height;
    Rectangle source{static_cast<float>(sx), static_cast<float>(sourceY),
                     static_cast<float>(width), static_cast<float>(sourceHeight)};
    // Only reverse UV traversal horizontally, after checking positive sizes.
    if (flipX) source.width = -source.width;
    return [=] { DrawTexturePro(texture, source, destination, origin, rotation, tint); };
}

} // namespace nixray
