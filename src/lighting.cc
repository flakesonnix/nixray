#include "lighting.hh"
#include "reader.hh"

#include <rlgl.h>
#include <cmath>
#include <utility>

namespace nixray {

namespace {

// Private built-in stages; user shader assets retain their fragment-only API.
constexpr auto vertexShader = R"GLSL(#version 330
// nixrayLighting
in vec3 vertexPosition;
in vec2 vertexTexCoord;
in vec3 vertexNormal;
in vec4 vertexColor;
uniform mat4 mvp;
uniform mat4 matModel;
uniform mat4 matNormal;
uniform int nixrayModel;
out vec3 worldPosition;
out vec3 worldNormal;
out vec2 uv;
out vec4 color;
void main() {
    // rlgl batches already bake primitive transforms on the CPU. Model VBOs do
    // not. Applying matModel to both would double-transform mid-batch spheres.
    worldPosition = nixrayModel != 0 ? vec3(matModel * vec4(vertexPosition, 1.0)) : vertexPosition;
    worldNormal = nixrayModel != 0 ? vec3(matNormal * vec4(vertexNormal, 0.0)) : vertexNormal;
    uv = vertexTexCoord;
    color = vertexColor;
    gl_Position = mvp * vec4(vertexPosition, 1.0);
}
)GLSL";

constexpr auto fragmentShader = R"GLSL(#version 330
in vec3 worldPosition;
in vec3 worldNormal;
in vec2 uv;
in vec4 color;
uniform sampler2D texture0;
uniform vec4 colDiffuse;
uniform vec3 nixrayAmbient;
uniform int nixrayLightCount;
uniform vec3 nixrayDirections[4];
uniform vec3 nixrayColors[4];
uniform vec3 nixrayCamera;
uniform vec3 nixrayViewDirection;
uniform int nixrayOrthographic;
uniform vec4 nixrayDiffuse;
uniform float nixraySpecular;
uniform float nixrayShininess;
uniform int nixrayNormals;
out vec4 finalColor;
vec3 unitVector(vec3 v) {
    float largest = max(max(abs(v.x), abs(v.y)), abs(v.z));
    if (!(largest > 0.0) || isinf(largest) || isnan(largest)) return vec3(0.0);
    vec3 scaled = v / largest;
    return scaled * inversesqrt(dot(scaled, scaled));
}
void main() {
    vec4 base = texture(texture0, uv) * color * colDiffuse * nixrayDiffuse;
    vec3 n = nixrayNormals != 0 ? unitVector(worldNormal) : vec3(0.0);
    if (dot(n, n) == 0.0) n = unitVector(cross(dFdx(worldPosition), dFdy(worldPosition)));
    vec3 view = nixrayOrthographic != 0 ? nixrayViewDirection : unitVector(nixrayCamera - worldPosition);
    vec3 result = base.rgb * nixrayAmbient;
    for (int i = 0; i < 4; ++i) {
        if (i >= nixrayLightCount) break;
        vec3 light = -nixrayDirections[i];
        float diffuse = max(dot(n, light), 0.0);
        float specular = 0.0;
        if (diffuse > 0.0) {
            vec3 halfVector = unitVector(light + view);
            specular = nixraySpecular * pow(max(dot(n, halfVector), 0.0), nixrayShininess);
        }
        result += nixrayColors[i] * (base.rgb * diffuse + vec3(specular));
    }
    finalColor = vec4(result, base.a);
}
)GLSL";

std::array<float, 3> rgb(EvalState & state, PosIdx pos, const Reader & r, Value & value)
{
    state.forceList(value, pos, context);
    if (value.listSize() != 3) r.fail("lighting RGB must contain exactly three numbers");
    std::array<float, 3> result;
    for (size_t i = 0; i < result.size(); ++i) result[i] = r.number(*value.listView()[i], "lighting RGB component", 0, 1);
    return result;
}

} // namespace

LightingSpec lightingSpec(EvalState & state, PosIdx pos, Value & value)
{
    Reader r(state, pos);
    r.fields(value, {"op", "ambient", "lights", "commands"});
    LightingSpec result;
    if (auto * ambient = r.optional(value, "ambient")) result.ambient = rgb(state, pos, r, *ambient);
    auto & lights = r.required(value, "lights");
    state.forceList(lights, pos, context);
    if (lights.listSize() > 4) r.fail("lighting must contain at most four directional lights");
    for (auto * light : lights.listView()) {
        r.fields(*light, {"direction", "color", "intensity"});
        auto & direction = r.required(*light, "direction");
        r.fields(direction, {"x", "y", "z"});
        double x = r.numberDouble(r.required(direction, "x"), "direction.x");
        double y = r.numberDouble(r.required(direction, "y"), "direction.y");
        double z = r.numberDouble(r.required(direction, "z"), "direction.z");
        double length = std::hypot(x, y, z);
        if (length == 0) r.fail("light direction must be nonzero");
        DirectionalLight entry{{static_cast<float>(x/length), static_cast<float>(y/length), static_cast<float>(z/length)}, {1, 1, 1}, 1};
        if (auto * color = r.optional(*light, "color")) entry.color = rgb(state, pos, r, *color);
        if (auto * intensity = r.optional(*light, "intensity")) entry.intensity = r.number(*intensity, "light intensity", 0, 16);
        result.lights.push_back(entry);
    }
    return result;
}

MaterialSpec materialSpec(EvalState & state, PosIdx pos, Value & value)
{
    Reader r(state, pos);
    r.fields(value, {"op", "diffuse", "specular", "shininess", "commands"});
    MaterialSpec result;
    if (auto * diffuse = r.optional(value, "diffuse")) result.diffuse = r.color(*diffuse);
    if (auto * specular = r.optional(value, "specular")) result.specular = r.number(*specular, "material specular", 0, 1);
    if (auto * shininess = r.optional(value, "shininess")) result.shininess = r.number(*shininess, "material shininess", 1, 256);
    return result;
}

std::unique_ptr<LightingShader> loadLightingShader(const Reader & r)
{
    auto result = std::make_unique<LightingShader>();
    auto & shader = result->resource.program;
    shader = LoadShaderFromMemory(vertexShader, fragmentShader);
    if (!IsShaderValid(shader) || shader.id == rlGetShaderIdDefault()) r.fail("could not compile built-in lighting shader");
    auto location = [&](const char * name) {
        int loc = GetShaderLocation(shader, name);
        if (loc < 0) r.fail(std::string("built-in lighting uniform is unavailable: ") + name);
        return loc;
    };
    result->ambient = location("nixrayAmbient");
    result->count = location("nixrayLightCount");
    result->directions = location("nixrayDirections[0]");
    result->colors = location("nixrayColors[0]");
    result->camera = location("nixrayCamera");
    result->viewDirection = location("nixrayViewDirection");
    result->orthographic = location("nixrayOrthographic");
    result->diffuse = location("nixrayDiffuse");
    result->specular = location("nixraySpecular");
    result->shininess = location("nixrayShininess");
    result->model = location("nixrayModel");
    result->normals = location("nixrayNormals");
    return result;
}

Command litCommand(const LightingShader & shader, LightingSpec lighting, MaterialSpec material,
                    Camera3D camera, bool model, bool normals, Command draw)
{
    return [&shader, lighting = std::move(lighting), material, camera, model, normals, draw = std::move(draw)] {
        // Uniforms are program-global, even between nested lighting/material
        // scopes using this same program. Never overwrite queued draw state.
        rlDrawRenderBatchActive();
        auto program = shader.resource.program;
        BeginShaderMode(program);
        std::array<float, 12> directions{}, colors{};
        for (size_t i = 0; i < lighting.lights.size(); ++i) {
            const auto & light = lighting.lights[i];
            directions[i*3] = light.direction.x; directions[i*3 + 1] = light.direction.y; directions[i*3 + 2] = light.direction.z;
            for (size_t j = 0; j < 3; ++j) colors[i*3 + j] = light.color[j]*light.intensity;
        }
        int count = lighting.lights.size(), modelValue = model, normalValue = normals;
        int orthographic = camera.projection == CAMERA_ORTHOGRAPHIC;
        Vector3 view{camera.position.x - camera.target.x, camera.position.y - camera.target.y, camera.position.z - camera.target.z};
        double length = std::hypot(static_cast<double>(view.x), static_cast<double>(view.y), static_cast<double>(view.z));
        view = {static_cast<float>(view.x/length), static_cast<float>(view.y/length), static_cast<float>(view.z/length)};
        float diffuse[]{material.diffuse.r/255.0f, material.diffuse.g/255.0f, material.diffuse.b/255.0f, material.diffuse.a/255.0f};
        SetShaderValue(program, shader.ambient, lighting.ambient.data(), SHADER_UNIFORM_VEC3);
        SetShaderValue(program, shader.count, &count, SHADER_UNIFORM_INT);
        SetShaderValueV(program, shader.directions, directions.data(), SHADER_UNIFORM_VEC3, 4);
        SetShaderValueV(program, shader.colors, colors.data(), SHADER_UNIFORM_VEC3, 4);
        SetShaderValue(program, shader.camera, &camera.position, SHADER_UNIFORM_VEC3);
        SetShaderValue(program, shader.viewDirection, &view, SHADER_UNIFORM_VEC3);
        SetShaderValue(program, shader.orthographic, &orthographic, SHADER_UNIFORM_INT);
        SetShaderValue(program, shader.diffuse, diffuse, SHADER_UNIFORM_VEC4);
        SetShaderValue(program, shader.specular, &material.specular, SHADER_UNIFORM_FLOAT);
        SetShaderValue(program, shader.shininess, &material.shininess, SHADER_UNIFORM_FLOAT);
        SetShaderValue(program, shader.model, &modelValue, SHADER_UNIFORM_INT);
        SetShaderValue(program, shader.normals, &normalValue, SHADER_UNIFORM_INT);
        draw();
        rlDrawRenderBatchActive();
        EndShaderMode();
    };
}

} // namespace nixray
