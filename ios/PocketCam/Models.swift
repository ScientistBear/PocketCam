import Foundation

enum BridgeConnectionState: Equatable {
    case disconnected
    case connecting
    case connected
    case failed(String)

    var label: String {
        switch self {
        case .disconnected:
            return "Disconnected"
        case .connecting:
            return "Connecting"
        case .connected:
            return "Connected"
        case .failed(let message):
            return message
        }
    }

    var isConnected: Bool {
        if case .connected = self { return true }
        return false
    }
}

struct PoseSample {
    let sequence: UInt64
    let timestamp: TimeInterval
    let position: [Float]
    let rotation: [Float]
    let tracking: String
}

struct BridgeStatus: Decodable, Equatable {
    var recording: Bool
    var tracking: String
    var availableCameras: [String]
    var selectedCamera: String?
    var movementScale: Double
    var smoothing: Double
    var lensMM: Double
    var message: String

    static let empty = BridgeStatus(
        recording: false,
        tracking: "Waiting for Blender",
        availableCameras: [],
        selectedCamera: nil,
        movementScale: 1.0,
        smoothing: 0.18,
        lensMM: 18.0,
        message: ""
    )

    private enum CodingKeys: String, CodingKey {
        case recording
        case tracking
        case availableCameras = "available_cameras"
        case selectedCamera = "selected_camera"
        case movementScale = "movement_scale"
        case smoothing
        case lensMM = "lens_mm"
        case message
    }

    init(
        recording: Bool,
        tracking: String,
        availableCameras: [String],
        selectedCamera: String?,
        movementScale: Double,
        smoothing: Double,
        lensMM: Double,
        message: String
    ) {
        self.recording = recording
        self.tracking = tracking
        self.availableCameras = availableCameras
        self.selectedCamera = selectedCamera
        self.movementScale = movementScale
        self.smoothing = smoothing
        self.lensMM = lensMM
        self.message = message
    }

    init(from decoder: Decoder) throws {
        let values = try decoder.container(keyedBy: CodingKeys.self)
        recording = try values.decodeIfPresent(Bool.self, forKey: .recording) ?? false
        tracking = try values.decodeIfPresent(String.self, forKey: .tracking) ?? "Connected"
        availableCameras = try values.decodeIfPresent([String].self, forKey: .availableCameras) ?? []
        selectedCamera = try values.decodeIfPresent(String.self, forKey: .selectedCamera)
        movementScale = try values.decodeIfPresent(Double.self, forKey: .movementScale) ?? 1.0
        smoothing = try values.decodeIfPresent(Double.self, forKey: .smoothing) ?? 0.18
        lensMM = try values.decodeIfPresent(Double.self, forKey: .lensMM) ?? 18.0
        message = try values.decodeIfPresent(String.self, forKey: .message) ?? ""
    }
}
