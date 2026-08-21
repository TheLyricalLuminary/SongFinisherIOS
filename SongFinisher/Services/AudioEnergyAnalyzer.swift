import AVFoundation

/// A coarse loudness profile of an audio file: RMS energy per fixed-size window,
/// read in chunks so memory use stays bounded regardless of file length.
struct AudioEnergyProfile {
    var windowDuration: TimeInterval
    var rmsValues: [Float]
    var duration: TimeInterval
}

enum AudioEnergyAnalyzer {
    static func analyze(url: URL, windowDuration: TimeInterval = 0.1) throws -> AudioEnergyProfile {
        let file = try AVAudioFile(forReading: url)
        let format = file.processingFormat
        let sampleRate = format.sampleRate
        guard sampleRate > 0, file.length > 0 else {
            throw AlignmentError.audioUnavailable
        }

        let windowFrameCount = AVAudioFrameCount(max(1, sampleRate * windowDuration))
        guard let buffer = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: windowFrameCount) else {
            throw AlignmentError.audioUnavailable
        }

        var rmsValues: [Float] = []
        while file.framePosition < file.length {
            try file.read(into: buffer, frameCount: windowFrameCount)
            guard buffer.frameLength > 0 else { break }
            rmsValues.append(rms(of: buffer))
        }

        let duration = Double(file.length) / sampleRate
        return AudioEnergyProfile(windowDuration: windowDuration, rmsValues: rmsValues, duration: duration)
    }

    private static func rms(of buffer: AVAudioPCMBuffer) -> Float {
        guard let channelData = buffer.floatChannelData else { return 0 }
        let channelCount = Int(buffer.format.channelCount)
        let frameLength = Int(buffer.frameLength)
        guard frameLength > 0, channelCount > 0 else { return 0 }

        var sumSquares: Float = 0
        for channel in 0..<channelCount {
            let samples = channelData[channel]
            for i in 0..<frameLength {
                sumSquares += samples[i] * samples[i]
            }
        }
        let totalSamples = Float(frameLength * channelCount)
        return (sumSquares / totalSamples).squareRoot()
    }

    // MARK: - Tempo estimation

    /// Coarser windows (like the 0.1s default used for silence-gap detection)
    /// smear note attacks together — this is fine-grained enough to resolve
    /// individual onsets in typical acoustic material.
    private static let onsetWindowDuration: TimeInterval = 0.02

    /// Estimates tempo (BPM) on-device from the audio's energy envelope: peak-
    /// pick sharp rises in loudness (a proxy for note/drum/syllable attacks —
    /// no FFT/spectral-flux needed for this), build a histogram of inter-onset
    /// intervals converted to BPM, and resolve half/double-time ambiguity
    /// toward the range most material actually sits in. Returns nil when
    /// there's too little onset activity to estimate confidently (a very
    /// short, quiet, or sustained-tone clip with no clear attacks) rather than
    /// guessing with no real signal.
    static func estimateTempo(url: URL) -> Int? {
        guard let profile = try? analyze(url: url, windowDuration: onsetWindowDuration),
              profile.rmsValues.count > 4 else {
            return nil
        }

        let onsets = pickOnsets(from: profile)
        guard onsets.count >= 4 else { return nil }

        let candidates = intervalCandidates(from: onsets)
        guard !candidates.isEmpty else { return nil }

        return resolveOctave(bestBPM(from: candidates))
    }

    /// A window counts as an onset when its energy rises sharply over the
    /// previous window and it's the local peak of that rise, with a short
    /// refractory period so one transient isn't counted twice.
    private static func pickOnsets(from profile: AudioEnergyProfile) -> [TimeInterval] {
        let values = profile.rmsValues
        var flux = [Float](repeating: 0, count: values.count)
        for i in 1..<values.count {
            flux[i] = max(0, values[i] - values[i - 1])
        }

        let mean = flux.reduce(0, +) / Float(max(1, flux.count))
        let variance = flux.reduce(Float(0)) { $0 + ($1 - mean) * ($1 - mean) } / Float(max(1, flux.count))
        let threshold = mean + variance.squareRoot() * 1.2

        let refractoryWindows = max(1, Int(0.08 / profile.windowDuration))
        var onsets: [TimeInterval] = []
        var lastOnsetIndex = -refractoryWindows

        for i in 1..<(flux.count - 1) {
            guard flux[i] > threshold, flux[i] >= flux[i - 1], flux[i] >= flux[i + 1] else { continue }
            guard i - lastOnsetIndex >= refractoryWindows else { continue }
            onsets.append(Double(i) * profile.windowDuration)
            lastOnsetIndex = i
        }
        return onsets
    }

    /// Converts onset spacing into BPM candidates within a plausible tempo
    /// range. Spans of 1-3 onsets are all considered (not just consecutive
    /// pairs) so a single missed onset doesn't throw off the estimate.
    private static func intervalCandidates(from onsets: [TimeInterval]) -> [Double] {
        var candidates: [Double] = []
        for span in 1...3 {
            guard onsets.count > span else { continue }
            for i in span..<onsets.count {
                let interval = onsets[i] - onsets[i - span]
                guard interval > 0 else { continue }
                let bpm = 60.0 / interval * Double(span)
                if bpm >= 40, bpm <= 220 { candidates.append(bpm) }
            }
        }
        return candidates
    }

    /// Buckets candidates into 1-BPM-wide bins, spreading each vote slightly
    /// into neighboring buckets to smooth quantization noise, and returns the
    /// most-voted bucket.
    private static func bestBPM(from candidates: [Double]) -> Double {
        var votes: [Int: Double] = [:]
        for bpm in candidates {
            let bucket = Int(bpm.rounded())
            for offset in -1...1 {
                votes[bucket + offset, default: 0] += offset == 0 ? 1.0 : 0.4
            }
        }
        let winner = votes.max { $0.value < $1.value }?.key ?? 120
        return Double(winner)
    }

    /// Resolves half/double-time ambiguity: if double or half the estimate
    /// lands in the range most songs actually sit in, prefer that instead.
    private static func resolveOctave(_ bpm: Double) -> Int {
        let common = 80.0...160.0
        if !common.contains(bpm) {
            if common.contains(bpm * 2) { return Int((bpm * 2).rounded()) }
            if common.contains(bpm / 2) { return Int((bpm / 2).rounded()) }
        }
        return Int(bpm.rounded())
    }
}
