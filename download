import Combine
import Foundation
import Network
import UIKit

final class BridgeConnection: ObservableObject {
    @Published private(set) var state: BridgeConnectionState = .disconnected
    @Published private(set) var serverStatus: BridgeStatus = .empty
    @Published private(set) var lastError = ""

    private let queue = DispatchQueue(label: "PocketCam.Network", qos: .userInteractive)
    private var connection: NWConnection?
    private var receiveBuffer = Data()

    func connect(host: String, port: UInt16) {
        let cleanHost = host.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !cleanHost.isEmpty, let endpointPort = NWEndpoint.Port(rawValue: port) else {
            publish { self.state = .failed("Enter a valid Blender address") }
            return
        }

        publish {
            self.state = .connecting
            self.lastError = ""
        }

        queue.async { [weak self] in
            guard let self else { return }
            self.connection?.cancel()
            self.receiveBuffer.removeAll(keepingCapacity: true)

            let parameters = NWParameters.tcp
            parameters.prohibitExpensivePaths = false
            let newConnection = NWConnection(
                host: NWEndpoint.Host(cleanHost),
                port: endpointPort,
                using: parameters
            )
            self.connection = newConnection
            newConnection.stateUpdateHandler = { [weak self, weak newConnection] newState in
                guard let self, let newConnection else { return }
                self.handleState(newState, for: newConnection)
            }
            newConnection.start(queue: self.queue)
            self.receiveNext(on: newConnection)
        }
    }

    func disconnect() {
        queue.async { [weak self] in
            guard let self else { return }
            self.connection?.cancel()
            self.connection = nil
            self.receiveBuffer.removeAll(keepingCapacity: false)
            self.publish {
                self.state = .disconnected
                self.serverStatus = .empty
            }
        }
    }

    func sendPose(_ pose: PoseSample) {
        sendJSON([
            "type": "pose",
            "seq": pose.sequence,
            "timestamp": pose.timestamp,
            "position": pose.position,
            "rotation": pose.rotation,
            "tracking": pose.tracking
        ])
    }

    func sendCommand(_ command: String) {
        sendJSON(["type": "command", "command": command])
    }

    func sendSettings(movementScale: Double, smoothing: Double, lensMM: Double) {
        sendJSON([
            "type": "settings",
            "movement_scale": movementScale,
            "smoothing": smoothing,
            "lens_mm": lensMM
        ])
    }

    func selectCamera(named name: String) {
        sendJSON(["type": "select_camera", "name": name])
    }

    func ping() {
        sendJSON(["type": "ping", "timestamp": Date().timeIntervalSince1970])
    }

    private func sendHello() {
        sendJSON([
            "type": "hello",
            "protocol": 1,
            "client": "PocketCam iOS",
            "device": UIDevice.current.name,
            "app_version": "0.1.0"
        ])
    }

    private func sendJSON(_ object: [String: Any]) {
        guard JSONSerialization.isValidJSONObject(object),
              var data = try? JSONSerialization.data(withJSONObject: object) else {
            return
        }
        data.append(0x0A)
        queue.async { [weak self] in
            guard let self, let connection = self.connection else { return }
            connection.send(content: data, completion: .contentProcessed { [weak self] error in
                guard let self, let error else { return }
                self.fail("Send failed: \(error.localizedDescription)")
            })
        }
    }

    private func handleState(_ newState: NWConnection.State, for candidate: NWConnection) {
        guard connection === candidate else { return }
        switch newState {
        case .ready:
            publish { self.state = .connected }
            sendHello()
            ping()
        case .waiting(let error):
            publish {
                self.state = .connecting
                self.lastError = error.localizedDescription
            }
        case .failed(let error):
            fail("Connection failed: \(error.localizedDescription)")
        case .cancelled:
            publish {
                self.state = .disconnected
            }
        default:
            break
        }
    }

    private func receiveNext(on candidate: NWConnection) {
        candidate.receive(minimumIncompleteLength: 1, maximumLength: 64 * 1024) {
            [weak self, weak candidate] data, _, isComplete, error in
            guard let self, let candidate, self.connection === candidate else { return }
            if let data, !data.isEmpty {
                self.receiveBuffer.append(data)
                self.consumeLines()
            }
            if let error {
                self.fail("Receive failed: \(error.localizedDescription)")
                return
            }
            if isComplete {
                self.fail("Blender closed the connection")
                return
            }
            self.receiveNext(on: candidate)
        }
    }

    private func consumeLines() {
        while let newline = receiveBuffer.firstIndex(of: 0x0A) {
            let line = Data(receiveBuffer[..<newline])
            receiveBuffer.removeSubrange(...newline)
            guard !line.isEmpty,
                  let envelope = try? JSONSerialization.jsonObject(with: line) as? [String: Any],
                  let type = envelope["type"] as? String else {
                continue
            }
            if type == "status", let status = try? JSONDecoder().decode(BridgeStatus.self, from: line) {
                publish {
                    self.serverStatus = status
                    if !status.message.isEmpty {
                        self.lastError = status.message
                    }
                }
            }
        }
    }

    private func fail(_ message: String) {
        publish {
            self.lastError = message
            self.state = .failed(message)
        }
    }

    private func publish(_ update: @escaping () -> Void) {
        DispatchQueue.main.async(execute: update)
    }
}
