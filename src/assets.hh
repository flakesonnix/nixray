#pragma once

#include <nix/expr/eval.hh>
#include "shader.hh"
#include "model.hh"
#include "lighting.hh"
#include "image.hh"
#include <raylib.h>
#include <map>
#include <memory>
#include <optional>
#include <string>
#include <set>
#include <vector>

namespace nixray {

class Reader;

struct FontSpec {
    std::string path;
    int size = 32;
    std::vector<int> codepoints;
    bool customized = false;
};

struct TextureOptions {
    std::optional<int> filter, wrap;
    bool repeats() const { return wrap && *wrap != TEXTURE_WRAP_CLAMP; }
};

struct TextureSpec {
    std::string path;
    std::shared_ptr<const ImageData> image;
    TextureOptions options;
};

struct TextureSize {
    int width, height;
    TextureOptions options;
};

struct MusicSpec {
    std::string path;
    bool looping = true;
};

struct AssetSpecs {
    std::map<std::string, TextureSpec> textures;
    std::map<std::string, FontSpec> fonts;
    std::map<std::string, TextureSize> renderTextures;
    std::map<std::string, ShaderSpec> shaders;
    std::map<std::string, std::string> sounds;
    std::map<std::string, MusicSpec> music;
    std::map<std::string, ModelSpec> models;
};

AssetSpecs assetSpecs(nix::EvalState & state, nix::PosIdx pos, nix::Value * value);

// Own native resources, never evaluator Values. Window/audio device outlive this.
class Assets {
    struct TextureDeleter { void operator()(Texture2D * texture) const; };
    struct FontDeleter { void operator()(Font * font) const; };
    struct RenderTextureDeleter { void operator()(RenderTexture2D * target) const; };
    struct SoundDeleter { void operator()(Sound * sound) const; };
    struct MusicDeleter { void operator()(Music * music) const; };
    std::map<std::string, std::unique_ptr<Texture2D, TextureDeleter>> textures;
    std::map<std::string, std::unique_ptr<Font, FontDeleter>> fonts;
    std::map<std::string, std::unique_ptr<RenderTexture2D, RenderTextureDeleter>> renderTextures;
    std::map<std::string, TextureOptions> textureOptions;
    std::map<std::string, std::unique_ptr<ShaderAsset>> shaders;
    std::map<std::string, std::unique_ptr<Sound, SoundDeleter>> sounds;
    std::map<std::string, std::unique_ptr<Music, MusicDeleter>> musicTracks;
    std::set<std::string> seekableMusic;
    std::vector<std::string> soundLabels, musicLabels;
    mutable std::unique_ptr<LightingShader> lightingProgram;
    std::map<std::string, std::unique_ptr<ModelAsset>> models;
    std::vector<std::string> modelLabels;

public:
    Assets(const AssetSpecs & specs, const Reader & reader);
    Assets(const Assets &) = delete;
    Assets & operator=(const Assets &) = delete;

    const Texture2D * texture(const std::string & name) const;
    const Font * font(const std::string & name) const;
    const RenderTexture2D * renderTexture(const std::string & name) const;
    bool textureRepeats(const std::string & name) const;
    const ShaderAsset * shader(const std::string & name) const;
    const Sound * sound(const std::string & name) const;
    const Music * music(const std::string & name) const;
    bool musicCanSeek(const std::string & name) const;
    const std::vector<std::string> & soundNames() const { return soundLabels; }
    const std::vector<std::string> & musicNames() const { return musicLabels; }
    void updateMusic() const;
    const ModelAsset * model(const std::string & name) const;
    const std::vector<std::string> & modelNames() const { return modelLabels; }
    const LightingShader & lighting(const Reader & reader) const;
};

} // namespace nixray
