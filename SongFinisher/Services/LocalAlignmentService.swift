import Foundation

/// The default `AlignmentService`. Tries on-device speech recognition first
/// (real, audio-derived word timing); if that's unavailable, denied, or too
/// low-confidence, falls back to the offline energy-based heuristic — which
/// itself degrades to a plain linear spread if the audio is too quiet or short
/// to segment. Between those tiers, alignment always succeeds for any project
/// with non-empty lyrics and a known duration.
struct LocalAlignmentService: AlignmentService {
    func align(lyricsText: String, audioURL: URL, duration: TimeInterval) async throws -> AlignedLyrics {
        try await align(lyricsText: lyricsText, audioURL: audioURL, duration: duration, sectionStarts: [])
    }

    /// Alignment with user-tapped section start times. Each element of
    /// `sectionStarts` is the audio timestamp where the corresponding section
    /// begins; an empty array falls back to fully automatic timing.
    func align(
        lyricsText: String,
        audioURL: URL,
        duration: TimeInterval,
        sectionStarts: [TimeInterval]
    ) async throws -> AlignedLyrics {
        let trimmed = lyricsText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { throw AlignmentError.emptyLyrics }
        guard duration > 0 else { throw AlignmentError.audioUnavailable }

        let document = LyricsTextParser.parse(lyricsText)
        guard !document.lines.isEmpty else { throw AlignmentError.emptyLyrics }

        let timings: [(start: TimeInterval, end: TimeInterval)]
        if sectionStarts.isEmpty {
            timings = await resolveTimings(document: document, audioURL: audioURL, duration: duration)
        } else {
            timings = await resolveTimingsWithSections(
                document: document, audioURL: audioURL, duration: duration, sectionStarts: sectionStarts
            )
        }
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

    /// Distributes each *marked* section's words within its user-tapped time
    /// window. Sections beyond the last mark are left out entirely — this is
    /// what makes testing a short clip against a couple of sections safe: with
    /// a full multi-section lyrics document but only e.g. a verse and chorus
    /// marked against a 34-second take, the unmarked sections (verse 2,
    /// bridge, ...) simply get no timing rather than being squeezed into
    /// whatever's left of the clip.
    ///
    /// ASR is attempted first, but only against the marked sections' words —
    /// not the full document — so its confidence gate isn't computed against
    /// reference words that were never sung in this take. If it succeeds,
    /// word-level acoustic timing overrides the section boundaries (it's more
    /// accurate). If it fails or is unavailable, words are spread
    /// proportionally within each marked section's window.
    private func resolveTimingsWithSections(
        document: LyricsDocument,
        audioURL: URL,
        duration: TimeInterval,
        sectionStarts: [TimeInterval]
    ) async -> [(start: TimeInterval, end: TimeInterval)] {
        let sectionLineGroups = Self.linesBySection(document)
        let usableSectionCount = min(sectionLineGroups.count, sectionStarts.count)
        guard usableSectionCount > 0 else { return [] }

        let usableLines = Array(sectionLineGroups[0..<usableSectionCount].joined())
        let usableDocument = LyricsDocument(lines: usableLines)

        if let speechTimings = try? await SpeechAligner.align(document: usableDocument, audioURL: audioURL, duration: duration) {
            return speechTimings
        }

        var result: [(TimeInterval, TimeInterval)] = []
        for (index, lines) in sectionLineGroups.prefix(usableSectionCount).enumerated() {
            let start = sectionStarts[index]
            let end: TimeInterval = index + 1 < sectionStarts.count ? sectionStarts[index + 1] : duration
            let window = max(0.01, end - start)
            let weights = lines.flatMap(\.words).map { max(1, $0.count) }
            let totalWeight = max(1, weights.reduce(0, +))
            var cursor = start
            for weight in weights {
                let slice = window * Double(weight) / Double(totalWeight)
                result.append((cursor, cursor + slice))
                cursor += slice
            }
        }
        return result
    }

    /// Groups document lines into per-section runs, split wherever a line
    /// carries a new section title. Mirrors how `SectionTimingView` derives
    /// its section list, so group indices line up with `sectionStarts`.
    private static func linesBySection(_ document: LyricsDocument) -> [[LyricsDocument.Line]] {
        var groups: [[LyricsDocument.Line]] = []
        var current: [LyricsDocument.Line] = []
        for line in document.lines {
            if line.sectionTitle != nil, !current.isEmpty {
                groups.append(current)
                current = []
            }
            current.append(line)
        }
        if !current.isEmpty { groups.append(current) }
        return groups
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
