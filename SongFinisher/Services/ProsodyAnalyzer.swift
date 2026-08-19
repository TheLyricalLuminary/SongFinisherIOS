import Foundation

/// Lightweight, dictionary-free English prosody heuristics: how many syllables a
/// line has, and whether two words rhyme. These are approximations (no
/// pronunciation dictionary), but they're good enough to bias line selection
/// toward the user's requested syllable target and rhyme scheme.
enum ProsodyAnalyzer {
    private static let vowels = Set("aeiouy")

    /// Word-final spelling variants that represent the same sound in Modern
    /// English, applied only to the rhyme key so genuine rhymes with different
    /// spellings ("door"/"more", "haze"/"days") are recognized as matching.
    /// Kept deliberately small and unambiguous. English spelling is too irregular
    /// for a broad table ("ere" is /ɪr/ in "here" but /ɜr/ in "were"), so anything
    /// ambiguous is left alone and handled by writing the line banks with
    /// spelling-consistent rhyme words instead.
    private static let rhymeEquivalents: [(String, String)] = [
        ("oor", "or"), ("oar", "or"), ("ore", "or"),
        ("aze", "az"), ("ays", "az"), ("aise", "az"),
        ("ir", "er"), ("ur", "er"),
        ("are", "air")
    ]

    /// 'y' reads as a consonant (/j/) when it opens a syllable and is followed by
    /// another vowel letter — "yet", "yes", "you" — and as a vowel otherwise —
    /// "happy", "gym", "sky". Plain membership in `vowels` can't tell those apart.
    private static func isVowelLetter(_ letters: [Character], at index: Int) -> Bool {
        let character = letters[index]
        guard character == "y" else { return vowels.contains(character) }
        guard index + 1 < letters.count else { return true }
        return !"aeiou".contains(letters[index + 1])
    }

    // MARK: - Words

    static func words(in line: String) -> [String] {
        line
            .lowercased()
            .split(whereSeparator: { !$0.isLetter && $0 != "'" })
            .map(String.init)
            .filter { $0.contains(where: \.isLetter) }
    }

    static func lastWord(of line: String) -> String {
        words(in: line).last ?? ""
    }

    // MARK: - Syllables

    /// Counts vowel groups, then corrects for silent trailing "e" — the standard
    /// cheap heuristic. "window" -> 2, "quietly" -> 3, "candle" -> 2.
    static func syllableCount(inWord word: String) -> Int {
        let letters = Array(word.lowercased().filter { $0.isLetter })
        guard !letters.isEmpty else { return 0 }

        var count = 0
        var previousWasVowel = false
        for index in letters.indices {
            let isVowel = isVowelLetter(letters, at: index)
            if isVowel && !previousWasVowel { count += 1 }
            previousWasVowel = isVowel
        }

        if letters.last == "e" && count > 1 {
            // A consonant + "le" ending keeps its syllable ("candle", "little").
            let keepsFinalSyllable = letters.count >= 3
                && letters[letters.count - 2] == "l"
                && !isVowelLetter(letters, at: letters.count - 3)
            if !keepsFinalSyllable { count -= 1 }
        }

        return max(1, count)
    }

    static func syllableCount(inLine line: String) -> Int {
        words(in: line).reduce(0) { $0 + syllableCount(inWord: $1) }
    }

    // MARK: - Rhyme keys

    /// Everything from the final vowel group onward — a decent stand-in for the
    /// stressed-vowel-to-end rhyme unit. "stayed" -> "ayed", "habit" -> "it".
    ///
    /// A trailing silent "e" is excluded from *both* the search and the returned
    /// slice — otherwise every such word would collapse to "e" ("phone" would
    /// rhyme with "voice"), or worse, leak back into the result and silently
    /// change it ("share" must land on "are" and "chair" on "air"; without
    /// slicing to the same bound they did not, because the search correctly
    /// ignored the silent e but the older slice went to the end of the word
    /// regardless).
    static func rhymeKey(for word: String) -> String {
        let letters = Array(word.lowercased().filter { $0.isLetter })
        guard !letters.isEmpty else { return "" }

        var searchEnd = letters.count - 1
        if letters.count > 2,
           letters[letters.count - 1] == "e",
           !isVowelLetter(letters, at: letters.count - 2) {
            searchEnd -= 1
        }

        var lastGroupStart: Int?
        var index = searchEnd
        while index >= 0 {
            if isVowelLetter(letters, at: index) {
                var start = index
                while start > 0 && isVowelLetter(letters, at: start - 1) { start -= 1 }
                lastGroupStart = start
                break
            }
            index -= 1
        }
        // Slice to the end of the word, not to `searchEnd`: the silent "e" is
        // excluded from the *search* (so "phone" keys on "o", not the final "e")
        // but must stay in the key, or "hide" would collapse to "id" and
        // false-match "hid".
        let start = lastGroupStart ?? 0
        return normalizeRhymeSuffix(String(letters[start...]))
    }

    private static func normalizeRhymeSuffix(_ key: String) -> String {
        for (pattern, replacement) in rhymeEquivalents where key.hasSuffix(pattern) {
            return String(key.dropLast(pattern.count)) + replacement
        }
        return key
    }

    /// The final vowel group alone (assonance) — "stayed" -> "aye".
    static func finalVowelGroup(for word: String) -> String {
        let key = rhymeKey(for: word)
        return String(key.prefix { vowels.contains($0) })
    }

    /// The consonants after the final vowel group (consonance) — "stayed" -> "d".
    static func finalConsonantCluster(for word: String) -> String {
        let key = rhymeKey(for: word)
        return String(key.drop { vowels.contains($0) })
    }

    /// Slant/near rhyme: shares either the vowel sound or the closing consonants.
    static func slantRhymes(_ a: String, _ b: String) -> Bool {
        guard !a.isEmpty, !b.isEmpty, a != b else { return false }
        let vowelA = finalVowelGroup(for: a), vowelB = finalVowelGroup(for: b)
        if !vowelA.isEmpty && vowelA == vowelB { return true }
        let consonantA = finalConsonantCluster(for: a), consonantB = finalConsonantCluster(for: b)
        if !consonantA.isEmpty && consonantA == consonantB { return true }
        return false
    }

    /// True rhyme, ignoring identity ("send"/"send" is repetition, not rhyme).
    static func endRhymes(_ a: String, _ b: String) -> Bool {
        guard !a.isEmpty, !b.isEmpty, a != b else { return false }
        let keyA = rhymeKey(for: a), keyB = rhymeKey(for: b)
        return !keyA.isEmpty && keyA == keyB
    }

    /// Does any earlier word in the line rhyme with a later one?
    static func hasInternalRhyme(in line: String) -> Bool {
        let candidates = words(in: line).filter { $0.count >= 3 }
        guard candidates.count >= 2 else { return false }
        for i in 0..<(candidates.count - 1) {
            for j in (i + 1)..<candidates.count where endRhymes(candidates[i], candidates[j]) {
                return true
            }
        }
        return false
    }
}
