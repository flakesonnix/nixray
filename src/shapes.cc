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

struct Arc {
    float start, end;
    int segments;
};

Arc arcSpec(const Reader & r, Value & value, float radius)
{
    // Check cross-field constraints before float rounding can conceal a violation.
    double start = r.numberDouble(r.required(value, "startAngle"), "startAngle");
    double end = r.numberDouble(r.required(value, "endAngle"), "endAngle");
    if (end < start) std::swap(start, end);
    double sweep = end - start;
    if (sweep > 360.0) r.fail("arc angle span must not exceed 360 degrees");
    start = std::fmod(start, 360.0);
    if (start < 0) start += 360.0;
    Arc arc{static_cast<float>(start), static_cast<float>(start + sweep), 0};
    if (auto * count = r.optional(value, "segments")) arc.segments = r.integer(*count, "segments", 0, maxSegments);
    // Never enter raylib's unsafe automatic path, even with a small explicit count.
    int minimum = std::max(1, static_cast<int>(std::ceil((arc.end - arc.start) / 90.0f)));
    if (!arc.segments) {
        double count = std::ceil(cornerSegments(radius, false) * 4.0 * sweep / 360.0);
        arc.segments = static_cast<int>(std::clamp(count, static_cast<double>(minimum), static_cast<double>(maxSegments)));
    } else arc.segments = std::max(arc.segments, minimum);
    return arc;
}

} // namespace

Command shapeCommand(EvalState & state, PosIdx pos, Value & value, const std::string & op)
{
    Reader r(state, pos);
    if (op == "lineEx") {
        r.fields(value, {"op", "x1", "y1", "x2", "y2", "thickness", "color"});
        Vector2 start{static_cast<float>(r.integerAttr(value, "x1")), static_cast<float>(r.integerAttr(value, "y1"))};
        Vector2 end{static_cast<float>(r.integerAttr(value, "x2")), static_cast<float>(r.integerAttr(value, "y2"))};
        float thickness = r.number(r.required(value, "thickness"), "thickness", 0);
        auto color = r.color(r.required(value, "color"));
        return [=] { DrawLineEx(start, end, thickness, color); };
    }
    if (op == "rectangleGradientV" || op == "rectangleGradientH" || op == "rectangleGradientEx") {
        if (op == "rectangleGradientV") r.fields(value, {"op", "x", "y", "width", "height", "top", "bottom"});
        else if (op == "rectangleGradientH") r.fields(value, {"op", "x", "y", "width", "height", "left", "right"});
        else r.fields(value, {"op", "x", "y", "width", "height", "topLeft", "bottomLeft", "bottomRight", "topRight"});
        Rectangle rec{static_cast<float>(r.integerAttr(value, "x")), static_cast<float>(r.integerAttr(value, "y")),
                      static_cast<float>(r.integerAttr(value, "width", 0)), static_cast<float>(r.integerAttr(value, "height", 0))};
        Color topLeft, bottomLeft, bottomRight, topRight;
        if (op == "rectangleGradientV") {
            topLeft = topRight = r.color(r.required(value, "top"));
            bottomLeft = bottomRight = r.color(r.required(value, "bottom"));
        } else if (op == "rectangleGradientH") {
            topLeft = bottomLeft = r.color(r.required(value, "left"));
            topRight = bottomRight = r.color(r.required(value, "right"));
        } else {
            topLeft = r.color(r.required(value, "topLeft"));
            bottomLeft = r.color(r.required(value, "bottomLeft"));
            bottomRight = r.color(r.required(value, "bottomRight"));
            topRight = r.color(r.required(value, "topRight"));
        }
        return [=] {
            if (rec.width == 0 || rec.height == 0) return;
            DrawRectangleGradientEx(rec, topLeft, bottomLeft, bottomRight, topRight);
        };
    }
    if (op == "circleGradient") {
        r.fields(value, {"op", "x", "y", "radius", "inner", "outer"});
        int x = r.integerAttr(value, "x"), y = r.integerAttr(value, "y");
        float radius = r.number(r.required(value, "radius"), "radius", 0);
        auto inner = r.color(r.required(value, "inner")), outer = r.color(r.required(value, "outer"));
        return [=] { if (radius > 0) DrawCircleGradient(x, y, radius, inner, outer); };
    }
    if (op == "circleSector" || op == "circleSectorLines" || op == "ring" || op == "ringLines") {
        bool ring = op == "ring" || op == "ringLines";
        if (ring) r.fields(value, {"op", "x", "y", "innerRadius", "outerRadius", "startAngle", "endAngle", "segments", "color"});
        else r.fields(value, {"op", "x", "y", "radius", "startAngle", "endAngle", "segments", "color"});
        Vector2 center{static_cast<float>(r.integerAttr(value, "x")), static_cast<float>(r.integerAttr(value, "y"))};
        double inner = ring ? r.numberDouble(r.required(value, "innerRadius"), "innerRadius", 0) : 0;
        double outer = r.numberDouble(r.required(value, ring ? "outerRadius" : "radius"), ring ? "outerRadius" : "radius", 0);
        if (inner > outer) r.fail("innerRadius must not exceed outerRadius");
        float innerRadius = static_cast<float>(inner), outerRadius = static_cast<float>(outer);
        auto arc = arcSpec(r, value, outerRadius);
        auto color = r.color(r.required(value, "color"));
        return [=] {
            if (outerRadius == 0 || innerRadius == outerRadius || arc.start == arc.end) return;
            if (op == "ring") DrawRing(center, innerRadius, outerRadius, arc.start, arc.end, arc.segments, color);
            else if (op == "ringLines") DrawRingLines(center, innerRadius, outerRadius, arc.start, arc.end, arc.segments, color);
            else if (op == "circleSectorLines") DrawCircleSectorLines(center, outerRadius, arc.start, arc.end, arc.segments, color);
            else DrawCircleSector(center, outerRadius, arc.start, arc.end, arc.segments, color);
        };
    }
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
