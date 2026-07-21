import SwiftUI

@main
struct MeeshyWatchApp: App {
    var body: some Scene {
        WindowGroup {
            ContentView()
        }
    }
}

struct ContentView: View {
    var body: some View {
        VStack {
            Image(systemName: "shippingbox.fill")
                .font(.largeTitle)
                .foregroundStyle(.tint)
                .accessibilityHidden(true)

            Text(NSLocalizedString("welcome_message", comment: ""))
                .padding()
                .accessibilityLabel(NSLocalizedString("welcome_message", comment: ""))
        }
        .accessibilityElement(children: .combine)
    }
}
