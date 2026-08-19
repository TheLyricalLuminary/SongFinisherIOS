import Foundation

/// A single lyric word with the time range it's sung/spoken during in the
/// original audio.
struct AlignedWord: Codable, Equatable {
    var text: String
    var start: TimeInterval
    var end: TimeInterval
}

/// A single lyric line: its words (each individually timed) plus the section
/// label ("Verse 1", "Chorus", ...) if this line starts a new section.
struct AlignedLine: Codable, Equatable {
    var sectionTitle: String?
    var text: String
    var words: [AlignedWord]
    var start: TimeInterval
    var end: TimeInterval
}

/// The full result of aligning a project's lyrics to its audio. `sourceText` is
/// the exact `Project.lyricsText` this was computed from, so callers can detect
/// when lyrics have since been edited and the alignment is stale.
struct AlignedLyrics: Codable, Equatable {
    var lines: [AlignedLine]
    var sourceText: String
    var duration: TimeInterval
}

/// Produces word-level timestamps mapping a project's lyrics onto its original
/// audio. Implementations are swappable — `LocalAlignmentService` is the
/// zero-config default (on-device speech recognition when it yields confident
/// results, otherwise an offline signal-analysis fallback); a remote,
/// higher-accuracy backend (e.g. WhisperX-style forced alignment) can conform
/// to this same protocol later without touching callers.
protocol AlignmentService {
    func align(lyricsText: String, audioURL: URL, duration: TimeInterval) async throws -> AlignedLyrics
}

enum AlignmentError: LocalizedError {
    case emptyLyrics
    case audioUnavailable
    case recognitionUnavailable
    case recognitionFailed(String)
    case insufficientConfidence

    var errorDescription: String? {
        switch self {
        case .emptyLyrics:
            return "Generate or write some lyrics before aligning."
        case .audioUnavailable:
            return "Couldn't read this project's audio."
        case .recognitionUnavailable:
            return "Speech recognition isn't available right now."
        case .recognitionFailed(let message):
            return message
        case .insufficientConfidence:
            return "Couldn't confidently match the lyrics to the recording."
        }
    }
}
