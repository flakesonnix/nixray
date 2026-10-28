#include "input.hh"

#include <raylib.h>
#include <string>
#include <vector>

namespace nixray {

using namespace nix;

namespace {

Value * inputList(EvalState & state, int count, bool (*read)(int))
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
}

} // namespace nixray
