import SwiftUI

@main
struct MeeshyTVApp: App {
    var body: some Scene {
        WindowGroup {
            ContentView()
        }
    }
}

struct ContentView: View {
    var body: some View {
        VStack(spacing: 20) {
            Image(systemName: "shippingbox.fill")
                .font(.system(.largeTitle, design: .rounded))
                .scaleEffect(2.5)
                .foregroundStyle(.tint)
                .accessibilityHidden(true)

            Text(NSLocalizedString("welcome_message", comment: ""))
                .font(.title)
                .accessibilityLabel(NSLocalizedString("welcome_message", comment: ""))
        }
        .accessibilityElement(children: .combine)
    }
}
