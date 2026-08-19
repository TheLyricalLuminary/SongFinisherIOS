import Foundation

/// A parsed (but not yet timed) lyric sheet: lines of words, with section labels
/// attached to the line that starts each section.
struct LyricsDocument {
    struct Line {
        var sectionTitle: String?
        var words: [String]
    }
    var lines: [Line]

    /// All words across all lines, in reading order — the sequence alignment
    /// operates on this flattened form.
    var flatWords: [String] { lines.flatMap(\.words) }
}

/// Parses the plain-text lyric format produced by `GenerateLyricsView`:
/// bracketed section labels ("[Verse 1]") on their own line, followed by lyric
/// lines, blank lines as separators. Tolerant of arbitrary user edits — lines
/// with no section labels at all parse just as well.
enum LyricsTextParser {
    static func parse(_ text: String) -> LyricsDocument {
        var lines: [LyricsDocument.Line] = []
        var pendingSectionTitle: String?

        for rawLine in text.components(separatedBy: .newlines) {
            let trimmed = rawLine.trimmingCharacters(in: .whitespaces)
            guard !trimmed.isEmpty else { continue }

            if trimmed.hasPrefix("["), trimmed.hasSuffix("]") {
                pendingSectionTitle = String(trimmed.dropFirst().dropLast())
                continue
            }

            let words = trimmed.split(separator: " ").map(String.init)
            guard !words.isEmpty else { continue }
            lines.append(LyricsDocument.Line(sectionTitle: pendingSectionTitle, words: words))
            pendingSectionTitle = nil
        }

        return LyricsDocument(lines: lines)
    }
}
