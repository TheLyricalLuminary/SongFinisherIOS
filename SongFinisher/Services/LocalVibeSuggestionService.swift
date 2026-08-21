import Foundation

/// Offline fallback for Auto-Generate Theme & Style, used when no Claude key
/// is configured. Genuinely cruder than the Claude path by necessity:
///
/// - STYLE is picked from a small curated table keyed by tempo bucket, plus
///   the time signature's feel description when it isn't the unremarkable
///   default of 4/4.
/// - THEME is just the recognized transcript itself, cleaned up — there's no
///   local model here to paraphrase or interpret it into something more
///   polished, so presenting the literal words as a starting point is the
///   honest option rather than pretending an algorithm found "the theme."
enum LocalVibeSuggestionService {
    static func suggestVibe(transcript: String?, bpm: Int?, timeSignature: TimeSignature) -> VibeSuggestion {
        VibeSuggestion(
            theme: suggestTheme(transcript: transcript),
            style: suggestStyle(bpm: bpm, timeSignature: timeSignature)
        )
    }

    private static func suggestTheme(transcript: String?) -> String? {
        guard let transcript else { return nil }
        let cleaned = transcript.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let first = cleaned.first else { return nil }
        return first.uppercased() + cleaned.dropFirst()
    }

    private static let styleByBucket: [(range: ClosedRange<Int>, phrases: [String])] = [
        (0...69, ["slow, spacious ballad — hushed and unhurried", "sparse and reflective, minimal instrumentation"]),
        (70...94, ["warm mid-tempo, tender and understated", "gentle acoustic, restrained and intimate"]),
        (95...119, ["easy mid-tempo pop, nostalgic and melodic", "laid-back groove, wistful and warm"]),
        (120...144, ["upbeat and driving, energetic pop/rock", "bright, propulsive, hook-forward"]),
        (145...220, ["fast and urgent, high-energy and raw", "restless, aggressive, anthemic"])
    ]

    private static func suggestStyle(bpm: Int?, timeSignature: TimeSignature) -> String {
        let effectiveBPM = bpm ?? 100
        let phrases = styleByBucket.first { $0.range.contains(effectiveBPM) }?.phrases ?? ["mid-tempo, melodic"]
        var style = phrases.randomElement() ?? phrases[0]
        if timeSignature != .fourFour {
            style += " · \(timeSignature.feelDescription)"
        }
        return style
    }
}
