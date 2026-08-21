import Foundation

/// Chooses which `LyricGenerationService` to use: Claude when the user has
/// configured an API key, otherwise the fully offline local generator. This is
/// the one place that decides — callers just ask for "the default" service.
enum LyricGenerationServiceFactory {
    /// DevSecrets.plist wins over the Keychain, so dropping a key in the file
    /// works without touching the in-app settings screen.
    static var apiKey: String? {
        DevSecrets.claudeAPIKey ?? KeychainService.loadAPIKey(for: .claudeAPIKey)
    }

    static func makeDefault() -> LyricGenerationService {
        if let key = apiKey, !key.isEmpty {
            return ClaudeLyricGenerationService(apiKey: key)
        }
        return LocalLyricGenerationService()
    }

    static var isRemoteConfigured: Bool {
        apiKey?.isEmpty == false
    }
}
