import AVFoundation
import Combine

/// Owns the app's single `AVAudioSession` configuration and publishes interruption /
/// route-change events so recording and playback services can react without each
/// duplicating NotificationCenter plumbing.
final class AudioSessionManager {
    static let shared = AudioSessionManager()
    private init() {}

    enum Mode {
        case recording
        case playback
    }

    private(set) var currentMode: Mode?

    let interruptionBegan = PassthroughSubject<Void, Never>()
    let interruptionEnded = PassthroughSubject<Bool, Never>()
    let routeChanged = PassthroughSubject<Void, Never>()

    /// Call once at app launch. Establishes a base category so audio session errors
    /// surface early rather than the first time the user hits record.
    func configureForPlaybackAndRecording() {
        do {
            try AVAudioSession.sharedInstance().setCategory(
                .playAndRecord,
                mode: .default,
                options: [.allowBluetooth, .defaultToSpeaker]
            )
        } catch {
            print("AudioSessionManager: failed to set base category: \(error)")
        }
        observeInterruptions()
        observeRouteChanges()
    }

    func activateForRecording() throws {
        let session = AVAudioSession.sharedInstance()
        try session.setCategory(.playAndRecord, mode: .default, options: [.allowBluetooth, .defaultToSpeaker])
        try session.setActive(true, options: [])
        currentMode = .recording
    }

    func activateForPlayback() throws {
        let session = AVAudioSession.sharedInstance()
        try session.setCategory(.playback, mode: .default, options: [])
        try session.setActive(true, options: [])
        currentMode = .playback
    }

    func deactivate() {
        try? AVAudioSession.sharedInstance().setActive(false, options: [.notifyOthersOnDeactivation])
        currentMode = nil
    }

    private func observeInterruptions() {
        NotificationCenter.default.addObserver(
            self,
            selector: #selector(handleInterruption(_:)),
            name: AVAudioSession.interruptionNotification,
            object: nil
        )
    }

    private func observeRouteChanges() {
        NotificationCenter.default.addObserver(
            self,
            selector: #selector(handleRouteChange(_:)),
            name: AVAudioSession.routeChangeNotification,
            object: nil
        )
    }

    @objc private func handleInterruption(_ notification: Notification) {
        guard let info = notification.userInfo,
              let typeValue = info[AVAudioSessionInterruptionTypeKey] as? UInt,
              let type = AVAudioSession.InterruptionType(rawValue: typeValue) else { return }
        switch type {
        case .began:
            interruptionBegan.send()
        case .ended:
            var shouldResume = false
            if let optionsValue = info[AVAudioSessionInterruptionOptionKey] as? UInt {
                let options = AVAudioSession.InterruptionOptions(rawValue: optionsValue)
                shouldResume = options.contains(.shouldResume)
            }
            interruptionEnded.send(shouldResume)
        @unknown default:
            break
        }
    }

    @objc private func handleRouteChange(_ notification: Notification) {
        routeChanged.send()
    }
}
