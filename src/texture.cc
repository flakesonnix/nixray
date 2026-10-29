#include "texture.hh"
#include "assets.hh"
#include "reader.hh"

#include <rlgl.h>
#include <algorithm>
#include <array>
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
        if (assets && !assets->textureRepeats(name) && (static_cast<int64_t>(sx) + width > texture.width ||
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
    float sourceY = sy, sourceHeight = height;
    if (rerouted) {
        // Traverse v bottom-up so logical crops display upright.
        // Repeated crops may exceed int32 when their nonnegative offsets add up.
        sourceY = static_cast<float>(static_cast<double>(texture.height) - sy - height);
        if (!flipY) sourceHeight = -height;
    } else if (flipY) sourceHeight = -height;
    Rectangle source{static_cast<float>(sx), static_cast<float>(sourceY),
                     static_cast<float>(width), static_cast<float>(sourceHeight)};
    // Only reverse UV traversal horizontally, after checking positive sizes.
    if (flipX) source.width = -source.width;
    return [=] { DrawTexturePro(texture, source, destination, origin, rotation, tint); };
}

Command texturePatchCommand(EvalState & state, PosIdx pos, Value & value, const Assets * assets,
                            const std::string * activeTexture)
{
    Reader r(state, pos);
    r.fields(value, {"op", "texture", "x", "y", "width", "height", "borders", "source", "tint", "origin", "rotation"});
    auto name = r.string(r.required(value, "texture"));
    if (name.empty()) r.fail("texture name must not be empty");
    if (activeTexture && *activeTexture == name) r.fail("cannot stamp texture '" + name + "' into its own paint");
    int x = r.integerAttr(value, "x"), y = r.integerAttr(value, "y");
    int width = r.integerAttr(value, "width", 0), height = r.integerAttr(value, "height", 0);
    auto & borders = r.required(value, "borders");
    r.fields(borders, {"left", "top", "right", "bottom"});
    int left = r.integerAttr(borders, "left", 0), top = r.integerAttr(borders, "top", 0);
    int right = r.integerAttr(borders, "right", 0), bottom = r.integerAttr(borders, "bottom", 0);
    auto * tintValue = r.optional(value, "tint");
    auto tint = tintValue ? r.color(*tintValue) : WHITE;
    float rotation = 0;
    if (auto * angle = r.optional(value, "rotation")) rotation = r.number(*angle, "rotation");
    Vector2 origin{};
    if (auto * pivot = r.optional(value, "origin")) {
        r.fields(*pivot, {"x", "y"});
        origin = {r.number(r.required(*pivot, "x"), "origin.x"), r.number(r.required(*pivot, "y"), "origin.y")};
    }
    double reachX = std::max(std::abs(static_cast<double>(origin.x)), std::abs(static_cast<double>(width) - origin.x));
    double reachY = std::max(std::abs(static_cast<double>(origin.y)), std::abs(static_cast<double>(height) - origin.y));
    if (std::hypot(reachX, reachY) > std::numeric_limits<float>::max())
        r.fail("texture origin and dimensions must fit finite raylib coordinates");
    Texture2D texture{};
    bool target = false;
    if (assets) {
        if (auto * found = assets->texture(name)) texture = *found;
        else if (auto * found = assets->renderTexture(name)) { texture = found->texture; target = true; }
        else r.fail("unknown texture '" + name + "'");
    }
    int sx = 0, sy = 0, sw = texture.width, sh = texture.height;
    auto * source = r.optional(value, "source");
    if (source) {
        r.fields(*source, {"x", "y", "width", "height"});
        sx = r.integerAttr(*source, "x", 0); sy = r.integerAttr(*source, "y", 0);
        sw = r.integerAttr(*source, "width", 1); sh = r.integerAttr(*source, "height", 1);
    }
    if (assets && (static_cast<int64_t>(sx) + sw > texture.width || static_cast<int64_t>(sy) + sh > texture.height))
        r.fail("source rectangle exceeds texture '" + name + "'");
    if ((assets || source) && (static_cast<int64_t>(left) + right >= sw || static_cast<int64_t>(top) + bottom >= sh))
        r.fail("nine-patch borders must leave a nonempty source center");
    // Pure validation cannot resolve an omitted source size; zero-area panels still validate fully.
    if (!assets || width == 0 || height == 0) return [] {};
    double dl = left, dr = right, dt = top, db = bottom;
    if (width < dl + dr) { dl = width * dl / (dl + dr); dr = width - dl; }
    if (height < dt + db) { dt = height * dt / (dt + db); db = height - dt; }
    const std::array<double, 4> sourceX{static_cast<double>(sx), static_cast<double>(sx) + left,
                                       static_cast<double>(sx) + sw - right, static_cast<double>(sx) + sw};
    const std::array<double, 4> sourceY{static_cast<double>(sy), static_cast<double>(sy) + top,
                                       static_cast<double>(sy) + sh - bottom, static_cast<double>(sy) + sh};
    const std::array<double, 4> destX{0, dl, width - dr, static_cast<double>(width)};
    const std::array<double, 4> destY{0, dt, height - db, static_cast<double>(height)};
    struct Part { Rectangle source, destination; };
    std::array<Part, 9> parts;
    for (size_t row = 0; row < 3; ++row) for (size_t col = 0; col < 3; ++col) {
        auto & part = parts[row * 3 + col];
        part.source = {static_cast<float>(sourceX[col]), static_cast<float>(sourceY[row]),
                       static_cast<float>(sourceX[col + 1] - sourceX[col]), static_cast<float>(sourceY[row + 1] - sourceY[row])};
        if (target) {
            part.source.y = texture.height - part.source.y - part.source.height;
            part.source.height = -part.source.height;
        }
        part.destination = {static_cast<float>(destX[col]), static_cast<float>(destY[row]),
                            static_cast<float>(destX[col + 1] - destX[col]), static_cast<float>(destY[row + 1] - destY[row])};
    }
    // A single panel transform preserves slice offsets even with large compensating
    // positions/pivots. Logical slices also avoid native NPatch's FBO UV and int casts.
    return [=] {
        rlPushMatrix();
        rlTranslatef(static_cast<float>(x), static_cast<float>(y), 0);
        rlRotatef(rotation, 0, 0, 1);
        rlTranslatef(-origin.x, -origin.y, 0);
        for (const auto & part : parts)
            if (part.destination.width > 0 && part.destination.height > 0 && part.source.width > 0 && part.source.height != 0)
                DrawTexturePro(texture, part.source, part.destination, {}, 0, tint);
        rlPopMatrix();
    };
}

} // namespace nixray
