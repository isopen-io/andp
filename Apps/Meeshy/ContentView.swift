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
                VStack(spacing: 24) {
                    Text("logged_in_message")
                        .font(.title2.bold())
                        .multilineTextAlignment(.center)
                        .accessibilityAddTraits(.isHeader)

                Button(role: .destructive, action: logoutTapped) {
                    HStack {
                        Image(systemName: "rectangle.portrait.and.arrow.right")
                            .accessibilityHidden(true)
                        Text("logout_button")
                            .fontWeight(.semibold)
                    }
                    .frame(maxWidth: .infinity)
                }
                .buttonStyle(.bordered)
                .controlSize(.large)
                .padding(.horizontal)
                .accessibilityLabel(Text("logout_button"))
                .hoverEffect()
                .confirmationDialog("logout_confirm_title", isPresented: $showLogoutConfirmation, titleVisibility: .visible) {
                    Button("logout_button_confirm", role: .destructive) {
                        withAnimation {
                            isLoggedIn = false
                        }
                        Button("cancel_button", role: .cancel) {}
                    }
                }
                .transition(.opacity.combined(with: .scale))
            } else {
                VStack(spacing: 24) {
                    Text("welcome_message")
                        .font(.title2.bold())
                        .multilineTextAlignment(.center)
                        .accessibilityAddTraits(.isHeader)

                Button(action: login) {
                    HStack {
                        if isLoading {
                            ProgressView()
                                .padding(.trailing, 8)
                        } else {
                            Image(systemName: "lock.fill")
                                .padding(.trailing, 4)
                                .accessibilityHidden(true)
                        }
                        .frame(maxWidth: .infinity)
                    }
                    .hoverEffect()
                    .buttonStyle(.borderedProminent)
                    .controlSize(.large)
                    .padding(.horizontal)
                    .disabled(isLoading)
                    .keyboardShortcut(.defaultAction)
                    .accessibilityIdentifier("loginButton")
                    .accessibilityLabel(Text(isLoading ? "logging_in_label" : "login_button"))
                    .accessibilityHint(Text("login_hint"))
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.large)
                .padding(.horizontal)
                .disabled(isLoading)
                .keyboardShortcut(.defaultAction)
                .accessibilityIdentifier("loginButton")
                .accessibilityLabel(isLoading ? Text("logging_in_status") : Text("login_button"))
                .accessibilityHint(Text("login_hint"))
                .hoverEffect()
            }

            Spacer()
        }
        .padding()
    }

    @ViewBuilder
    private var logoView: some View {
        Image(systemName: "shippingbox.fill")
            .font(.system(size: 80, weight: .regular, design: .rounded))
            .foregroundStyle(.tint)
            .pulseEffect(isActive: isLoading)
            .scaleEffect(iconScale)
            .opacity(iconOpacity)
            .accessibilityHidden(true)
    }

        if #available(iOS 17.0, macOS 14.0, visionOS 1.0, *) {
            logo.symbolEffect(.pulse, isActive: isLoading)
        } else {
            logo
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
        showLogoutConfirmation = true
    }
}
