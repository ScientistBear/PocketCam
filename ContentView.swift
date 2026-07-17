# PocketCam protocol v1

PocketCam uses newline-delimited UTF-8 JSON over one local TCP connection. The Blender add-on listens on `0.0.0.0:8766` by default and accepts one phone at a time. Each JSON object ends with a single line-feed byte.

## Coordinate convention

The phone sends the ARKit camera transform relative to the ARKit world origin:

- right-handed coordinates
- +X is camera right
- +Y is up
- the camera looks along -Z
- position is in meters
- quaternion wire order is `[x, y, z, w]`

Blender cameras also look along local -Z with local +Y up, so the reference-relative ARKit camera transform can drive the Blender camera without an axis-remapping shim. On recenter, Blender stores both the current phone pose and current camera world matrix. Subsequent motion is evaluated as:

```text
delta = inverse(phone_reference) * phone_pose
target = blender_camera_start * scale_translation(delta)
```

## Phone to Blender

### Hello

```json
{"type":"hello","protocol":1,"client":"PocketCam iOS","device":"My iPhone","app_version":"0.1.0"}
```

### Pose

```json
{"type":"pose","seq":42,"timestamp":1234.567,"position":[0.1,1.2,-0.4],"rotation":[0.0,0.2,0.0,0.98],"tracking":"Tracking"}
```

Pose messages are coalesced by the server. If Blender's main thread is busy, it applies the newest pose rather than replaying a stale backlog.

### Settings

```json
{"type":"settings","movement_scale":1.0,"smoothing":0.18,"lens_mm":24.0}
```

### Camera selection

```json
{"type":"select_camera","name":"Camera"}
```

### Command

```json
{"type":"command","command":"recenter"}
```

Command values in v1 are `recenter`, `record_start`, and `record_stop`.

### Ping

```json
{"type":"ping","timestamp":1720000000.0}
```

## Blender to phone

### Status

```json
{
  "type":"status",
  "protocol":1,
  "connected":true,
  "recording":false,
  "tracking":"Connected",
  "available_cameras":["Camera","Camera.001"],
  "selected_camera":"Camera",
  "movement_scale":1.0,
  "smoothing":0.18,
  "lens_mm":24.0,
  "message":"Handshake accepted"
}
```

### Pong

```json
{"type":"pong","timestamp":1720000000.0}
```

## Limits and trust model

- Maximum line size: 256 KiB
- One phone client at a time
- No authentication or encryption in v1
- Intended only for a trusted private LAN
- Blender API mutations occur on Blender's main thread; the network listener never touches scene data directly

