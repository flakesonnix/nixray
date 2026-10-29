// Test-only raylib query fixture: deterministic press/release edges per window.
#include <raylib.h>
#include <algorithm>
#include <array>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <dlfcn.h>
#include <limits>

namespace {

unsigned frame = 0;
size_t character = 0;
bool synth = false;
enum class Devices { Off, Standard, Bounds };
Devices devices = Devices::Off;
unsigned int gestureMask = 1023;
// One bit per native getter/slot: pads [0,428), touches [428,449), gestures [449,455).
std::array<bool, 455> deviceReads{};

void require(bool valid)
{
    if (!valid) {
        std::fputs("nixray input fixture: invalid or repeated device query\n", stderr);
        std::abort();
    }
}

void mark(size_t query)
{
    if (devices == Devices::Off) return;
    require(query < deviceReads.size() && !deviceReads[query]);
    deviceReads[query] = true;
}

bool available(int id)
{
    require(id >= 0 && id < 4);
    if (devices == Devices::Bounds) return frame == 0 ? id == 0 || id == 3 : frame == 1 && id == 0;
    if (devices == Devices::Off) return false;
    if (frame == 0) return id == 0 || id == 3;
    if (frame == 1) return id == 0 || id == 2;
    if (frame == 2) return id == 2;
    return frame == 4 && id == 0;
}

int axes(int id)
{
    require(available(id));
    if (devices == Devices::Bounds) return frame == 0 && id == 0 ? 1000 : -4;
    if (id == 3) return 8;
    if (id == 2) return frame == 1 ? 0 : 3;
    return frame == 1 ? 2 : 6;
}

int contacts()
{
    if (devices == Devices::Bounds) return frame == 0 ? 1000 : -7;
    if (devices == Devices::Off) return 0;
    return frame < 2 ? 2 : (frame == 2 || frame == 4) ? 1 : 0;
}

int detected()
{
    if (devices == Devices::Off) return GESTURE_NONE;
    if (devices == Devices::Bounds) return GESTURE_HOLD;
    constexpr int codes[]{GESTURE_TAP, GESTURE_HOLD, GESTURE_DRAG, GESTURE_PINCH_OUT, GESTURE_SWIPE_LEFT,
                          GESTURE_DOUBLETAP, GESTURE_SWIPE_RIGHT, GESTURE_SWIPE_UP, GESTURE_SWIPE_DOWN, GESTURE_PINCH_IN};
    return frame < std::size(codes) ? codes[frame] : GESTURE_NONE;
}

void checkDeviceReads()
{
    if (devices == Devices::Off) return;
    size_t expected = 4 + 1 + 6 + 2*std::clamp(contacts(), 0, 10);
    for (int id = 0; id < 4; ++id) if (available(id)) expected += 2 + 3*32 + std::clamp(axes(id), 0, 8);
    require(static_cast<size_t>(std::count(deviceReads.begin(), deviceReads.end(), true)) == expected);
}

template<typename Function>
Function original(const char * name)
{
    auto function = reinterpret_cast<Function>(dlsym(RTLD_NEXT, name));
    if (!function) {
        std::fprintf(stderr, "nixray input fixture: cannot find %s\n", name);
        std::abort();
    }
    return function;
}

} // namespace

extern "C" void InitWindow(int width, int height, const char * title)
{
    static const auto initialize = original<void (*)(int, int, const char *)>("InitWindow");
    frame = 0;
    character = 0;
    synth = std::getenv("NIXRAY_TEST_SYNTH_INPUT") != nullptr;
    initialize(width, height, title);
    const char * mode = std::getenv("NIXRAY_TEST_DEVICE_INPUT");
    devices = !mode || std::strcmp(mode, "off") == 0 ? Devices::Off :
              std::strcmp(mode, "bounds") == 0 ? Devices::Bounds : Devices::Standard;
    deviceReads.fill(false);
}

extern "C" void EndDrawing()
{
    static const auto finish = original<void (*)()>("EndDrawing");
    checkDeviceReads();
    finish();
    ++frame;
    character = 0;
    deviceReads.fill(false);
}

extern "C" bool IsKeyDown(int key)
{
    if (synth) return (frame < 8 && key == KEY_A) || (frame == 1 && key == KEY_X) || (frame == 3 && key == KEY_Z);
    return (frame == 0 && key == KEY_A) || (frame == 2 && key == KEY_KB_MENU) ||
           (frame == 5 && key == KEY_ENTER);
}

extern "C" bool IsKeyPressed(int key)
{
    if (synth) return (frame == 0 && key == KEY_A) || (frame == 1 && key == KEY_X) || (frame == 3 && key == KEY_Z);
    return IsKeyDown(key);
}

extern "C" bool IsKeyReleased(int key)
{
    if (synth) return (frame == 8 && key == KEY_A) || (frame == 2 && key == KEY_X) || (frame == 4 && key == KEY_Z);
    return (frame == 1 && key == KEY_A) || (frame == 3 && key == KEY_KB_MENU) ||
           (frame == 6 && key == KEY_ENTER);
}

extern "C" bool IsMouseButtonDown(int button)
{
    if (synth) return button == MOUSE_BUTTON_LEFT && (frame < 3 || frame == 4 || frame == 5 || frame == 7 || frame == 8);
    return (frame == 0 && button == MOUSE_BUTTON_LEFT) || (frame == 2 && button == MOUSE_BUTTON_BACK);
}

extern "C" bool IsMouseButtonPressed(int button)
{
    if (synth) return button == MOUSE_BUTTON_LEFT && (frame == 0 || frame == 4 || frame == 7);
    return IsMouseButtonDown(button);
}

extern "C" bool IsMouseButtonReleased(int button)
{
    if (synth) return button == MOUSE_BUTTON_LEFT && (frame == 3 || frame == 6 || frame == 9);
    return (frame == 1 && button == MOUSE_BUTTON_LEFT) || (frame == 3 && button == MOUSE_BUTTON_BACK);
}

extern "C" Vector2 GetMouseWheelMoveV()
{
    if (synth) return {0, 0};
    if (frame == 0) return {1.5f, -2.0f};
    if (frame == 1) return {0.0f, 1.25f};
    if (frame == 2) return {-0.5f, 0.0f};
    return {0.0f, 0.0f};
}

extern "C" int GetMouseX()
{
    if (synth) {
        if (frame == 0) return 50;
        if (frame == 1) return 125;
        if (frame == 2) return 200;
        if (frame == 4) return 300;
        if (frame == 5) return 40;
        if (frame == 7) return 630;
        if (frame == 8) return 370;
        return -1;
    }
    static const auto read = original<int (*)()>("GetMouseX");
    return read();
}

extern "C" int GetMouseY()
{
    if (synth) return frame < 3 ? 355 : 304;
    static const auto read = original<int (*)()>("GetMouseY");
    return read();
}

extern "C" int GetCharPressed()
{
    if (synth) return 0;
    static constexpr int first[] = {'A', 0x00e4, 0x1f642, 0};
    static constexpr int second[] = {0x03bb, 0x20ac, '\n', 0};
    static constexpr int invalid[] = {0xd800, 0xdfff, 0x110000, -1, 0};
    static constexpr int boundaries[] = {0x7f, 0x80, 0x7ff, 0x800, 0xffff, 0x10000, 0x10ffff, 0};
    const int * queued = nullptr;
    if (frame == 0) queued = first;
    else if (frame == 1) queued = second;
    else if (frame == 2) queued = invalid;
    else if (frame == 4) queued = boundaries;
    if (!queued) return 0;
    int codepoint = queued[character];
    if (codepoint) ++character;
    return codepoint;
}

extern "C" bool IsGamepadAvailable(int id)
{
    bool ready = available(id);
    mark(id);
    return ready;
}

extern "C" const char * GetGamepadName(int id)
{
    require(available(id));
    mark(4 + id);
    if (devices == Devices::Bounds) return id == 0 ? nullptr : "Bounds pad";
    // Reuse one native buffer: snapshots must copy names before the next query.
    static char name[64];
    std::snprintf(name, sizeof(name), "Pad %i frame %u \xce\xa9", id, frame);
    return name;
}

extern "C" int GetGamepadAxisCount(int id)
{
    mark(8 + id);
    return axes(id);
}

extern "C" float GetGamepadAxisMovement(int id, int axis)
{
    require(available(id) && axis >= 0 && axis < std::clamp(axes(id), 0, 8));
    mark(12 + id*8 + axis);
    if (devices == Devices::Bounds) {
        constexpr float values[]{std::numeric_limits<float>::quiet_NaN(), std::numeric_limits<float>::infinity(),
                                 -std::numeric_limits<float>::infinity(), 1.25f, -1.25f, 0.5f, 0, -1};
        return values[axis];
    }
    if (id == 3) { constexpr float values[]{-1, 0.5f, -0.25f, 0, 1, -1, 0.125f, -0.125f}; return values[axis]; }
    if (id == 2) { constexpr float values[]{0, 0.25f, -0.25f}; return values[axis]; }
    if (frame == 1) return axis == 0 ? -0.75f : 0.5f;
    if (frame == 4) return axis >= 4 ? -1 : 0;
    constexpr float values[]{0.25f, -0.5f, 0, 1, -1, 0.75f};
    return values[axis];
}

extern "C" bool IsGamepadButtonDown(int id, int button)
{
    require(available(id) && button >= 0 && button < 32);
    mark(44 + id*32 + button);
    if (devices == Devices::Bounds) return button == 0 || button == 31;
    if (id == 3) return button == 17;
    if (id == 2) return frame == 1 && button == 12;
    if (frame == 0) return button == 1 || button == 7 || button == 31;
    if (frame == 1) return button == 1;
    return button == 7;
}

extern "C" bool IsGamepadButtonPressed(int id, int button)
{
    require(available(id) && button >= 0 && button < 32);
    mark(44 + (4 + id)*32 + button);
    if (devices == Devices::Bounds) return button == 31;
    if (id == 3) return button == 17;
    if (id == 2) return frame == 1 && button == 12;
    return frame == 0 ? button == 1 || button == 7 || button == 31 : frame == 4 && button == 7;
}

extern "C" bool IsGamepadButtonReleased(int id, int button)
{
    require(available(id) && button >= 0 && button < 32);
    mark(44 + (8 + id)*32 + button);
    return devices == Devices::Standard && ((id == 0 && frame == 1 && (button == 7 || button == 31)) ||
                                            (id == 2 && frame == 2 && button == 12));
}

extern "C" int GetTouchPointCount()
{
    mark(428);
    return contacts();
}

extern "C" int GetTouchPointId(int index)
{
    require(index >= 0 && index < std::clamp(contacts(), 0, 10));
    mark(429 + index);
    if (devices == Devices::Bounds) return index == 0 ? -1 : index;
    if (frame == 4) return 202;
    if (frame == 1) return index == 0 ? 99 : 41;
    return index == 0 ? 41 : 99;
}

extern "C" Vector2 GetTouchPosition(int index)
{
    require(index >= 0 && index < std::clamp(contacts(), 0, 10));
    mark(439 + index);
    if (devices == Devices::Bounds) {
        if (index == 0) return {std::numeric_limits<float>::quiet_NaN(), std::numeric_limits<float>::infinity()};
        if (index == 1) return {-std::numeric_limits<float>::infinity(), -2.5f};
        return {index + 0.25f, -index - 0.5f};
    }
    if (frame == 0) return index == 0 ? Vector2{10.25f, 20.5f} : Vector2{100.5f, 80.25f};
    if (frame == 1) return index == 0 ? Vector2{101.5f, 81.25f} : Vector2{12.25f, 22.5f};
    return frame == 2 ? Vector2{14.25f, 24.5f} : Vector2{30, 40};
}

extern "C" void SetGesturesEnabled(unsigned int flags)
{
    static const auto enable = original<void (*)(unsigned int)>("SetGesturesEnabled");
    gestureMask = flags;
    enable(flags);
}

extern "C" int GetGestureDetected() { mark(449); return detected() & gestureMask; }
extern "C" float GetGestureHoldDuration()
{
    mark(450);
    if (devices == Devices::Bounds) return std::numeric_limits<float>::quiet_NaN();
    return devices == Devices::Standard && frame == 1 ? 2.5f : 0;
}
extern "C" Vector2 GetGestureDragVector()
{
    mark(451);
    if (devices == Devices::Bounds) return {std::numeric_limits<float>::infinity(), -std::numeric_limits<float>::infinity()};
    return devices == Devices::Standard && frame >= 2 ? Vector2{0.25f, -0.5f} : Vector2{};
}
extern "C" float GetGestureDragAngle()
{
    mark(452);
    if (devices == Devices::Bounds) return std::numeric_limits<float>::infinity();
    return devices == Devices::Standard && frame >= 2 ? 90 : 0;
}
extern "C" Vector2 GetGesturePinchVector()
{
    mark(453);
    if (devices == Devices::Bounds) return {std::numeric_limits<float>::quiet_NaN(), std::numeric_limits<float>::infinity()};
    return devices == Devices::Standard && frame >= 3 ? Vector2{0.75f, 0.125f} : Vector2{};
}
extern "C" float GetGesturePinchAngle()
{
    mark(454);
    if (devices == Devices::Bounds) return -std::numeric_limits<float>::infinity();
    return devices == Devices::Standard && frame >= 3 ? 315 : 0;
}
