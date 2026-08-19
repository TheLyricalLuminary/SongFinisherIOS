import SwiftUI

/// Centralized visual language for the app: a minimal, dark-first palette with a
/// single accent color, consistent spacing, and reusable gradients.
enum AppTheme {
    static let accent = Color(red: 0.98, green: 0.36, blue: 0.42) // warm coral

    static let background = Color(red: 0.06, green: 0.06, blue: 0.08)
    static let surface = Color(red: 0.11, green: 0.11, blue: 0.135)
    static let surfaceElevated = Color(red: 0.15, green: 0.15, blue: 0.18)

    static let textPrimary = Color.white
    static let textSecondary = Color.white.opacity(0.62)
    static let textTertiary = Color.white.opacity(0.38)

    static let danger = Color(red: 0.95, green: 0.3, blue: 0.35)
    static let success = Color(red: 0.35, green: 0.85, blue: 0.55)

    static let backgroundGradient = LinearGradient(
        colors: [Color(red: 0.09, green: 0.07, blue: 0.12), Color(red: 0.04, green: 0.05, blue: 0.08)],
        startPoint: .top,
        endPoint: .bottom
    )

    static let accentGradient = LinearGradient(
        colors: [accent, Color(red: 0.86, green: 0.24, blue: 0.55)],
        startPoint: .leading,
        endPoint: .trailing
    )

    enum Spacing {
        static let xs: CGFloat = 4
        static let sm: CGFloat = 8
        static let md: CGFloat = 16
        static let lg: CGFloat = 24
        static let xl: CGFloat = 32
        static let xxl: CGFloat = 48
    }

    enum Radius {
        static let sm: CGFloat = 10
        static let md: CGFloat = 16
        static let lg: CGFloat = 24
        static let pill: CGFloat = 999
    }
}

extension View {
    /// Applies the app's standard card surface styling.
    func cardSurface(cornerRadius: CGFloat = AppTheme.Radius.md) -> some View {
        self
            .background(AppTheme.surface)
            .clipShape(RoundedRectangle(cornerRadius: cornerRadius, style: .continuous))
    }
}
