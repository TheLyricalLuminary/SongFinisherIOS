import SwiftUI
import SwiftData

/// Lets the user describe a song, dial in how it should be written, generate
/// structured lyrics, edit them freely, and save.
///
/// Theme and style stay inline as the two things you always touch; the rest of
/// the craft controls live one tap away in `LyricCraftSettingsView` so this
/// screen keeps room for the lyrics themselves.
struct GenerateLyricsView: View {
    let project: Project

    @Environment(\.dismiss) private var dismiss
    @Environment(\.modelContext) private var modelContext

    @State private var promptText: String
    @State private var lyricsText: String
    @State private var settings: LyricSettings
    @State private var service: LyricGenerationService
    @State private var isGenerating = false
    @State private var isSaving = false
    @State private var errorMessage: String?
    @State private var isServiceSettingsPresented = false
    @State private var isCraftSettingsPresented = false
    @State private var isDetectingTempo = false
    @State private var vocalDetectionResult: VocalContentResult?
    @State private var isSuggestingVibe = false

    init(project: Project) {
        self.project = project
        _promptText = State(initialValue: project.lyricsPrompt)
        _lyricsText = State(initialValue: project.lyricsText)
        _settings = State(initialValue: project.lyricSettings)
        _service = State(initialValue: LyricGenerationServiceFactory.makeDefault())
    }

    private var trimmedPrompt: String {
        promptText.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private var canGenerate: Bool { !trimmedPrompt.isEmpty && !isGenerating }

    private var canSave: Bool {
        !lyricsText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && !isSaving
    }

    var body: some View {
        NavigationStack {
            ZStack {
                AppTheme.background.ignoresSafeArea()

                VStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
                    briefSection
                    lyricsSection
                }
                .padding(AppTheme.Spacing.lg)
            }
            .navigationTitle(project.title)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
                ToolbarItem(placement: .primaryAction) {
                    Button {
                        isServiceSettingsPresented = true
                    } label: {
                        Image(systemName: "gearshape")
                    }
                }
            }
            .sheet(isPresented: $isServiceSettingsPresented, onDismiss: {
                service = LyricGenerationServiceFactory.makeDefault()
            }) {
                LyricServiceSettingsView()
            }
            .sheet(isPresented: $isCraftSettingsPresented, onDismiss: persistSettings) {
                LyricCraftSettingsView(mode: .full, settings: $settings)
            }
            .alert(
                "Something went wrong",
                isPresented: Binding(
                    get: { errorMessage != nil },
                    set: { newValue in if !newValue { errorMessage = nil } }
                )
            ) {
                Button("OK") { errorMessage = nil }
            } message: {
                Text(errorMessage ?? "")
            }
        }
    }

    // MARK: - Sections

    private var briefSection: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
            fieldLabel("Theme")
            TextField(
                "e.g. leaving a small town at night",
                text: $promptText,
                axis: .vertical
            )
            .lineLimit(1...3)
            .padding(AppTheme.Spacing.md)
            .background(AppTheme.surface)
            .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.sm, style: .continuous))
            .foregroundStyle(AppTheme.textPrimary)

            fieldLabel("Style")
            TextField(
                "e.g. sparse indie folk, restrained",
                text: $settings.style,
                axis: .vertical
            )
            .lineLimit(1...2)
            .padding(AppTheme.Spacing.md)
            .background(AppTheme.surface)
            .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.sm, style: .continuous))
            .foregroundStyle(AppTheme.textPrimary)

            Text("Shapes the tone and vocabulary. These words never appear in the lyrics themselves.")
                .font(.caption2)
                .foregroundStyle(AppTheme.textTertiary)

            craftSummaryButton
            autoDetectTempoButton
            autoGenerateVibeButton

            Button {
                Task { await generate() }
            } label: {
                HStack(spacing: AppTheme.Spacing.sm) {
                    if isGenerating {
                        ProgressView().tint(.black)
                        Text("Writing…").font(.headline)
                    } else {
                        Image(systemName: "sparkles")
                        Text(lyricsText.isEmpty ? "Generate Lyrics" : "Regenerate")
                            .font(.headline)
                    }
                }
                .foregroundStyle(.black)
                .frame(maxWidth: .infinity)
                .padding(.vertical, 12)
            }
            .buttonStyle(.plain)
            .disabled(!canGenerate)
            .background(canGenerate ? Color.white : Color.white.opacity(0.3))
            .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.pill, style: .continuous))

            if !LyricGenerationServiceFactory.isRemoteConfigured {
                Text("Using the built-in local generator (fully offline). Add a Claude API key in Settings for AI-written lyrics.")
                    .font(.caption2)
                    .foregroundStyle(AppTheme.textTertiary)
            }
        }
    }

    private var craftSummaryButton: some View {
        Button {
            isCraftSettingsPresented = true
        } label: {
            HStack(spacing: AppTheme.Spacing.sm) {
                Image(systemName: "slider.horizontal.3")
                    .foregroundStyle(AppTheme.accent)
                VStack(alignment: .leading, spacing: 1) {
                    Text("Craft & Music")
                        .font(.subheadline.weight(.medium))
                        .foregroundStyle(AppTheme.textPrimary)
                    Text(settings.summary)
                        .font(.caption2)
                        .foregroundStyle(AppTheme.textSecondary)
                        .lineLimit(1)
                }
                Spacer()
                Image(systemName: "chevron.right")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(AppTheme.textTertiary)
            }
            .padding(AppTheme.Spacing.md)
            .background(AppTheme.surface)
            .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.sm, style: .continuous))
        }
        .buttonStyle(.plain)
    }

    /// On-device tempo estimate from the project's own recording — no network
    /// call, no third-party audio-analysis account. Phase 1 of auto-detect;
    /// syllables/rhyme (from a transcript, when the take has words) and
    /// theme/style (via the existing Claude integration, from that same
    /// transcript) are later phases, not audio properties this button covers.
    private var autoDetectTempoButton: some View {
        VStack(alignment: .leading, spacing: 4) {
            Button {
                Task { await detectTempo() }
            } label: {
                HStack(spacing: AppTheme.Spacing.sm) {
                    if isDetectingTempo {
                        ProgressView().tint(AppTheme.accent)
                        Text("Listening…")
                    } else {
                        Image(systemName: "waveform.badge.magnifyingglass")
                        Text("Auto-Detect Tempo")
                    }
                }
                .font(.caption.weight(.medium))
                .foregroundStyle(AppTheme.accent)
            }
            .buttonStyle(.plain)
            .disabled(isDetectingTempo)

            if let vocalDetectionResult {
                vocalDetectionLabel(vocalDetectionResult)
            }
        }
    }

    /// STYLE is a fair guess from tempo/time-signature alone, so it's always
    /// offered; THEME only comes back populated when there's a real transcript
    /// (run via Auto-Detect Tempo, or here if that hasn't happened yet) — a
    /// wordless take gets no theme suggestion rather than an invented one.
    /// Works with or without a Claude key: falls back to a local, cruder
    /// suggestion (see LocalVibeSuggestionService) when none is configured.
    private var autoGenerateVibeButton: some View {
        Button {
            Task { await suggestVibe() }
        } label: {
            HStack(spacing: AppTheme.Spacing.sm) {
                if isSuggestingVibe {
                    ProgressView().tint(AppTheme.accent)
                    Text("Thinking…")
                } else {
                    Image(systemName: "sparkles")
                    Text("Auto-Generate Theme & Style")
                }
            }
            .font(.caption.weight(.medium))
            .foregroundStyle(AppTheme.accent)
        }
        .buttonStyle(.plain)
        .disabled(isSuggestingVibe)
    }

    private func vocalDetectionLabel(_ result: VocalContentResult) -> some View {
        Group {
            switch result {
            case .instrumental:
                Text("Instrumental — no vocals detected in this take")
            case .vocals(let wordCount, _):
                Text("Vocals detected — \(wordCount) word\(wordCount == 1 ? "" : "s") recognized")
            }
        }
        .font(.caption2)
        .foregroundStyle(AppTheme.textTertiary)
    }

    private var lyricsSection: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
            fieldLabel("Lyrics")

            ZStack(alignment: .topLeading) {
                if lyricsText.isEmpty {
                    Text("Your generated lyrics will appear here. You can edit freely before saving.")
                        .font(.body)
                        .foregroundStyle(AppTheme.textTertiary)
                        .padding(.horizontal, 16)
                        .padding(.vertical, 20)
                }
                TextEditor(text: $lyricsText)
                    .scrollContentBackground(.hidden)
                    .font(.body)
                    .foregroundStyle(AppTheme.textPrimary)
                    .padding(AppTheme.Spacing.sm)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(AppTheme.surface)
            .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous))

            Button {
                save()
            } label: {
                Group {
                    if isSaving {
                        ProgressView().tint(.black)
                    } else {
                        Text("Save Lyrics").font(.headline)
                    }
                }
                .foregroundStyle(.black)
                .frame(maxWidth: .infinity)
                .padding(.vertical, 14)
            }
            .buttonStyle(.plain)
            .disabled(!canSave)
            .background(canSave ? Color.white : Color.white.opacity(0.3))
            .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.pill, style: .continuous))
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private func fieldLabel(_ text: String) -> some View {
        Text(text)
            .font(.caption.weight(.semibold))
            .foregroundStyle(AppTheme.textSecondary)
            .textCase(.uppercase)
    }

    // MARK: - Actions

    private func generate() async {
        errorMessage = nil
        isGenerating = true
        defer { isGenerating = false }
        do {
            let request = LyricGenerationRequest(prompt: trimmedPrompt, settings: settings)
            let result = try await service.generateLyrics(request)
            lyricsText = result.text
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    private func detectTempo() async {
        errorMessage = nil
        isDetectingTempo = true
        defer { isDetectingTempo = false }

        let url = FileStorage.audioURL(projectID: project.id, fileName: project.audioFileName)

        // Tempo (pure local DSP) and vocal detection (speech recognition) are
        // independent, so they run concurrently rather than one after the other.
        async let tempoResult: Int? = Task.detached(priority: .userInitiated) {
            AudioEnergyAnalyzer.estimateTempo(url: url)
        }.value
        async let vocalResult = VocalContentDetector.detect(audioURL: url)

        let (bpm, vocals) = await (tempoResult, vocalResult)

        vocalDetectionResult = vocals
        if let bpm {
            settings.bpm = bpm
            persistSettings()
        } else {
            errorMessage = "Couldn't confidently detect a tempo from this recording — try setting it manually in Craft & Music."
        }
    }

    private func suggestVibe() async {
        errorMessage = nil
        isSuggestingVibe = true
        defer { isSuggestingVibe = false }

        if vocalDetectionResult == nil {
            let url = FileStorage.audioURL(projectID: project.id, fileName: project.audioFileName)
            vocalDetectionResult = await VocalContentDetector.detect(audioURL: url)
        }
        let transcript: String? = {
            if case .vocals(_, let transcript) = vocalDetectionResult { return transcript }
            return nil
        }()

        do {
            let suggestion = try await VibeSuggestionServiceFactory.suggestVibe(
                transcript: transcript,
                bpm: settings.bpm > 0 ? settings.bpm : nil,
                timeSignature: settings.timeSignature
            )
            if let theme = suggestion.theme { promptText = theme }
            settings.style = suggestion.style
            persistSettings()
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    /// Settings are saved as soon as the craft sheet closes, so tweaking them is
    /// never lost even if the user backs out without saving lyrics.
    private func persistSettings() {
        try? ProjectStore.saveLyricSettings(settings, to: project, context: modelContext)
    }

    private func save() {
        isSaving = true
        do {
            try ProjectStore.saveLyricSettings(settings, to: project, context: modelContext)
            try ProjectStore.saveLyrics(
                prompt: trimmedPrompt,
                text: lyricsText,
                to: project,
                context: modelContext
            )
            dismiss()
        } catch {
            errorMessage = "Couldn't save lyrics."
            isSaving = false
        }
    }
}
