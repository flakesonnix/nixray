#include "model.hh"
#include "reader.hh"
#include "assets.hh"

#include <raymath.h>
#include <rlgl.h>
#include <algorithm>
#include <charconv>
#include <cmath>
#include <cstring>
#include <fstream>
#include <optional>
#include <set>
#include <sstream>
#include <utility>

namespace nixray {

namespace {

bool objHasNormals(const std::string & path)
{
    // raylib's OBJ loader allocates normals even when they were absent and
    // substitutes (0,1,0). Pointers alone cannot distinguish authored normals.
    std::ifstream input(path);
    if (!input) return false;
    bool normal = false, face = false;
    for (std::string line; std::getline(input, line);) {
        std::istringstream fields(line);
        std::string kind;
        fields >> kind;
        if (kind == "vn") normal = true;
        if (kind != "f") continue;
        face = true;
        for (std::string vertex; fields >> vertex;) {
            if (vertex.starts_with('#')) break;
            if (vertex == "\\") continue;
            auto first = vertex.find('/'), last = vertex.rfind('/');
            if (first == std::string::npos || first == last) return false;
            std::string_view index(vertex.data() + last + 1, vertex.size() - last - 1);
            if (index.starts_with('+')) index.remove_prefix(1);
            int number = 0;
            auto parsed = std::from_chars(index.data(), index.data() + index.size(), number);
            if (parsed.ec != std::errc{} || parsed.ptr != index.data() + index.size() || number == 0) return false;
        }
    }
    return input.eof() && normal && face;
}

bool finite(Matrix m)
{
    for (float x : MatrixToFloatV(m).v) if (!std::isfinite(x)) return false;
    return true;
}

void matrix(const Reader & r, Matrix m)
{
    float determinant = MatrixDeterminant(m);
    if (!finite(m) || !std::isfinite(determinant) || determinant == 0 || !finite(MatrixInvert(m)))
        r.fail("model transform must be finite and invertible");
}

void numbers(const Reader & r, const float * values, size_t count)
{
    for (size_t i = 0; i < count; ++i) if (!std::isfinite(values[i])) r.fail("model data must remain finite");
}

Vector3 point(const Reader & r, Value & value)
{
    r.fields(value, {"x", "y", "z"});
    return {r.number(r.required(value, "x"), "x"), r.number(r.required(value, "y"), "y"), r.number(r.required(value, "z"), "z")};
}

BoundingBox transformedBounds(const Reader & r, BoundingBox box, Matrix transform)
{
    BoundingBox result{};
    for (int i = 0; i < 8; ++i) {
        Vector3 p = Vector3Transform({i & 1 ? box.max.x : box.min.x, i & 2 ? box.max.y : box.min.y,
                                      i & 4 ? box.max.z : box.min.z}, transform);
        if (!std::isfinite(p.x) || !std::isfinite(p.y) || !std::isfinite(p.z)) r.fail("model geometry bounds must remain finite");
        if (i == 0) result = {p, p};
        else {
            result.min = Vector3Min(result.min, p);
            result.max = Vector3Max(result.max, p);
        }
    }
    return result;
}

Matrix transform(const Reader & r, Transform t)
{
    float values[]{t.translation.x, t.translation.y, t.translation.z, t.rotation.x, t.rotation.y, t.rotation.z, t.rotation.w,
                   t.scale.x, t.scale.y, t.scale.z};
    numbers(r, values, 10);
    double norm = static_cast<double>(t.rotation.x)*t.rotation.x + static_cast<double>(t.rotation.y)*t.rotation.y +
                  static_cast<double>(t.rotation.z)*t.rotation.z + static_cast<double>(t.rotation.w)*t.rotation.w;
    if (norm == 0) r.fail("model rotation quaternion must be nonzero");
    auto m = MatrixMultiply(MatrixMultiply(MatrixScale(t.scale.x, t.scale.y, t.scale.z), QuaternionToMatrix(t.rotation)),
                            MatrixTranslate(t.translation.x, t.translation.y, t.translation.z));
    matrix(r, m);
    return m;
}

void pointValue(EvalState & state, Value & out, Vector3 p)
{
    auto v = state.buildBindings(3);
    v.alloc("x").mkFloat(p.x);
    v.alloc("y").mkFloat(p.y);
    v.alloc("z").mkFloat(p.z);
    out.mkAttrs(v);
}

} // namespace

ModelAsset::~ModelAsset()
{
    if (animations) UnloadModelAnimations(animations, animationCount);
    // UnloadModel frees material maps, but deliberately does NOT free their
    // textures. Imported assets own those textures; default/shared shaders do not.
    std::set<unsigned> seen;
    std::vector<Texture2D> textures;
    if (value.materials) for (int i = 0; i < value.materialCount; ++i) if (value.materials[i].maps)
        for (int j = 0; j <= MATERIAL_MAP_BRDF; ++j) {
            auto texture = value.materials[i].maps[j].texture;
            if (texture.id && texture.id != rlGetTextureIdDefault() && seen.insert(texture.id).second) textures.push_back(texture);
        }
    if (!value.meshes) value.meshCount = 0;
    if (!value.materials) value.materialCount = 0;
    UnloadModel(value);
    for (auto texture : textures) UnloadTexture(texture);
}

std::unique_ptr<ModelAsset> loadModelAsset(const ModelSpec & spec, const std::string & name, const Reader & r)
{
    if (!FileExists(spec.path.c_str())) r.fail("could not load model '" + name + "' from '" + spec.path + "'");
    auto asset = std::make_unique<ModelAsset>();
    auto & m = asset->value;
    m = LoadModel(spec.path.c_str());
    if (!m.meshes || !m.materials || !m.meshMaterial || m.meshCount < 1 || m.materialCount < 1)
        r.fail("could not load model '" + name + "' from '" + spec.path + "'");
    if (m.meshCount > 1024 || m.materialCount > 4096 || m.boneCount < 0 || m.boneCount > 256)
        r.fail("model exceeds mesh, material or bone limits");
    matrix(r, m.transform);
    for (int i = 0; i < m.materialCount; ++i) if (!m.materials[i].maps) r.fail("model material maps are missing");
    for (int i = 0; i < m.meshCount; ++i) {
        const auto & mesh = m.meshes[i];
        if (!mesh.normals) asset->hasVertexNormals = false;
        if (!mesh.vertices || !mesh.vboId || !mesh.vboId[0] || mesh.vertexCount < 1 || mesh.vertexCount > 1000000 ||
            mesh.triangleCount < 1 || mesh.triangleCount > 1000000 || m.meshMaterial[i] < 0 || m.meshMaterial[i] >= m.materialCount ||
            (mesh.normals && !mesh.vboId[2]) || (mesh.texcoords && !mesh.vboId[1]) || (mesh.indices && !mesh.vboId[6]))
            r.fail("model '" + name + "' contains invalid mesh data");
        if (mesh.boneMatrices && mesh.boneCount != m.boneCount) r.fail("model bone matrix counts do not match its skeleton");
        asset->vertexCount += mesh.vertexCount;
        asset->triangleCount += mesh.triangleCount;
        if (asset->vertexCount > 1000000 || asset->triangleCount > 1000000) r.fail("model exceeds vertex or triangle limits");
        numbers(r, mesh.vertices, static_cast<size_t>(mesh.vertexCount)*3);
        if (mesh.normals) numbers(r, mesh.normals, static_cast<size_t>(mesh.vertexCount)*3);
        if (mesh.texcoords) numbers(r, mesh.texcoords, static_cast<size_t>(mesh.vertexCount)*2);
        if (mesh.texcoords2) numbers(r, mesh.texcoords2, static_cast<size_t>(mesh.vertexCount)*2);
        if (mesh.tangents) numbers(r, mesh.tangents, static_cast<size_t>(mesh.vertexCount)*4);
        if (mesh.indices) {
            for (int j = 0; j < mesh.triangleCount*3; ++j) if (mesh.indices[j] >= mesh.vertexCount) r.fail("model mesh index is out of bounds");
        } else if (mesh.vertexCount != mesh.triangleCount*3) r.fail("model triangle counts do not match vertices");
        if (mesh.boneWeights || mesh.boneIds) {
            if (!mesh.boneWeights || !mesh.boneIds || !mesh.animVertices || !mesh.boneMatrices || mesh.boneCount != m.boneCount ||
                !m.boneCount || (mesh.normals && !mesh.animNormals)) r.fail("model contains incomplete skinning data");
            for (int v = 0; v < mesh.vertexCount; ++v) {
                float sum = 0;
                for (int j = 0; j < 4; ++j) {
                    float weight = mesh.boneWeights[v*4 + j];
                    if (!std::isfinite(weight) || weight < 0 || weight > 1 || mesh.boneIds[v*4 + j] >= m.boneCount)
                        r.fail("model contains invalid bone weights or indices");
                    sum += weight;
                }
                if (std::abs(sum - 1) > 0.0001f) r.fail("model bone weights must sum to one");
            }
        }
    }
    if (IsFileExtension(spec.path.c_str(), ".obj")) asset->hasVertexNormals &= objHasNormals(spec.path);
    asset->bounds = GetModelBoundingBox(m);
    transformedBounds(r, asset->bounds, m.transform);
    if (m.boneCount && (!m.bones || !m.bindPose)) r.fail("model skeleton is incomplete");
    std::vector<Matrix> bindInverse;
    for (int b = 0; b < m.boneCount; ++b) bindInverse.push_back(MatrixInvert(transform(r, m.bindPose[b])));
    if (!spec.animations.empty()) {
        if (!FileExists(spec.animations.c_str())) r.fail("could not load model animations for '" + name + "'");
        asset->animations = LoadModelAnimations(spec.animations.c_str(), &asset->animationCount);
        if (!asset->animations || asset->animationCount < 1) r.fail("could not load model animations for '" + name + "'");
        if (asset->animationCount > 256) r.fail("model exceeds animation limits");
        size_t poses = 0;
        for (int a = 0; a < asset->animationCount; ++a) {
            auto & anim = asset->animations[a];
            if (!m.boneCount || !anim.bones || !anim.framePoses || !IsModelAnimationValid(m, anim)) r.fail("model animation skeleton is incompatible");
            for (int b = 0; b < m.boneCount; ++b)
                if (std::strncmp(m.bones[b].name, anim.bones[b].name, sizeof(m.bones[b].name))) r.fail("model animation skeleton is incompatible");
            if (anim.frameCount < 1 || anim.frameCount > 65536) r.fail("model animation frame count is out of bounds");
            poses += static_cast<size_t>(anim.frameCount)*m.boneCount;
            if (poses > 1000000) r.fail("model exceeds animation pose limits");
            std::vector<BoundingBox> frames;
            for (int f = 0; f < anim.frameCount; ++f) {
                if (!anim.framePoses[f]) r.fail("model animation frame is missing");
                auto box = asset->bounds;
                for (int b = 0; b < m.boneCount; ++b) {
                    auto bone = MatrixMultiply(bindInverse[b], transform(r, anim.framePoses[f][b]));
                    matrix(r, bone);
                    auto moved = transformedBounds(r, asset->bounds, bone);
                    box.min = Vector3Min(box.min, moved.min);
                    box.max = Vector3Max(box.max, moved.max);
                }
                frames.push_back(box);
            }
            asset->poseBounds.push_back(std::move(frames));
        }
    }
    return asset;
}

Command modelCommand(EvalState & state, PosIdx pos, Value & value, const std::string & op, const Assets * assets, const Shader * shader)
{
    Reader r(state, pos);
    r.fields(value, {"op", "model", "position", "scale", "rotationAxis", "rotation", "tint", "pose"});
    auto name = r.string(r.required(value, "model"));
    if (name.empty()) r.fail("model name must not be empty");
    auto position = point(r, r.required(value, "position"));
    float scale = 1;
    if (auto * v = r.optional(value, "scale")) scale = r.number(*v, "scale", 0);
    if (scale == 0) r.fail("model scale must be positive");
    Vector3 axis{0, 1, 0};
    if (auto * v = r.optional(value, "rotationAxis")) axis = point(r, *v);
    double length = std::hypot(static_cast<double>(axis.x), static_cast<double>(axis.y), static_cast<double>(axis.z));
    if (length == 0) r.fail("model rotation axis must be nonzero");
    axis = {static_cast<float>(axis.x/length), static_cast<float>(axis.y/length), static_cast<float>(axis.z/length)};
    double angle = 0;
    if (auto * v = r.optional(value, "rotation")) angle = r.numberDouble(*v, "rotation");
    float rotation = static_cast<float>(std::fmod(angle, 360.0));
    auto tintValue = r.optional(value, "tint");
    auto tint = tintValue ? r.color(*tintValue) : WHITE;
    auto user = MatrixMultiply(MatrixMultiply(MatrixScale(scale, scale, scale), MatrixRotate(axis, rotation*DEG2RAD)),
                               MatrixTranslate(position.x, position.y, position.z));
    matrix(r, user);
    int animation = -1, frame = 0;
    if (auto * pose = r.optional(value, "pose")) {
        r.fields(*pose, {"animation", "frame"});
        animation = r.integerAttr(*pose, "animation", 0);
        frame = r.integerAttr(*pose, "frame", 0);
    }
    if (!assets) return [] {}; // Pure validation never loads or mutates resources.
    auto * asset = assets->model(name);
    if (!asset) r.fail("unknown model '" + name + "'");
    auto m = asset->value;
    auto box = asset->bounds;
    if (animation >= 0) {
        if (animation >= asset->animationCount || frame >= asset->animations[animation].frameCount) r.fail("model pose is out of bounds");
        box = asset->poseBounds[animation][frame];
    }
    auto combined = MatrixMultiply(m.transform, user);
    matrix(r, combined);
    transformedBounds(r, box, combined);
    std::optional<Shader> overrideShader = shader ? std::optional<Shader>(*shader) : std::nullopt;
    std::vector<Shader> originalShaders;
    for (int i = 0; i < m.materialCount; ++i) originalShaders.push_back(m.materials[i].shader);
    return [=] {
        rlDrawRenderBatchActive(); // Model VBO draws and pose uploads must follow queued primitives.
        if (m.boneCount) {
            if (animation >= 0) UpdateModelAnimation(m, asset->animations[animation], frame);
            else {
                Transform * bind = m.bindPose;
                ModelAnimation pose{};
                pose.boneCount = m.boneCount;
                pose.frameCount = 1;
                pose.bones = m.bones;
                pose.framePoses = &bind;
                UpdateModelAnimation(m, pose, 0);
            }
        }
        if (overrideShader) for (int i = 0; i < m.materialCount; ++i) m.materials[i].shader = *overrideShader;
        if (op == "modelWires") DrawModelWiresEx(m, position, axis, rotation, {scale, scale, scale}, tint);
        else DrawModelEx(m, position, axis, rotation, {scale, scale, scale}, tint);
        for (int i = 0; i < m.materialCount; ++i) m.materials[i].shader = originalShaders[i];
    };
}

void modelSnapshot(EvalState & state, const Assets & assets, Value & out)
{
    auto models = state.buildBindings(assets.modelNames().size());
    for (const auto & name : assets.modelNames()) {
        auto & asset = *assets.model(name);
        auto info = state.buildBindings(7);
        info.alloc("meshCount").mkInt(asset.value.meshCount);
        info.alloc("materialCount").mkInt(asset.value.materialCount);
        info.alloc("boneCount").mkInt(asset.value.boneCount);
        info.alloc("vertexCount").mkInt(asset.vertexCount);
        info.alloc("triangleCount").mkInt(asset.triangleCount);
        auto box = state.buildBindings(2);
        pointValue(state, box.alloc("min"), asset.bounds.min);
        pointValue(state, box.alloc("max"), asset.bounds.max);
        info.alloc("bounds").mkAttrs(box);
        auto clips = state.buildList(asset.animationCount);
        for (int i = 0; i < asset.animationCount; ++i) {
            auto clip = state.buildBindings(3);
            auto & anim = asset.animations[i];
            clip.alloc("name").mkString(std::string_view(anim.name, ::strnlen(anim.name, sizeof(anim.name))), state.mem);
            clip.alloc("frameCount").mkInt(anim.frameCount);
            clip.alloc("boneCount").mkInt(anim.boneCount);
            clips[i] = state.allocValue();
            clips[i]->mkAttrs(clip);
        }
        info.alloc("animations").mkList(clips);
        models.alloc(name).mkAttrs(info);
    }
    out.mkAttrs(models);
}

} // namespace nixray
