import Foundation

/// The result of a lyric generation request: plain text formatted with
/// "[Verse 1]" / "[Chorus]" / "[Bridge]" section labels, one lyric line per line.
struct GeneratedLyrics {
    var text: String
}

/// Everything a generator needs: the theme prompt plus the craft settings
/// (style, rhyme, syllables, musical context) the user dialed in.
struct LyricGenerationRequest {
    var prompt: String
    var settings: LyricSettings

    var trimmedPrompt: String {
        prompt.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    /// Style words that must never appear in the generated lyrics.
    var bannedWords: [String] {
        StyleWordGuard.bannedWords(from: settings.style)
    }
}

/// Produces structured song lyrics from a theme prompt and craft settings.
/// Implementations are swappable — see `LocalLyricGenerationService` (fully
/// offline, zero-config default) and `ClaudeLyricGenerationService` (optional,
/// requires an API key). Both honor every field of `LyricGenerationRequest`.
protocol LyricGenerationService {
    func generateLyrics(_ request: LyricGenerationRequest) async throws -> GeneratedLyrics
}

enum LyricGenerationError: LocalizedError {
    case emptyPrompt
    case missingAPIKey
    case requestFailed(String)
    case emptyResponse

    var errorDescription: String? {
        switch self {
        case .emptyPrompt:
            return "Enter a short prompt to generate lyrics."
        case .missingAPIKey:
            return "Add a Claude API key in Lyric Settings, or clear it to use the built-in local generator."
        case .requestFailed(let message):
            return message
        case .emptyResponse:
            return "The lyric generator returned nothing. Try again."
        }
    }
}
