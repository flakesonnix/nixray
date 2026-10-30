#include "texture.hh"
#include "assets.hh"
#include "reader.hh"

#include <raymath.h>
#include <rlgl.h>
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <limits>

namespace nixray {

namespace {

Vector3 point(const Reader & r, Value & value)
{
    r.fields(value, {"x", "y", "z"});
    return {r.number(r.required(value, "x"), "x"), r.number(r.required(value, "y"), "y"), r.number(r.required(value, "z"), "z")};
}

Vector3 finite(const Reader & r, Vector3 v)
{
    if (!std::isfinite(v.x) || !std::isfinite(v.y) || !std::isfinite(v.z))
        r.fail("billboard geometry must remain finite");
    return v;
}

Vector3 nativeUnit(const Reader & r, Vector3 v)
{
    float length = Vector3Length(v);
    if (!std::isfinite(length) || length == 0) r.fail("billboard basis must be finite and nondegenerate");
    auto result = Vector3Normalize(v);
    float unitLength = Vector3Length(result);
    if (!std::isfinite(unitLength) || std::abs(unitLength - 1) > 0.001f)
        r.fail("billboard basis must be finite and nondegenerate");
    return result;
}

} // namespace

Command billboardCommand(EvalState & state, PosIdx pos, Value & value, Camera3D camera,
                          const Assets * assets, const std::string * activeTexture)
{
    Reader r(state, pos);
    r.fields(value, {"op", "texture", "position", "height", "width", "source", "up", "origin", "rotation", "tint", "flipX", "flipY"});
    auto name = r.string(r.required(value, "texture"));
    if (name.empty()) r.fail("texture name must not be empty");
    if (activeTexture && *activeTexture == name) r.fail("cannot stamp texture '" + name + "' into its own paint");
    auto position = point(r, r.required(value, "position"));
    float height = r.number(r.required(value, "height"), "height", 0);
    auto * widthValue = r.optional(value, "width");
    float width = widthValue ? r.number(*widthValue, "width", 0) : 0;
    Vector3 up{0, 1, 0};
    if (auto * v = r.optional(value, "up")) up = point(r, *v);
    double length = std::hypot(static_cast<double>(up.x), static_cast<double>(up.y), static_cast<double>(up.z));
    if (length == 0) r.fail("billboard up must be nonzero");
    up = {static_cast<float>(up.x/length), static_cast<float>(up.y/length), static_cast<float>(up.z/length)};
    auto view = GetCameraMatrix(camera);
    auto right = nativeUnit(r, {view.m0, view.m4, view.m8});
    auto forward = nativeUnit(r, Vector3CrossProduct(right, up));
    double angle = 0;
    if (auto * v = r.optional(value, "rotation")) angle = r.numberDouble(*v, "rotation");
    float rotation = static_cast<float>(std::fmod(angle, 360.0));
    auto * tintValue = r.optional(value, "tint");
    auto tint = tintValue ? r.color(*tintValue) : WHITE;
    bool flipX = r.defaultBool(value, "flipX", false), flipY = r.defaultBool(value, "flipY", false);

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
    if (assets && !assets->textureRepeats(name) && (static_cast<int64_t>(sx) + sw > texture.width ||
                                                  static_cast<int64_t>(sy) + sh > texture.height))
        r.fail("source rectangle exceeds texture '" + name + "'");
    if (!widthValue && (source || assets)) {
        double derived = static_cast<double>(height)*sw/sh;
        if (!std::isfinite(derived) || derived > std::numeric_limits<float>::max())
            r.fail("billboard aspect-derived width must remain finite");
        width = static_cast<float>(derived);
    }
    Vector2 origin{width/2, height/2};
    if (auto * v = r.optional(value, "origin")) {
        r.fields(*v, {"x", "y"});
        origin = {r.number(r.required(*v, "x"), "origin.x"), r.number(r.required(*v, "y"), "origin.y")};
    }
    // Pure validation uses width=0 when neither an explicit width nor source
    // aspect is known. A real run resolves all dimensions before any effects.
    auto origin3D = finite(r, Vector3Add(Vector3Scale(right, origin.x), Vector3Scale(up, origin.y)));
    right = finite(r, Vector3Scale(right, width));
    up = finite(r, Vector3Scale(up, height));
    std::array<Vector3, 4> points{{{}, right, finite(r, Vector3Add(up, right)), up}};
    for (auto & p : points) {
        p = finite(r, Vector3Subtract(p, origin3D));
        if (rotation != 0) p = finite(r, Vector3RotateByAxisAngle(p, forward, rotation*DEG2RAD));
        p = finite(r, Vector3Add(p, position));
    }
    if (!assets) return [] {};

    float left = static_cast<double>(sx)/texture.width, rightU = (static_cast<double>(sx) + sw)/texture.width;
    float top = static_cast<double>(sy)/texture.height, bottom = (static_cast<double>(sy) + sh)/texture.height;
    if (target) {
        top = (static_cast<double>(texture.height) - sy)/texture.height;
        bottom = (static_cast<double>(texture.height) - sy - sh)/texture.height;
    }
    if (flipX) std::swap(left, rightU);
    if (flipY) std::swap(top, bottom);
    std::array<Vector2, 4> uv{{{left, bottom}, {rightU, bottom}, {rightU, top}, {left, top}}};
    return [=] {
        if (width == 0 || height == 0) return;
        // The native billboard is a textured quad in this same vertex order.
        // Prepared UVs keep flips independent of geometry/winding, including FBOs.
        rlSetTexture(texture.id);
        rlBegin(RL_QUADS);
        rlColor4ub(tint.r, tint.g, tint.b, tint.a);
        for (size_t i = 0; i < points.size(); ++i) {
            rlTexCoord2f(uv[i].x, uv[i].y);
            rlVertex3f(points[i].x, points[i].y, points[i].z);
        }
        rlEnd();
        rlSetTexture(0);
    };
}

} // namespace nixray
