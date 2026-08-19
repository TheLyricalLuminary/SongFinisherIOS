import SwiftUI

/// A compact play/pause + scrubber control bound to an `AudioPlaybackService`.
/// Used both for reviewing a fresh take before saving and for basic playback of
/// a saved project.
struct AudioPreviewPlayer: View {
    @ObservedObject var playback: AudioPlaybackService

    @State private var isScrubbing = false
    @State private var scrubTime: TimeInterval = 0

    private var displayTime: TimeInterval {
        isScrubbing ? scrubTime : playback.currentTime
    }

    var body: some View {
        VStack(spacing: AppTheme.Spacing.md) {
            HStack(spacing: AppTheme.Spacing.md) {
                Button {
                    playback.togglePlayPause()
                } label: {
                    Image(systemName: playback.isPlaying ? "pause.fill" : "play.fill")
                        .font(.system(size: 20, weight: .semibold))
                        .foregroundStyle(.black)
                        .frame(width: 48, height: 48)
                        .background(Circle().fill(Color.white))
                }
                .buttonStyle(.plain)

                VStack(spacing: 6) {
                    Slider(
                        value: Binding(
                            get: { displayTime },
                            set: { newValue in
                                isScrubbing = true
                                scrubTime = newValue
                            }
                        ),
                        in: 0...max(playback.duration, 0.01),
                        onEditingChanged: { editing in
                            if !editing {
                                playback.seek(to: scrubTime)
                                isScrubbing = false
                            }
                        }
                    )
                    .tint(AppTheme.accent)

                    HStack {
                        Text(displayTime.mmss)
                        Spacer()
                        Text(playback.duration.mmss)
                    }
                    .font(.caption.monospacedDigit())
                    .foregroundStyle(AppTheme.textSecondary)
                }
            }
        }
    }
}
