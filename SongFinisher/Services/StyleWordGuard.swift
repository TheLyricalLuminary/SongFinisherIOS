import Foundation

/// Enforces the hard rule that the user's *style* words shape the writing but
/// never show up in the lyrics themselves — "americana funk fusion" should
/// influence the vocabulary and attitude without the word "funk" ever being sung.
///
/// The local generator uses this to keep style words out of extracted imagery and
/// out of any candidate line; the Claude generator uses it to state the ban
/// explicitly and to verify the result, retrying once if the model slips.
enum StyleWordGuard {
    /// Common connectives that carry no style meaning and shouldn't be banned —
    /// banning "and" would make most lyrics impossible to write.
    private static let stopwords: Set<String> = [
        "and", "the", "with", "for", "but", "or", "a", "an", "of", "in", "on", "at",
        "to", "from", "very", "quite", "kind", "sort", "bit", "more", "less", "like",
        "style", "vibe", "feel", "feeling", "sound", "sounding", "song", "music",
        "lyrics", "tone", "mood", "genre", "influence", "influenced", "inspired"
    ]

    /// Content words from the style field, lowercased. Short words (< 3 letters)
    /// are skipped — they're too likely to collide with ordinary lyric words.
    static func bannedWords(from style: String) -> [String] {
        let words = style
            .lowercased()
            .split(whereSeparator: { !$0.isLetter })
            .map(String.init)
            .filter { $0.count >= 3 && !stopwords.contains($0) }
        return Array(Set(words)).sorted()
    }

    /// Matches a banned word, plus obvious inflections in either direction
    /// ("folk" catches "folky"/"folks"; "introspective" catches "introspect").
    static func containsBannedWord(_ text: String, banned: [String]) -> Bool {
        guard !banned.isEmpty else { return false }
        let words = ProsodyAnalyzer.words(in: text)
        for word in words {
            let normalized = word.filter(\.isLetter)
            guard !normalized.isEmpty else { continue }
            for bannedWord in banned where matches(normalized, bannedWord) {
                return true
            }
        }
        return false
    }

    private static func matches(_ word: String, _ bannedWord: String) -> Bool {
        if word == bannedWord { return true }
        if bannedWord.count >= 4 && word.hasPrefix(bannedWord) { return true }
        if word.count >= 4 && bannedWord.hasPrefix(word) { return true }
        return false
    }
}
