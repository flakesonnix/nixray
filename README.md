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

### Graphics drivers

`NIXRAY_GRAPHICS` selects the launcher's graphics environment:

| Value | Behavior |
| --- | --- |
| `mesa` (default, also when empty) | Select packaged Mesa EGL/GLX and DRI paths; prepend its library path while retaining the caller's suffix |
| `system` | Leave all inherited graphics variables untouched; use your system's driver setup |

The default avoids mixing the plugin's Nix closure with a separately versioned
graphics-driver store. To use your system's drivers instead:

```sh
NIXRAY_GRAPHICS=system nix run . -- examples/hello.nix
```

For an already configured NVIDIA PRIME setup using X11/GLX, for example:

```sh
NIXRAY_GRAPHICS=system __NV_PRIME_RENDER_OFFLOAD=1 __GLX_VENDOR_LIBRARY_NAME=nvidia \
  nix run . -- examples/hello.nix
```

System mode preserves `LD_LIBRARY_PATH`, EGL/GLX vendor selections, DRI paths,
and NVIDIA/PRIME settings; it does not install drivers, repair ABI mismatches,
or silently fall back to Mesa. Invalid mode names fail before evaluating Nix.
On non-NixOS systems, a suitable graphics wrapper may still be required.

`nix develop` intentionally exports software-Mesa settings for headless tests.
System mode preserves those too: use a fresh desktop shell to test real system
drivers, rather than expecting it to undo the development shell's environment.

## API

Loading the plugin registers:

- `builtins.raylib config render`: own a window and its frame loop.
- `builtins.raylibRun config render`: compatibility alias for `builtins.raylib`.
- `builtins.raylibValidate commands`: recursively validate commands without a
  display; return the top-level list length (each drawing scope counts as one command).
  Also usable during pure evaluation.
- `builtins.raylibValidateAudio actions`: validate a flat audio action list and
  return its length. Pure; no window, device or asset loading.
- `builtins.raylibVersion`: linked raylib version string.
- `builtins.raylibWorldToScreen2D camera point` and
  `builtins.raylibScreenToWorld2D camera point`: pure coordinate conversions;
  no display or window required.
- `builtins.raylibCheckCollisionRecs`, `raylibCheckCollisionCircles`,
  `raylibCheckCollisionCircleRec`, `raylibCheckCollisionPointRec`,
  `raylibCheckCollisionPointCircle`, `raylibCheckCollisionPointTriangle`,
  `raylibCheckCollisionPointPoly`, `raylibCheckCollisionPointLine`,
  `raylibCheckCollisionCircleLine`, `raylibCheckCollisionLines` and
  `raylibGetCollisionRec`: pure geometry queries; see collision and picking below.

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
| `audio` | `false` | Opt in to an audio device, sound effects and streamed music |
| `gestures` | All gesture codes | List of enabled `ray.gestures` integer codes; `[]` disables detection |
| `state` | `null` | Initial application state |
| `assets` | `{}` | Named `textures`, `fonts`, `renderTextures`, `shaders`, `sounds` and `music` maps |

The callback receives a fresh attribute set each frame:

```nix
{
  frame = 0;                # Zero-based frame number
  time = 0.0; delta = 0.0;   # Raylib seconds and previous frame duration
  width = 800; height = 450; # Current drawable dimensions
  mouseX = 0; mouseY = 0;
  mouseWheelX = 0.0; mouseWheelY = 0.0; # Per-frame wheel movement on both axes
  textInput = "";                     # Queued committed characters as UTF-8
  keysDown = []; keysPressed = [];    # Lists of raylib integer key codes
  keysReleased = [];                 # Released during this frame
  mouseDown = []; mousePressed = []; # Lists of raylib mouse button codes
  mouseReleased = [];
  gamepads = [];                     # Connected gamepad snapshots, ordered by slot ID
  touches = [];                      # Current contacts: { id; x; y; }
  gesture = { detected = 0; holdDuration = 0.0;
    dragVector = { x = 0.0; y = 0.0; }; dragAngle = 0.0;
    pinchVector = { x = 0.0; y = 0.0; }; pinchAngle = 0.0; };
  audio = { enabled = false; sounds = {}; music = {}; }; # Playback snapshot
  state = null;                     # Previous frame's application state
}
```

It returns `{ commands = [ ... ]; audio = [ ... ]; state = nextState; close = false; }`.
Only `commands` is required. Omitted `state` preserves the previous state.
Omitted `audio` means no playback actions. `close = true` exits **after** processing
audio and drawing that frame. The native loop returns
`{ frames = totalRenderedFrames; state = finalState; }`.

The frame also contains `measureText`, a native function for text layout with
the window's fonts; see [Text measurement](#text-measurement).

`ray.keyReleased frame key` and `ray.mouseReleased frame button` test the release
lists; down/pressed fields and their existing behavior are unchanged.

Wheel values are signed per-frame deltas from raylib, including fractional
movement; they are not accumulated scroll positions. Store a running total in
application state if needed.

`textInput` drains raylib's character queue once per snapshot and concatenates
its Unicode codepoints into a UTF-8 string, even if the callback ignores the
field. It contains this frame's queued text only; append it to your own state
when desired. Invalid scalar values become U+FFFD. Editing keys still use the
keyboard lists; IME pre-edit/composition state and text shaping are not exposed.
Text input is independent of the loaded font's glyph coverage.

Try `nix run . -- examples/input.nix`: type to append text, press Enter to clear
it, scroll to resize the circle, and release A or the left mouse button to
change its color. The example deliberately uses the default font, so some
Unicode characters may be retained in state but displayed as fallback glyphs.

#### Gamepads, touch and gestures

`frame.gamepads` contains only connected controllers, in ascending native slot
order. Slots `0..3` are polled, so list positions are **not** controller IDs:

```nix
{
  id = 0; name = "Controller name";
  axes = [ 0.0 0.0 0.0 0.0 (-1.0) (-1.0) ];
  buttonsDown = []; buttonsPressed = []; buttonsReleased = [];
}
```

Button lists contain native integer codes `0..31`; `ray.gamepadButtons` names
the public raylib codes (`leftFaceUp/Right/Down/Left`,
`rightFaceUp/Right/Down/Left`, `leftTrigger1/2`, `rightTrigger1/2`,
`middleLeft`, `middle`, `middleRight`, `leftThumb`, `rightThumb`, `unknown`).
Pressed/released are native per-frame edges, not inferred by the plugin.
Disconnecting removes the entry; it does not synthesize release events. A slot
may later be reused for another device, and is not a persistent hardware identity.

`axes` contains the reported axis values in native index order, capped at eight
values per pad. `ray.gamepadAxes` names `leftX`, `leftY`, `rightX`, `rightY`,
`leftTrigger`, `rightTrigger` (indices `0..5`). Stick values are normally in
`-1..1`, and native triggers normally run from **-1 released to +1 pressed**;
mappings and support depend on the device/backend. There is no additional
deadzone, remapping or finite-value clamp. A null native name becomes `""`.

Use the plain Nix helpers for hotplug-safe access:

```nix
let
  pad = ray.gamepad frame 0; # Snapshot with ID 0, or null
  x = ray.gamepadAxis pad ray.gamepadAxes.leftX; # 0 if absent/out of bounds
  fire = ray.gamepadButtonPressed pad ray.gamepadButtons.rightFaceDown;
in ...
```

`ray.gamepadButtonDown`, `ray.gamepadButtonPressed` and
`ray.gamepadButtonReleased` return false for `null`. Use a fresh lookup each
frame so a disconnected pad does not leave stale held buttons in your state.

`frame.touches` contains up to ten `{ id; x; y; }` contacts in **native order**.
Coordinates are floats in logical screen pixels; IDs remain native integers,
including an unsupported `-1` ID if a backend supplies one. Indices may change
as contacts enter/leave: compare IDs across snapshots instead. No synthetic
pressed/released events or mouse fallback contacts are added by the plugin.
Actual touch support and mouse/touch emulation depend on the raylib backend.

`frame.gesture.detected` is the latest native gesture code. `ray.gestures`
provides `none`, `tap`, `doubleTap`, `hold`, `drag`, `swipeRight`, `swipeLeft`,
`swipeUp`, `swipeDown`, `pinchIn` and `pinchOut`.
`ray.gestureDetected frame ray.gestures.tap` compares the snapshot code, just
like native `IsGestureDetected`; `none` matches code zero. This is not a queue
or a synthetic pressed-edge API: holds/drags can remain detected across frames.

`holdDuration` uses seconds. The drag/pinch vectors preserve raylib's normalized
screen-coordinate units, **not pixels or per-frame deltas**: drag is displacement
within the gesture, and pinch is the separation vector between contacts, not a
zoom factor. Angles preserve native degrees: 0/360 points right, and positive
angles turn toward up, unlike clockwise drawing rotations. Metrics can retain
native cached values between gestures (or windows); gate their use on `detected`.

Optional config `gestures = [ ray.gestures.tap ray.gestures.drag ];` filters the
detected code using native `SetGesturesEnabled`. An empty list makes detection
zero; native metric getters can still return cached/ongoing values. Duplicates
are harmless and `none` adds no flag. Unknown codes, combined bitmasks and
non-integer entries are errors. The default enables all ten gestures, and flags
are reset explicitly for each window, including after a prior disabled run.
Desktop builds with mouse gestures enabled can recognize single-pointer gestures
without a touchscreen; multi-touch pinch support is backend-dependent.

All device fields are eagerly copied once per callback frame, even if Nix never
forces them. Retaining a snapshot or a closure over it never polls a later frame
or accesses a closed window. Native counts are clamped to the limits above
(negative counts become zero). Nonfinite new device/gesture numbers become
`0.0`, keeping evaluator state and JSON finite; other finite values are preserved.
No vibration, controller mapping changes or live query builtins are exposed.

Try `nix run . -- examples/devices.nix`: move with a gamepad's left stick or
keyboard arrows; tap/click or press the south face button to change color.
The plain Nix demo displays contacts and native gesture state, and works without
connected gamepads or touch hardware.

### Drawing commands

Colors are four integers, `[ red green blue alpha ]`, each in `0..255`.
Positions and rectangular dimensions are signed 32-bit integers; sizes must be
nonnegative (text size must be positive). Circle radii accept finite,
nonnegative integers or floats, as do ellipse/ring radii and line thickness.

| `op` | Required attributes besides `op` |
| --- | --- |
| `clear` | `color` |
| `clip` | `x`, `y`, `width`, `height`, `commands` |
| `camera2D` | `camera`, `commands` |
| `blend` | `mode`, `commands` |
| `shader` | `shader` (asset name), `commands` |
| `paint` | `texture` (render texture name), `commands` |
| `text` | `text`, `x`, `y`, `size`, `color` |
| `texture` | `texture` (asset name), `x`, `y` |
| `textureNPatch` | `texture`, `x`, `y`, `width`, `height`, `borders = { left; top; right; bottom; }` |
| `rectangle`, `rectangleLines` | `x`, `y`, `width`, `height`, `color` |
| `rectangleGradientV` | `x`, `y`, `width`, `height`, `top`, `bottom` |
| `rectangleGradientH` | `x`, `y`, `width`, `height`, `left`, `right` |
| `rectangleGradientEx` | `x`, `y`, `width`, `height`, `topLeft`, `bottomLeft`, `bottomRight`, `topRight` |
| `rectangleRounded`, `rectangleRoundedLines` | `x`, `y`, `width`, `height`, `roundness`, `color` |
| `circle`, `circleLines` | `x`, `y`, `radius`, `color` |
| `circleGradient` | `x`, `y`, `radius`, `inner`, `outer` |
| `circleSector`, `circleSectorLines` | `x`, `y`, `radius`, `startAngle`, `endAngle`, `color` |
| `ring`, `ringLines` | `x`, `y`, `innerRadius`, `outerRadius`, `startAngle`, `endAngle`, `color` |
| `ellipse`, `ellipseLines` | `x`, `y`, `radiusX`, `radiusY`, `color` |
| `triangle`, `triangleLines` | `x1`, `y1`, `x2`, `y2`, `x3`, `y3`, `color` |
| `line` | `x1`, `y1`, `x2`, `y2`, `color` |
| `lineEx` | `x1`, `y1`, `x2`, `y2`, `thickness`, `color` |
| `poly`, `polyLines` | `x`, `y`, `sides`, `radius`, `color` |
| `polyLinesEx` | `x`, `y`, `sides`, `radius`, `thickness`, `color` |
| `lineBezier` | `x1`, `y1`, `x2`, `y2`, `thickness`, `color` |
| `splineLinear`, `splineBasis`, `splineCatmullRom`, `splineBezierQuadratic`, `splineBezierCubic` | `points = [ { x; y; } ... ]`, `thickness`, `color` |
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

`origin = { x; y; }` selects a texture's pivot offset in scaled destination
pixels, not normalized UVs or source pixels. Both coordinates accept finite
integers/floats, including negative offsets and pivots outside the image.
The pivot is placed at command position `(x, y)` before rotation. For a 32x32
source at `scale = 4`, `origin = { x = 64; y = 64; }` rotates around its center.
The default is `{ x = 0; y = 0; }`, retaining the existing top-left anchor.

`flipX` and `flipY` are optional booleans (both default `false`). They mirror
the selected image region before scaling/rotation, without changing its output
size or pivot. Source widths/heights remain positive; use these flags rather
than negative dimensions.

For sprites/atlases, `texture` accepts `source = { x; y; width; height; }` in
image pixels. Offsets must be nonnegative integers and dimensions positive
integers. The rectangle must fit the loaded texture unless that asset explicitly
selects `wrap = "repeat"` or `"mirrorRepeat"`; cropping happens before
scaling and rotation. Omitting `source` uses the whole image. Pure validation
checks the rectangle's structure, but its texture bounds are checked only when
running with loaded assets.

### Additional 2D shapes

`triangle` and `triangleLines` accept either vertex winding order; native
rendering normalizes the order so filled triangles do not disappear because
of back-face culling. Ellipses are centered at `(x, y)`, with separate horizontal
`radiusX` and vertical `radiusY` values. All coordinates are signed 32-bit
integers; ellipse radii are finite nonnegative integers or floats.

Rounded rectangles use the same integer bounds as rectangles. `roundness` is
a required finite number in `0..1`: zero gives square corners, and one uses a
corner radius of half the smaller dimension. Optional `segments` is either `0`
(the default, automatic) or an integer in `4..4096`, specifying segments per
corner. Automatic tessellation is bounded to the same range and avoids
raylib's problematic automatic segment calculation at extreme radii.

The `Lines` variants draw one-pixel contours. Rounded rectangle contours follow
raylib's outer outline and may extend one pixel beyond the nominal rectangle.
Zero-area triangles, zero-radius ellipses and zero-width/height rounded
rectangles draw nothing, including their outline variants. Commands are still
fully validated in these cases.

Try `nix run . -- examples/shapes.nix` for all six commands. Matching helpers
such as `ray.triangle { ... }` and `ray.rectangleRoundedLines { ... }` construct
the same command attribute sets.

#### Gradients and thick lines

`lineEx` uses a finite nonnegative `thickness` in drawing-coordinate units, with
butt caps at the endpoints. Zero thickness and coincident native float endpoints
draw nothing. The existing `line` command remains a one-pixel line.

Rectangle gradients use the same integer bounds as rectangles. `V` blends top
to bottom; `H` blends left to right. `Ex` assigns the four named corner colors
and follows raylib's two-triangle vertex interpolation, not a bilinear four-corner
blend. `circleGradient` blends `inner` at the center toward `outer` on raylib's
fixed 36-segment circular boundary. These commands take their named colors instead
of a single `color`, and support normal alpha, blend and shader scopes.

#### Sectors and rings

Arc angles are finite degrees: **0 points right and positive angles turn clockwise**.
Reversed bounds swap, rather than implicitly wrapping: `350..10` becomes
`10..350`. Use `350..370` for a 20-degree arc across zero. The absolute span
must not exceed 360 degrees, checked before float rounding; the start angle is
normalized before native drawing. Negative and large finite angles are accepted
when their span is valid.

All four arc commands accept optional `segments`, an integer in `0..4096`.
Omitted or zero selects bounded automatic tessellation based on the outer radius
and span. Positive counts are raised to raylib's minimum (roughly one segment
per 90 degrees), avoiding its unsafe automatic path at extreme radii.

Ring radii must satisfy `0 <= innerRadius <= outerRadius`, checked before float
rounding. A zero inner radius produces a sector. Zero-radius sectors, equal-radius
rings, zero-angle spans, and zero-width/height rectangle gradients draw nothing,
including outline variants; all fields are still validated. Arc `Lines` variants
draw one-pixel contours **and radial caps**, including raylib's full-turn seam.

Try `nix run . -- examples/drawing.nix` for all nine commands. The example rotates
the arcs; holding Space switches their span from 270 to 90 degrees. Matching Nix
constructors, e.g. `ray.ring { ... }`, use the attribute sets above.

#### Regular polygons and curves

`poly` fills a regular polygon centered at `(x, y)`; `polyLines` draws its
one-pixel contour, and `polyLinesEx` draws a thick native contour inside the
outer polygon. `sides` is an integer in `3..4096`; `radius` and `thickness` are
finite nonnegative numbers. A thickness at least as large as the radius fills
the polygon instead of inverting its inner contour. Zero radius or zero thick
outline thickness draws nothing, after full validation. Optional `rotation`
defaults to `0`: its first vertex points right, and positive degrees turn
clockwise. Finite rotations are normalized before drawing.

`lineBezier` is raylib's **eased connector**, not a control-point Bézier:
x advances linearly while y uses cubic ease-in/out between the two endpoints.
Use the quadratic/cubic spline commands for explicit Bézier control points.

```nix
ray.splineBezierCubic {
  points = [ { x = 24; y = 180; } { x = 80; y = 24; }
             { x = 240; y = 24; } { x = 300; y = 180; } ];
  thickness = 5; color = ray.colors.skyblue;
  segments = 48; # optional, per polynomial span
}
```

All point coordinates are signed 32-bit **integers**, matching other drawing
positions; thickness accepts finite nonnegative integers/floats. Point sets
allow exactly `x` and `y`. Lists contain at most 4096 points:

| Command | Point-list rules and path |
| --- | --- |
| `splineLinear` | At least 2; open polyline through every point |
| `splineBasis` | At least 4; uniform cubic B-spline over overlapping groups of 4; generally does not pass through control points |
| `splineCatmullRom` | At least 4; overlapping groups of 4 interpolate the middle two; first/last points control tangents, not path endpoints |
| `splineBezierQuadratic` | `2n + 1` points, `n >= 1`; start, control, end, control, end, ... |
| `splineBezierCubic` | `3n + 1` points, `n >= 1`; start, control, control, end, control, control, end, ... |

Incomplete Bézier spans are errors, not silently ignored. Repeat the first and
last Catmull-Rom knots if those knots should also be path endpoints. Splines
remain open: no implicit closing segment, padding or arbitrary-polygon fill.

`lineBezier` and nonlinear splines accept optional `segments`, default `24`, an
integer in `1..4096` per span. The total is bounded to **65536 sampled intervals
per command**, even for zero thickness or constant controls. Large point lists
may therefore need a smaller segment count. `splineLinear` has no `segments`.

Curves use the standard interpolation polynomials with double intermediates,
then native float vertices. Strokes use butt caps and shared miter cross-sections
limited to one full thickness from the centerline (twice the half-width), rather
than native spline caps/unsafe zero-length normal divisions. Coincident samples
are skipped, and forward collinear subdivisions merge. Exact retraces meet as
separate butt-capped segments; self-intersections/retraces can blend more than
once. Zero thickness and fully collapsed paths draw nothing, after validation.
These are sampled strokes, not analytic or antialiased curves.

All nine commands honor clips, cameras, blends, shaders and render textures.
`ray.validate` performs the same point/count/work-limit checks without opening
a window. Try `nix run . -- examples/curves.nix`: the mouse wheel adjusts stroke
thickness; Space toggles control guides. The entire demonstration is plain Nix.

### Clipping

`clip` limits all of its child commands to a rectangular window region:

```nix
ray.clip {
  x = 24; y = 64; width = 592; height = 240;
  commands = [
    (ray.rectangle { x = 0; y = 0; width = 640; height = 360; color = ray.colors.skyblue; })
    (ray.text { text = "Clipped content"; x = 32; y = 72; size = 24; color = ray.colors.black; })
  ];
}
```

Coordinates are absolute window coordinates, not offsets from the parent clip.
`x`/`y` are signed 32-bit integers; `width`/`height` are nonnegative signed 32-bit
integers. Bounds are safely clamped to the window; the right and bottom edges
are excluded. Nested clips intersect their parent's region and restore it on
exit. Leaving the outermost clip restores unclipped drawing, including in
subsequent frames. Clips, cameras, blends, shaders and paints share a maximum
nesting depth of 64 scopes.

The scope applies to shapes, text, textures and `clear`. Clears affect only the
active region and preserve command order by flushing earlier queued geometry.
Clipping does not translate drawing coordinates, change input snapshots or alter
text measurement. Zero-size, off-screen and disjoint regions draw nothing, but
their children are still fully evaluated and validated before drawing begins;
undeclared assets remain errors even inside an invisible clip. Pure validation
recurses through children without opening a window or resolving asset names.

Try `nix run . -- examples/clipping.nix`: the mouse wheel scrolls a list inside
a panel while its header, border and footer remain outside the clip.

### 2D cameras

`camera2D` applies a camera to its child drawing commands and restores the
previous camera afterwards. A nested camera **replaces**, rather than composes
with, its parent's transform. Leaving the outermost camera restores normal
window drawing, so HUD commands can follow it in the same list.

```nix
ray.camera2D {
  camera = {
    target = { x = 100; y = 50; };
    offset = { x = 320; y = 180; };
    zoom = 2.0;
    rotation = 30.0;
  };
  commands = [
    (ray.rectangle { x = 80; y = 30; width = 40; height = 40; color = ray.colors.blue; })
  ];
}
```

The `camera` set is required, but all of its fields are optional:

| Field | Default | Meaning |
| --- | --- | --- |
| `target` | `{ x = 0; y = 0; }` | World point placed at `offset` |
| `offset` | `{ x = 0; y = 0; }` | Target's position in window coordinates |
| `zoom` | `1` | Positive scale; larger values enlarge the scene |
| `rotation` | `0` | Clockwise degrees, normalized modulo 360 |

Point coordinates, zoom and rotation accept finite integers/floats in raylib's
float range. Provided point sets require both `x` and `y`. Unknown attributes,
nonpositive zoom, overflowing matrices and transforms without a finite native
inverse are rejected, including during pure command validation. This can reject
extremely small/large positive zoom values even when the individual number is
finite. The default `camera = {}` is the identity transform.

`ray.worldToScreen2D camera { x; y; }` and `ray.screenToWorld2D camera { x; y; }`
use the same camera defaults/math and return float coordinates `{ x; y; }`.
They are aliases for the corresponding builtins and work during pure evaluation
without opening a window. Non-finite conversion results are errors; round trips
have raylib's single-precision rounding, not exact arithmetic. For mouse picking:

```nix
worldMouse = ray.screenToWorld2D camera { x = frame.mouseX; y = frame.mouseY; };
```

Camera transforms apply to shapes, text and textures. Clip rectangles remain in
absolute window coordinates regardless of whether the camera or clip is outermost.
`clear` still clears the active clip/window, not a transformed world rectangle.
Input coordinates and `frame.measureText` remain untransformed. Scope children
are validated before drawing; cameras, clips, blends, shaders and paints share the
64-scope nesting limit.

Try `nix run . -- examples/camera.nix`: WASD pans, the wheel zooms, left/right
arrows rotate, and a world-space marker follows the mouse beneath a fixed HUD.

### Blend modes

`blend` changes how each child draw combines with pixels already in the active
window/render texture. The `mode` string and `commands` list are required:

```nix
ray.blend {
  mode = "additive";
  commands = [
    (ray.circle { x = 120; y = 100; radius = 40; color = ray.rgba 240 120 80 160; })
    (ray.circle { x = 160; y = 100; radius = 40; color = ray.rgba 80 200 240 160; })
  ];
}
```

Only these four raylib presets are supported. In the formulas, `S` is the source
RGB after texture/tint multiplication, `D` is the existing destination RGB, and
`As` is source alpha, all normalized to `0..1`. Results clamp to `0..1`:

| `mode` | raylib preset | RGB equation |
| --- | --- | --- |
| `alpha` | `BLEND_ALPHA` | `S * As + D * (1 - As)` |
| `additive` | `BLEND_ADDITIVE` | `S * As + D` |
| `multiply` | `BLEND_MULTIPLIED` | `S * D + D * (1 - As)` |
| `subtract` | `BLEND_SUBTRACT_COLORS` | `S - D` |

These are native formulas, not Photoshop-style modes: **subtract is source minus
destination**, ignoring source alpha in RGB; multiply's `S * D` term is also not
weighted by source alpha, so even alpha-zero draws can change pixels in these
two modes. Native blend factors/equations also apply to the alpha channel; there
are no custom factors, separate-alpha settings or premultiplied-alpha modes.

Nested blends **replace**, rather than combine with, the outer mode. Leaving a
scope restores its parent; leaving the outermost restores normal alpha drawing.
Mode changes flush queued geometry, preserving command order. Blending applies
to individual shapes, text and textures, not to an automatically flattened group.
It does not change coordinates, cameras or clipping. `clear` bypasses blending
and still clears only the active clip/target, in list order.

`paint` starts its children in **alpha mode**, independent of any enclosing blend.
Use an explicit blend inside `paint` to choose another mode. On exit the enclosing
mode is restored, and later texture stamps use whatever blend is active where
they are drawn. This separates painting a texture from compositing it.

Blend children are fully validated before drawing, including in pure validation
and invisible clips. Unknown modes/attributes are errors. Blends share the
64-scope nesting budget with clips, cameras, shaders and paints. `raylibValidate` counts
only the top-level list entries, not nested child commands.

Try `nix run . -- examples/blend.nix` for a four-panel comparison. The mouse
wheel changes source alpha; labels outside each blend scope retain normal alpha.

### Collision and picking

Collision queries are pure native raylib calls, available without a display,
including during pure/restricted evaluation. The helpers below alias
`builtins.raylibCheckCollisionRecs` etc.; no window or assets are needed.
Each function takes two arguments: geometry sets, or an ordered point list for polygons:

| Helper | First argument | Second argument | Result |
| --- | --- | --- | --- |
| `ray.checkCollisionRecs` | Rectangle | Rectangle | Boolean |
| `ray.checkCollisionCircles` | Circle | Circle | Boolean |
| `ray.checkCollisionCircleRec` | Circle | Rectangle | Boolean |
| `ray.checkCollisionPointRec` | Point | Rectangle | Boolean |
| `ray.checkCollisionPointCircle` | Point | Circle | Boolean |
| `ray.checkCollisionPointTriangle` | Point | Triangle | Boolean |
| `ray.checkCollisionPointPoly` | Point | List of points | Boolean |
| `ray.checkCollisionPointLine` | Point | Segment plus optional `threshold` | Boolean |
| `ray.checkCollisionCircleLine` | Circle | Segment | Boolean |
| `ray.checkCollisionLines` | Segment | Segment | `{ x; y; }` intersection, or `null` |
| `ray.getCollisionRec` | Rectangle | Rectangle | Overlapping rectangle |

Geometry sets contain only these required fields (no `op`/`color`):

- Point: `{ x; y; }`
- Rectangle: `{ x; y; width; height; }`
- Circle: `{ x; y; radius; }`
- Segment: `{ x1; y1; x2; y2; }`
- Triangle: `{ x1; y1; x2; y2; x3; y3; }`
- Polygon: `[ { x; y; } ... ]`, ordered vertices, implicitly closed. Concave
  polygons and a repeated closing vertex are accepted. All vertices are validated;
  lists with fewer than three vertices return false.
- Point–line picking alone allows `threshold ? 1` in its segment set; it must
  be a nonnegative signed 32-bit integer. Other segment queries still reject it.

All fields accept finite integers/floats in raylib's float range; widths,
heights and radii must be nonnegative. Unknown/missing fields, wrong types,
non-finite coordinates and overflowing native arithmetic are errors, even when
every individual input is finite. Queries retain raylib's single-precision
rounding and underflow; they are not exact arbitrary-precision geometry.
Returned point/rectangle fields are floats. If rectangles have no positive-area
overlap, `getCollisionRec` returns `{ x = 0.0; y = 0.0; width = 0.0; height = 0.0; }`.

Boundary behavior follows raylib:

- Rectangle point picking includes left/top, excludes right/bottom. Edge-only
  contact between positive-area rectangles is not a collision.
- Circles include their boundary: tangency is a collision, including circle–rectangle
  tangency. A zero-radius circle can contain its center.
- Zero-size rectangles retain native behavior: point–rectangle picking is false,
  but `checkCollisionRecs` can report true for a zero-size rectangle strictly
  inside another one. Use `getCollisionRec`'s dimensions when positive area matters.
- Segment endpoints count for nonparallel intersections. Parallel, collinear
  (even overlapping) and zero-length segments return `null`. Raylib treats a
  determinant smaller than float epsilon (about `1.19e-7`) as parallel.
- Triangle picking is strictly interior: edges/vertices and zero-area triangles
  return false, with either winding.
- Polygon picking uses native even–odd ray casting. Boundaries are not uniformly
  included or excluded: for an axis-aligned rectangle, left/top count and
  right/bottom do not. Self-intersections retain the native even–odd rule.
- Point–line picking uses a **strict cross-product heuristic**, not Euclidean
  distance: `abs(cross(point - start, end - start)) < threshold * max(abs(dx), abs(dy))`,
  followed by an inclusive dominant-axis segment bound. Threshold zero and
  zero-length segments always return false. Threshold uses the geometry's own
  coordinate units, not automatically screen pixels.
- Circle–line picking includes tangency and endpoints, clamping projection to the
  segment. Segments with `abs(dx) + abs(dy) <= float epsilon` are treated as their
  first endpoint, retaining native near-zero-length behavior.

Convert window mouse coordinates before querying world-space shapes:

```nix
worldMouse = ray.screenToWorld2D camera { x = frame.mouseX; y = frame.mouseY; };
hovered = ray.checkCollisionPointRec worldMouse {
  x = 36; y = 48; width = 120; height = 80;
};
nearLine = ray.checkCollisionPointLine worldMouse {
  x1 = 16; y1 = 88; x2 = 360; y2 = 88; threshold = 3;
};
```

Queries do not automatically apply cameras, clipping or render-target transforms;
put both shapes in the same coordinate system yourself. Try
`nix run . -- examples/collision.nix` for camera-aware mouse picking, rectangle
overlap highlighting, circle contacts, triangle/concave-polygon picking,
line-hover highlighting and a segment-intersection marker.

### Render textures

`paint` redirects its child commands into a named render texture declared in the
window config; the texture command then stamps that GPU texture like any loaded
image:

```nix
ray.run {
  assets.renderTextures.panel = { width = 96; height = 64; };
} (_: {
  commands = [
    (ray.paint {
      texture = "panel";
      commands = [
        (ray.rectangle { x = 0; y = 0; width = 96; height = 64; color = ray.colors.skyblue; })
        (ray.rectangle { x = 4; y = 4; width = 40; height = 20; color = ray.colors.purple; })
      ];
    })
    (ray.texture { texture = "panel"; x = 240; y = 24; scale = 3.0; })
    (ray.texture { texture = "panel"; x = 240; y = 240; scale = 3.0; flipX = true; })
  ];
})
```

Declare `assets.renderTextures.<name> = { width; height; }` with integer
dimensions in `1..16384`. Render textures are allocated once per window, before
the first callback, and start fully transparent so stamps only show painted
content. GPU resources are released with the other assets before the window
closes.

Optional `filter` and `wrap` fields use the same sampling controls as image
textures below. They persist across paints; no mipmap generation is required.

`paint` requires `texture` (a declared render texture name) and `commands`;
`clear` is an optional boolean, defaulting to `true`, which replaces previous
contents with transparent black before the children draw. Set `clear = false`
to accumulate across paints and frames. Children start a fresh coordinate
system with `(0, 0)` at the texture's top-left: enclosing clips and cameras do
not apply inside, blending starts in alpha mode, and the default shader is used.
Paint children may freely use `clip`, `camera2D`, `blend`, `shader`, shapes, text
and `texture`/`textureNPatch` stamps.
Painting may not nest inside another paint, and a
texture-stamping command may not sample the texture being painted; alternating two
textures covers ping-pong effects.

When a paint appears inside a window clip, the scissor pauses for the target
drawing and resumes for following commands, while enclosing camera, blend and
shader/uniform state is restored after the paint. Stamp attributes work as for loaded images
(`tint`, `scale`, `rotation`, `source`, `origin`, `flipX`/`flipY`), and crop
rectangles address the last painted image in image pixels. Paint children are
validated before drawing, share the 64-scope nesting limit with clips, cameras,
blends and shaders, and pure validation recurses into them without opening a window; render
texture names resolve only when running with loaded assets.

Try `nix run . -- examples/render.nix`: one square accumulates per frame into a
diagonal mural, stamped twice side by side with horizontal mirroring.

### Fragment shaders

Declare a fragment shader and typed uniform defaults in `assets.shaders`:

```nix
ray.run {
  assets.shaders.fx = {
    fragment = ./examples/shaders/tint.fs;
    uniforms = {
      gain = { type = "float"; value = 1.0; };
      tint = { type = "vec3"; value = [ 1 1 1 ]; };
    };
  };
} (_: {
  commands = [
    (ray.clear ray.colors.black)
    (ray.shader {
      shader = "fx";
      uniforms = { gain = 0.5; tint = [ 1 0.6 1 ]; };
      commands = [
        (ray.rectangle { x = 24; y = 24; width = 120; height = 80; color = ray.colors.white; })
      ];
    })
  ];
})
```

`fragment` is required and accepts a Nix path or an absolute/context-bearing
string, like other asset paths. The shader uses raylib's default vertex shader;
custom vertex stages are not exposed. Programs compile/link once per window,
before the first callback. Missing files, compile/link failures and raylib's
silent fallback to the default program are errors. Programs and location data
are released before the window closes, including on partial loading failures.
This uses the existing desktop GLFW/OpenGL backend; the example is GLSL 330.

The optional asset `uniforms` map declares configurable uniforms. Each entry
requires exactly `{ type; value; }`, with a default value matching its type:

| `type` | Nix value |
| --- | --- |
| `float` | Finite integer/float in raylib's single-precision range |
| `int` | Signed 32-bit integer |
| `vec2`, `vec3`, `vec4` | List of exactly 2, 3 or 4 finite numeric components |

Native reflection verifies that each declared uniform is active and its GLSL
type matches. Missing/optimized-out uniforms, arrays and mismatched types are
errors. Uniform names must be ordinary GLSL identifiers, with no `gl_` prefix.
Raylib-managed names such as `mvp`, `colDiffuse` and `texture0` are reserved;
matrices, sampler overrides, booleans and uniform arrays are not exposed.
Undeclared custom uniforms retain their GLSL initial values and cannot be
overridden through a scope.

A `shader` command requires `shader` (asset name) and `commands`; its optional
`uniforms` map contains plain replacement values, not type/default descriptors.
Every entry must appear in that asset's schema. Each scope starts from the
**asset defaults**, not its parent's overrides. Nested shader scopes replace the
active shader, then restore the parent program and its effective uniform values
on exit, including when both scopes use the same program. Leaving the outermost
scope restores raylib's default shader. Pending geometry is flushed before
program or uniform changes, so sibling draws cannot pick up later values.

Shaders apply to shapes, text and textures; they do not automatically capture a
scene or change cameras/clipping. Shader output feeds the active blend mode.
`clear` bypasses shaders and preserves list/scissor order. `paint` starts with
the default shader, restoring its enclosing shader and uniforms afterward.
Put a shader scope **inside** paint to affect target drawing, or wrap a later
`texture` stamp to post-process an already-painted scene. `texture0` is bound
automatically; `fragTexCoord`, `fragColor` and `colDiffuse` follow raylib's shader
conventions (see `examples/shaders/tint.fs`).

Shader scopes share the 64-scope budget with clips, cameras, blends and paints.
Children are fully validated before drawing. Pure `raylibValidate` checks names,
value shapes and finite numeric values without loading shaders; declared asset
names, uniform schemas and GLSL types resolve only in a real window run.

Try `nix run . -- examples/shader.nix`: the same render texture is stamped normally
and through a tint/gain shader. The mouse wheel changes gain, while labels outside
the shader scope retain their original colors.

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
errors. Render textures follow the same lifecycle and are initialized to
transparent black instead of loading file contents. Native resources are
released before the window closes, including on
callback exceptions or partial loading failures. `raylibValidate` checks command
structure only: it does not load assets or verify that names are declared.

#### Texture sampling

Path-only texture declarations remain unchanged. An options set additionally
selects filtering and wrapping, once per asset:

```nix
assets.textures.logo = { path = ./logo.png; filter = "bilinear"; wrap = "clamp"; };
assets.textures.tiles = { path = ./tiles.png; wrap = "repeat"; };
assets.renderTextures.canvas = { width = 128; height = 128; filter = "bilinear"; };
```

- `filter`: `"point"` or `"bilinear"`. Options sets default to point filtering;
  path-only declarations retain raylib's original sampler defaults.
- `wrap`: `"clamp"`, `"repeat"` or `"mirrorRepeat"`, applied to both axes.
  Omitting it preserves native wrapping **and the existing strict crop bounds**.
  Explicit repeat modes allow ordinary `texture` source rectangles beyond the
  image dimensions, including render textures; coordinates stay nonnegative and
  dimensions positive signed 32-bit integers.

To tile, extend the source rectangle instead of merely increasing `scale`:

```nix
ray.texture { texture = "tiles"; x = 0; y = 0;
  source = { x = 0; y = 0; width = 512; height = 256; };
}
```

Filtering/wrapping belong to each named GPU asset, not global drawing state.
Declare the same path under separate names for different settings. Bilinear atlas
crops can blend neighboring texels; pad atlas regions when that matters. Mipmapped
and anisotropic filters, and mirror-clamp wrapping, are not exposed yet.

#### Nine-patch panels

`textureNPatch` stretches a nine-slice panel while retaining border sizes in
drawing-coordinate units (one source pixel per border unit before camera scaling):

```nix
ray.textureNPatch {
  texture = "logo"; x = 24; y = 24; width = 320; height = 140;
  borders = { left = 4; top = 4; right = 4; bottom = 4; };
}
```

Destination bounds and all four border widths are nonnegative signed 32-bit
integers. Source regions must retain a **nonempty center**: left + right must be
less than source width, and top + bottom less than source height. Optional
`source = { x; y; width; height; }` always selects a bounded region, even on a
repeating asset. Omitting it selects the whole image. Zero destination width or
height draws nothing, but every field and known asset bound is still validated.

If the destination is smaller than the borders, each axis compresses its two
borders proportionally; the full source corners are preserved and the destination
center disappears. `tint`, `rotation` and `origin` match ordinary texture stamps,
with the pivot relative to the **whole panel**, not each slice. Scale/flip flags
and three-slice layouts are not exposed by this command.

Panels work with image and render-texture assets, including top-left logical
crops on framebuffer textures, and honor camera, clip, blend and shader scopes.
They may paint into another target, but never sample their own active paint target.
Pure validation checks border sums when an explicit source size is provided;
whole-asset dimensions resolve during the window run.

Try `nix run . -- examples/textures.nix` for a self-contained Nix demonstration:
point/bilinear scaling, repeat/mirror-repeat tiling, and a nine-patch panel resized
by holding the left mouse button and moving the pointer. All source images are
painted into render textures; no external files are needed.

#### Font assets

Font paths retain raylib's `LoadFont` defaults (including a 32-pixel TrueType
atlas and ASCII glyphs 32..126). Alternatively, declare a font options set:

```nix
assets.fonts.ui = {
  path = ./ui.ttf;
  size = 48;
  codepoints = (builtins.genList (n: n + 32) 95) ++ [ 228 955 ]; # ASCII + ä, λ
};
```

`path` is required and accepts the same paths/context-bearing strings as above.
`size` is the atlas rasterization size (integer `1..512`, default `32`), not the
draw command's size. `codepoints` is an optional list of `1..4096` distinct
Unicode scalars in `1..1114111`, excluding surrogates. Omitting it uses raylib's
ASCII set; an empty list is an error. Include `63` (`?`) for a fallback glyph.
Unsupported characters retain raylib's fallback behavior; no shaping or IME
composition is added. `size`/`codepoints` require a `.ttf` or `.otf` file;
`{ path = ./bitmap.fnt; }` works without these options. Bitmap fonts must retain
their atlas images beside the font file. Copy/package the whole asset directory
when using store paths for bitmap fonts.

Run the asset example with your own files:

```sh
nix run . -- examples/assets.nix --arg image ./logo.png --arg font ./ui.ttf
```

### Text measurement

`frame.measureText { text; size; font ? ...; }` returns float attributes
`{ width; height; }` using the default font or a named loaded font. `text` is a
context-free UTF-8 string without NUL bytes; `size` is a positive signed 32-bit
integer, just as for drawing. Unknown attributes/font names are errors.

Measurement uses raylib's logical layout metrics, not tight ink/pixel bounds.
It handles Unicode codepoints, fallback glyphs and newlines with raylib's
default two-pixel line gap. Custom fonts use one-pixel glyph spacing; omitting
`font` matches `DrawText`'s minimum size of 10 and integer `size / 10` spacing.
Empty strings return zero dimensions, and newline-only widths are clamped to
zero. Missing glyphs are not synthesized. The function retains immutable CPU
metrics, so it remains safe to call after its original window has closed or
while another window is open; GPU resources are still released normally.

For example, reuse the same text attributes for measuring and drawing:

```nix
frame:
let
  label = { text = "Nix: ä λ"; size = 32; font = "ui"; };
  measured = frame.measureText label;
in {
  commands = [ (ray.text (label // {
    x = builtins.floor ((frame.width - measured.width) / 2);
    y = 100; color = ray.colors.black;
  })) ];
}
```

Try `nix run . -- examples/text.nix --arg font ./ui.ttf` for explicit Unicode
glyphs and a centered label with its measured layout box.

### Sprite sheets

Select an atlas region and transform it with the same `texture` command:

```nix
ray.texture {
  texture = "sheet"; x = 280; y = 120;
  source = { x = 32; y = 0; width = 32; height = 32; };
  scale = 4.0; rotation = 30.0;
  origin = { x = 64; y = 64; };
  flipX = true;
}
```

Declare `assets.textures.sheet` as usual. `examples/sprites.nix` cycles through
the first row of a sprite sheet while rotating around its center, at 12 frames
per second. Each pass alternates horizontal mirroring without moving the pivot.
For an atlas containing four horizontal 32x32 frames:

```sh
nix run . -- examples/sprites.nix --arg image ./atlas.png \
  --arg frameWidth 32 --arg frameHeight 32 --arg columns 4
```

### Audio

Audio is **opt-in**: ordinary runs never initialize or probe an audio device.
Set `audio = true` in the window config before declaring audio assets or returning
nonempty audio action lists. `hidden = true` does not mute an enabled device.
Playback still runs inside the existing graphical frame loop, so a display is
required even when `commands = []`.

```nix
let ray = import ./lib;
in ray.run {
  audio = true;
  assets = {
    sounds.click = ./click.wav;
    music.theme = { path = ./theme.ogg; looping = true; };
  };
} (frame: {
  commands = [ (ray.clear ray.colors.raywhite) ];
  audio = (if frame.frame == 0 then [
    (ray.setMusicVolume { music = "theme"; volume = 0.5; })
    (ray.playMusic "theme")
  ] else []) ++ (if ray.keyPressed frame ray.keys.a then [
    (ray.playSound "click")
  ] else []);
})
```

`assets.sounds.<name>` accepts a path and decodes the whole effect into memory.
`assets.music.<name>` accepts either a path (default `looping = true`) or
`{ path; looping ? true; }`, retaining a decoder and streaming buffers. Both use
the same Nix paths/absolute context-bearing strings as graphics assets and load
once per window. Available file formats follow the linked raylib build; tests
exercise native WAV decoding for both kinds. Music frame counts above signed
32-bit range are rejected because native playback-time queries use signed frame
arithmetic.

The callback's optional `audio` list is **separate from drawing commands**:

| `op` | Required fields besides `op` |
| --- | --- |
| `playSound`, `pauseSound`, `resumeSound`, `stopSound` | `sound` (asset name) |
| `setSoundVolume` | `sound`, `volume` |
| `setSoundPitch` | `sound`, `pitch` (speed/pitch multiplier) |
| `setSoundPan` | `sound`, `pan` (stereo position) |
| `playMusic`, `pauseMusic`, `resumeMusic`, `stopMusic` | `music` (asset name) |
| `setMusicVolume` | `music`, `volume` |
| `setMusicPitch` | `music`, `pitch` (speed/pitch multiplier) |
| `setMusicPan` | `music`, `pan` (stereo position) |
| `seekMusic` | `music`, `position` (seconds) |

Transport helpers take a name, e.g. `ray.pauseMusic "theme"`; volume/pitch/pan/seek helpers
take the field set shown above. Volume must be a finite number in `0..1`.
Pitch must be finite and in `0.125..8`: `1` is normal, `2` is one octave up and
twice as fast, and `0.5` is one octave down and half as fast. This bounded range
keeps native resampling coordinates safe. This is playback-rate adjustment,
not time stretching. Pan must be finite and in `-1..1`: **-1 left, 0 center,
+1 right**. Mono assets are mixed into stereo; for stereo assets pan scales
the existing channels rather than folding one channel into the other.

```nix
audio = [
  (ray.setSoundPitch { sound = "click"; pitch = 2; })
  (ray.setSoundPan { sound = "click"; pan = -1; })
  (ray.setMusicPitch { music = "theme"; pitch = 0.5; })
  (ray.setMusicPan { music = "theme"; pan = 0.5; })
];
```

Pitch/pan are absolute per-asset settings, not cumulative offsets. Defaults are
pitch `1` and centered pan `0`; changes can be made before or during playback and
persist through pause/resume and stop/play until changed or the window exits.
Repeatedly setting the same pitch does not keep transposing the asset. These
settings do not change the system mixer volume or route, and the playback
snapshot schema is unchanged.

Seek positions must be finite, nonnegative and no greater than track length,
with a safe native frame conversion. Seeking is exposed for WAV/OGG/MP3/FLAC/QOA,
not module formats; decoder/buffer precision means it is not sample-exact output
scheduling. Unknown attributes, operations and resource names are errors.

Actions execute in list order **once per submitted frame**. Emit play/seek actions
on input edges or state transitions, not unconditionally every frame. Repeated
`playSound` calls restart that asset's single voice; no overlapping-voice API is
added. Use pause/resume to preserve playback, and stop/play to restart music.
Audio actions cannot nest under camera/clip/blend/shader scopes or appear in the
drawing list. `ray.validateAudio actions` aliases the pure audio validator; it
checks syntax/ranges without resolving asset names or track lengths.

Every frame includes an immutable `frame.audio` snapshot:

```nix
{
  enabled = true;
  sounds.click = { playing = false; };
  music.theme = { playing = false; looping = true; timePlayed = 0.0; timeLength = 10.0; };
}
```

The snapshot is captured **before this frame's actions**, and can be retained
after resource cleanup without live native handles. `playing` is false for both
paused and stopped assets; music times are native float seconds. With audio
disabled, `enabled = false` and both maps are empty. Backend playback proceeds
asynchronously; these values are not a sample-synchronized clock.

Drawing actions, audio actions, `close` and the next state are all evaluated and
validated before any of this frame's playback changes. The loop then executes
audio actions, calls `UpdateMusicStream` once for each loaded track, and renders
the frame. Existing playback is not frozen during evaluation, and slow callbacks
can starve streaming audio. Sound/music resources are unloaded before the owned
audio device closes, on normal exit, early close and exceptions. An already-active
device is not taken over. Initialization failures are errors; raylib/miniaudio may
also select a silent/null backend, so `enabled` does not certify audible output.

Try your own files with:

```sh
nix run . -- examples/audio.nix --arg sound ./click.wav --arg music ./theme.ogg
```

A plays a sound effect, Enter pauses/resumes music, and the wheel changes volume.

`examples/audio-controls.nix` needs no external files: it uses the Nix-generated
tone bank, starts a looping tone, and exposes pitch with Up/Down, pan with
Left/Right, volume with the wheel, A for a sound effect, and Space to pause/resume:

```sh
nix run . -- examples/audio-controls.nix
```

#### Self-contained Nix synth

```sh
nix run . -- examples/synth.nix
```

Hold **A W S E D F T G Y H U J K** to play a chromatic C4–C5 keyboard;
multiple keys play chords. **Space** cycles triangle/square/saw, the **wheel**
changes volume, and **Enter** silences all voices until held keys are released.
**Z/X** (or the on-screen buttons) select the C3–C4, C4–C5 or C5–C6 range.
Click keys or hold the left mouse button and drag for glissando; black keys take
priority where they overlap white keys. Mouse and keyboard can play together.
Panic also blocks a held mouse gesture until the button is released.

Drag the **Attack** (5–500 ms) and **Release** (20–1000 ms) sliders to adjust
the envelopes, including while notes are sounding. Sliders retain their drag
outside the track and clamp at each end; dragging a control cannot play keys.
Keys light up while held and their level bars shrink during release.

The instrument, oscillator math, PCM samples, envelopes and drawing are Nix.
No Python, downloaded samples or external audio files are used. First launch
builds a small WAV bank using the pinned nixpkgs; a build shell only writes the
Nix-computed bytes. The same bank is available as `nix build .#synth-tones`,
or can be supplied with `--arg tones ./my-tone-bank`.
The expanded bank contains 111 WAVs: three waveforms at every semitone from C3
through C6. Custom banks must supply these same filenames (e.g. `triangle-c3.wav`).
The bank uses signed 16-bit PCM; this raylib version loads 8-bit WAV music
without error but does not decode its samples during streaming.

This demonstrates the existing audio API, not a real-time PCM callback: each
note loops a generated periodic waveform through a music stream. Attack (default
20 ms) and release (default 150 ms) volume updates occur per graphical frame, not
per sample; waveform/octave changes restart held notes. All old voices stop before
new ones start, including the shared C at adjacent octave boundaries.
Sample rates approximate equal temperament
within 0.004 Hz, the square/saw waves are not band-limited, and output volume has
headroom for all 13 voices. The example requires a working audio backend to hear.
If keys light up but sound is absent, check the system mixer: the application
stream is typically named `nix`, and its saved volume is separate from the wheel.

## Evaluation semantics and safety

Nix is lazy and memoizes expressions. Independent side-effecting builtins for
`BeginDrawing` and `EndDrawing` would therefore be easy to skip, reorder, or run
only once. Instead, the plugin owns an iterative C++ loop, calls a Nix function
with a fresh snapshot, fully validates drawing/audio batches and state, then
applies audio actions and draws in order. It closes owned devices and the window
on normal exit and evaluator exceptions, and checks for
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
nix build .#synth-tones --out-link build/synth-tones
env -u WAYLAND_DISPLAY XDG_SESSION_TYPE=x11 NIXRAY_TEST_SYNTH_TONES="$PWD/build/synth-tones" \
  xvfb-run -a -s '-screen 0 800x600x24 -noreset' \
  python3 tests/test_plugin.py \
  --nix "$(command -v nix-instantiate)" --plugin "$PWD/build/nixray.so" \
  --capture-library "$PWD/build/nixray-test-capture.so" \
  --input-library "$PWD/build/nixray-test-input.so" \
  --audio-library "$PWD/build/nixray-test-audio.so"
```

Use the Nix binary from `nix develop`, not one outside that shell. The dev
shell selects software Mesa and sets up `XDG_RUNTIME_DIR` so the Xvfb command
works without a GPU. `-noreset` avoids X server reset races when tests close and
immediately reopen windows. Package checks compile the real plugin and run evaluator
tests plus actual OpenGL rendering under Xvfb; an install check also exercises
the wrapped launcher. Tests generate tiny PNG/bitmap-font fixtures, and the dev
shell supplies a TrueType test font. Linux x86_64 and aarch64 packages are exposed;
only the local host architecture is tested by default. Pixel tests preload a
test-only capture module, flush the real raylib draw batch, and inspect the back
buffer before the buffer swap. That module is never installed with the plugin.
Assertions cover shader uniforms/reflection, same-program nested restoration,
shader post-processing, blend equations, nested mode restoration, isolated render-target
blending, camera transforms/restoration, pure coordinate round trips,
pure collision queries/boundaries/overflow, camera-aware picking and geometry-driven drawing,
camera/clip combinations, nested clipping, scissor restoration across frames, clipped
clears, extreme clip bounds, shape fills/outlines, both triangle windings, degenerate shapes,
command order, Unicode glyph selection, measured
text placement, custom fonts, texture orientation,
scaling, crops, rotations, tint, and alpha blending, plus render texture
painting, stamp orientation/mirroring, crop and scaling, cross-frame persistence,
incremental painting, clips/cameras inside targets, and transparent initialization. RGB comparisons are exact,
except for a one-step quantization tolerance in fractional blend checks.
Input tests preload a separate polling-state fixture for release edges, wheel
axes, UTF-8 queues and snapshot lifetime checks. They do not require physical
devices or claim to cover OS event delivery or IME integration. Audio tests use
silent WAV fixtures and isolated backend settings (silent ALSA/default-null
fallback), with a tracing/failure-injection hook around real native decoding,
playback and streaming. They check action ordering, playback snapshots and device/
resource cleanup, not acoustics or physical speaker output. Synth regressions
also capture the real stereo float mixer output and check AC energy and waveform
cycles, rather than accepting successful playback calls as evidence of sound.
No test hook is installed with the plugin.

`.github/workflows/checks.yml` runs `nix flake check` on Ubuntu 24.04 for pushes,
pull requests, and manual runs. Actions are pinned to commit hashes, with
read-only repository permissions. The flake also validates the workflow with
`actionlint`, so CI configuration is checked by the same local command.

The wrapper is MIT licensed. Raylib is separately licensed under zlib/libpng.
