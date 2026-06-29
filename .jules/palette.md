## 2026-06-25 - [Widget Accessibility & iOS 17 Rendering]
**Learning:** Widgets in iOS 17+ require the `.containerBackground` modifier for correct rendering. Additionally, for small-format widgets, using `.accessibilityElement(children: .combine)` creates a much smoother VoiceOver experience by summarizing the widget's state in a single announcement rather than forcing the user to navigate individual elements in a tiny space.
**Action:** Always combine accessibility elements in simple widgets and ensure iOS 17+ container background compliance.

## 2026-06-26 - [Validator Context and Async UI Feedback]
**Learning:** Static analysis tools for accessibility (like `accessibility-validator.py`) may fail on complex nested SwiftUI structures (e.g., buttons containing an `HStack` with a `ProgressView`). Increasing the lookahead context to 20 lines provides a better balance for modern SwiftUI coding styles. For UX, providing immediate feedback via `ProgressView` in primary buttons and requiring confirmation for destructive actions like Logout ensures a "smooth and safe" interaction model.
**Action:** Use 20-line context for accessibility validation and always implement loading states for async UI actions.

## 2026-06-27 - [iOS Accessibility & Haptic Feedback]
**Learning:** For interactive elements with icons and text, use `.accessibilityHidden(true)` on decorative icons and provide a clear `.accessibilityLabel` on the parent container (like a Button) to satisfy accessibility auditors. Additionally, combining `symbolEffect` for visual feedback with `UINotificationFeedbackGenerator` for haptic feedback creates a much more cohesive and premium-feeling interaction.
**Action:** Hide decorative icons from VoiceOver and pair visual state changes with haptic feedback for primary actions.
