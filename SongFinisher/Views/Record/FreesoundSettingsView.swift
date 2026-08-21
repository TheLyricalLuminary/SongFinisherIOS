import SwiftUI

/// Lets the user configure a Freesound API key so the sound browser can search
/// and pull in royalty-free samples. The key is stored in the Keychain, never
/// in UserDefaults or the SwiftData store.
struct FreesoundSettingsView: View {
    @Environment(\.dismiss) private var dismiss
    @State private var apiKey: String = KeychainService.loadAPIKey(for: .freesoundAPIKey) ?? ""

    var body: some View {
        NavigationStack {
            ZStack {
                AppTheme.background.ignoresSafeArea()

                VStack(alignment: .leading, spacing: AppTheme.Spacing.lg) {
                    VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
                        Text("Freesound API Key")
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(AppTheme.textSecondary)
                            .textCase(.uppercase)

                        SecureField("Paste your Api Key", text: $apiKey)
                            .textContentType(.password)
                            .autocorrectionDisabled()
                            .padding(AppTheme.Spacing.md)
                            .background(AppTheme.surface)
                            .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.sm, style: .continuous))
                            .foregroundStyle(AppTheme.textPrimary)

                        Text("Free at freesound.org — create an account, then generate API credentials from your account settings. Paste the \"Api Key\" here, not the Client id.")
                            .font(.footnote)
                            .foregroundStyle(AppTheme.textTertiary)
                    }

                    Spacer()

                    Button(role: .destructive) {
                        apiKey = ""
                        KeychainService.saveAPIKey("", for: .freesoundAPIKey)
                    } label: {
                        Text("Clear Key")
                            .font(.headline)
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, 14)
                    }
                    .foregroundStyle(AppTheme.danger)
                    .background(AppTheme.surface)
                    .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.pill, style: .continuous))

                    Button {
                        KeychainService.saveAPIKey(apiKey, for: .freesoundAPIKey)
                        dismiss()
                    } label: {
                        Text("Save")
                            .font(.headline)
                            .foregroundStyle(.black)
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, 14)
                    }
                    .background(Color.white)
                    .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.pill, style: .continuous))
                }
                .padding(AppTheme.Spacing.lg)
            }
            .navigationTitle("Sound Browser")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
            }
        }
    }
}
