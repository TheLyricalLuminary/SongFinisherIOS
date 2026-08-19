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
}
