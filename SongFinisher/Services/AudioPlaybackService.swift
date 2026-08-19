import AVFoundation
import Combine

/// Plays a single local audio file and publishes playback position for UI binding.
/// Phase 1 scope: local file playback only (no lock-screen/remote-command
/// integration yet — that lands with the full synced player).
@MainActor
final class AudioPlaybackService: NSObject, ObservableObject {
    @Published private(set) var isPlaying = false
    @Published private(set) var currentTime: TimeInterval = 0
    @Published private(set) var duration: TimeInterval = 0

    private var player: AVAudioPlayer?
    private var displayTimer: Timer?
    private var cancellables = Set<AnyCancellable>()

    override init() {
        super.init()
        AudioSessionManager.shared.interruptionBegan
            .sink { [weak self] in self?.pause() }
            .store(in: &cancellables)
    }

    func load(url: URL) throws {
        stop()
        let newPlayer = try AVAudioPlayer(contentsOf: url)
        newPlayer.delegate = self
        newPlayer.prepareToPlay()
        player = newPlayer
        duration = newPlayer.duration
        currentTime = 0
    }

    func play() {
        guard let player else { return }
        try? AudioSessionManager.shared.activateForPlayback()
        player.play()
        isPlaying = true
        startDisplayTimer()
    }

    func pause() {
        player?.pause()
        isPlaying = false
        stopDisplayTimer()
    }

    func stop() {
        player?.stop()
        player = nil
        isPlaying = false
        currentTime = 0
        duration = 0
        stopDisplayTimer()
    }

    func togglePlayPause() {
        isPlaying ? pause() : play()
    }

    func seek(to time: TimeInterval) {
        guard let player else { return }
        let clamped = max(0, min(time, player.duration))
        player.currentTime = clamped
        currentTime = clamped
    }

    private func startDisplayTimer() {
        displayTimer?.invalidate()
        displayTimer = Timer.scheduledTimer(withTimeInterval: 1.0 / 30.0, repeats: true) { [weak self] _ in
            Task { @MainActor in self?.tick() }
        }
    }

    private func stopDisplayTimer() {
        displayTimer?.invalidate()
        displayTimer = nil
    }

    private func tick() {
        guard let player else { return }
        currentTime = player.currentTime
    }
}

extension AudioPlaybackService: AVAudioPlayerDelegate {
    nonisolated func audioPlayerDidFinishPlaying(_ player: AVAudioPlayer, successfully flag: Bool) {
        Task { @MainActor [weak self] in
            guard let self else { return }
            self.isPlaying = false
            self.currentTime = 0
            self.stopDisplayTimer()
        }
    }
}
