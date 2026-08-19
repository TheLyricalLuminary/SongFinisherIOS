import SwiftUI
import SwiftData

/// The record-or-import flow for creating a new project: capture or pick audio,
/// preview it, name the project, and save. Phase 1 scope — no lyrics yet.
struct RecordAudioView: View {
    @Environment(\.dismiss) private var dismiss
    @Environment(\.modelContext) private var modelContext

    @StateObject private var recorder = AudioRecorderService()
    @StateObject private var playback = AudioPlaybackService()

    enum Mode: String, CaseIterable {
        case record = "Record"
        case importFile = "Import"
    }

    @State private var mode: Mode = .record
    @State private var capturedURL: URL?
    @State private var capturedDuration: TimeInterval = 0
    @State private var titleText: String = ""
    @State private var errorMessage: String?
    @State private var isImporterPresented = false
    @State private var isSaving = false

    private var hasCapture: Bool { capturedURL != nil }

    var body: some View {
        NavigationStack {
            ZStack {
                AppTheme.backgroundGradient.ignoresSafeArea()

                VStack(spacing: AppTheme.Spacing.xl) {
                    if hasCapture {
                        reviewSection
                    } else {
                        modePicker
                        Spacer()
                        if mode == .record {
                            recordSection
                        } else {
                            importSection
                        }
                        Spacer()
                    }
                }
                .padding(AppTheme.Spacing.lg)
            }
            .navigationTitle("New Song")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { cancelAndDismiss() }
                }
            }
            .fileImporter(
                isPresented: $isImporterPresented,
                allowedContentTypes: AudioImportService.supportedTypes
            ) { result in
                handleImportResult(result)
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

    private var modePicker: some View {
        Picker("Mode", selection: $mode) {
            ForEach(Mode.allCases, id: \.self) { m in
                Text(m.rawValue).tag(m)
            }
        }
        .pickerStyle(.segmented)
    }

    private var recordSection: some View {
        VStack(spacing: AppTheme.Spacing.xl) {
            Text(recorder.currentTime.mmss)
                .font(.system(size: 48, weight: .light, design: .rounded))
                .monospacedDigit()
                .foregroundStyle(AppTheme.textPrimary)

            LevelMeterView(level: recorder.meterLevel)
                .frame(height: 48)

            Button {
                Task { await toggleRecording() }
            } label: {
                ZStack {
                    Circle()
                        .fill(recorder.isRecording ? AppTheme.danger : Color.white)
                        .frame(width: 84, height: 84)
                    if recorder.isRecording {
                        RoundedRectangle(cornerRadius: 6, style: .continuous)
                            .fill(Color.white)
                            .frame(width: 28, height: 28)
                    } else {
                        Circle()
                            .fill(AppTheme.danger)
                            .frame(width: 68, height: 68)
                    }
                }
            }
            .buttonStyle(.plain)

            Text(recorder.isRecording ? "Tap to stop" : "Tap to record")
                .font(.subheadline)
                .foregroundStyle(AppTheme.textSecondary)
        }
    }

    private var importSection: some View {
        VStack(spacing: AppTheme.Spacing.lg) {
            Image(systemName: "square.and.arrow.down")
                .font(.system(size: 40))
                .foregroundStyle(AppTheme.textSecondary)
            Text("Import an existing recording")
                .font(.headline)
                .foregroundStyle(AppTheme.textPrimary)
            Text("m4a, mp3, wav, aiff and more")
                .font(.footnote)
                .foregroundStyle(AppTheme.textTertiary)
            Button {
                isImporterPresented = true
            } label: {
                Text("Choose File")
                    .font(.headline)
                    .foregroundStyle(.black)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 14)
                    .background(Color.white)
                    .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.pill, style: .continuous))
            }
            .buttonStyle(.plain)
        }
    }

    private var reviewSection: some View {
        VStack(spacing: AppTheme.Spacing.lg) {
            Spacer()

            VStack(spacing: AppTheme.Spacing.sm) {
                Image(systemName: "waveform")
                    .font(.system(size: 36))
                    .foregroundStyle(AppTheme.accent)
                Text("Take ready")
                    .font(.headline)
                    .foregroundStyle(AppTheme.textPrimary)
            }

            AudioPreviewPlayer(playback: playback)
                .padding(AppTheme.Spacing.md)
                .cardSurface()

            TextField("Song title", text: $titleText)
                .textFieldStyle(.plain)
                .padding(AppTheme.Spacing.md)
                .background(AppTheme.surface)
                .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.sm, style: .continuous))
                .foregroundStyle(AppTheme.textPrimary)

            Spacer()

            HStack(spacing: AppTheme.Spacing.md) {
                Button {
                    discardCapture()
                } label: {
                    Text("Discard")
                        .font(.headline)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 14)
                }
                .foregroundStyle(AppTheme.danger)
                .background(AppTheme.surface)
                .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.pill, style: .continuous))

                Button {
                    save()
                } label: {
                    Group {
                        if isSaving {
                            ProgressView().tint(.black)
                        } else {
                            Text("Save").font(.headline)
                        }
                    }
                    .foregroundStyle(.black)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 14)
                }
                .disabled(isSaveDisabled)
                .background(isSaveDisabled ? Color.white.opacity(0.3) : Color.white)
                .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.pill, style: .continuous))
            }
        }
    }

    private var isSaveDisabled: Bool {
        titleText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || isSaving
    }

    // MARK: - Actions

    private func toggleRecording() async {
        if recorder.isRecording {
            guard let url = recorder.stopRecording() else { return }
            finishCapture(url: url)
        } else {
            do {
                _ = try await recorder.startRecording()
            } catch {
                errorMessage = error.localizedDescription
            }
        }
    }

    private func handleImportResult(_ result: Result<URL, Error>) {
        switch result {
        case .success(let pickedURL):
            do {
                let localURL = try AudioImportService.importFile(from: pickedURL)
                finishCapture(url: localURL)
            } catch {
                errorMessage = error.localizedDescription
            }
        case .failure(let error):
            errorMessage = error.localizedDescription
        }
    }

    private func finishCapture(url: URL) {
        do {
            try playback.load(url: url)
            capturedURL = url
            capturedDuration = playback.duration
            if titleText.isEmpty {
                titleText = defaultTitle()
            }
        } catch {
            errorMessage = "Couldn't load that audio file."
        }
    }

    private func discardCapture() {
        playback.stop()
        if let capturedURL {
            try? FileManager.default.removeItem(at: capturedURL)
        }
        self.capturedURL = nil
        capturedDuration = 0
        titleText = ""
    }

    private func cancelAndDismiss() {
        recorder.cancelRecording()
        playback.stop()
        if let capturedURL {
            try? FileManager.default.removeItem(at: capturedURL)
        }
        dismiss()
    }

    private func save() {
        guard let capturedURL else { return }
        isSaving = true
        let trimmedTitle = titleText.trimmingCharacters(in: .whitespacesAndNewlines)
        do {
            try ProjectStore.createProject(
                title: trimmedTitle,
                audioURL: capturedURL,
                duration: capturedDuration,
                context: modelContext
            )
            playback.stop()
            try? FileManager.default.removeItem(at: capturedURL)
            dismiss()
        } catch {
            errorMessage = "Couldn't save this project."
            isSaving = false
        }
    }

    private func defaultTitle() -> String {
        let formatter = DateFormatter()
        formatter.dateFormat = "MMM d, h:mm a"
        return "Untitled — \(formatter.string(from: Date()))"
    }
}
