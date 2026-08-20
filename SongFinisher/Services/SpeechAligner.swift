import Speech

/// Best-effort forced alignment using on-device (or system) speech recognition:
/// transcribes the user's actual recording with word-level timestamps via
/// `SFSpeechRecognizer`, then sequence-aligns the recognized words to the
/// reference lyrics with `LyricWordAligner` so timestamps transfer from "what
/// was heard" onto "what the lyrics say". This only recognizes an existing
/// audio file (`SFSpeechURLRecognitionRequest`) — no live microphone capture,
/// no separate microphone permission.
///
/// This is a genuine best effort, not true acoustic forced alignment: it needs
/// intelligible words in the recording (hums or pure melody won't transcribe to
/// anything), and very long files may exceed the recognizer's practical limits.
/// Both failure modes — and low-confidence matches — throw so the caller can
/// fall back to the always-available heuristic aligner.
enum SpeechAligner {
    static func align(
        document: LyricsDocument,
        audioURL: URL,
        duration: TimeInterval
    ) async throws -> [(start: TimeInterval, end: TimeInterval)] {
        guard await requestAuthorizationIfNeeded() else {
            throw AlignmentError.recognitionUnavailable
        }
        guard let recognizer = SFSpeechRecognizer(), recognizer.isAvailable else {
            throw AlignmentError.recognitionUnavailable
        }

        let segments = try await transcribe(url: audioURL, recognizer: recognizer)
        guard !segments.isEmpty else {
            throw AlignmentError.recognitionFailed("No speech was recognized in this recording.")
        }

        // SFSpeechRecognizer can misreport timestamps for stereo files (e.g.
        // 44100 Hz stereo recorded by this app): it converts to mono internally
        // but may count interleaved stereo samples as if they were mono, halving
        // all reported timestamps relative to actual audio time. We detect this
        // by comparing the last segment's end to the known audio duration and
        // applying a correction when the ratio falls in the plausible range for
        // a channel/sample-rate mismatch (1.3×–3.0×).
        let asrEnd = segments.reduce(0.0) { max($0, $1.timestamp + $1.duration) }
        let rawRatio = asrEnd > 0.5 ? duration / asrEnd : 1.0
        let timeScale = (rawRatio >= 1.3 && rawRatio <= 3.0) ? rawRatio : 1.0

        let referenceWords = document.flatWords
        let hypothesisWords = segments.map {
            (text: $0.substring,
             start: $0.timestamp * timeScale,
             end: ($0.timestamp + $0.duration) * timeScale)
        }
        let aligned = LyricWordAligner.align(reference: referenceWords, hypothesis: hypothesisWords)

        let matchedCount = aligned.filter(\.matched).count
        let confidence = Double(matchedCount) / Double(max(1, referenceWords.count))
        guard confidence >= 0.2 else {
            throw AlignmentError.insufficientConfidence
        }

        return LyricWordAligner.interpolate(aligned, duration: duration)
    }

    private static func requestAuthorizationIfNeeded() async -> Bool {
        switch SFSpeechRecognizer.authorizationStatus() {
        case .authorized:
            return true
        case .denied, .restricted:
            return false
        case .notDetermined:
            return await withCheckedContinuation { continuation in
                SFSpeechRecognizer.requestAuthorization { status in
                    continuation.resume(returning: status == .authorized)
                }
            }
        @unknown default:
            return false
        }
    }

    private static func transcribe(url: URL, recognizer: SFSpeechRecognizer) async throws -> [SFTranscriptionSegment] {
        try await withCheckedThrowingContinuation { continuation in
            let request = SFSpeechURLRecognitionRequest(url: url)
            request.shouldReportPartialResults = false

            var didResume = false
            recognizer.recognitionTask(with: request) { result, error in
                guard !didResume else { return }
                if let error {
                    didResume = true
                    continuation.resume(throwing: AlignmentError.recognitionFailed(error.localizedDescription))
                    return
                }
                guard let result, result.isFinal else { return }
                didResume = true
                continuation.resume(returning: result.bestTranscription.segments)
            }
        }
    }
}
