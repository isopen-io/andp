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

            logoView
                .onAppear {
                    withAnimation(.spring(response: 0.6, dampingFraction: 0.7)) {
                        iconScale = 1.0
                        iconOpacity = 1.0
                    }
                }

            if isLoggedIn {
                loggedInView
                    .transition(.opacity.combined(with: .scale))
            } else {
                loginView
                    .transition(.opacity.combined(with: .scale))
            }

            Spacer()
        }
        .padding()
    }

    @ViewBuilder
    private var logoView: some View {
        let logo = Image(systemName: "shippingbox.fill")
            .font(.system(.largeTitle, design: .rounded))
            .imageScale(.large)
            .foregroundStyle(.tint)
            .scaleEffect(iconScale)
            .opacity(iconOpacity)
            .accessibilityHidden(true)

        if #available(iOS 17.0, macOS 14.0, visionOS 1.0, *) {
            logo.symbolEffect(.pulse, isActive: isLoading)
        } else {
            logo
        }
    }

    private var loggedInView: some View {
        VStack(spacing: 24) {
            Text("logged_in_message")
                .font(.title2.bold())
                .multilineTextAlignment(.center)
                .accessibilityAddTraits(.isHeader)

            Button(role: .destructive, action: logoutTapped) {
                logoutLabel
            }
            .buttonStyle(.bordered)
            .controlSize(.large)
            .padding(.horizontal)
            .hoverEffect()
            .accessibilityLabel(Text("logout_button"))
            .accessibilityHint(Text("logout_hint"))
            .confirmationDialog("logout_confirm_title", isPresented: $showLogoutConfirmation, titleVisibility: .visible) {
                Button("logout_button_confirm", role: .destructive) {
                    withAnimation {
                        isLoggedIn = false
                    }
                }
                Button("cancel_button", role: .cancel) {}
            }
        }
    }

    private var loginView: some View {
        VStack(spacing: 24) {
            Text("welcome_message")
                .font(.title2.bold())
                .multilineTextAlignment(.center)
                .accessibilityAddTraits(.isHeader)

            Button(action: login) {
                loginLabel
            }
            .buttonStyle(.borderedProminent)
            .controlSize(.large)
            .padding(.horizontal)
            .hoverEffect()
            .disabled(isLoading)
            .keyboardShortcut(.defaultAction)
            .accessibilityIdentifier("loginButton")
            .accessibilityLabel(isLoading ? Text("logging_in_status") : Text("login_button"))
            .accessibilityHint(Text("login_hint"))
        }
    }

    @ViewBuilder
    private var loginLabel: some View {
        Group {
            if isLoading {
                Label {
                    Text("logging_in_status")
                } icon: {
                    ProgressView()
                }
            } else {
                Label("login_button", systemImage: "lock.fill")
            }
        }
        .fontWeight(.semibold)
        .frame(maxWidth: .infinity)
    }

    @ViewBuilder
    private var logoutLabel: some View {
        Label("logout_button", systemImage: "rectangle.portrait.and.arrow.right")
            .fontWeight(.semibold)
            .frame(maxWidth: .infinity)
    }

    private func login() {
        #if os(iOS)
        UIImpactFeedbackGenerator(style: .medium).impactOccurred()
        #endif
        isLoading = true
        // Simulate login
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.5) {
            #if os(iOS)
            let generator = UINotificationFeedbackGenerator()
            generator.notificationOccurred(.success)
            #endif

            withAnimation {
                isLoading = false
                isLoggedIn = true
            }
        }
    }

    private func logoutTapped() {
        showLogoutConfirmation = true
    }
}
