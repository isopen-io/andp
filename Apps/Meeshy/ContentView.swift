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
                Label("logout_button", systemImage: "rectangle.portrait.and.arrow.right")
                    .fontWeight(.semibold)
                    .frame(maxWidth: .infinity)
            }
            .hoverEffect()
            .buttonStyle(.bordered)
            .controlSize(.large)
            .padding(.horizontal)
            .accessibilityHint(Text("logout_hint"))
            .confirmationDialog("logout_confirm_title", isPresented: $showLogoutConfirmation, titleVisibility: .visible) {
                Button("logout_button_confirm", role: .destructive) {
                    withAnimation {
                        isLoggedIn = false
                    }
                }
                .hoverEffect()

                Button("cancel_button", role: .cancel) {}
                    .hoverEffect()
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
                loginButtonLabel
            }
            .hoverEffect()
            .buttonStyle(.borderedProminent)
            .controlSize(.large)
            .padding(.horizontal)
            .disabled(isLoading)
            .keyboardShortcut(.defaultAction)
            .accessibilityIdentifier("loginButton")
            .accessibilityHint(Text("login_hint"))
        }
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
            }
        }
        .frame(maxWidth: .infinity)
        .accessibilityElement(children: .combine)
        .accessibilityLabel(isLoading ? Text("logging_in_status") : Text("login_button"))
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
