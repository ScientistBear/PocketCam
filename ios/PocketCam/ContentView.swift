import Foundation
import SwiftUI

struct ContentView: View {
    @EnvironmentObject private var model: AppModel
    @EnvironmentObject private var bridge: BridgeConnection
    @EnvironmentObject private var tracker: ARTrackingService
    @Environment(\.scenePhase) private var scenePhase
    @FocusState private var focusedField: Field?

    private enum Field: Hashable {
        case host
        case port
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 16) {
                    hero
                    connectionCard
                    trackingCard
                    cameraCard
                    tuningCard
                    footer
                }
                .padding(.horizontal, 18)
                .padding(.vertical, 14)
            }
            .background(Color(red: 0.035, green: 0.045, blue: 0.065).ignoresSafeArea())
            .toolbar {
                ToolbarItemGroup(placement: .keyboard) {
                    Spacer()
                    Button("Done") { focusedField = nil }
                }
            }
        }
        .onChange(of: model.movementScale) { _, _ in model.pushSettings() }
        .onChange(of: model.smoothing) { _, _ in model.pushSettings() }
        .onChange(of: model.lensMM) { _, _ in model.pushSettings() }
        .onChange(of: scenePhase) { _, phase in
            if phase != .active && tracker.isRunning {
                tracker.stop()
            }
        }
    }

    private var hero: some View {
        HStack(spacing: 15) {
            ZStack {
                Circle()
                    .fill(
                        LinearGradient(
                            colors: [.cyan, .blue, .indigo],
                            startPoint: .topLeading,
                            endPoint: .bottomTrailing
                        )
                    )
                    .frame(width: 62, height: 62)
                Image(systemName: "viewfinder.circle.fill")
                    .font(.system(size: 34, weight: .semibold))
                    .foregroundStyle(.white)
            }
            VStack(alignment: .leading, spacing: 4) {
                Text("PocketCam")
                    .font(.system(size: 30, weight: .bold, design: .rounded))
                Text("Your iPhone, now a Blender camera")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            }
            Spacer()
        }
        .padding(.vertical, 8)
    }

    private var connectionCard: some View {
        Card(title: "Blender Connection", icon: "network") {
            VStack(spacing: 12) {
                HStack(spacing: 10) {
                    TextField("Blender IP (for example 192.168.1.40)", text: $model.host)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .keyboardType(.numbersAndPunctuation)
                        .focused($focusedField, equals: .host)
                        .fieldStyle()

                    TextField("Port", text: $model.portText)
                        .keyboardType(.numberPad)
                        .focused($focusedField, equals: .port)
                        .frame(width: 78)
                        .fieldStyle()
                }

                Button(action: model.toggleConnection) {
                    HStack {
                        Image(systemName: bridge.state.isConnected ? "xmark.circle.fill" : "bolt.horizontal.circle.fill")
                        Text(bridge.state.isConnected ? "Disconnect" : "Connect to Blender")
                            .fontWeight(.semibold)
                    }
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 12)
                }
                .buttonStyle(.borderedProminent)
                .tint(bridge.state.isConnected ? .gray : .blue)

                StatusLine(
                    text: bridge.state.label,
                    color: connectionColor,
                    detail: bridge.serverStatus.message
                )
            }
        }
    }

    private var trackingCard: some View {
        Card(title: "Motion Capture", icon: "gyroscope") {
            VStack(spacing: 12) {
                HStack {
                    VStack(alignment: .leading, spacing: 4) {
                        Text(tracker.trackingDescription)
                            .font(.headline)
                        Text("ARKit 6DoF pose at \(Int(model.sendRate)) fps")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    Spacer()
                    Circle()
                        .fill(tracker.trackingIsGood ? Color.green : (tracker.isRunning ? .orange : .gray))
                        .frame(width: 12, height: 12)
                        .shadow(color: tracker.trackingIsGood ? .green.opacity(0.7) : .clear, radius: 6)
                }

                Button(action: model.toggleTracking) {
                    Label(
                        tracker.isRunning ? "Stop Tracking" : "Start Tracking",
                        systemImage: tracker.isRunning ? "stop.fill" : "play.fill"
                    )
                    .fontWeight(.semibold)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 10)
                }
                .buttonStyle(.borderedProminent)
                .tint(tracker.isRunning ? .orange : .green)
                .disabled(!bridge.state.isConnected)

                HStack(spacing: 10) {
                    Button(action: model.recenter) {
                        Label("Recenter", systemImage: "scope")
                            .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.bordered)

                    Button(action: model.toggleRecording) {
                        Label(
                            bridge.serverStatus.recording ? "Stop Take" : "Record Take",
                            systemImage: bridge.serverStatus.recording ? "stop.circle.fill" : "record.circle"
                        )
                        .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.borderedProminent)
                    .tint(bridge.serverStatus.recording ? .red : .indigo)
                }
                .disabled(!bridge.state.isConnected || !tracker.isRunning)
            }
        }
    }

    @ViewBuilder
    private var cameraCard: some View {
        if !bridge.serverStatus.availableCameras.isEmpty {
            Card(title: "Scene Camera", icon: "video.fill") {
                Picker("Active camera", selection: $model.selectedCamera) {
                    ForEach(bridge.serverStatus.availableCameras, id: \.self) { camera in
                        Text(camera).tag(camera)
                    }
                }
                .pickerStyle(.menu)
                .frame(maxWidth: .infinity, alignment: .leading)
                .onChange(of: model.selectedCamera) { oldValue, newValue in
                    if oldValue != newValue, !newValue.isEmpty {
                        model.chooseCamera(newValue)
                    }
                }
            }
        }
    }

    private var tuningCard: some View {
        Card(title: "Camera Feel", icon: "slider.horizontal.3") {
            VStack(spacing: 17) {
                ValueSlider(
                    title: "Movement scale",
                    valueText: String(format: "%.2fx", model.movementScale),
                    value: $model.movementScale,
                    range: 0.1...10.0
                )
                ValueSlider(
                    title: "Smoothing",
                    valueText: "\(Int(model.smoothing * 100))%",
                    value: $model.smoothing,
                    range: 0.0...0.85
                )
                ValueSlider(
                    title: "Lens",
                    valueText: "\(Int(model.lensMM)) mm",
                    value: $model.lensMM,
                    range: 8.0...120.0
                )
                ValueSlider(
                    title: "Send rate",
                    valueText: "\(Int(model.sendRate)) fps",
                    value: $model.sendRate,
                    range: 15.0...60.0,
                    step: 15.0
                )
            }
        }
    }

    private var footer: some View {
        Text("Keep the phone and Blender PC on the same private Wi-Fi. Start the PocketCam server in Blender before connecting.")
            .font(.caption)
            .foregroundStyle(.secondary)
            .multilineTextAlignment(.center)
            .padding(.horizontal, 12)
            .padding(.bottom, 20)
    }

    private var connectionColor: Color {
        switch bridge.state {
        case .connected: return .green
        case .connecting: return .orange
        case .failed: return .red
        case .disconnected: return .gray
        }
    }
}

private struct Card<Content: View>: View {
    let title: String
    let icon: String
    let content: Content

    init(title: String, icon: String, @ViewBuilder content: () -> Content) {
        self.title = title
        self.icon = icon
        self.content = content()
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            Label(title, systemImage: icon)
                .font(.headline)
                .foregroundStyle(.white.opacity(0.95))
            content
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(
            RoundedRectangle(cornerRadius: 20, style: .continuous)
                .fill(Color.white.opacity(0.065))
                .overlay(
                    RoundedRectangle(cornerRadius: 20, style: .continuous)
                        .stroke(Color.white.opacity(0.08), lineWidth: 1)
                )
        )
    }
}

private struct StatusLine: View {
    let text: String
    let color: Color
    let detail: String

    var body: some View {
        HStack(alignment: .top, spacing: 9) {
            Circle()
                .fill(color)
                .frame(width: 9, height: 9)
                .padding(.top, 4)
            VStack(alignment: .leading, spacing: 2) {
                Text(text)
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(color)
                    .lineLimit(2)
                if !detail.isEmpty {
                    Text(detail)
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
            }
            Spacer()
        }
    }
}

private struct ValueSlider: View {
    let title: String
    let valueText: String
    @Binding var value: Double
    let range: ClosedRange<Double>
    var step: Double = 0.01

    var body: some View {
        VStack(spacing: 7) {
            HStack {
                Text(title)
                    .font(.subheadline)
                Spacer()
                Text(valueText)
                    .font(.subheadline.monospacedDigit().weight(.semibold))
                    .foregroundStyle(.cyan)
            }
            Slider(value: $value, in: range, step: step)
                .tint(.cyan)
        }
    }
}

private extension View {
    func fieldStyle() -> some View {
        self
            .padding(.horizontal, 11)
            .padding(.vertical, 10)
            .background(Color.black.opacity(0.25), in: RoundedRectangle(cornerRadius: 10))
            .overlay(
                RoundedRectangle(cornerRadius: 10)
                    .stroke(Color.white.opacity(0.1), lineWidth: 1)
            )
    }
}
