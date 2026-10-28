#include "shapes.hh"
#include "reader.hh"

#include <algorithm>
#include <cmath>
#include <numbers>

namespace nixray {

namespace {

constexpr int maxSegments = 4096;

int cornerSegments(float radius, bool outline)
{
    if (radius <= 0.5f) return 4;
    // Use doubles and an explicit bound rather than raylib's automatic path:
    // very small/large radii can otherwise convert NaN/infinity to an integer.
    double angle = 2 * std::acos(1 - 0.5 / static_cast<double>(radius));
    double count = std::ceil(2 * std::numbers::pi / angle / (outline ? 2 : 4));
    return static_cast<int>(std::clamp(count, 4.0, static_cast<double>(maxSegments)));
}

} // namespace

Command shapeCommand(EvalState & state, PosIdx pos, Value & value, const std::string & op)
{
    Reader r(state, pos);
    if (op == "triangle" || op == "triangleLines") {
        r.fields(value, {"op", "x1", "y1", "x2", "y2", "x3", "y3", "color"});
        auto vertex = [&](const char * x, const char * y) {
            return Vector2{static_cast<float>(r.integerAttr(value, x)), static_cast<float>(r.integerAttr(value, y))};
        };
        auto a = vertex("x1", "y1"), b = vertex("x2", "y2"), c = vertex("x3", "y3");
        auto color = r.color(r.required(value, "color"));
        // Compute using the actual float vertices, without signed integer overflow.
        double area = (static_cast<double>(b.x) - a.x) * (static_cast<double>(c.y) - a.y) -
                      (static_cast<double>(b.y) - a.y) * (static_cast<double>(c.x) - a.x);
        if (area == 0) return [] {};
        // Raylib's filled triangles require counter-clockwise screen vertices.
        if (area > 0) std::swap(b, c);
        bool outline = op == "triangleLines";
        return [=] {
            if (outline) DrawTriangleLines(a, b, c, color);
            else DrawTriangle(a, b, c, color);
        };
    }
    if (op == "ellipse" || op == "ellipseLines") {
        r.fields(value, {"op", "x", "y", "radiusX", "radiusY", "color"});
        int x = r.integerAttr(value, "x"), y = r.integerAttr(value, "y");
        float radiusX = r.number(r.required(value, "radiusX"), "radiusX", 0);
        float radiusY = r.number(r.required(value, "radiusY"), "radiusY", 0);
        auto color = r.color(r.required(value, "color"));
        bool outline = op == "ellipseLines";
        return [=] {
            if (radiusX == 0 || radiusY == 0) return;
            if (outline) DrawEllipseLines(x, y, radiusX, radiusY, color);
            else DrawEllipse(x, y, radiusX, radiusY, color);
        };
    }
    if (op == "rectangleRounded" || op == "rectangleRoundedLines") {
        r.fields(value, {"op", "x", "y", "width", "height", "roundness", "segments", "color"});
        Rectangle rectangle{static_cast<float>(r.integerAttr(value, "x")),
                            static_cast<float>(r.integerAttr(value, "y")),
                            static_cast<float>(r.integerAttr(value, "width", 0)),
                            static_cast<float>(r.integerAttr(value, "height", 0))};
        float roundness = r.number(r.required(value, "roundness"), "roundness", 0, 1);
        int segments = 0;
        if (auto * count = r.optional(value, "segments")) segments = r.integer(*count, "segments", 0, maxSegments);
        if (segments > 0 && segments < 4) r.fail("'segments' must be 0 (automatic) or an integer in [4, 4096]");
        auto color = r.color(r.required(value, "color"));
        bool outline = op == "rectangleRoundedLines";
        float radius = std::min(rectangle.width, rectangle.height) * roundness / 2;
        if (radius == 0) roundness = 0;
        if (!segments) segments = cornerSegments(radius, outline);
        return [=] {
            if (rectangle.width == 0 || rectangle.height == 0) return;
            if (outline) DrawRectangleRoundedLines(rectangle, roundness, segments, color);
            else DrawRectangleRounded(rectangle, roundness, segments, color);
        };
    }
    r.fail("unknown shape operation '" + op + "'");
}

} // namespace nixray
