#include "assets.hh"
#include "reader.hh"

#include <set>

namespace nixray {

AssetSpecs assetSpecs(EvalState & state, PosIdx pos, Value * value)
{
    if (!value) return {};
    Reader r(state, pos);
    r.fields(*value, {"textures", "fonts"});
    auto path = [&](Value & entry) {
        state.forceValue(entry, pos);
        if (entry.type() == nString) {
            auto text = state.forceString(entry, pos, context);
            if (text.empty() || text.front() != '/' || text.find('\0') != std::string_view::npos)
                r.fail("asset paths must be Nix paths or absolute strings without NUL bytes");
        } else if (entry.type() != nPath) {
            r.fail("asset paths must be Nix paths or absolute strings");
        }
        // Preserve and realise Nix string contexts (including derivation outputs).
        auto local = state.realisePath(pos, entry).getPhysicalPath();
        if (!local) r.fail("asset paths must refer to local files");
        auto physical = local->string();
        if (physical.find('\0') != std::string::npos) r.fail("asset paths must not contain NUL bytes");
        return physical;
    };
    auto entries = [&](const char * group, auto consume) {
        auto * groupValue = r.optional(*value, group);
        if (!groupValue) return;
        state.forceAttrs(*groupValue, pos, context);
        for (const auto & attr : *groupValue->attrs()) {
            std::string name(state.symbols[attr.name]);
            if (name.empty() || name.find('\0') != std::string::npos)
                r.fail("asset names must be nonempty and contain no NUL bytes");
            state.forceValue(*attr.value, pos);
            consume(std::move(name), *attr.value);
        }
    };
    AssetSpecs specs;
    entries("textures", [&](std::string name, Value & entry) {
        specs.textures.emplace(std::move(name), path(entry));
    });
    entries("fonts", [&](std::string name, Value & entry) {
        FontSpec font;
        if (entry.type() == nAttrs) {
            r.fields(entry, {"path", "size", "codepoints"});
            font.path = path(r.required(entry, "path"));
            if (auto * size = r.optional(entry, "size")) {
                font.size = r.integer(*size, "font size", 1, 512);
                font.customized = true;
            }
            if (auto * codepoints = r.optional(entry, "codepoints")) {
                state.forceList(*codepoints, pos, context);
                if (!codepoints->listSize() || codepoints->listSize() > 4096)
                    r.fail("font codepoints must contain between 1 and 4096 Unicode scalars");
                std::set<int> seen;
                for (auto * item : codepoints->listView()) {
                    int codepoint = r.integer(*item, "font codepoint", 1, 0x10ffff);
                    if (codepoint >= 0xd800 && codepoint <= 0xdfff)
                        r.fail("font codepoints must be Unicode scalars, not surrogates");
                    if (!seen.insert(codepoint).second) r.fail("font codepoints must not contain duplicates");
                    font.codepoints.push_back(codepoint);
                }
                font.customized = true;
            }
            if (font.customized && !IsFileExtension(font.path.c_str(), ".ttf") &&
                !IsFileExtension(font.path.c_str(), ".otf"))
                r.fail("font size and codepoints require a .ttf or .otf font");
        } else font.path = path(entry);
        specs.fonts.emplace(std::move(name), std::move(font));
    });
    return specs;
}

void Assets::TextureDeleter::operator()(Texture2D * texture) const
{
    if (texture->id) UnloadTexture(*texture);
    delete texture;
}

void Assets::FontDeleter::operator()(Font * font) const
{
    // LoadFont silently returns the shared default font on failure. Never own it.
    if (font->texture.id != GetFontDefault().texture.id &&
        (font->texture.id || font->glyphs || font->recs)) UnloadFont(*font);
    delete font;
}

Assets::Assets(const AssetSpecs & specs, const Reader & r)
{
    for (const auto & [name, path] : specs.textures) {
        std::unique_ptr<Texture2D, TextureDeleter> texture(new Texture2D{});
        *texture = LoadTexture(path.c_str());
        if (!IsTextureValid(*texture)) r.fail("could not load texture '" + name + "' from '" + path + "'");
        textures.emplace(name, std::move(texture));
    }
    for (const auto & [name, spec] : specs.fonts) {
        std::unique_ptr<Font, FontDeleter> font(new Font{});
        // raylib's API takes a mutable pointer but does not modify this list.
        auto codepoints = spec.codepoints;
        *font = spec.customized
            ? LoadFontEx(spec.path.c_str(), spec.size, codepoints.empty() ? nullptr : codepoints.data(),
                         codepoints.empty() ? 0 : static_cast<int>(codepoints.size()))
            : LoadFont(spec.path.c_str());
        if (!IsFontValid(*font) || !IsTextureValid(font->texture) ||
            font->texture.id == GetFontDefault().texture.id)
            r.fail("could not load font '" + name + "' from '" + spec.path + "'");
        fonts.emplace(name, std::move(font));
    }
}

const Texture2D * Assets::texture(const std::string & name) const
{
    auto found = textures.find(name);
    return found == textures.end() ? nullptr : found->second.get();
}

const Font * Assets::font(const std::string & name) const
{
    auto found = fonts.find(name);
    return found == fonts.end() ? nullptr : found->second.get();
}

} // namespace nixray
