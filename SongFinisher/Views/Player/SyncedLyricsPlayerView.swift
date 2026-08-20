import SwiftUI

/// The Phase 3 synced player: plays only the project's original audio while
/// its aligned lyrics scroll and highlight in real time. The current line is
/// centered and enlarged with karaoke-style word highlighting; tapping any
/// line seeks playback there, and scrubbing (via the shared preview player)
/// snaps the highlight to match immediately since both are driven by the same
/// `AudioPlaybackService.currentTime`.
struct SyncedLyricsPlayerView: View {
    let project: Project

    @Environment(\.dismiss) private var dismiss
    @StateObject private var playback = AudioPlaybackService()
    @State private var loadError: String?
    @State private var lyricPace: Double = 1.0
    @State private var showDiagnostic = false

    private static let paceSteps: [Double] = [0.15, 0.25, 0.40, 0.60, 0.80, 1.00]

    private var aligned: AlignedLyrics? { project.alignedLyrics }

    /// Real audio time scaled by lyricPace so the lyric renderer can run
    /// slower or faster than the underlying audio without touching BPM,
    /// syllable analysis, or alignment timestamps.
    private var effectiveDisplayTime: TimeInterval {
        playback.currentTime * lyricPace
    }

    private var currentLineIndex: Int? {
        guard let aligned else { return nil }
        var result: Int?
        for (index, line) in aligned.lines.enumerated() {
            if line.start <= effectiveDisplayTime {
                result = index
            } else {
                break
            }
        }
        return result
    }

    var body: some View {
        ZStack {
            AppTheme.background.ignoresSafeArea()

            VStack(spacing: 0) {
                header

                if let loadError {
                    Spacer()
                    Text(loadError)
                        .font(.footnote)
                        .foregroundStyle(AppTheme.danger)
                        .padding(.horizontal, AppTheme.Spacing.lg)
                    Spacer()
                } else if let aligned {
                    if showDiagnostic { diagnosticBar }
                    lyricsScrollView(aligned: aligned)
                } else {
                    Spacer()
                    Text("No synced lyrics yet.")
                        .foregroundStyle(AppTheme.textSecondary)
                    Spacer()
                }

                paceControl
                AudioPreviewPlayer(playback: playback)
                    .padding(AppTheme.Spacing.lg)
            }
        }
        .onAppear(perform: loadAudio)
    }

    private var header: some View {
        HStack {
            Button {
                playback.stop()
                dismiss()
            } label: {
                Image(systemName: "chevron.down")
                    .font(.headline)
                    .foregroundStyle(AppTheme.textPrimary)
                    .frame(width: 36, height: 36)
                    .background(Circle().fill(AppTheme.surface))
            }
            .buttonStyle(.plain)

            Spacer()

            Text(project.title)
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(AppTheme.textSecondary)
                .lineLimit(1)

            Spacer()

            Button {
                showDiagnostic.toggle()
            } label: {
                Image(systemName: "waveform.badge.magnifyingglass")
                    .font(.subheadline)
                    .foregroundStyle(showDiagnostic ? AppTheme.accent : AppTheme.textTertiary)
                    .frame(width: 36, height: 36)
            }
            .buttonStyle(.plain)
        }
        .padding(.horizontal, AppTheme.Spacing.lg)
        .padding(.top, AppTheme.Spacing.md)
    }

    private var paceControl: some View {
        VStack(spacing: 6) {
            HStack {
                Text("LYRIC PACE")
                    .font(.caption2.weight(.bold))
                    .foregroundStyle(AppTheme.textTertiary)
                Spacer()
                Text(Self.paceLabel(lyricPace))
                    .font(.caption.weight(.bold).monospacedDigit())
                    .foregroundStyle(AppTheme.accent)
            }

            Slider(value: $lyricPace, in: 0.10...1.50, step: 0.01)
                .tint(AppTheme.accent)

            HStack(spacing: 4) {
                ForEach(Self.paceSteps, id: \.self) { step in
                    Button {
                        withAnimation(.easeInOut(duration: 0.15)) { lyricPace = step }
                    } label: {
                        Text(Self.paceLabel(step))
                            .font(.caption2.weight(.semibold))
                            .foregroundStyle(abs(lyricPace - step) < 0.005 ? .black : AppTheme.textSecondary)
                            .padding(.horizontal, 8)
                            .padding(.vertical, 4)
                            .background(
                                RoundedRectangle(cornerRadius: AppTheme.Radius.pill, style: .continuous)
                                    .fill(abs(lyricPace - step) < 0.005 ? AppTheme.accent : AppTheme.surface)
                            )
                    }
                    .buttonStyle(.plain)
                }
            }
        }
        .padding(.horizontal, AppTheme.Spacing.lg)
        .padding(.bottom, AppTheme.Spacing.sm)
    }

    private var diagnosticBar: some View {
        HStack(spacing: 16) {
            label("Audio", value: String(format: "%.2fs", playback.currentTime))
            label("Effective", value: String(format: "%.2fs", effectiveDisplayTime))
            label("Pace", value: Self.paceLabel(lyricPace))
            if let idx = currentLineIndex {
                label("Line", value: "\(idx + 1)")
            }
        }
        .font(.caption2.monospaced())
        .foregroundStyle(AppTheme.textSecondary)
        .padding(.horizontal, AppTheme.Spacing.lg)
        .padding(.vertical, 6)
        .frame(maxWidth: .infinity)
        .background(AppTheme.surface)
    }

    private func label(_ title: String, value: String) -> some View {
        VStack(spacing: 1) {
            Text(title.uppercased())
                .foregroundStyle(AppTheme.textTertiary)
            Text(value)
                .foregroundStyle(AppTheme.textPrimary)
        }
    }

    private static func paceLabel(_ pace: Double) -> String {
        pace == 1.0 ? "1×" : String(format: "%.2g×", pace)
    }

    private func lyricsScrollView(aligned: AlignedLyrics) -> some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(spacing: AppTheme.Spacing.md) {
                    Color.clear.frame(height: 140)

                    ForEach(aligned.lines.indices, id: \.self) { index in
                        VStack(spacing: 4) {
                            if let title = aligned.lines[index].sectionTitle {
                                Text(title.uppercased())
                                    .font(.caption2.weight(.bold))
                                    .foregroundStyle(AppTheme.accent)
                                    .padding(.top, AppTheme.Spacing.sm)
                            }
                            LyricLineView(
                                line: aligned.lines[index],
                                isCurrent: index == currentLineIndex,
                                currentTime: effectiveDisplayTime
                            )
                        }
                        .id(index)
                        .contentShape(Rectangle())
                        .onTapGesture {
                            playback.seek(to: aligned.lines[index].start)
                        }
                    }

                    Color.clear.frame(height: 220)
                }
            }
            .onChange(of: currentLineIndex) { _, newIndex in
                guard let newIndex else { return }
                withAnimation(.easeInOut(duration: 0.4)) {
                    proxy.scrollTo(newIndex, anchor: .center)
                }
            }
        }
    }

    private func loadAudio() {
        let url = FileStorage.audioURL(projectID: project.id, fileName: project.audioFileName)
        do {
            try playback.load(url: url)
        } catch {
            loadError = "Couldn't load this project's audio."
        }
    }
}
