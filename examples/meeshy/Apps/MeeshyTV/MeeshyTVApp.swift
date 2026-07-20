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
        VStack {
            Image(systemName: "shippingbox.fill")
                .font(.system(size: 100))
                .foregroundStyle(.tint)
            Text("welcome_message")
                .font(.title)
        }
    }
}
