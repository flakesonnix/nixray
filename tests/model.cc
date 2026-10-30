// Test-only native ownership audit. Rendering/loading still use real raylib.
#include <raylib.h>
#include <rlgl.h>
#include <cstdio>
#include <cstdlib>
#include <dlfcn.h>
#include <set>

namespace {
int models = 0, animations = 0;
std::set<unsigned> importedTextures;
template<typename F> F original(const char * name)
{
    auto f = reinterpret_cast<F>(dlsym(RTLD_NEXT, name));
    if (!f) std::abort();
    return f;
}
void trace(const char * event)
{
    if (auto * path = std::getenv("NIXRAY_TEST_MODEL_TRACE")) if (auto * file = std::fopen(path, "a")) {
        std::fprintf(file, "%s\n", event); std::fclose(file);
    }
}
}

extern "C" Model LoadModel(const char * path)
{
    auto model = original<Model (*)(const char *)>("LoadModel")(path);
    ++models; trace("load-model");
    if (model.materials) for (int i = 0; i < model.materialCount; ++i) if (model.materials[i].maps)
        for (int j = 0; j <= MATERIAL_MAP_BRDF; ++j) {
            auto id = model.materials[i].maps[j].texture.id;
            if (id && id != rlGetTextureIdDefault()) importedTextures.insert(id);
        }
    return model;
}
extern "C" void UnloadModel(Model model)
{
    --models; trace("unload-model");
    original<void (*)(Model)>("UnloadModel")(model);
}
extern "C" ModelAnimation * LoadModelAnimations(const char * path, int * count)
{
    auto * data = original<ModelAnimation * (*)(const char *, int *)>("LoadModelAnimations")(path, count);
    if (data) { ++animations; trace("load-animations"); }
    return data;
}
extern "C" void UnloadModelAnimations(ModelAnimation * data, int count)
{
    --animations; trace("unload-animations");
    original<void (*)(ModelAnimation *, int)>("UnloadModelAnimations")(data, count);
}
extern "C" void UnloadTexture(Texture2D texture)
{
    if (importedTextures.erase(texture.id)) trace("unload-imported-texture");
    original<void (*)(Texture2D)>("UnloadTexture")(texture);
}
extern "C" void CloseWindow()
{
    if (models || animations || !importedTextures.empty()) {
        std::fputs("nixray model fixture: native resources survived until window close\n", stderr); std::abort();
    }
    trace("close");
    original<void (*)()>("CloseWindow")();
}
