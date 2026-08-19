import SwiftUI

/// Basic playback sheet for a saved project: waveform, title, and a preview
/// player. Once the project has lyrics, this also offers alignment and a way
/// into the full-screen synced player (`SyncedLyricsPlayerView`).
struct ProjectPlaybackSheet: View {
    let project: Project

    @Environment(\.dismiss) private var dismiss
    @Environment(\.modelContext) private var modelContext
    @StateObject private var playback = AudioPlaybackService()
    @State private var loadError: String?
    @State private var isLyricsPresented = false
    @State private var isAligning = false
    @State private var isRegenerating = false
    @State private var alignmentErrorMessage: String?
    @State private var isSyncedPlayerPresented = false
    @State private var isCraftSettingsPresented = false
    @State private var craftSettings: LyricSettings = .default

    var body: some View {
        NavigationStack {
            ZStack {
                AppTheme.backgroundGradient.ignoresSafeArea()

                VStack(spacing: AppTheme.Spacing.xl) {
                    Spacer()

                    ZStack {
                        Circle()
                            .fill(AppTheme.accentGradient)
                            .frame(width: 180, height: 180)
                            .opacity(0.9)
                        Image(systemName: "waveform")
                            .font(.system(size: 56, weight: .semibold))
                            .foregroundStyle(.white)
                    }

                    Text(project.title)
                        .font(.title2.weight(.semibold))
                        .foregroundStyle(AppTheme.textPrimary)
                        .multilineTextAlignment(.center)
                        .padding(.horizontal, AppTheme.Spacing.lg)

                    Spacer()

                    if !project.lyricsText.isEmpty {
                        lyricsSyncSection
                    }

                    if let loadError {
                        Text(loadError)
                            .font(.footnote)
                            .foregroundStyle(AppTheme.danger)
                    } else {
                        AudioPreviewPlayer(playback: playback)
                            .padding(AppTheme.Spacing.lg)
                    }
                }
            }
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Close") {
                        playback.stop()
                        dismiss()
                    }
                }
                ToolbarItem(placement: .primaryAction) {
                    Button {
                        isLyricsPresented = true
                    } label: {
                        Label(project.lyricsText.isEmpty ? "Lyrics" : "Edit Lyrics", systemImage: "text.quote")
                    }
                }
            }
            .sheet(isPresented: $isLyricsPresented) {
                GenerateLyricsView(project: project)
            }
            .sheet(isPresented: $isCraftSettingsPresented, onDismiss: persistCraftSettings) {
                LyricCraftSettingsView(
                    mode: .postAlignment,
                    settings: $craftSettings,
                    isBusy: isRegenerating || isAligning,
                    onRegenerate: {
                        isCraftSettingsPresented = false
                        Task { await regenerateLyrics() }
                    },
                    onRealign: {
                        isCraftSettingsPresented = false
                        Task { await runAlignment() }
                    }
                )
            }
            .fullScreenCover(isPresented: $isSyncedPlayerPresented) {
                SyncedLyricsPlayerView(project: project)
            }
            .alert(
                "Something went wrong",
                isPresented: Binding(
                    get: { alignmentErrorMessage != nil },
                    set: { newValue in if !newValue { alignmentErrorMessage = nil } }
                )
            ) {
                Button("OK") { alignmentErrorMessage = nil }
            } message: {
                Text(alignmentErrorMessage ?? "")
            }
        }
        .onAppear(perform: loadAudio)
    }

    private var lyricsSyncSection: some View {
        VStack(spacing: AppTheme.Spacing.sm) {
            alignmentActionButton

            // Once there's an alignment to compare against, expose the craft
            // settings so the user can tune and regenerate or re-align.
            if project.hasAlignment {
                Button {
                    craftSettings = project.lyricSettings
                    isCraftSettingsPresented = true
                } label: {
                    HStack(spacing: AppTheme.Spacing.sm) {
                        Image(systemName: "slider.horizontal.3")
                        Text("Lyric Settings").font(.subheadline.weight(.medium))
                        Spacer()
                        Text(project.lyricSettings.summary)
                            .font(.caption2)
                            .foregroundStyle(AppTheme.textTertiary)
                            .lineLimit(1)
                    }
                    .foregroundStyle(AppTheme.textPrimary)
                    .padding(.horizontal, AppTheme.Spacing.md)
                    .padding(.vertical, 10)
                    .frame(maxWidth: .infinity)
                    .background(AppTheme.surface)
                    .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.pill, style: .continuous))
                }
                .buttonStyle(.plain)
            }
        }
        .padding(.horizontal, AppTheme.Spacing.lg)
    }

    private var alignmentActionButton: some View {
        Group {
            if isRegenerating {
                HStack(spacing: AppTheme.Spacing.sm) {
                    ProgressView().tint(AppTheme.textPrimary)
                    Text("Rewriting lyrics…")
                }
                .font(.headline)
                .foregroundStyle(AppTheme.textPrimary)
                .frame(maxWidth: .infinity)
                .padding(.vertical, 12)
                .background(AppTheme.surface)
                .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.pill, style: .continuous))
            } else if project.hasAlignment && !project.isAlignmentStale {
                Button {
                    isSyncedPlayerPresented = true
                } label: {
                    HStack(spacing: AppTheme.Spacing.sm) {
                        Image(systemName: "text.line.first.and.arrowtriangle.forward")
                        Text("Play with Lyrics").font(.headline)
                    }
                    .foregroundStyle(.black)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 12)
                }
                .buttonStyle(.plain)
                .background(Color.white)
                .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.pill, style: .continuous))
            } else {
                Button {
                    Task { await runAlignment() }
                } label: {
                    HStack(spacing: AppTheme.Spacing.sm) {
                        if isAligning {
                            ProgressView().tint(AppTheme.textPrimary)
                            Text("Aligning…")
                        } else {
                            Image(systemName: "waveform.badge.magnifyingglass")
                            Text(project.hasAlignment ? "Re-align Lyrics" : "Align Lyrics")
                        }
                    }
                    .font(.headline)
                    .foregroundStyle(AppTheme.textPrimary)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 12)
                }
                .buttonStyle(.plain)
                .disabled(isAligning)
                .background(AppTheme.surface)
                .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.pill, style: .continuous))
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

    private func runAlignment() async {
        isAligning = true
        defer { isAligning = false }
        do {
            let audioURL = FileStorage.audioURL(projectID: project.id, fileName: project.audioFileName)
            let service = LocalAlignmentService()
            let aligned = try await service.align(lyricsText: project.lyricsText, audioURL: audioURL, duration: project.duration)
            try ProjectStore.saveAlignment(aligned, to: project, context: modelContext)
        } catch {
            alignmentErrorMessage = error.localizedDescription
        }
    }

    /// Saves whatever the user changed in the craft sheet, even if they close it
    /// without regenerating or re-aligning.
    private func persistCraftSettings() {
        try? ProjectStore.saveLyricSettings(craftSettings, to: project, context: modelContext)
    }

    /// Rewrites the lyrics from the saved theme using the freshly tuned settings.
    /// The new text makes the existing alignment stale, so the sheet then offers
    /// "Re-align Lyrics" — one tap to bring the timing back in sync.
    private func regenerateLyrics() async {
        let prompt = project.lyricsPrompt.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !prompt.isEmpty else {
            alignmentErrorMessage = "This project has no theme prompt yet. Open Lyrics to write one first."
            return
        }

        isRegenerating = true
        defer { isRegenerating = false }
        do {
            try ProjectStore.saveLyricSettings(craftSettings, to: project, context: modelContext)
            let service = LyricGenerationServiceFactory.makeDefault()
            let request = LyricGenerationRequest(prompt: prompt, settings: craftSettings)
            let result = try await service.generateLyrics(request)
            try ProjectStore.saveLyrics(
                prompt: prompt,
                text: result.text,
                to: project,
                context: modelContext
            )
        } catch {
            alignmentErrorMessage = error.localizedDescription
        }
    }
}
