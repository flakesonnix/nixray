#include "assets.hh"
#include "reader.hh"
#include "render_texture.hh"

#include <set>
#include <limits>

namespace nixray {

namespace {

TextureOptions textureOptions(const Reader & r, Value & value)
{
    TextureOptions options;
    options.filter = TEXTURE_FILTER_POINT;
    if (auto * filter = r.optional(value, "filter")) {
        auto name = r.string(*filter);
        if (name == "point") options.filter = TEXTURE_FILTER_POINT;
        else if (name == "bilinear") options.filter = TEXTURE_FILTER_BILINEAR;
        else r.fail("unknown texture filter '" + name + "'");
    }
    if (auto * wrap = r.optional(value, "wrap")) {
        auto name = r.string(*wrap);
        if (name == "clamp") options.wrap = TEXTURE_WRAP_CLAMP;
        else if (name == "repeat") options.wrap = TEXTURE_WRAP_REPEAT;
        else if (name == "mirrorRepeat") options.wrap = TEXTURE_WRAP_MIRROR_REPEAT;
        else r.fail("unknown texture wrap '" + name + "'");
    }
    return options;
}

void applyTextureOptions(Texture2D texture, const TextureOptions & options)
{
    if (options.filter) SetTextureFilter(texture, *options.filter);
    if (options.wrap) SetTextureWrap(texture, *options.wrap);
}

} // namespace

AssetSpecs assetSpecs(EvalState & state, PosIdx pos, Value * value)
{
    if (!value) return {};
    Reader r(state, pos);
    r.fields(*value, {"textures", "fonts", "renderTextures", "shaders", "sounds", "music", "models"});
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
        TextureSpec texture;
        if (entry.type() == nAttrs) {
            r.fields(entry, {"path", "image", "filter", "wrap"});
            auto * sourceImage = r.optional(entry, "image");
            if (sourceImage) {
                if (r.optional(entry, "path")) r.fail("texture asset requires exactly one of 'path' or 'image'");
                texture.image = imageValue(state, pos, *sourceImage);
            } else texture.path = path(r.required(entry, "path"));
            texture.options = textureOptions(r, entry);
        } else texture.path = path(entry);
        specs.textures.emplace(std::move(name), std::move(texture));
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
    entries("renderTextures", [&](std::string name, Value & entry) {
        r.fields(entry, {"width", "height", "filter", "wrap"});
        TextureSize size{r.integer(r.required(entry, "width"), "width", 1, 16384),
                         r.integer(r.required(entry, "height"), "height", 1, 16384), textureOptions(r, entry)};
        specs.renderTextures.emplace(std::move(name), size);
    });
    // The texture command resolves both groups in one namespace.
    for (const auto & [name, size] : specs.renderTextures)
        if (specs.textures.count(name)) r.fail("asset name '" + name + "' is declared more than once");
    entries("shaders", [&](std::string name, Value & entry) {
        r.fields(entry, {"fragment", "uniforms"});
        ShaderSpec spec{path(r.required(entry, "fragment")), uniformSpecs(state, pos, r.optional(entry, "uniforms"))};
        specs.shaders.emplace(std::move(name), std::move(spec));
    });
    entries("sounds", [&](std::string name, Value & entry) {
        specs.sounds.emplace(std::move(name), path(entry));
    });
    entries("models", [&](std::string name, Value & entry) {
        ModelSpec model;
        if (entry.type() == nAttrs) {
            r.fields(entry, {"path", "animations"});
            model.path = path(r.required(entry, "path"));
            if (auto * animations = r.optional(entry, "animations")) model.animations = path(*animations);
        } else model.path = path(entry);
        specs.models.emplace(std::move(name), std::move(model));
    });
    entries("music", [&](std::string name, Value & entry) {
        MusicSpec music;
        if (entry.type() == nAttrs) {
            r.fields(entry, {"path", "looping"});
            music.path = path(r.required(entry, "path"));
            music.looping = r.defaultBool(entry, "looping", true);
        } else music.path = path(entry);
        specs.music.emplace(std::move(name), std::move(music));
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

void Assets::RenderTextureDeleter::operator()(RenderTexture2D * target) const
{
    if (target->id) UnloadRenderTexture(*target);
    delete target;
}

void Assets::SoundDeleter::operator()(Sound * sound) const
{
    if (sound->stream.buffer) UnloadSound(*sound);
    delete sound;
}

void Assets::MusicDeleter::operator()(Music * music) const
{
    if (music->ctxData || music->stream.buffer) UnloadMusicStream(*music);
    delete music;
}

Assets::Assets(const AssetSpecs & specs, const Reader & r)
{
    for (const auto & [name, spec] : specs.textures) {
        std::unique_ptr<Texture2D, TextureDeleter> texture(new Texture2D{});
        *texture = spec.image ? LoadTextureFromImage(spec.image->value) : LoadTexture(spec.path.c_str());
        if (!IsTextureValid(*texture)) r.fail(spec.image ? "could not upload image texture '" + name + "'"
                                                       : "could not load texture '" + name + "' from '" + spec.path + "'");
        applyTextureOptions(*texture, spec.options);
        textureOptions.emplace(name, spec.options);
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
    for (const auto & [name, spec] : specs.renderTextures) {
        std::unique_ptr<RenderTexture2D, RenderTextureDeleter> target(new RenderTexture2D{});
        *target = LoadRenderTexture(spec.width, spec.height);
        if (!IsRenderTextureValid(*target)) r.fail("could not create render texture '" + name + "'");
        // Framebuffer contents start undefined; stamps must never read stale pixels.
        initializeRenderTexture(*target);
        applyTextureOptions(target->texture, spec.options);
        textureOptions.emplace(name, spec.options);
        renderTextures.emplace(name, std::move(target));
    }
    for (const auto & [name, spec] : specs.shaders)
        shaders.emplace(name, loadShaderAsset(spec, name, r));
    for (const auto & [name, path] : specs.sounds) {
        std::unique_ptr<Sound, SoundDeleter> sound(new Sound{});
        *sound = LoadSound(path.c_str());
        if (!IsSoundValid(*sound)) r.fail("could not load sound '" + name + "' from '" + path + "'");
        sounds.emplace(name, std::move(sound));
        soundLabels.push_back(name);
    }
    for (const auto & [name, spec] : specs.music) {
        std::unique_ptr<Music, MusicDeleter> music(new Music{});
        *music = LoadMusicStream(spec.path.c_str());
        if (!IsMusicValid(*music) || !music->stream.buffer)
            r.fail("could not load music '" + name + "' from '" + spec.path + "'");
        // Native playback-time queries use signed int frame arithmetic.
        if (music->frameCount > static_cast<unsigned>(std::numeric_limits<int>::max()))
            r.fail("music frame count must fit signed 32-bit native coordinates");
        music->looping = spec.looping;
        for (const char * extension : {".wav", ".ogg", ".mp3", ".flac", ".qoa"})
            if (IsFileExtension(spec.path.c_str(), extension)) seekableMusic.insert(name);
        musicTracks.emplace(name, std::move(music));
        musicLabels.push_back(name);
    }
    for (const auto & [name, spec] : specs.models) {
        models.emplace(name, loadModelAsset(spec, name, r));
        modelLabels.push_back(name);
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

const RenderTexture2D * Assets::renderTexture(const std::string & name) const
{
    auto found = renderTextures.find(name);
    return found == renderTextures.end() ? nullptr : found->second.get();
}

const ShaderAsset * Assets::shader(const std::string & name) const
{
    auto found = shaders.find(name);
    return found == shaders.end() ? nullptr : found->second.get();
}

bool Assets::textureRepeats(const std::string & name) const
{
    auto found = textureOptions.find(name);
    return found != textureOptions.end() && found->second.repeats();
}

const Sound * Assets::sound(const std::string & name) const
{
    auto found = sounds.find(name);
    return found == sounds.end() ? nullptr : found->second.get();
}

const Music * Assets::music(const std::string & name) const
{
    auto found = musicTracks.find(name);
    return found == musicTracks.end() ? nullptr : found->second.get();
}

bool Assets::musicCanSeek(const std::string & name) const
{
    return seekableMusic.count(name);
}

void Assets::updateMusic() const
{
    for (const auto & [name, track] : musicTracks) UpdateMusicStream(*track);
}

const ModelAsset * Assets::model(const std::string & name) const
{
    auto found = models.find(name);
    return found == models.end() ? nullptr : found->second.get();
}

const LightingShader & Assets::lighting(const Reader & r) const
{
    if (!lightingProgram) lightingProgram = loadLightingShader(r);
    return *lightingProgram;
}

} // namespace nixray
