import SwiftUI

@main
struct PocketCamApp: App {
    @StateObject private var model = AppModel()

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(model)
                .environmentObject(model.bridge)
                .environmentObject(model.tracker)
                .preferredColorScheme(.dark)
        }
    }
}
