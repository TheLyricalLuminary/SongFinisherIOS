import Foundation

/// Chooses which `LyricGenerationService` to use: Claude when the user has
/// configured an API key, otherwise the fully offline local generator. This is
/// the one place that decides — callers just ask for "the default" service.
enum LyricGenerationServiceFactory {
    static func makeDefault() -> LyricGenerationService {
        if let key = KeychainService.loadAPIKey(for: .claudeAPIKey), !key.isEmpty {
            return ClaudeLyricGenerationService(apiKey: key)
        }
        return LocalLyricGenerationService()
    }

    static var isRemoteConfigured: Bool {
        KeychainService.loadAPIKey(for: .claudeAPIKey)?.isEmpty == false
    }
}
