import Foundation

/// How rhyming lines pair up within a four-line stanza.
enum RhymeScheme: String, Codable, CaseIterable, Identifiable {
    case aabb = "AABB"
    case abab = "ABAB"
    case abba = "ABBA"
    case abcb = "ABCB"
    case aaaa = "AAAA"
    case free = "Free"

    var id: String { rawValue }

    /// One rhyme-group label per line. Labels that appear only once impose no
    /// constraint, which is what makes "ABCB" (only lines 2 and 4 rhyme) and
    /// "Free" (nothing rhymes) fall out of the same representation.
    var pattern: [Character] {
        switch self {
        case .aabb: return ["A", "A", "B", "B"]
        case .abab: return ["A", "B", "A", "B"]
        case .abba: return ["A", "B", "B", "A"]
        case .abcb: return ["A", "B", "C", "B"]
        case .aaaa: return ["A", "A", "A", "A"]
        case .free: return ["A", "B", "C", "D"]
        }
    }
}

/// The kind(s) of rhyme to favor. These combine — picking End + Internal asks
/// for lines that rhyme at the end *and* carry a rhyme inside the line.
enum RhymeType: String, Codable, CaseIterable, Identifiable {
    case end = "End"
    case slant = "Near/Slant"
    case internalRhyme = "Internal"

    var id: String { rawValue }
}

enum TimeSignature: String, Codable, CaseIterable, Identifiable {
    case fourFour = "4/4"
    case threeFour = "3/4"
    case sixEight = "6/8"
    case twoFour = "2/4"
    case fiveFour = "5/4"
    case sevenEight = "7/8"

    var id: String { rawValue }

    /// Nudge applied to the syllable target: shorter bars want shorter lines.
    var syllableAdjustment: Int {
        switch self {
        case .fourFour: return 0
        case .threeFour, .sixEight: return -1
        case .twoFour: return -2
        case .fiveFour, .sevenEight: return 1
        }
    }

    /// Triple/compound meters swing; useful context for the AI generator.
    var feelDescription: String {
        switch self {
        case .fourFour: return "steady four-on-the-floor pulse"
        case .threeFour: return "waltz feel, three beats per bar"
        case .sixEight: return "compound triple, lilting swung eighths"
        case .twoFour: return "brisk two-beat march feel"
        case .fiveFour: return "odd-meter five, uneven phrasing"
        case .sevenEight: return "odd-meter seven, clipped phrasing"
        }
    }
}

/// Everything the user can dial in to shape how lyrics get written, saved with
/// the project so it persists and can be reused or adjusted after alignment.
struct LyricSettings: Codable, Equatable {
    /// Free-text style direction ("americana funk fusion", "restrained and
    /// introspective"). Shapes tone/vocabulary/attitude — but the style words
    /// themselves must never surface in the lyrics. See `StyleWordGuard`.
    var style: String
    var rhymeScheme: RhymeScheme
    var rhymeTypes: [RhymeType]
    var syllableTarget: Int
    /// Musical key, e.g. "G major". Empty when unspecified.
    var key: String
    /// Beats per minute. Zero when unspecified.
    var bpm: Int
    var timeSignature: TimeSignature

    init(
        style: String = "",
        rhymeScheme: RhymeScheme = .aabb,
        rhymeTypes: [RhymeType] = [.end],
        syllableTarget: Int = 8,
        key: String = "",
        bpm: Int = 0,
        timeSignature: TimeSignature = .fourFour
    ) {
        self.style = style
        self.rhymeScheme = rhymeScheme
        self.rhymeTypes = rhymeTypes
        self.syllableTarget = syllableTarget
        self.key = key
        self.bpm = bpm
        self.timeSignature = timeSignature
    }

    static let `default` = LyricSettings()

    /// Decoded field-by-field with fallbacks so settings saved by an older build
    /// keep loading if fields are added later.
    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        let fallback = LyricSettings()
        func value<T: Decodable>(_ type: T.Type, _ key: CodingKeys, default fallbackValue: T) -> T {
            ((try? container.decodeIfPresent(type, forKey: key)) ?? nil) ?? fallbackValue
        }
        style = value(String.self, .style, default: fallback.style)
        rhymeScheme = value(RhymeScheme.self, .rhymeScheme, default: fallback.rhymeScheme)
        rhymeTypes = value([RhymeType].self, .rhymeTypes, default: fallback.rhymeTypes)
        syllableTarget = value(Int.self, .syllableTarget, default: fallback.syllableTarget)
        key = value(String.self, .key, default: fallback.key)
        bpm = value(Int.self, .bpm, default: fallback.bpm)
        timeSignature = value(TimeSignature.self, .timeSignature, default: fallback.timeSignature)
    }

    /// Never empty — an empty selection falls back to plain end rhymes.
    var effectiveRhymeTypes: [RhymeType] {
        rhymeTypes.isEmpty ? [.end] : rhymeTypes
    }

    /// The syllable count line selection actually aims for, after letting meter
    /// and tempo nudge the user's target: shorter bars and slow tempos favor
    /// shorter lines, odd meters and fast tempos slightly longer ones.
    var effectiveSyllableTarget: Int {
        var target = syllableTarget + timeSignature.syllableAdjustment
        if bpm > 0 {
            if bpm < 70 { target -= 1 } else if bpm > 140 { target += 1 }
        }
        return max(3, min(24, target))
    }

    var trimmedStyle: String {
        style.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    var trimmedKey: String {
        key.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    /// Compact one-line description for the collapsed settings row.
    var summary: String {
        var parts = [
            rhymeScheme.rawValue,
            effectiveRhymeTypes.map(\.rawValue).joined(separator: "+"),
            "\(syllableTarget) syll",
            timeSignature.rawValue
        ]
        if bpm > 0 { parts.append("\(bpm) BPM") }
        if !trimmedKey.isEmpty { parts.append(trimmedKey) }
        return parts.joined(separator: " · ")
    }
}
