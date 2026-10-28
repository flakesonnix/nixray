#include "text.hh"
#include "assets.hh"
#include "reader.hh"

#include <nix/expr/eval-gc.hh>
#include <algorithm>
#include <ostream>

namespace nixray {

namespace {

struct TextOptions {
    std::string text;
    std::string font;
    int size;
};

TextOptions textOptions(const Reader & r, Value & value)
{
    TextOptions options{r.string(r.required(value, "text")), "", r.integerAttr(value, "size", 1)};
    if (options.text.size() > std::numeric_limits<int>::max()) r.fail("text is too long for raylib");
    if (auto * font = r.optional(value, "font")) {
        options.font = r.string(*font);
        if (options.font.empty()) r.fail("font name must not be empty");
    }
    return options;
}

// Retain no atlas, glyph image or pointers into Assets. Nix closures can outlive
// their window, and a new window may load entirely different fonts.
struct FontMetrics {
    int baseSize;
    std::vector<GlyphInfo> glyphs;
    std::vector<Rectangle> rectangles;

    explicit FontMetrics(const Font & font) : baseSize(font.baseSize), rectangles(font.recs, font.recs + font.glyphCount)
    {
        glyphs.reserve(font.glyphCount);
        for (int i = 0; i < font.glyphCount; ++i) {
            GlyphInfo glyph{};
            glyph.value = font.glyphs[i].value;
            glyph.offsetX = font.glyphs[i].offsetX;
            glyph.advanceX = font.glyphs[i].advanceX;
            glyphs.push_back(glyph);
        }
    }

    Font view() const
    {
        Font font{};
        font.baseSize = baseSize;
        font.glyphCount = static_cast<int>(glyphs.size());
        // MeasureTextEx checks only that the id is nonzero; it never uses GL.
        font.texture.id = 1;
        font.glyphs = const_cast<GlyphInfo *>(glyphs.data());
        font.recs = const_cast<Rectangle *>(rectangles.data());
        return font;
    }
};

class TextMetrics final : public ExternalValueBase, public gc_cleanup {
public:
    FontMetrics defaultFont{GetFontDefault()};
    std::map<std::string, FontMetrics> fonts;

    std::string showType() const override { return "nixray font metrics"; }
    std::string typeOf() const override { return "nixray-font-metrics"; }
    std::ostream & print(std::ostream & stream) const override { return stream << "<nixray font metrics>"; }
};

PrimOp measureOp{
    .name = "nixray.measureText",
    .args = {"metrics", "options"},
    .arity = 2,
    .doc = "Measure text using an immutable snapshot of a window's font metrics.",
    .impl = [](EvalState & state, PosIdx pos, Value ** args, Value & out) {
        Reader r(state, pos);
        r.fields(*args[1], {"text", "size", "font"});
        auto options = textOptions(r, *args[1]);
        const auto & metrics = *static_cast<const TextMetrics *>(args[0]->external());
        auto * font = &metrics.defaultFont;
        if (!options.font.empty()) {
            auto found = metrics.fonts.find(options.font);
            if (found == metrics.fonts.end()) r.fail("unknown font '" + options.font + "'");
            font = &found->second;
        }
        // Match DrawText's minimum size/integer spacing and DrawTextEx's fixed
        // custom-font spacing, rather than measuring with different defaults.
        int size = options.font.empty() ? std::max(options.size, 10) : options.size;
        float spacing = options.font.empty() ? static_cast<float>(size / 10) : 1.0f;
        auto measured = MeasureTextEx(font->view(), options.text.c_str(), static_cast<float>(size), spacing);
        if (!std::isfinite(measured.x) || !std::isfinite(measured.y)) r.fail("text dimensions must be finite");
        auto result = state.buildBindings(2);
        // Raylib reports negative spacing for strings containing only newlines.
        result.alloc("width").mkFloat(std::max(measured.x, 0.0f));
        result.alloc("height").mkFloat(measured.y);
        out.mkAttrs(result);
    },
    .experimentalFeature = std::nullopt,
};

} // namespace

Command textCommand(EvalState & state, PosIdx pos, Value & value, const Assets * assets)
{
    Reader r(state, pos);
    r.fields(value, {"op", "text", "x", "y", "size", "color", "font"});
    auto options = textOptions(r, value);
    int x = r.integerAttr(value, "x"), y = r.integerAttr(value, "y");
    auto color = r.color(r.required(value, "color"));
    Font font{};
    if (!options.font.empty() && assets) {
        auto * found = assets->font(options.font);
        if (!found) r.fail("unknown font '" + options.font + "'");
        font = *found;
    }
    return [=] {
        if (!options.font.empty()) DrawTextEx(font, options.text.c_str(), {static_cast<float>(x), static_cast<float>(y)},
                                             static_cast<float>(options.size), 1.0f, color);
        else DrawText(options.text.c_str(), x, y, options.size, color);
    };
}

Value * textMeasurer(EvalState & state, const Assets & assets, const AssetSpecs & specs)
{
    auto * value = state.allocValue();
    auto * metrics = new TextMetrics;
    value->mkExternal(metrics);
    for (const auto & [name, _] : specs.fonts) metrics->fonts.emplace(name, FontMetrics(*assets.font(name)));
    auto * function = state.allocValue();
    function->mkPrimOp(&measureOp);
    auto * result = state.allocValue();
    result->mkPrimOpApp(function, value);
    return result;
}

} // namespace nixray
