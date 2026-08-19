import AVFoundation
import Combine

enum AudioRecorderError: LocalizedError {
    case permissionDenied
    case failedToStart

    var errorDescription: String? {
        switch self {
        case .permissionDenied: return "Microphone access is required to record audio."
        case .failedToStart: return "Could not start recording."
        }
    }
}

/// Records high-quality audio (AAC, 44.1kHz, 256kbps) to a temporary file and
/// publishes live level metering for a waveform-style UI.
@MainActor
final class AudioRecorderService: NSObject, ObservableObject {
    @Published private(set) var isRecording = false
    @Published private(set) var currentTime: TimeInterval = 0
    @Published private(set) var meterLevel: Float = 0 // normalized 0...1

    private var recorder: AVAudioRecorder?
    private var levelTimer: Timer?
    private var recordingURL: URL?
    private var cancellables = Set<AnyCancellable>()

    private static let recordingSettings: [String: Any] = [
        AVFormatIDKey: Int(kAudioFormatMPEG4AAC),
        AVSampleRateKey: 44_100.0,
        AVNumberOfChannelsKey: 2,
        AVEncoderAudioQualityKey: AVAudioQuality.max.rawValue,
        AVEncoderBitRateKey: 256_000
    ]

    override init() {
        super.init()
        AudioSessionManager.shared.interruptionBegan
            .sink { [weak self] in self?.handleInterruption() }
            .store(in: &cancellables)
    }

    var permissionStatus: AVAudioApplication.recordPermission {
        AVAudioApplication.shared.recordPermission
    }

    func requestPermission() async -> Bool {
        await withCheckedContinuation { continuation in
            AVAudioApplication.requestRecordPermission { granted in
                continuation.resume(returning: granted)
            }
        }
    }

    @discardableResult
    func startRecording() async throws -> URL {
        if permissionStatus != .granted {
            let granted = await requestPermission()
            guard granted else { throw AudioRecorderError.permissionDenied }
        }

        try AudioSessionManager.shared.activateForRecording()

        let url = FileManager.default.temporaryDirectory
            .appendingPathComponent("recording-\(UUID().uuidString)")
            .appendingPathExtension("m4a")

        let newRecorder = try AVAudioRecorder(url: url, settings: Self.recordingSettings)
        newRecorder.delegate = self
        newRecorder.isMeteringEnabled = true
        guard newRecorder.record() else {
            throw AudioRecorderError.failedToStart
        }

        recorder = newRecorder
        recordingURL = url
        isRecording = true
        currentTime = 0
        startLevelTimer()
        return url
    }

    /// Stops recording and returns the file URL of the finished take, or nil if
    /// nothing was recorded.
    @discardableResult
    func stopRecording() -> URL? {
        recorder?.stop()
        stopLevelTimer()
        isRecording = false
        AudioSessionManager.shared.deactivate()
        return recordingURL
    }

    func cancelRecording() {
        recorder?.stop()
        if let url = recordingURL {
            try? FileManager.default.removeItem(at: url)
        }
        stopLevelTimer()
        isRecording = false
        recordingURL = nil
        currentTime = 0
        AudioSessionManager.shared.deactivate()
    }

    private func handleInterruption() {
        guard isRecording else { return }
        _ = stopRecording()
    }

    private func startLevelTimer() {
        levelTimer?.invalidate()
        levelTimer = Timer.scheduledTimer(withTimeInterval: 1.0 / 30.0, repeats: true) { [weak self] _ in
            Task { @MainActor in self?.tick() }
        }
    }

    private func stopLevelTimer() {
        levelTimer?.invalidate()
        levelTimer = nil
        meterLevel = 0
    }

    private func tick() {
        guard let recorder, recorder.isRecording else { return }
        recorder.updateMeters()
        let db = recorder.averagePower(forChannel: 0)
        let minDb: Float = -50
        let clamped = max(minDb, min(0, db))
        meterLevel = (clamped - minDb) / (0 - minDb)
        currentTime = recorder.currentTime
    }
}

extension AudioRecorderService: AVAudioRecorderDelegate {
    nonisolated func audioRecorderDidFinishRecording(_ recorder: AVAudioRecorder, successfully flag: Bool) {
        // State transitions are driven explicitly by stopRecording()/cancelRecording();
        // nothing to do here.
    }
}
