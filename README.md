# nixray

A native **Nix evaluator plugin** backed by [raylib](https://github.com/raysan5/raylib).
Open a window, draw 2D graphics, and handle keyboard/mouse input directly from Nix.
Supports 2D primitives, textures, and custom fonts. This is not a binding to
raylib's entire API (no audio or 3D yet).

## Run

On Linux with Nix flakes and an X11/Wayland desktop:

```sh
nix build
./result/bin/nixray examples/hello.nix
# Or:
nix run . -- examples/hello.nix
# A finite, hidden run (still needs a display):
./result/bin/nixray examples/hello.nix --arg hidden true --arg maxFrames 2
```

Arrow keys move the circle; Escape or the window close button exits. The launcher
prints the final `{ frames, state }` as JSON after the window closes. When no
`--arg` or `--argstr` is supplied, a top-level function is invoked with `{}`, so
defaulted expressions run directly; pass either option to override defaults.

**Use the bundled launcher.** Nix's C++ plugin ABI is unstable; `nixray` invokes
the exact Nix build used to compile its plugin (Nix 2.34 from the locked nixpkgs).
Do not load the `.so` into an arbitrary system Nix. To select another compatible
2.34 build, override `nixComponents` in `package.nix` and rebuild both together.

The launcher also selects the packaged Mesa EGL/GLX vendor and DRI paths. This
avoids a runtime mismatch between the plugin's Nix closure and a separately
versioned system graphics-driver store.

## API

Loading the plugin registers:

- `builtins.raylib config render`: own a window and its frame loop.
- `builtins.raylibRun config render`: compatibility alias for `builtins.raylib`.
- `builtins.raylibValidate commands`: validate commands without a display; return
  their count. Also usable during pure evaluation.
- `builtins.raylibVersion`: linked raylib version string.

`builtins.raylib` is a native plugin-provided builtin, not a modification to
stock Nix. The bundled launcher loads it automatically. No helper import is
required: save this as `draw.nix` and run `nix run . -- draw.nix`:

```nix
builtins.raylib { width = 640; height = 480; title = "Hello Nix"; } (_: {
  commands = [
    { op = "clear"; color = [ 245 245 245 255 ]; }
    {
      op = "text"; text = "Hello from a Nix builtin!";
      x = 120; y = 200; size = 24; color = [ 0 121 241 255 ];
    }
  ];
})
```

Optionally, `lib/default.nix` provides command constructors, colors, and common
key codes; `ray.run` is an alias for `builtins.raylib`:

```nix
let ray = import ./lib;
in ray.run { width = 640; height = 480; title = "Hello Nix"; } (frame: {
  commands = [
    (ray.clear ray.colors.raywhite)
    (ray.text {
      text = "Hello from raylib!";
      x = 120; y = 200; size = 24; color = ray.colors.blue;
    })
  ];
})
```

### Window config

| Attribute | Default | Meaning |
| --- | --- | --- |
| `width`, `height` | `800`, `450` | Positive integer window dimensions |
| `title` | `"nixray"` | Window title (context-free string) |
| `fps` | `60` | Target FPS; `0` means uncapped |
| `maxFrames` | `0` | Stop after this many rendered frames; `0` means unlimited |
| `hidden` | `false` | Hidden window, useful for headless tests |
| `resizable` | `false` | Allow window resizing |
| `state` | `null` | Initial application state |
| `assets` | `{}` | Named `textures` and `fonts` maps; see below |

The callback receives a fresh attribute set each frame:

```nix
{
  frame = 0;                # Zero-based frame number
  time = 0.0; delta = 0.0;   # Raylib seconds and previous frame duration
  width = 800; height = 450; # Current drawable dimensions
  mouseX = 0; mouseY = 0;
  keysDown = []; keysPressed = [];    # Lists of raylib integer key codes
  mouseDown = []; mousePressed = []; # Lists of raylib mouse button codes
  state = null;                     # Previous frame's application state
}
```

It returns `{ commands = [ ... ]; state = nextState; close = false; }`.
Only `commands` is required. Omitted `state` preserves the previous state.
`close = true` exits **after** drawing that frame. The native loop returns
`{ frames = totalRenderedFrames; state = finalState; }`.

### Drawing commands

Colors are four integers, `[ red green blue alpha ]`, each in `0..255`.
Coordinates and dimensions are signed 32-bit integers; sizes must be
nonnegative (text size must be positive). Circle radii accept finite,
nonnegative integers or floats.

| `op` | Required attributes besides `op` |
| --- | --- |
| `clear` | `color` |
| `text` | `text`, `x`, `y`, `size`, `color` |
| `texture` | `texture` (asset name), `x`, `y` |
| `rectangle`, `rectangleLines` | `x`, `y`, `width`, `height`, `color` |
| `circle`, `circleLines` | `x`, `y`, `radius`, `color` |
| `line` | `x1`, `y1`, `x2`, `y2`, `color` |
| `pixel` | `x`, `y`, `color` |
| `fps` | `x`, `y` |

For example, `ray.clear ray.colors.white` constructs
`{ op = "clear"; color = [ 255 255 255 255 ]; }`. Other constructors take
the attribute sets listed above; `ray.fps x y` takes two integers.
Commands execute in list order. Unknown attributes/operations and invalid
arguments are errors, including typos in config or callback results.

`texture` additionally accepts `tint` (default white), `scale` (default `1`),
and `rotation` (default `0`). Rotation is clockwise in degrees around `(x, y)`;
scale is a finite positive integer or float. Scaled dimensions must fit finite
raylib coordinates. Defaults draw the image at native size without rotation.
`text` accepts an optional `font` asset name; omitting it preserves raylib's
default-font behavior.

For sprites/atlases, `texture` accepts `source = { x; y; width; height; }` in
image pixels. Offsets must be nonnegative integers and dimensions positive
integers. The rectangle must fit the loaded texture; cropping happens before
scaling and rotation. Omitting `source` uses the whole image. Pure validation
checks the rectangle's structure, but its texture bounds are checked only when
running with loaded assets.

### Textures and fonts

Declare assets in the window config and refer to them by name in commands:

```nix
let ray = import ./lib;
in ray.run {
  assets = {
    textures.logo = ./logo.png;
    fonts.ui = ./ui.ttf;
  };
} (_: {
  commands = [
    (ray.clear ray.colors.white)
    (ray.texture { texture = "logo"; x = 24; y = 24; })
    (ray.text {
      font = "ui"; text = "Hello assets!";
      x = 24; y = 200; size = 24; color = ray.colors.blue;
    })
  ];
})
```

Paths may be Nix path values or absolute strings, including strings with Nix
store context. The launcher enables `--read-write-mode` so newly referenced
sources can be copied to the store. Use that flag yourself when invoking
`nix-instantiate --eval` directly with such paths.

Assets load once, before the first callback. Unknown names and failed loads are
errors. Native resources are released before the window closes, including on
callback exceptions or partial loading failures. `raylibValidate` checks command
structure only: it does not load assets or verify that names are declared.

Fonts use raylib's `LoadFont` defaults (including its default TrueType atlas size
and glyph set); arbitrary Unicode shaping and glyph selection are not exposed.
Bitmap fonts must retain their atlas images beside the font file. Copy/package
the whole asset directory when using store paths for bitmap fonts.

Run the asset example with your own files:

```sh
nix run . -- examples/assets.nix --arg image ./logo.png --arg font ./ui.ttf
```

### Sprite sheets

Select an atlas region and transform it with the same `texture` command:

```nix
ray.texture {
  texture = "sheet"; x = 280; y = 120;
  source = { x = 32; y = 0; width = 32; height = 32; };
  scale = 4.0; rotation = 30.0;
}
```

Declare `assets.textures.sheet` as usual. `examples/sprites.nix` cycles through
the first row of a sprite sheet while rotating it, at 12 frames per second.
For an atlas containing four horizontal 32x32 frames:

```sh
nix run . -- examples/sprites.nix --arg image ./atlas.png \
  --arg frameWidth 32 --arg frameHeight 32 --arg columns 4
```

## Evaluation semantics and safety

Nix is lazy and memoizes expressions. Independent side-effecting builtins for
`BeginDrawing` and `EndDrawing` would therefore be easy to skip, reorder, or run
only once. Instead, the plugin owns an iterative C++ loop, calls a Nix function
with a fresh snapshot, fully validates each batch, then draws it in order.
It closes the window on normal exit and evaluator exceptions, and checks for
Nix interrupts every frame. Nested windows are rejected.

State is deeply evaluated each frame to avoid accumulating a chain of unevaluated
updates. Avoid explicitly retaining old snapshots or large histories in state.
There is no claim of bounded memory for arbitrary callbacks. A result bound with
`let` is still memoized by Nix: forcing it twice does not run the window twice.

Window evaluation is intentionally impure and rejects `pure-eval` and
`restrict-eval`. Do not use it in derivations, production NixOS configuration,
or evaluation of untrusted expressions. A native plugin runs inside the evaluator
with the user's privileges; it is **not a sandbox**. A working display and OpenGL
context are required, even with `hidden = true` (use Xvfb for headless rendering).

## Build and test

```sh
nix flake check -L
nix develop
cmake -S . -B build
cmake --build build
env -u WAYLAND_DISPLAY XDG_SESSION_TYPE=x11 xvfb-run -a python3 tests/test_plugin.py \
  --nix "$(command -v nix-instantiate)" --plugin "$PWD/build/nixray.so" \
  --capture-library "$PWD/build/nixray-test-capture.so"
```

Use the Nix binary from `nix develop`, not one outside that shell. The dev
shell selects software Mesa and sets up `XDG_RUNTIME_DIR` so the Xvfb command
works without a GPU. Package checks compile the real plugin and run evaluator
tests plus actual OpenGL rendering under Xvfb; an install check also exercises
the wrapped launcher. Tests generate tiny PNG/bitmap-font fixtures, and the dev
shell supplies a TrueType test font. Linux x86_64 and aarch64 packages are exposed;
only the local host architecture is tested by default. Pixel tests preload a
test-only capture module, flush the real raylib draw batch, and inspect the back
buffer before the buffer swap. That module is never installed with the plugin.
Assertions cover primitive fills, command order, custom fonts, texture orientation,
scaling, crops, rotations, tint, and alpha blending. RGB comparisons are exact,
except for a one-step quantization tolerance in the alpha-blending check.

`.github/workflows/checks.yml` runs `nix flake check` on Ubuntu 24.04 for pushes,
pull requests, and manual runs. Actions are pinned to commit hashes, with
read-only repository permissions. The flake also validates the workflow with
`actionlint`, so CI configuration is checked by the same local command.

The wrapper is MIT licensed. Raylib is separately licensed under zlib/libpng.
