import Foundation

/// Whether a clip contains recognizable singing/speech, versus being purely
/// instrumental. Deliberately not a separate audio classifier (no on-device ML
/// model, no spectral heuristic for vocal formants) — `SFSpeechRecognizer`
/// already fails gracefully on pure instrumental material rather than
/// hallucinating words, so its own result *is* the signal. This is what lets
/// auto-detect pick the right analysis path: a transcript to run syllable/
/// rhyme detection on, or nothing to analyze at all for a wordless melody.
enum VocalContentResult: Equatable {
    case instrumental
    case vocals(wordCount: Int, transcript: String)
}

enum VocalContentDetector {
    /// A single stray misrecognition on instrumental noise is common; several
    /// consistent words in a row is not. This threshold is what tells them apart.
    private static let minimumWordCount = 3

    static func detect(audioURL: URL) async -> VocalContentResult {
        guard let segments = await SpeechAligner.transcribeIfPossible(audioURL: audioURL) else {
            return .instrumental
        }
        let words = segments.map(\.substring).filter { $0.contains(where: \.isLetter) }
        guard words.count >= minimumWordCount else { return .instrumental }
        return .vocals(wordCount: words.count, transcript: words.joined(separator: " "))
    }
}
