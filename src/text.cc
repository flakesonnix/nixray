#include "text.hh"
#include "assets.hh"
#include "reader.hh"

#include <nix/expr/eval-gc.hh>
#include <raymath.h>
#include <rlgl.h>
#include <algorithm>
#include <optional>
#include <ostream>

namespace nixray {

namespace {

enum class TextSource { string, codepoint, codepoints };

struct TextOptions {
    TextSource source = TextSource::string;
    std::string text;
    std::string font;
    std::vector<int> codepoints;
    int size = 0;
    float spacing = 0;
};

int scalar(const Reader & r, Value & value)
{
    int cp = r.integer(value, "codepoint", 0, 0x10ffff);
    if (cp >= 0xd800 && cp <= 0xdfff) r.fail("codepoints must be Unicode scalars, not surrogates");
    return cp;
}

TextOptions textOptions(EvalState & state, PosIdx pos, const Reader & r, Value & value,
                        std::optional<TextSource> expected = std::nullopt)
{
    TextOptions options;
    auto * text = r.optional(value, "text"), * cp = r.optional(value, "codepoint"), * cps = r.optional(value, "codepoints");
    if (static_cast<int>(text != nullptr) + (cp != nullptr) + (cps != nullptr) > 1)
        r.fail("provide exactly one of text, codepoint or codepoints");
    options.source = expected.value_or(cp ? TextSource::codepoint : cps ? TextSource::codepoints : TextSource::string);
    if (options.source == TextSource::string) {
        options.text = r.string(r.required(value, "text"));
        if (options.text.size() > std::numeric_limits<int>::max()) r.fail("text is too long for raylib");
    } else if (options.source == TextSource::codepoint) options.codepoints.push_back(scalar(r, r.required(value, "codepoint")));
    else {
        auto & points = r.required(value, "codepoints");
        state.forceList(points, pos, context);
        if (points.listSize() > 4096) r.fail("codepoints must contain at most 4096 Unicode scalars");
        options.codepoints.reserve(points.listSize());
        for (auto * point : points.listView()) options.codepoints.push_back(scalar(r, *point));
    }
    options.size = r.integerAttr(value, "size", 1);
    if (auto * font = r.optional(value, "font")) {
        options.font = r.string(*font);
        if (options.font.empty()) r.fail("font name must not be empty");
    }
    if (options.font.empty()) options.size = std::max(options.size, 10);
    options.spacing = options.font.empty() ? static_cast<float>(options.size/10) : 1;
    if (auto * spacing = r.optional(value, "spacing")) options.spacing = r.number(*spacing, "spacing");
    return options;
}

template<typename Visit> void eachCodepoint(const TextOptions & options, Visit visit)
{
    if (options.source != TextSource::string) { for (int cp : options.codepoints) visit(cp); return; }
    for (size_t i = 0; i < options.text.size();) {
        int bytes = 0;
        int cp = GetCodepointNext(options.text.c_str() + i, &bytes);
        visit(cp);
        i += std::max(bytes, 1);
    }
}

float lineGap(Font font)
{
    // There is no native getter. Snapshot the linked renderer's line gap while
    // the font/window exists, without making retained measurement query globals.
    return MeasureTextEx(font, "\n", 10, 0).y - 20;
}

struct TextTransform {
    Vector2 position{}, origin{};
    float rotation = 0;
    Matrix matrix{};
    bool transformed = false;
};

TextTransform textTransform(const Reader & r, Value & value, Vector2 position)
{
    TextTransform result;
    result.position = position;
    if (auto * origin = r.optional(value, "origin")) {
        r.fields(*origin, {"x", "y"});
        result.origin = {r.number(r.required(*origin, "x"), "origin.x"), r.number(r.required(*origin, "y"), "origin.y")};
    }
    double angle = 0;
    if (auto * rotation = r.optional(value, "rotation")) angle = r.numberDouble(*rotation, "rotation");
    result.rotation = static_cast<float>(std::fmod(angle, 360.0));
    if (std::hypot(static_cast<double>(result.origin.x), static_cast<double>(result.origin.y)) > std::numeric_limits<float>::max())
        r.fail("text transform bounds must remain finite");
    result.transformed = result.rotation != 0 || result.origin.x != 0 || result.origin.y != 0;
    result.matrix = MatrixMultiply(MatrixMultiply(MatrixTranslate(-result.origin.x, -result.origin.y, 0),
                                   MatrixRotateZ(result.rotation*DEG2RAD)), MatrixTranslate(position.x, position.y, 0));
    for (float v : MatrixToFloatV(result.matrix).v) if (!std::isfinite(v)) r.fail("text transform bounds must remain finite");
    return result;
}

Vector2 analyseText(const Reader & r, Font font, const TextOptions & options, float gap, const TextTransform * transform = nullptr)
{
    if (font.baseSize < 1 || font.glyphCount < 1 || !font.glyphs || !font.recs) r.fail("font metrics are unavailable");
    if (options.source == TextSource::string ? options.text.empty() : options.codepoints.empty()) return {};
    float size = static_cast<float>(options.size), scale = size/font.baseSize;
    float penX = 0, penY = 0, width = 0, maximumWidth = 0, height = size;
    int count = 0, maximumCount = 0;
    bool literal = options.source == TextSource::codepoint;
    eachCodepoint(options, [&](int cp) {
        ++count;
        int index = GetGlyphIndex(font, cp);
        const auto & glyph = font.glyphs[index];
        const auto & rec = font.recs[index];
        if (!literal && cp == '\n') {
            maximumWidth = std::max(maximumWidth, width);
            width = 0; count = 0; penX = 0;
            penY += size + gap; height += size + gap;
        } else {
            // Match MeasureTextEx's logical advances, including its separate
            // maximum line-width/count rule. These are not glyph ink bounds.
            width += glyph.advanceX > 0 ? static_cast<float>(glyph.advanceX) : rec.width + glyph.offsetX;
            if (transform && (literal || (cp != ' ' && cp != '\t'))) {
                Vector2 position = transform->transformed ? Vector2{} : transform->position;
                float x = position.x + penX + glyph.offsetX*scale - font.glyphPadding*scale;
                float y = position.y + penY + glyph.offsetY*scale - font.glyphPadding*scale;
                float w = (rec.width + 2.0f*font.glyphPadding)*scale;
                float h = (rec.height + 2.0f*font.glyphPadding)*scale;
                for (int i = 0; i < 4; ++i) {
                    Vector2 point{x + (i & 1 ? w : 0), y + (i & 2 ? h : 0)};
                    if (!std::isfinite(point.x) || !std::isfinite(point.y)) r.fail("text layout bounds must remain finite");
                    if (transform->transformed) point = Vector2Transform(point, transform->matrix);
                    if (!std::isfinite(point.x) || !std::isfinite(point.y)) r.fail("text transform bounds must remain finite");
                }
            }
            penX += (glyph.advanceX == 0 ? rec.width : static_cast<float>(glyph.advanceX))*scale + options.spacing;
        }
        maximumCount = std::max(maximumCount, count);
        if (!std::isfinite(penX) || !std::isfinite(penY) || !std::isfinite(width) || !std::isfinite(height))
            r.fail("text layout must remain finite");
    });
    maximumWidth = std::max(maximumWidth, width);
    Vector2 result{maximumWidth*scale + static_cast<float>(maximumCount - 1)*options.spacing, height};
    if (!std::isfinite(result.x) || !std::isfinite(result.y)) r.fail("text dimensions must be finite");
    result.x = std::max(result.x, 0.0f);
    return result;
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
        // Native glyph lookup needs a nonzero atlas id but never queries GL.
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
    float gap = lineGap(GetFontDefault());

    std::string showType() const override { return "nixray font metrics"; }
    std::string typeOf() const override { return "nixray-font-metrics"; }
    std::ostream & print(std::ostream & stream) const override { return stream << "<nixray font metrics>"; }
};

PrimOp measureOp{
    .name = "nixray.measureText",
    .args = {"metrics", "options"},
    .arity = 2,
    .doc = "Measure text using immutable font metrics and line spacing; return unrotated logical dimensions.",
    .impl = [](EvalState & state, PosIdx pos, Value ** args, Value & out) {
        Reader r(state, pos);
        r.fields(*args[1], {"text", "codepoint", "codepoints", "size", "font", "spacing"});
        auto options = textOptions(state, pos, r, *args[1]);
        const auto & metrics = *static_cast<const TextMetrics *>(args[0]->external());
        auto * font = &metrics.defaultFont;
        if (!options.font.empty()) {
            auto found = metrics.fonts.find(options.font);
            if (found == metrics.fonts.end()) r.fail("unknown font '" + options.font + "'");
            font = &found->second;
        }
        auto measured = analyseText(r, font->view(), options, metrics.gap);
        auto result = state.buildBindings(2);
        result.alloc("width").mkFloat(measured.x);
        result.alloc("height").mkFloat(measured.y);
        out.mkAttrs(result);
    },
    .experimentalFeature = std::nullopt,
};

} // namespace

Command textCommand(EvalState & state, PosIdx pos, Value & value, const std::string & op, const Assets * assets)
{
    Reader r(state, pos);
    TextSource source = op == "textCodepoint" ? TextSource::codepoint : op == "textCodepoints" ? TextSource::codepoints : TextSource::string;
    const char * field = source == TextSource::codepoint ? "codepoint" : source == TextSource::codepoints ? "codepoints" : "text";
    r.fields(value, {"op", field, "x", "y", "size", "color", "font", "spacing", "rotation", "origin"});
    auto options = textOptions(state, pos, r, value, source);
    int x = r.integerAttr(value, "x"), y = r.integerAttr(value, "y");
    auto transform = textTransform(r, value, {static_cast<float>(x), static_cast<float>(y)});
    auto color = r.color(r.required(value, "color"));
    Font font{};
    if (assets) {
        font = GetFontDefault();
        if (!options.font.empty()) {
            auto * found = assets->font(options.font);
            if (!found) r.fail("unknown font '" + options.font + "'");
            font = *found;
        }
        analyseText(r, font, options, lineGap(font), &transform);
    }
    return [=] {
        Vector2 position = transform.position;
        if (transform.transformed) {
            rlPushMatrix();
            rlTranslatef(position.x, position.y, 0);
            rlRotatef(transform.rotation, 0, 0, 1);
            rlTranslatef(-transform.origin.x, -transform.origin.y, 0);
            position = {};
        }
        if (source == TextSource::codepoint) DrawTextCodepoint(font, options.codepoints[0], position, options.size, color);
        else if (source == TextSource::codepoints) DrawTextCodepoints(font, options.codepoints.data(), options.codepoints.size(), position, options.size, options.spacing, color);
        else DrawTextEx(font, options.text.c_str(), position, options.size, options.spacing, color);
        if (transform.transformed) rlPopMatrix();
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
