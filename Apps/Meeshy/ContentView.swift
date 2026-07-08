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
            .font(.system(size: 80, weight: .regular, design: .rounded))
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

            Button(role: .destructive, action: logoutTapped) { logoutButtonLabel }
                .buttonStyle(.bordered)
                .controlSize(.large)
                .padding(.horizontal)
                .accessibilityIdentifier("logoutButton")
                .accessibilityLabel("logout_button")
                .accessibilityHint("logout_hint")
                .hoverEffect()
                .confirmationDialog("logout_confirm_title", isPresented: $showLogoutConfirmation, titleVisibility: .visible) {
                    Button("logout_button_confirm", role: .destructive) { withAnimation { isLoggedIn = false } }
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

            Button(action: login) { loginButtonLabel }
                .buttonStyle(.borderedProminent)
                .controlSize(.large)
                .padding(.horizontal)
                .disabled(isLoading)
                .keyboardShortcut(.defaultAction)
                .accessibilityIdentifier("loginButton")
                .accessibilityLabel(isLoading ? "logging_in_status" : "login_button")
                .accessibilityHint("login_hint")
                .hoverEffect()
        }
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
        #if os(iOS)
        UIImpactFeedbackGenerator(style: .light).impactOccurred()
        #endif
        showLogoutConfirmation = true
    }

    @ViewBuilder
    private var loginButtonLabel: some View {
        Label {
            Text(isLoading ? "logging_in_status" : "login_button")
                .fontWeight(.semibold)
        } icon: {
            if isLoading {
                ProgressView()
            } else {
                Image(systemName: "lock.fill")
                    .accessibilityHidden(true)
            }
        }
        .frame(maxWidth: .infinity)
    }

    @ViewBuilder
    private var logoutButtonLabel: some View {
        Label {
            Text("logout_button")
                .fontWeight(.semibold)
        } icon: {
            let logoutIcon = Image(systemName: "rectangle.portrait.and.arrow.right")
                .accessibilityHidden(true)

            if #available(iOS 17.0, macOS 14.0, visionOS 1.0, *) {
                logoutIcon.symbolEffect(.bounce, value: showLogoutConfirmation)
            } else {
                logoutIcon
            }
        }
        .frame(maxWidth: .infinity)
    }
}
