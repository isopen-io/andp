import SwiftUI

struct ContentView: View {
    var body: some View {
        VStack(spacing: 24) {
            Spacer()

            Image(systemName: "shippingbox.fill")
                .font(.system(size: 80, weight: .regular, design: .rounded))
                .foregroundStyle(.tint)
                .accessibilityHidden(true)

            Text("welcome_message")
                .font(.title2.bold())
                .multilineTextAlignment(.center)
                .accessibilityLabel(Text("welcome_message"))

            Button(action: {}) {
                Text("login_button")
                    .fontWeight(.semibold)
                    .frame(maxWidth: .infinity)
                    .accessibilityLabel(Text("login_button"))
            }
            .buttonStyle(.borderedProminent)
            .controlSize(.large)
            .padding(.horizontal)
            .accessibilityIdentifier("loginButton")

            Spacer()
        }
        .padding()
    }
}
