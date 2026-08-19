import Foundation

/// Aligns a sequence of reference lyric words to a sequence of recognized
/// (timestamped) hypothesis words, using the same dynamic-programming approach
/// as text diffing (Needleman-Wunsch style global alignment): find the lowest-
/// cost way to walk both sequences in order, where matching words are free,
/// substitutions cost 1, and skipping a word in either sequence costs 1. Words
/// that don't align to anything are left unmatched — `interpolate` fills those
/// in from their matched neighbors afterward.
enum LyricWordAligner {
    struct AlignedReferenceWord {
        var text: String
        var start: TimeInterval?
        var end: TimeInterval?
        var matched: Bool
    }

    static func align(
        reference: [String],
        hypothesis: [(text: String, start: TimeInterval, end: TimeInterval)]
    ) -> [AlignedReferenceWord] {
        guard !reference.isEmpty else { return [] }
        guard !hypothesis.isEmpty else {
            return reference.map { AlignedReferenceWord(text: $0, start: nil, end: nil, matched: false) }
        }

        let refNorm = reference.map(normalize)
        let hypNorm = hypothesis.map { normalize($0.text) }
        let n = refNorm.count
        let m = hypNorm.count

        var dp = Array(repeating: Array(repeating: 0, count: m + 1), count: n + 1)
        for i in 1...n { dp[i][0] = dp[i - 1][0] - 1 }
        for j in 1...m { dp[0][j] = dp[0][j - 1] - 1 }

        for i in 1...n {
            for j in 1...m {
                let matchScore = refNorm[i - 1] == hypNorm[j - 1] ? 2 : -1
                dp[i][j] = max(
                    dp[i - 1][j - 1] + matchScore,
                    dp[i - 1][j] - 1,
                    dp[i][j - 1] - 1
                )
            }
        }

        var matches: [Int: Int] = [:] // reference index -> hypothesis index
        var i = n, j = m
        while i > 0 && j > 0 {
            let matchScore = refNorm[i - 1] == hypNorm[j - 1] ? 2 : -1
            if dp[i][j] == dp[i - 1][j - 1] + matchScore {
                if refNorm[i - 1] == hypNorm[j - 1] {
                    matches[i - 1] = j - 1
                }
                i -= 1
                j -= 1
            } else if dp[i][j] == dp[i - 1][j] - 1 {
                i -= 1
            } else {
                j -= 1
            }
        }

        return reference.enumerated().map { index, word in
            if let hypIndex = matches[index] {
                let h = hypothesis[hypIndex]
                return AlignedReferenceWord(text: word, start: h.start, end: h.end, matched: true)
            }
            return AlignedReferenceWord(text: word, start: nil, end: nil, matched: false)
        }
    }

    /// Fills every unmatched word's timing by linearly interpolating between its
    /// nearest matched neighbors (or the clip boundaries, for a run of unmatched
    /// words at the very start or end). Guarantees every word ends up with a
    /// timestamp, in order, with no gaps.
    static func interpolate(_ aligned: [AlignedReferenceWord], duration: TimeInterval) -> [(start: TimeInterval, end: TimeInterval)] {
        guard !aligned.isEmpty else { return [] }

        var starts: [TimeInterval?] = aligned.map(\.start)
        var ends: [TimeInterval?] = aligned.map(\.end)

        var index = 0
        while index < starts.count {
            guard starts[index] == nil else { index += 1; continue }

            var gapEnd = index
            while gapEnd < starts.count && starts[gapEnd] == nil { gapEnd += 1 }

            let lowerBound: TimeInterval = index > 0 ? (ends[index - 1] ?? 0) : 0
            let upperBound: TimeInterval = gapEnd < starts.count ? (starts[gapEnd] ?? duration) : duration
            let span = max(upperBound - lowerBound, 0)
            let count = gapEnd - index

            for k in 0..<count {
                starts[index + k] = lowerBound + span * (Double(k) / Double(count))
                ends[index + k] = lowerBound + span * (Double(k + 1) / Double(count))
            }
            index = gapEnd
        }

        return zip(starts, ends).map { (start: $0 ?? 0, end: $1 ?? ($0 ?? 0)) }
    }

    private static func normalize(_ word: String) -> String {
        word.lowercased().filter { $0.isLetter || $0.isNumber || $0 == "'" }
    }
}
