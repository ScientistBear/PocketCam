import ARKit
import Combine
import Foundation
import simd

final class ARTrackingService: NSObject, ObservableObject, ARSessionDelegate {
    @Published private(set) var isRunning = false
    @Published private(set) var trackingDescription = "Stopped"
    @Published private(set) var trackingIsGood = false
    @Published private(set) var poseFPS = 0.0
    @Published private(set) var poseCount: UInt64 = 0

    let session = ARSession()
    var onPose: ((PoseSample) -> Void)?
    var sendRate: Double = 60.0

    private let delegateQueue = DispatchQueue(label: "PocketCam.ARKit", qos: .userInteractive)
    private var sequence: UInt64 = 0
    private var lastSentTimestamp: TimeInterval = 0
    private var lastTrackingDescription = ""
    private var rateWindowStart: TimeInterval = 0
    private var rateWindowFrames = 0

    override init() {
        super.init()
        session.delegate = self
        session.delegateQueue = delegateQueue
    }

    func start() {
        guard ARWorldTrackingConfiguration.isSupported else {
            publishTracking("AR world tracking is unavailable", good: false)
            return
        }
        let configuration = ARWorldTrackingConfiguration()
        configuration.worldAlignment = .gravity
        configuration.isAutoFocusEnabled = true
        sequence = 0
        lastSentTimestamp = 0
        rateWindowStart = 0
        rateWindowFrames = 0
        session.run(configuration, options: [.resetTracking, .removeExistingAnchors])
        DispatchQueue.main.async {
            self.isRunning = true
            self.trackingDescription = "Initializing"
            self.trackingIsGood = false
            self.poseFPS = 0
            self.poseCount = 0
        }
    }

    func stop() {
        session.pause()
        DispatchQueue.main.async {
            self.isRunning = false
            self.trackingDescription = "Stopped"
            self.trackingIsGood = false
        }
    }

    func session(_ session: ARSession, didUpdate frame: ARFrame) {
        let quality = describe(frame.camera.trackingState)
        if quality.text != lastTrackingDescription {
            lastTrackingDescription = quality.text
            publishTracking(quality.text, good: quality.good)
        }

        let minimumInterval = 1.0 / max(15.0, min(60.0, sendRate))
        guard frame.timestamp - lastSentTimestamp >= minimumInterval else { return }
        lastSentTimestamp = frame.timestamp
        sequence &+= 1

        let transform = frame.camera.transform
        let translation = transform.columns.3
        let quaternion = simd_normalize(simd_quatf(transform))
        onPose?(
            PoseSample(
                sequence: sequence,
                timestamp: frame.timestamp,
                position: [translation.x, translation.y, translation.z],
                rotation: [
                    quaternion.vector.x,
                    quaternion.vector.y,
                    quaternion.vector.z,
                    quaternion.vector.w
                ],
                tracking: quality.text
            )
        )
        rateWindowFrames += 1
        if rateWindowStart == 0 {
            rateWindowStart = frame.timestamp
        }
        let elapsed = frame.timestamp - rateWindowStart
        if elapsed >= 0.75 {
            let measuredFPS = Double(rateWindowFrames) / elapsed
            let count = sequence
            rateWindowFrames = 0
            rateWindowStart = frame.timestamp
            DispatchQueue.main.async {
                self.poseFPS = measuredFPS
                self.poseCount = count
            }
        }
    }

    func session(_ session: ARSession, cameraDidChangeTrackingState camera: ARCamera) {
        let quality = describe(camera.trackingState)
        lastTrackingDescription = quality.text
        publishTracking(quality.text, good: quality.good)
    }

    func session(_ session: ARSession, didFailWithError error: Error) {
        publishTracking("Tracking failed: \(error.localizedDescription)", good: false)
    }

    func sessionWasInterrupted(_ session: ARSession) {
        publishTracking("Tracking interrupted", good: false)
    }

    func sessionInterruptionEnded(_ session: ARSession) {
        publishTracking("Restarting tracking", good: false)
    }

    private func describe(_ state: ARCamera.TrackingState) -> (text: String, good: Bool) {
        switch state {
        case .normal:
            return ("Tracking", true)
        case .notAvailable:
            return ("Tracking unavailable", false)
        case .limited(let reason):
            switch reason {
            case .initializing:
                return ("Initializing", false)
            case .excessiveMotion:
                return ("Move more slowly", false)
            case .insufficientFeatures:
                return ("Point at a detailed surface", false)
            case .relocalizing:
                return ("Relocalizing", false)
            @unknown default:
                return ("Tracking limited", false)
            }
        }
    }

    private func publishTracking(_ description: String, good: Bool) {
        DispatchQueue.main.async {
            self.trackingDescription = description
            self.trackingIsGood = good
        }
    }
}
