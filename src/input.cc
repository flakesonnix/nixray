#include "input.hh"
#include "reader.hh"

#include <raylib.h>
#include <algorithm>
#include <array>
#include <cmath>
#include <string>
#include <vector>

namespace nixray {

using namespace nix;

namespace {

// Raylib's public header omits build-time limits; bound polling to the pinned
// desktop backend's capacities. Availability/count queries gate every access.
constexpr int gamepadCount = 4, gamepadAxisCount = 8, gamepadButtonCount = 32, touchCount = 10;
constexpr std::array<int, 11> gestures{GESTURE_NONE, GESTURE_TAP, GESTURE_DOUBLETAP, GESTURE_HOLD, GESTURE_DRAG,
                                    GESTURE_SWIPE_RIGHT, GESTURE_SWIPE_LEFT, GESTURE_SWIPE_UP, GESTURE_SWIPE_DOWN,
                                    GESTURE_PINCH_IN, GESTURE_PINCH_OUT};

template<typename Read>
Value * inputList(EvalState & state, int count, Read read)
{
    std::vector<int> active;
    for (int i = 0; i < count; ++i) if (read(i)) active.push_back(i);
    auto list = state.buildList(active.size());
    for (size_t i = 0; i < active.size(); ++i) {
        list[i] = state.allocValue();
        list[i]->mkInt(active[i]);
    }
    auto * value = state.allocValue();
    value->mkList(list);
    return value;
}

float finiteInput(float value)
{
    // Backend/device failures must not inject NaN/infinity into Nix state/JSON.
    return std::isfinite(value) ? value : 0.0f;
}

void inputVector(EvalState & state, Value & out, Vector2 vector)
{
    auto result = state.buildBindings(2);
    result.alloc("x").mkFloat(finiteInput(vector.x));
    result.alloc("y").mkFloat(finiteInput(vector.y));
    out.mkAttrs(result);
}

void gamepads(EvalState & state, Value & out)
{
    std::vector<int> available;
    for (int id = 0; id < gamepadCount; ++id) if (IsGamepadAvailable(id)) available.push_back(id);
    auto list = state.buildList(available.size());
    for (size_t i = 0; i < available.size(); ++i) {
        int id = available[i];
        auto pad = state.buildBindings(6);
        pad.alloc("id").mkInt(id);
        const char * name = GetGamepadName(id);
        pad.alloc("name").mkString(name ? name : "", state.mem);
        int count = std::clamp(GetGamepadAxisCount(id), 0, gamepadAxisCount);
        auto axes = state.buildList(count);
        for (int axis = 0; axis < count; ++axis) {
            axes[axis] = state.allocValue();
            axes[axis]->mkFloat(finiteInput(GetGamepadAxisMovement(id, axis)));
        }
        pad.alloc("axes").mkList(axes);
        pad.insert(state.symbols.create("buttonsDown"), inputList(state, gamepadButtonCount, [=](int b) { return IsGamepadButtonDown(id, b); }));
        pad.insert(state.symbols.create("buttonsPressed"), inputList(state, gamepadButtonCount, [=](int b) { return IsGamepadButtonPressed(id, b); }));
        pad.insert(state.symbols.create("buttonsReleased"), inputList(state, gamepadButtonCount, [=](int b) { return IsGamepadButtonReleased(id, b); }));
        list[i] = state.allocValue();
        list[i]->mkAttrs(pad);
    }
    out.mkList(list);
}

void touches(EvalState & state, Value & out)
{
    int count = std::clamp(GetTouchPointCount(), 0, touchCount);
    auto list = state.buildList(count);
    for (int i = 0; i < count; ++i) {
        auto touch = state.buildBindings(3);
        touch.alloc("id").mkInt(GetTouchPointId(i));
        auto position = GetTouchPosition(i);
        touch.alloc("x").mkFloat(finiteInput(position.x));
        touch.alloc("y").mkFloat(finiteInput(position.y));
        list[i] = state.allocValue();
        list[i]->mkAttrs(touch);
    }
    out.mkList(list);
}

void gesture(EvalState & state, Value & out)
{
    auto result = state.buildBindings(6);
    result.alloc("detected").mkInt(GetGestureDetected());
    result.alloc("holdDuration").mkFloat(finiteInput(GetGestureHoldDuration()));
    inputVector(state, result.alloc("dragVector"), GetGestureDragVector());
    result.alloc("dragAngle").mkFloat(finiteInput(GetGestureDragAngle()));
    inputVector(state, result.alloc("pinchVector"), GetGesturePinchVector());
    result.alloc("pinchAngle").mkFloat(finiteInput(GetGesturePinchAngle()));
    out.mkAttrs(result);
}

std::string inputText()
{
    std::string text;
    for (int codepoint; (codepoint = GetCharPressed()) != 0;) {
        if (codepoint < 0 || codepoint > 0x10ffff || (codepoint >= 0xd800 && codepoint <= 0xdfff))
            codepoint = 0xfffd;
        int size = 0;
        const char * encoded = CodepointToUTF8(codepoint, &size);
        text.append(encoded, static_cast<size_t>(size));
    }
    return text;
}

} // namespace

unsigned int gestureFlags(EvalState & state, PosIdx pos, Value * value)
{
    if (!value) return GESTURE_TAP | GESTURE_DOUBLETAP | GESTURE_HOLD | GESTURE_DRAG | GESTURE_SWIPE_RIGHT |
                       GESTURE_SWIPE_LEFT | GESTURE_SWIPE_UP | GESTURE_SWIPE_DOWN | GESTURE_PINCH_IN | GESTURE_PINCH_OUT;
    Reader r(state, pos);
    state.forceList(*value, pos, context);
    unsigned int flags = 0;
    for (auto * entry : value->listView()) {
        int code = r.integer(*entry, "gesture", GESTURE_NONE, GESTURE_PINCH_OUT);
        if (std::find(gestures.begin(), gestures.end(), code) == gestures.end()) r.fail("unknown gesture code '" + std::to_string(code) + "'");
        flags |= static_cast<unsigned int>(code);
    }
    return flags;
}

void addInput(EvalState & state, BindingsBuilder & frame)
{
    constexpr int keyCount = KEY_KB_MENU + 1;
    constexpr int mouseCount = MOUSE_BUTTON_BACK + 1;
    frame.alloc("mouseX").mkInt(GetMouseX());
    frame.alloc("mouseY").mkInt(GetMouseY());
    auto wheel = GetMouseWheelMoveV();
    frame.alloc("mouseWheelX").mkFloat(wheel.x);
    frame.alloc("mouseWheelY").mkFloat(wheel.y);
    // Consume the character queue now, regardless of which fields Nix later forces.
    frame.alloc("textInput").mkString(inputText(), state.mem);
    frame.insert(state.symbols.create("keysDown"), inputList(state, keyCount, IsKeyDown));
    frame.insert(state.symbols.create("keysPressed"), inputList(state, keyCount, IsKeyPressed));
    frame.insert(state.symbols.create("keysReleased"), inputList(state, keyCount, IsKeyReleased));
    frame.insert(state.symbols.create("mouseDown"), inputList(state, mouseCount, IsMouseButtonDown));
    frame.insert(state.symbols.create("mousePressed"), inputList(state, mouseCount, IsMouseButtonPressed));
    frame.insert(state.symbols.create("mouseReleased"), inputList(state, mouseCount, IsMouseButtonReleased));
    gamepads(state, frame.alloc("gamepads"));
    touches(state, frame.alloc("touches"));
    gesture(state, frame.alloc("gesture"));
}

} // namespace nixray
