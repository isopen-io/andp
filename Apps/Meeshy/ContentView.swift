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

                Button(role: .destructive, action: logoutTapped) {
                    Label("logout_button", systemImage: "rectangle.portrait.and.arrow.right")
                        .fontWeight(.semibold)
                        .frame(maxWidth: .infinity)
                }
                .hoverEffect()
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

        if #available(iOS 17.0, *) {
            logo.symbolEffect(.pulse, isActive: isLoading)
        } else {
            logo
        }
    }

    private func logoutTapped() {
        #if os(iOS)
        UIImpactFeedbackGenerator(style: .medium).impactOccurred()
        #endif
        showLogoutConfirmation = true
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
