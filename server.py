name: Build unsigned iOS app

on:
  workflow_dispatch:
  push:
    branches:
      - main
    paths:
      - "ios/**"
      - ".github/workflows/build-ios.yml"

permissions:
  contents: read

jobs:
  build:
    runs-on: macos-15
    timeout-minutes: 20

    steps:
      - name: Check out source
        uses: actions/checkout@v4

      - name: Install XcodeGen
        run: brew install xcodegen

      - name: Generate Xcode project
        working-directory: ios
        run: xcodegen generate

      - name: Build device app without signing
        run: |
          xcodebuild \
            -project ios/PocketCam.xcodeproj \
            -scheme PocketCam \
            -configuration Release \
            -destination 'generic/platform=iOS' \
            -derivedDataPath "$RUNNER_TEMP/PocketCamDerivedData" \
            CODE_SIGNING_ALLOWED=NO \
            CODE_SIGNING_REQUIRED=NO \
            build

      - name: Package unsigned IPA
        run: |
          APP_PATH="$RUNNER_TEMP/PocketCamDerivedData/Build/Products/Release-iphoneos/PocketCam.app"
          test -d "$APP_PATH"
          mkdir -p "$RUNNER_TEMP/PocketCamIPA/Payload"
          cp -R "$APP_PATH" "$RUNNER_TEMP/PocketCamIPA/Payload/PocketCam.app"
          cd "$RUNNER_TEMP/PocketCamIPA"
          ditto -c -k --sequesterRsrc --keepParent Payload "$RUNNER_TEMP/PocketCam-unsigned.ipa"

      - name: Upload PocketCam IPA
        uses: actions/upload-artifact@v4
        with:
          name: PocketCam-unsigned
          path: ${{ runner.temp }}/PocketCam-unsigned.ipa
          if-no-files-found: error
          retention-days: 30

