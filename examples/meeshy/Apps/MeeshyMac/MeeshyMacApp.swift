import SwiftUI

@main
struct MeeshyMacApp: App {
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
