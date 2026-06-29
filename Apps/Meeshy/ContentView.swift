import SwiftUI
#if os(iOS)
import UIKit
#endif

struct ContentView: View {
    @State private var isLoggedIn = false
    @State private var isLoading = false
    @State private var showLogoutConfirmation = false
    @State private var iconScale = 0.5
    @State private var iconOpacity = 0.0

    var body: some View {
        VStack(spacing: 24) {
            Spacer()

            Image(systemName: "shippingbox.fill")
                .font(.system(size: 80, weight: .regular, design: .rounded))
                .foregroundStyle(.tint)
                .pulseEffect(isActive: isLoading)
                .scaleEffect(iconScale)
                .opacity(iconOpacity)
                .accessibilityHidden(true)
                .onAppear {
                    withAnimation(.spring(response: 0.6, dampingFraction: 0.7)) {
                        iconScale = 1.0
                        iconOpacity = 1.0
                    }
                }

            if isLoggedIn {
                Text("logged_in_message")
                    .font(.title2.bold())
                    .multilineTextAlignment(.center)
                    .accessibilityAddTraits(.isHeader)

                Button(role: .destructive, action: {
                    showLogoutConfirmation = true
                }) {
                    Text("logout_button")
                        .fontWeight(.semibold)
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.bordered)
                .controlSize(.large)
                .padding(.horizontal)
                .accessibilityLabel(Text("logout_button"))
                .confirmationDialog("logout_confirm_title", isPresented: $showLogoutConfirmation, titleVisibility: .visible) {
                    Button("logout_button_confirm", role: .destructive) {
                        withAnimation {
                            isLoggedIn = false
                        }
                    }
                    Button("cancel_button", role: .cancel) {}
                }
            } else {
                Text("welcome_message")
                    .font(.title2.bold())
                    .multilineTextAlignment(.center)
                    .accessibilityAddTraits(.isHeader)

                Button(action: login) {
                    HStack {
                        if isLoading {
                            ProgressView()
                                .padding(.trailing, 8)
                                .accessibilityHidden(true)
                        }
                        Text("login_button")
                            .fontWeight(.semibold)
                    }
                    .frame(maxWidth: .infinity)
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.large)
                .padding(.horizontal)
                .disabled(isLoading)
                .keyboardShortcut(.defaultAction)
                .accessibilityIdentifier("loginButton")
                .accessibilityLabel(Text(isLoading ? "logging_in_label" : "login_button"))
                .accessibilityHint(Text("login_hint"))
            }

            Spacer()
        }
        .padding()
    }

    private func login() {
        isLoading = true
        // Simulate login
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.5) {
            withAnimation {
                isLoading = false
                isLoggedIn = true
                #if os(iOS)
                UINotificationFeedbackGenerator().notificationOccurred(.success)
                #endif
            }
        }
    }
}

extension View {
    @ViewBuilder
    func pulseEffect(isActive: Bool) -> some View {
        if #available(iOS 17.0, *) {
            self.symbolEffect(.pulse, isActive: isActive)
        } else {
            self
        }
    }
}
