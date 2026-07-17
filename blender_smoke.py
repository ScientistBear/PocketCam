import Combine
import Foundation

final class AppModel: ObservableObject {
    let bridge = BridgeConnection()
    let tracker = ARTrackingService()

    @Published var host: String {
        didSet { UserDefaults.standard.set(host, forKey: "blenderHost") }
    }
    @Published var portText: String {
        didSet { UserDefaults.standard.set(portText, forKey: "blenderPort") }
    }
    @Published var movementScale = 1.0
    @Published var smoothing = 0.18
    @Published var lensMM = 18.0
    @Published var sendRate = 60.0 {
        didSet { tracker.sendRate = sendRate }
    }
    @Published var selectedCamera = ""

    private var subscriptions = Set<AnyCancellable>()

    init() {
        host = UserDefaults.standard.string(forKey: "blenderHost") ?? ""
        portText = UserDefaults.standard.string(forKey: "blenderPort") ?? "8766"
        tracker.sendRate = sendRate
        tracker.onPose = { [weak bridge = self.bridge] pose in
            bridge?.sendPose(pose)
        }

        bridge.$serverStatus
            .receive(on: RunLoop.main)
            .sink { [weak self] status in
                guard let self, status != .empty else { return }
                self.movementScale = status.movementScale
                self.smoothing = status.smoothing
                self.lensMM = status.lensMM
                if let camera = status.selectedCamera {
                    self.selectedCamera = camera
                }
            }
            .store(in: &subscriptions)
    }

    func toggleConnection() {
        if bridge.state.isConnected || bridge.state == .connecting {
            tracker.stop()
            bridge.disconnect()
            return
        }
        guard let port = UInt16(portText) else { return }
        bridge.connect(host: host, port: port)
    }

    func toggleTracking() {
        if tracker.isRunning {
            tracker.stop()
        } else {
            tracker.start()
        }
    }

    func recenter() {
        bridge.sendCommand("recenter")
    }

    func toggleRecording() {
        bridge.sendCommand(bridge.serverStatus.recording ? "record_stop" : "record_start")
    }

    func pushSettings() {
        guard bridge.state.isConnected else { return }
        bridge.sendSettings(
            movementScale: movementScale,
            smoothing: smoothing,
            lensMM: lensMM
        )
    }

    func chooseCamera(_ camera: String) {
        selectedCamera = camera
        bridge.selectCamera(named: camera)
    }
}
