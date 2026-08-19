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

    private var aligned: AlignedLyrics? { project.alignedLyrics }

    private var currentLineIndex: Int? {
        guard let aligned else { return nil }
        var result: Int?
        for (index, line) in aligned.lines.enumerated() {
            if line.start <= playback.currentTime {
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
                    lyricsScrollView(aligned: aligned)
                } else {
                    Spacer()
                    Text("No synced lyrics yet.")
                        .foregroundStyle(AppTheme.textSecondary)
                    Spacer()
                }

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

            Color.clear.frame(width: 36, height: 36)
        }
        .padding(.horizontal, AppTheme.Spacing.lg)
        .padding(.top, AppTheme.Spacing.md)
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
                                currentTime: playback.currentTime
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
