#include "commands.hh"
#include "assets.hh"
#include "reader.hh"

namespace nixray {

// Parse every command before BeginDrawing: evaluation errors cannot leave an
// unfinished drawing batch, and command execution never re-enters the evaluator.
std::vector<Command> commands(EvalState & state, PosIdx pos, Value & value, const Assets * assets)
{
    Reader r(state, pos);
    state.forceList(value, pos, context);
    std::vector<Command> result;
    result.reserve(value.listSize());
    auto values = value.listView();
    for (auto * entry : values) {
        auto op = r.string(r.required(*entry, "op"));
        if (op == "clear") {
            r.fields(*entry, {"op", "color"});
            auto color = r.color(r.required(*entry, "color"));
            result.emplace_back([=] { ClearBackground(color); });
        } else if (op == "texture") {
            r.fields(*entry, {"op", "texture", "x", "y", "tint"});
            auto name = r.string(r.required(*entry, "texture"));
            if (name.empty()) r.fail("texture name must not be empty");
            int x = r.integerAttr(*entry, "x"), y = r.integerAttr(*entry, "y");
            auto * tintValue = r.optional(*entry, "tint");
            auto tint = tintValue ? r.color(*tintValue) : WHITE;
            Texture2D texture{};
            if (assets) {
                auto * found = assets->texture(name);
                if (!found) r.fail("unknown texture '" + name + "'");
                texture = *found;
            }
            result.emplace_back([=] { DrawTexture(texture, x, y, tint); });
        } else if (op == "text") {
            r.fields(*entry, {"op", "text", "x", "y", "size", "color", "font"});
            auto text = r.string(r.required(*entry, "text"));
            int x = r.integerAttr(*entry, "x"), y = r.integerAttr(*entry, "y");
            int size = r.integerAttr(*entry, "size", 1);
            auto color = r.color(r.required(*entry, "color"));
            auto * fontValue = r.optional(*entry, "font");
            bool customFont = fontValue != nullptr;
            Font font{};
            if (customFont) {
                auto name = r.string(*fontValue);
                if (name.empty()) r.fail("font name must not be empty");
                if (assets) {
                    auto * found = assets->font(name);
                    if (!found) r.fail("unknown font '" + name + "'");
                    font = *found;
                }
            }
            result.emplace_back([=] {
                if (customFont) DrawTextEx(font, text.c_str(), {static_cast<float>(x), static_cast<float>(y)},
                                           static_cast<float>(size), 1.0f, color);
                else DrawText(text.c_str(), x, y, size, color);
            });
        } else if (op == "rectangle" || op == "rectangleLines") {
            r.fields(*entry, {"op", "x", "y", "width", "height", "color"});
            int x = r.integerAttr(*entry, "x"), y = r.integerAttr(*entry, "y");
            int w = r.integerAttr(*entry, "width", 0), h = r.integerAttr(*entry, "height", 0);
            auto color = r.color(r.required(*entry, "color"));
            result.emplace_back([=] {
                if (op == "rectangle") DrawRectangle(x, y, w, h, color);
                else DrawRectangleLines(x, y, w, h, color);
            });
        } else if (op == "circle" || op == "circleLines") {
            r.fields(*entry, {"op", "x", "y", "radius", "color"});
            int x = r.integerAttr(*entry, "x"), y = r.integerAttr(*entry, "y");
            float radius = r.number(r.required(*entry, "radius"), "radius", 0);
            auto color = r.color(r.required(*entry, "color"));
            result.emplace_back([=] {
                if (op == "circle") DrawCircle(x, y, radius, color);
                else DrawCircleLines(x, y, radius, color);
            });
        } else if (op == "line") {
            r.fields(*entry, {"op", "x1", "y1", "x2", "y2", "color"});
            int x1 = r.integerAttr(*entry, "x1"), y1 = r.integerAttr(*entry, "y1");
            int x2 = r.integerAttr(*entry, "x2"), y2 = r.integerAttr(*entry, "y2");
            auto color = r.color(r.required(*entry, "color"));
            result.emplace_back([=] { DrawLine(x1, y1, x2, y2, color); });
        } else if (op == "pixel") {
            r.fields(*entry, {"op", "x", "y", "color"});
            int x = r.integerAttr(*entry, "x"), y = r.integerAttr(*entry, "y");
            auto color = r.color(r.required(*entry, "color"));
            result.emplace_back([=] { DrawPixel(x, y, color); });
        } else if (op == "fps") {
            r.fields(*entry, {"op", "x", "y"});
            int x = r.integerAttr(*entry, "x"), y = r.integerAttr(*entry, "y");
            result.emplace_back([=] { DrawFPS(x, y); });
        } else {
            r.fail("unknown drawing operation '" + op + "'");
        }
    }
    return result;
}

} // namespace nixray
