# PocketCam Bridge

PocketCam Bridge is a free, local-network virtual camera controller for Blender. An iPhone runs ARKit world tracking and streams its six-degree-of-freedom pose to a Blender add-on, where the motion can be previewed and recorded as camera keyframes.

This first release is aimed at handheld/found-footage camera work. It includes the useful core of a virtual camera app without an account, subscription, or cloud service.

## What works in v0.1

- ARKit position and rotation tracking at 15, 30, 45, or 60 updates per second
- Direct TCP connection over your private Wi-Fi; no relay or cloud account
- Select any camera in the open Blender scene
- Recenter without moving the Blender camera
- Adjustable physical-to-virtual movement scale
- Adjustable motion smoothing and lens focal length
- Start and stop Blender takes from the phone
- New Blender Actions for every recorded take, sampled at the scene frame rate
- Correct world-space control for parented cameras

The current version does **not** stream the Blender viewport back to the phone. Keep the Blender viewport visible on the PC while operating the camera. Viewport streaming is the main planned follow-up.

## The two parts

```text
iPhone (ARKit pose)  -->  private Wi-Fi  -->  Blender add-on  -->  camera + keyframes
       controls      <--     TCP JSON     <--  status/cameras
```

Everything stays on the local network. The v0.1 protocol is intentionally simple and is not encrypted, so use it only on a trusted private network.

## Fast setup

### 1. Install the Blender add-on

1. Download `PocketCam-Bridge-Blender-Addon-v0.1.0.zip`.
2. In Blender, open **Edit > Preferences > Get Extensions**.
3. Use the menu in the upper-right, choose **Install from Disk**, select the zip, and approve its local-network permission.
4. In a 3D View, press **N** and open the **PocketCam** tab.
5. Pick a camera and click **Start Server**.
6. If Windows Firewall asks, allow Blender on **Private networks** only.
7. Copy the address shown in the panel, such as `192.168.1.40:8766`.

### 2. Build and install the iPhone app

The source targets iOS 18 and later and uses stable ARKit APIs, so it is suitable for an iPhone 16 Pro running a newer iOS beta.

On Windows, the included GitHub Actions workflow builds an unsigned IPA on a hosted Mac:

1. Put this source in a GitHub repository.
2. Open the repository's **Actions** tab.
3. Run **Build unsigned iOS app**.
4. Download the `PocketCam-unsigned` artifact when it finishes.
5. Extract the artifact and sign/install `PocketCam-unsigned.ipa` with a tool such as [Sideloadly](https://sideloadly.io/) or [AltStore Classic](https://faq.altstore.io/altstore-classic/how-to-install-altstore-windows).

An unsigned IPA cannot be installed directly. Apple says a free Personal Team provisioning profile expires after seven days, so the app must then be rebuilt or re-signed and reinstalled. See [Apple's account overview](https://developer.apple.com/help/account/basics/about-your-developer-account/) and [docs/BUILD_IOS.md](docs/BUILD_IOS.md).

### 3. Connect and shoot

1. Put the iPhone and PC on the same Wi-Fi network.
2. Enter the Blender IP and port in PocketCam, then tap **Connect to Blender**.
3. Accept the camera and local-network permission prompts.
4. Tap **Start Tracking** and wait for the green `Tracking` indicator.
5. Hold the phone in the starting pose and tap **Recenter**.
6. Tap **Record Take**, perform the move, then tap **Stop Take**.

The take is stored as a new `PocketCam_Take_...` Action on the camera, with a companion lens Action on the camera data block. Save the `.blend` file after a take you want to keep.

## Good found-footage starting values

- Movement scale: `0.7x` to `1.2x`
- Smoothing: `10%` to `25%`
- Lens: `18 mm` to `28 mm`
- Send rate: `60 fps`; use `30 fps` if the network is congested
- Blender scene rate: `24` or `30 fps`

Give ARKit visible detail and steady lighting. Blank walls, darkness, severe motion blur, or covering the cameras can reduce tracking quality. For a believable handheld feel, use light smoothing and keep some natural translation rather than rotating from one fixed point.

## Troubleshooting

**The phone will not connect**

- Start the server in Blender first.
- Verify the phone uses Wi-Fi rather than cellular and is on the same LAN as the PC.
- Disable a VPN temporarily.
- Allow Blender through Windows Firewall on private networks.
- Check that the Blender port and phone port match; the default is `8766`.
- Some guest Wi-Fi networks block devices from talking to one another.

**Tracking says it is limited**

- Move the phone slowly while ARKit initializes.
- Point the phone toward textured surfaces with clear visual features.
- Improve room lighting and avoid reflective/featureless walls.
- Tap **Recenter** after tracking returns to normal.

**The motion is too shaky or delayed**

- Raise smoothing for less jitter; lower it for less latency.
- Reduce the send rate to 30 fps on poor Wi-Fi.
- A crowded 2.4 GHz network can be much less consistent than 5/6 GHz Wi-Fi.

## Validation performed

- TCP protocol unit tests cover handshakes, pose coalescing, replies, and malformed packets.
- A Blender 5.0.1 headless smoke test covers registration, parented camera motion, lens control, Action creation, and recorded keyframes.
- The iOS plist and project specification are machine-validated on Windows. The Swift app must be compiled on macOS/Xcode; the included workflow performs that build once placed in GitHub.

## Project layout

- `blender_addon/pocketcam_bridge/` - installable Blender add-on
- `ios/PocketCam/` - SwiftUI + ARKit app
- `ios/project.yml` - XcodeGen project definition
- `.github/workflows/build-ios.yml` - unsigned IPA build
- `docs/PROTOCOL.md` - wire protocol and coordinate convention
- `tests/` - normal Python protocol tests and Blender runtime smoke test

PocketCam Bridge is an independent open-source project and is not affiliated with VirtuCamera or Blender Foundation.
