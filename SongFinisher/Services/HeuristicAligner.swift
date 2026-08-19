import Foundation

/// The always-available, offline fallback aligner. It has no idea what's
/// actually being said or sung — it finds gaps of silence to skip (so an
/// instrumental intro or a pause between phrases doesn't eat into lyric timing)
/// and then spreads the lyric words proportionally (by word length) across
/// whatever's left. When the audio is too quiet or short to segment
/// meaningfully, it degrades further to a plain linear spread across the full
/// duration — which always produces a usable (if approximate) result.
enum HeuristicAligner {
    static func align(document: LyricsDocument, energy: AudioEnergyProfile?, duration: TimeInterval) -> [(start: TimeInterval, end: TimeInterval)] {
        let words = document.flatWords
        guard !words.isEmpty, duration > 0 else { return [] }

        let ranges = activeRanges(energy: energy, duration: duration)
        let weights = words.map { max(1, $0.count) }
        return distribute(weights: weights, across: ranges)
    }

    /// Finds the (start, end) ranges of the file that aren't silence, merging
    /// silence gaps shorter than `minSilenceGap` into their surrounding active
    /// range so brief pauses between words don't fragment a phrase. Falls back
    /// to the whole file as a single range when there isn't enough signal to
    /// draw that distinction confidently.
    private static func activeRanges(energy: AudioEnergyProfile?, duration: TimeInterval) -> [(TimeInterval, TimeInterval)] {
        guard let energy, !energy.rmsValues.isEmpty else {
            return [(0, duration)]
        }

        let peak = energy.rmsValues.max() ?? 0
        guard peak > 0 else { return [(0, duration)] }

        let threshold = peak * 0.08
        let minSilenceGap: TimeInterval = 0.35

        var ranges: [(TimeInterval, TimeInterval)] = []
        var rangeStart: TimeInterval?
        var silenceStart: TimeInterval?

        for (index, value) in energy.rmsValues.enumerated() {
            let t = Double(index) * energy.windowDuration
            let isActive = value >= threshold

            if isActive {
                silenceStart = nil
                if rangeStart == nil { rangeStart = t }
            } else if let start = rangeStart {
                if silenceStart == nil {
                    silenceStart = t
                } else if let sStart = silenceStart, t - sStart >= minSilenceGap {
                    ranges.append((start, sStart))
                    rangeStart = nil
                    silenceStart = nil
                }
            }
        }
        if let start = rangeStart {
            ranges.append((start, duration))
        }

        let totalActive = ranges.reduce(0) { $0 + ($1.1 - $1.0) }
        guard totalActive >= duration * 0.15 else {
            return [(0, duration)]
        }
        return ranges
    }

    /// Walks the weighted word list, consuming time from the active ranges in
    /// order (jumping over the gaps between ranges), so every word's slice maps
    /// back to real, in-bounds audio time.
    private static func distribute(weights: [Int], across ranges: [(TimeInterval, TimeInterval)]) -> [(start: TimeInterval, end: TimeInterval)] {
        guard !ranges.isEmpty else { return [] }
        let totalWeight = max(1, weights.reduce(0, +))
        let totalActive = ranges.reduce(0) { $0 + ($1.1 - $1.0) }
        guard totalActive > 0 else { return [] }

        var results: [(TimeInterval, TimeInterval)] = []
        var rangeIndex = 0
        var cursor = ranges[0].0
        var remainingInRange = ranges[0].1 - ranges[0].0

        for weight in weights {
            var need = totalActive * (Double(weight) / Double(totalWeight))
            var wordStart: TimeInterval?
            var wordEnd = cursor

            while need > 0 {
                if remainingInRange <= 0 {
                    rangeIndex += 1
                    guard rangeIndex < ranges.count else {
                        wordEnd = ranges.last?.1 ?? wordEnd
                        break
                    }
                    cursor = ranges[rangeIndex].0
                    remainingInRange = ranges[rangeIndex].1 - ranges[rangeIndex].0
                }
                if wordStart == nil { wordStart = cursor }
                let take = min(need, remainingInRange)
                cursor += take
                remainingInRange -= take
                need -= take
                wordEnd = cursor
            }

            results.append((wordStart ?? cursor, wordEnd))
        }
        return results
    }
}
