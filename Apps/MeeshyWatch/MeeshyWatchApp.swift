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
            Text("welcome_message")
                .padding()
        }
    }
}
