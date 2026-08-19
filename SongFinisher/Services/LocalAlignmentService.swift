import Foundation

/// The default `AlignmentService`. Tries on-device speech recognition first
/// (real, audio-derived word timing); if that's unavailable, denied, or too
/// low-confidence, falls back to the offline energy-based heuristic — which
/// itself degrades to a plain linear spread if the audio is too quiet or short
/// to segment. Between those tiers, alignment always succeeds for any project
/// with non-empty lyrics and a known duration.
struct LocalAlignmentService: AlignmentService {
    func align(lyricsText: String, audioURL: URL, duration: TimeInterval) async throws -> AlignedLyrics {
        let trimmed = lyricsText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { throw AlignmentError.emptyLyrics }
        guard duration > 0 else { throw AlignmentError.audioUnavailable }

        let document = LyricsTextParser.parse(lyricsText)
        guard !document.lines.isEmpty else { throw AlignmentError.emptyLyrics }

        let timings = await resolveTimings(document: document, audioURL: audioURL, duration: duration)
        return Self.assemble(document: document, timings: timings, sourceText: lyricsText, duration: duration)
    }

    private func resolveTimings(
        document: LyricsDocument,
        audioURL: URL,
        duration: TimeInterval
    ) async -> [(start: TimeInterval, end: TimeInterval)] {
        if let speechTimings = try? await SpeechAligner.align(document: document, audioURL: audioURL, duration: duration) {
            return speechTimings
        }
        let energy = try? AudioEnergyAnalyzer.analyze(url: audioURL)
        return HeuristicAligner.align(document: document, energy: energy, duration: duration)
    }

    private static func assemble(
        document: LyricsDocument,
        timings: [(start: TimeInterval, end: TimeInterval)],
        sourceText: String,
        duration: TimeInterval
    ) -> AlignedLyrics {
        var cursor = 0
        var lines: [AlignedLine] = []

        for line in document.lines {
            let count = line.words.count
            guard cursor + count <= timings.count else { break }
            let slice = timings[cursor..<(cursor + count)]
            cursor += count

            let words = zip(line.words, slice).map { text, timing in
                AlignedWord(text: text, start: timing.start, end: timing.end)
            }
            let start = words.first?.start ?? 0
            let end = words.last?.end ?? start
            lines.append(AlignedLine(
                sectionTitle: line.sectionTitle,
                text: line.words.joined(separator: " "),
                words: words,
                start: start,
                end: end
            ))
        }

        return AlignedLyrics(lines: lines, sourceText: sourceText, duration: duration)
    }
}
