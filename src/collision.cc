#include "collision.hh"
#include "reader.hh"

#include <cmath>
#include <limits>

namespace nixray {

namespace {

void finiteArithmetic(const Reader & r, std::initializer_list<float> values)
{
    for (float value : values)
        if (!std::isfinite(value)) r.fail("collision arithmetic must remain finite");
}

Vector2 point(const Reader & r, Value & value)
{
    r.fields(value, {"x", "y"});
    return {r.number(r.required(value, "x"), "x"), r.number(r.required(value, "y"), "y")};
}

Rectangle rectangle(const Reader & r, Value & value)
{
    r.fields(value, {"x", "y", "width", "height"});
    Rectangle rec{r.number(r.required(value, "x"), "x"), r.number(r.required(value, "y"), "y"),
                  r.number(r.required(value, "width"), "width", 0),
                  r.number(r.required(value, "height"), "height", 0)};
    finiteArithmetic(r, {rec.x + rec.width, rec.y + rec.height});
    return rec;
}

struct Circle {
    Vector2 center;
    float radius;
};

Circle circle(const Reader & r, Value & value)
{
    r.fields(value, {"x", "y", "radius"});
    Circle result{{r.number(r.required(value, "x"), "x"), r.number(r.required(value, "y"), "y")},
                  r.number(r.required(value, "radius"), "radius", 0)};
    finiteArithmetic(r, {result.radius * result.radius});
    return result;
}

void finiteDistance(const Reader & r, Vector2 a, Vector2 b)
{
    float dx = a.x - b.x, dy = a.y - b.y;
    finiteArithmetic(r, {dx * dx + dy * dy});
}

struct Segment {
    Vector2 start, end;
};

Segment segment(const Reader & r, Value & value)
{
    r.fields(value, {"x1", "y1", "x2", "y2"});
    return {{r.number(r.required(value, "x1"), "x1"), r.number(r.required(value, "y1"), "y1")},
            {r.number(r.required(value, "x2"), "x2"), r.number(r.required(value, "y2"), "y2")}};
}

void pointResult(EvalState & state, Vector2 point, Value & out)
{
    auto result = state.buildBindings(2);
    result.alloc("x").mkFloat(point.x);
    result.alloc("y").mkFloat(point.y);
    out.mkAttrs(result);
}

} // namespace

void checkCollisionRecs(EvalState & state, PosIdx pos, Value ** args, Value & out)
{
    Reader r(state, pos);
    auto a = rectangle(r, *args[0]), b = rectangle(r, *args[1]);
    out.mkBool(CheckCollisionRecs(a, b));
}

void checkCollisionCircles(EvalState & state, PosIdx pos, Value ** args, Value & out)
{
    Reader r(state, pos);
    auto a = circle(r, *args[0]), b = circle(r, *args[1]);
    finiteDistance(r, a.center, b.center);
    float radiusSum = a.radius + b.radius;
    finiteArithmetic(r, {radiusSum * radiusSum});
    out.mkBool(CheckCollisionCircles(a.center, a.radius, b.center, b.radius));
}

void checkCollisionCircleRec(EvalState & state, PosIdx pos, Value ** args, Value & out)
{
    Reader r(state, pos);
    auto c = circle(r, *args[0]);
    auto rec = rectangle(r, *args[1]);
    float halfWidth = rec.width / 2.0f, halfHeight = rec.height / 2.0f;
    float dx = std::abs(c.center.x - (rec.x + halfWidth));
    float dy = std::abs(c.center.y - (rec.y + halfHeight));
    finiteArithmetic(r, {dx, dy, halfWidth + c.radius, halfHeight + c.radius});
    // raylib only squares corner distances after its axis-aligned early exits.
    if (dx <= halfWidth + c.radius && dy <= halfHeight + c.radius && dx > halfWidth && dy > halfHeight) {
        float cornerX = dx - halfWidth, cornerY = dy - halfHeight;
        finiteArithmetic(r, {cornerX * cornerX + cornerY * cornerY});
    }
    out.mkBool(CheckCollisionCircleRec(c.center, c.radius, rec));
}

void checkCollisionPointRec(EvalState & state, PosIdx pos, Value ** args, Value & out)
{
    Reader r(state, pos);
    auto p = point(r, *args[0]);
    auto rec = rectangle(r, *args[1]);
    out.mkBool(CheckCollisionPointRec(p, rec));
}

void checkCollisionPointCircle(EvalState & state, PosIdx pos, Value ** args, Value & out)
{
    Reader r(state, pos);
    auto p = point(r, *args[0]);
    auto c = circle(r, *args[1]);
    finiteDistance(r, p, c.center);
    out.mkBool(CheckCollisionPointCircle(p, c.center, c.radius));
}

void checkCollisionLines(EvalState & state, PosIdx pos, Value ** args, Value & out)
{
    Reader r(state, pos);
    auto a = segment(r, *args[0]), b = segment(r, *args[1]);
    float dx1 = a.end.x - a.start.x, dy1 = a.end.y - a.start.y;
    float dx2 = b.end.x - b.start.x, dy2 = b.end.y - b.start.y;
    float div = dy2 * dx1 - dx2 * dy1;
    finiteArithmetic(r, {dx1, dy1, dx2, dy2, div});
    if (std::abs(div) < std::numeric_limits<float>::epsilon()) {
        out.mkNull();
        return;
    }
    // Guard the native cubic numerators as well as the determinant: a finite
    // result alone cannot rule out inf/inf or finite/inf false intersections.
    float cross1 = a.start.x * a.end.y - a.start.y * a.end.x;
    float cross2 = b.start.x * b.end.y - b.start.y * b.end.x;
    float numeratorX = -dx2 * cross1 + dx1 * cross2;
    float numeratorY = -dy2 * cross1 + dy1 * cross2;
    finiteArithmetic(r, {cross1, cross2, numeratorX, numeratorY, numeratorX / div, numeratorY / div});
    Vector2 intersection{};
    if (!CheckCollisionLines(a.start, a.end, b.start, b.end, &intersection)) out.mkNull();
    else {
        finiteArithmetic(r, {intersection.x, intersection.y});
        pointResult(state, intersection, out);
    }
}

void getCollisionRec(EvalState & state, PosIdx pos, Value ** args, Value & out)
{
    Reader r(state, pos);
    auto a = rectangle(r, *args[0]), b = rectangle(r, *args[1]);
    auto overlap = GetCollisionRec(a, b);
    finiteArithmetic(r, {overlap.x, overlap.y, overlap.width, overlap.height});
    auto result = state.buildBindings(4);
    result.alloc("x").mkFloat(overlap.x);
    result.alloc("y").mkFloat(overlap.y);
    result.alloc("width").mkFloat(overlap.width);
    result.alloc("height").mkFloat(overlap.height);
    out.mkAttrs(result);
}

} // namespace nixray
