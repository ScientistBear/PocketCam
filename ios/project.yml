name: PocketCam

options:
  bundleIdPrefix: com.pocketcambridge
  deploymentTarget:
    iOS: "18.0"
  xcodeVersion: "16.0"

settings:
  base:
    SWIFT_VERSION: "5.0"
    IPHONEOS_DEPLOYMENT_TARGET: "18.0"
    SUPPORTS_MACCATALYST: NO

targets:
  PocketCam:
    type: application
    platform: iOS
    sources:
      - path: PocketCam
        excludes:
          - Info.plist
    settings:
      base:
        PRODUCT_BUNDLE_IDENTIFIER: com.pocketcambridge.app
        PRODUCT_NAME: PocketCam
        INFOPLIST_FILE: PocketCam/Info.plist
        GENERATE_INFOPLIST_FILE: NO
        CODE_SIGN_STYLE: Automatic
        TARGETED_DEVICE_FAMILY: "1"
        ASSETCATALOG_COMPILER_APPICON_NAME: ""
    scheme:
      gatherCoverageData: false

