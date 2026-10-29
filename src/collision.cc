#include "collision.hh"
#include "reader.hh"

#include <array>
#include <cmath>
#include <limits>
#include <vector>

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

Segment segment(const Reader & r, Value & value, bool allowThreshold = false)
{
    if (allowThreshold) r.fields(value, {"x1", "y1", "x2", "y2", "threshold"});
    else r.fields(value, {"x1", "y1", "x2", "y2"});
    return {{r.number(r.required(value, "x1"), "x1"), r.number(r.required(value, "y1"), "y1")},
            {r.number(r.required(value, "x2"), "x2"), r.number(r.required(value, "y2"), "y2")}};
}

std::array<Vector2, 3> triangle(const Reader & r, Value & value)
{
    r.fields(value, {"x1", "y1", "x2", "y2", "x3", "y3"});
    return {{{r.number(r.required(value, "x1"), "x1"), r.number(r.required(value, "y1"), "y1")},
             {r.number(r.required(value, "x2"), "x2"), r.number(r.required(value, "y2"), "y2")},
             {r.number(r.required(value, "x3"), "x3"), r.number(r.required(value, "y3"), "y3")}}};
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

void checkCollisionPointTriangle(EvalState & state, PosIdx pos, Value ** args, Value & out)
{
    Reader r(state, pos);
    auto p = point(r, *args[0]);
    auto [a, b, c] = triangle(r, *args[1]);
    float ay = b.y - c.y, ax = c.x - b.x;
    float by = a.x - c.x, bx = c.y - a.y;
    float dx = p.x - c.x, dy = p.y - c.y;
    float div = ay * (a.x - c.x) + ax * (a.y - c.y);
    float numeratorA = ay * dx + ax * dy, numeratorB = bx * dx + by * dy;
    finiteArithmetic(r, {ay, ax, by, bx, dx, dy, a.x - c.x, a.y - c.y, div, numeratorA, numeratorB});
    // Native zero-area triangles cannot have three positive barycentric weights.
    if (div == 0.0f) {
        out.mkBool(false);
        return;
    }
    float alpha = numeratorA / div, beta = numeratorB / div;
    finiteArithmetic(r, {alpha, beta, 1.0f - alpha - beta});
    out.mkBool(CheckCollisionPointTriangle(p, a, b, c));
}

void checkCollisionPointPoly(EvalState & state, PosIdx pos, Value ** args, Value & out)
{
    Reader r(state, pos);
    auto p = point(r, *args[0]);
    state.forceList(*args[1], pos, context);
    if (args[1]->listSize() > static_cast<size_t>(std::numeric_limits<int>::max()))
        r.fail("polygon point count must fit a signed 32-bit integer");
    std::vector<Vector2> points;
    points.reserve(args[1]->listSize());
    for (auto * entry : args[1]->listView()) points.push_back(point(r, *entry));
    if (points.size() > 2) {
        for (size_t i = 0, j = points.size() - 1; i < points.size(); j = i++) {
            // Only straddling edges reach native division; horizontal edges do not.
            if ((points[i].y > p.y) != (points[j].y > p.y)) {
                float dx = points[j].x - points[i].x, dy = points[j].y - points[i].y;
                float offset = p.y - points[i].y;
                float product = dx * offset, crossing = product / dy;
                finiteArithmetic(r, {dx, dy, offset, product, crossing, crossing + points[i].x});
            }
        }
    }
    out.mkBool(CheckCollisionPointPoly(p, points.data(), static_cast<int>(points.size())));
}

void checkCollisionPointLine(EvalState & state, PosIdx pos, Value ** args, Value & out)
{
    Reader r(state, pos);
    auto p = point(r, *args[0]);
    auto line = segment(r, *args[1], true);
    int threshold = r.defaultInt(*args[1], "threshold", 1);
    float dx = p.x - line.start.x, dy = p.y - line.start.y;
    float lx = line.end.x - line.start.x, ly = line.end.y - line.start.y;
    finiteArithmetic(r, {dx, dy, lx, ly, dx * ly - dy * lx,
                         threshold * std::fmax(std::abs(lx), std::abs(ly))});
    out.mkBool(CheckCollisionPointLine(p, line.start, line.end, threshold));
}

void checkCollisionCircleLine(EvalState & state, PosIdx pos, Value ** args, Value & out)
{
    Reader r(state, pos);
    auto c = circle(r, *args[0]);
    auto line = segment(r, *args[1]);
    float dx = line.start.x - line.end.x, dy = line.start.y - line.end.y;
    float span = std::abs(dx) + std::abs(dy);
    finiteArithmetic(r, {dx, dy, span});
    if (span <= std::numeric_limits<float>::epsilon()) finiteDistance(r, line.start, c.center);
    else {
        float lengthSquared = dx * dx + dy * dy;
        float cx = c.center.x - line.start.x, cy = c.center.y - line.start.y;
        float numerator = cx * (line.end.x - line.start.x) + cy * (line.end.y - line.start.y);
        finiteArithmetic(r, {lengthSquared, cx, cy, numerator});
        float projection = numerator / lengthSquared;
        finiteArithmetic(r, {projection});
        if (projection > 1.0f) projection = 1.0f;
        else if (projection < 0.0f) projection = 0.0f;
        float closestX = line.start.x - projection * dx, closestY = line.start.y - projection * dy;
        float distanceX = closestX - c.center.x, distanceY = closestY - c.center.y;
        finiteArithmetic(r, {closestX, closestY, distanceX, distanceY, distanceX * distanceX + distanceY * distanceY});
    }
    out.mkBool(CheckCollisionCircleLine(c.center, c.radius, line.start, line.end));
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
