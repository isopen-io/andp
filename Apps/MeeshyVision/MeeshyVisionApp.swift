import SwiftUI

@main
struct MeeshyVisionApp: App {
    var body: some Scene {
        WindowGroup {
            ContentView()
        }
    }
}

struct ContentView: View {
    var body: some View {
        Text(NSLocalizedString("welcome_message", comment: ""))
            .padding()
            .accessibilityLabel(NSLocalizedString("welcome_message", comment: ""))
    }
}
