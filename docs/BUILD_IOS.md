# Building and installing PocketCam on iPhone

PocketCam is a native SwiftUI/ARKit app. Apple only ships the iPhone SDK and code-signing tools with Xcode on macOS, so Windows can prepare the source and run Blender but cannot perform the final native iOS build locally.

## Windows: GitHub Actions build

The repository includes `.github/workflows/build-ios.yml`. It creates a normal device build on a hosted macOS runner, wraps `PocketCam.app` in an IPA, and publishes it as the `PocketCam-unsigned` workflow artifact.

1. Create a GitHub repository and add this project's files.
2. In GitHub, select **Actions > Build unsigned iOS app > Run workflow**.
3. Open the finished workflow run and download the `PocketCam-unsigned` artifact.
4. Extract the downloaded artifact zip.
5. Sign and install `PocketCam-unsigned.ipa` with [Sideloadly](https://sideloadly.io/) or [AltStore Classic](https://faq.altstore.io/altstore-classic/how-to-install-altstore-windows).

The workflow deliberately does not ask for an Apple ID, certificate, or password. Never place those credentials in a public repository or workflow file.

### Free-account limitation

[Apple documents](https://developer.apple.com/help/account/basics/about-your-developer-account/) that a free Personal Team profile expires seven days after issuance. You can install up to three apps per device this way; after expiration, rebuild or re-sign and reinstall PocketCam. A paid Apple Developer Program membership is not required for personal device testing, but it removes several free-account limits.

## macOS: build directly with Xcode

1. Install current Xcode and XcodeGen (`brew install xcodegen`).
2. In Terminal, change to the `ios` directory.
3. Run `xcodegen generate`.
4. Open `PocketCam.xcodeproj`.
5. Select the **PocketCam** target, then **Signing & Capabilities**.
6. Choose your Apple ID's Personal Team and change the bundle identifier if Xcode says it is already taken.
7. Connect and trust the iPhone, select it as the run destination, and press **Run**.
8. If iOS asks, enable Developer Mode and trust the developer profile in Settings.

## Why the deployment target is iOS 18

The app intentionally uses stable ARKit and Network framework APIs rather than tying the project to a beta-only SDK. Newer iOS versions remain backward compatible with that deployment target. The app still gets the iPhone 16 Pro's normal ARKit world-tracking data.

## Permissions

PocketCam asks for:

- **Camera** - ARKit uses the rear cameras and motion sensors to estimate the device pose.
- **Local Network** - the app opens a direct TCP connection to the Blender PC.

No internet service, analytics SDK, login, or cloud storage is used by the app.
