#include "assets.hh"
#include "reader.hh"

namespace nixray {

AssetSpecs assetSpecs(EvalState & state, PosIdx pos, Value * value)
{
    if (!value) return {};
    Reader r(state, pos);
    r.fields(*value, {"textures", "fonts"});
    auto paths = [&](const char * group) {
        std::map<std::string, std::string> result;
        auto * entries = r.optional(*value, group);
        if (!entries) return result;
        state.forceAttrs(*entries, pos, context);
        for (const auto & attr : *entries->attrs()) {
            std::string name(state.symbols[attr.name]);
            if (name.empty() || name.find('\0') != std::string::npos)
                r.fail("asset names must be nonempty and contain no NUL bytes");
            state.forceValue(*attr.value, pos);
            if (attr.value->type() == nString) {
                auto text = state.forceString(*attr.value, pos, context);
                if (text.empty() || text.front() != '/' || text.find('\0') != std::string_view::npos)
                    r.fail("asset paths must be Nix paths or absolute strings without NUL bytes");
            } else if (attr.value->type() != nPath) {
                r.fail("asset paths must be Nix paths or absolute strings");
            }
            // Preserve and realise Nix string contexts (including derivation outputs).
            auto path = state.realisePath(pos, *attr.value).getPhysicalPath();
            if (!path) r.fail("asset paths must refer to local files");
            auto physical = path->string();
            if (physical.find('\0') != std::string::npos) r.fail("asset paths must not contain NUL bytes");
            result.emplace(std::move(name), std::move(physical));
        }
        return result;
    };
    return {paths("textures"), paths("fonts")};
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
    for (const auto & [name, path] : specs.fonts) {
        std::unique_ptr<Font, FontDeleter> font(new Font{});
        *font = LoadFont(path.c_str());
        if (!IsFontValid(*font) || !IsTextureValid(font->texture) ||
            font->texture.id == GetFontDefault().texture.id)
            r.fail("could not load font '" + name + "' from '" + path + "'");
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
