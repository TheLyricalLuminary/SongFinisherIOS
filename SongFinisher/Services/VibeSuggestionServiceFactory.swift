import Foundation

/// Chooses which vibe-suggestion path to use: Claude when a key is
/// configured, otherwise the local, no-account fallback. Mirrors
/// `LyricGenerationServiceFactory`'s pattern -- chosen upfront by
/// configuration, not a silent runtime fallback on failure, so a real Claude
/// error surfaces instead of quietly downgrading to the cruder local guess.
enum VibeSuggestionServiceFactory {
    static func suggestVibe(
        transcript: String?,
        bpm: Int?,
        timeSignature: TimeSignature
    ) async throws -> VibeSuggestion {
        if let apiKey = LyricGenerationServiceFactory.apiKey, !apiKey.isEmpty {
            return try await ClaudeVibeSuggestionService.suggestVibe(
                transcript: transcript, bpm: bpm, timeSignature: timeSignature
            )
        }
        return LocalVibeSuggestionService.suggestVibe(transcript: transcript, bpm: bpm, timeSignature: timeSignature)
    }
}
