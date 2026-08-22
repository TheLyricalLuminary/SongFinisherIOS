import Foundation

/// Offline fallback for Auto-Generate Theme & Style, used when no Claude key
/// is configured. Genuinely cruder than the Claude path by necessity:
///
/// - STYLE is picked from a small curated table keyed by tempo bucket, plus
///   the time signature's feel description when it isn't the unremarkable
///   default of 4/4.
/// - THEME: when a transcript exists, it's the recognized words themselves,
///   cleaned up — there's no local model to paraphrase them into something
///   more polished. When there's no transcript (a wordless instrumental
///   someone plans to practice singing over), THEME instead offers a
///   tempo-informed creative starting idea — clearly a suggestion for
///   inspiration, never framed as something detected in audio that has no
///   words in it yet.
enum LocalVibeSuggestionService {
    static func suggestVibe(transcript: String?, bpm: Int?, timeSignature: TimeSignature) -> VibeSuggestion {
        VibeSuggestion(
            theme: suggestTheme(transcript: transcript, bpm: bpm),
            style: suggestStyle(bpm: bpm, timeSignature: timeSignature)
        )
    }

    private static func suggestTheme(transcript: String?, bpm: Int?) -> String? {
        if let transcript {
            let cleaned = transcript.trimmingCharacters(in: .whitespacesAndNewlines)
            if let first = cleaned.first { return first.uppercased() + cleaned.dropFirst() }
        }
        return suggestThemeStarter(bpm: bpm)
    }

    /// A creative theme idea to sing to, informed only by tempo — a starting
    /// point for practice, not a claim about what the (wordless) take is about.
    private static let themeStartersByBucket: [(range: ClosedRange<Int>, phrases: [String])] = [
        (0...69, ["losing track of time in a slow afternoon", "a memory that feels more real than the room you're in", "drifting somewhere between awake and asleep"]),
        (70...94, ["a quiet moment you don't want to end", "holding onto someone without saying so", "the small kindness that changed everything"]),
        (95...119, ["a summer that ended too fast", "the town you can't stop thinking about", "a friendship you let drift away"]),
        (120...144, ["needing to leave before you know where you're going", "outrunning a feeling you can't name", "the pull to just go, no plan, no map"]),
        (145...220, ["walking away and not looking back", "finally saying the thing you swallowed for years", "proving someone wrong just by surviving"])
    ]

    private static func suggestThemeStarter(bpm: Int?) -> String {
        let effectiveBPM = bpm ?? 100
        let phrases = themeStartersByBucket.first { $0.range.contains(effectiveBPM) }?.phrases ?? ["a feeling you haven't named yet"]
        return phrases.randomElement() ?? phrases[0]
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
