import SwiftUI

/// Guides the user through marking where each song section begins in the
/// audio recording. The tapped timestamps replace the heuristic's proportional
/// guess with real musical boundaries, so each section's lyrics are distributed
/// within the correct audio window rather than spread uniformly across the track.
struct SectionTimingView: View {
    /// Section titles in document order (e.g. ["Verse 1","Chorus","Verse 2"]).
    let sectionTitles: [String]
    let audioURL: URL
    let duration: TimeInterval
    /// Called with one start time per section title, in order.
    /// An empty array signals "use automatic timing" (user tapped Auto).
    let onComplete: ([TimeInterval]) -> Void

    @Environment(\.dismiss) private var dismiss
    @StateObject private var playback = AudioPlaybackService()
    @State private var markedTimes: [TimeInterval] = []

    private var pendingIndex: Int { markedTimes.count }
    private var isDone: Bool { markedTimes.count == sectionTitles.count }

    var body: some View {
        ZStack {
            AppTheme.background.ignoresSafeArea()

            VStack(spacing: 0) {
                header
                sectionStrip
                Spacer()
                centerLabel
                Spacer()
                AudioPreviewPlayer(playback: playback)
                    .padding(.horizontal, AppTheme.Spacing.lg)
                    .padding(.bottom, AppTheme.Spacing.sm)
                markButton
                    .padding(.horizontal, AppTheme.Spacing.lg)
                    .padding(.bottom, AppTheme.Spacing.xl)
            }
        }
        .onAppear {
            try? playback.load(url: audioURL)
        }
    }

    // MARK: - Subviews

    private var header: some View {
        HStack {
            Button("Cancel") {
                playback.stop()
                dismiss()
            }
            .font(.subheadline)
            .foregroundStyle(AppTheme.textSecondary)

            Spacer()

            Text("Time Sections")
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(AppTheme.textPrimary)

            Spacer()

            Button("Auto") {
                playback.stop()
                onComplete([])
                dismiss()
            }
            .font(.subheadline)
            .foregroundStyle(AppTheme.textTertiary)
        }
        .padding(.horizontal, AppTheme.Spacing.lg)
        .padding(.vertical, AppTheme.Spacing.md)
    }

    private var sectionStrip: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 6) {
                ForEach(sectionTitles.indices, id: \.self) { index in
                    let done = index < markedTimes.count
                    let active = index == pendingIndex && !isDone
                    Text(displayLabel(for: index))
                        .font(.caption2.weight(.semibold))
                        .foregroundStyle(done ? .black : (active ? AppTheme.accent : AppTheme.textTertiary))
                        .padding(.horizontal, 8)
                        .padding(.vertical, 4)
                        .background(
                            RoundedRectangle(cornerRadius: AppTheme.Radius.pill, style: .continuous)
                                .fill(done ? AppTheme.accent : (active ? AppTheme.accent.opacity(0.15) : AppTheme.surface))
                        )
                }
            }
            .padding(.horizontal, AppTheme.Spacing.lg)
        }
    }

    private var centerLabel: some View {
        VStack(spacing: AppTheme.Spacing.sm) {
            if isDone {
                Image(systemName: "checkmark.circle.fill")
                    .font(.system(size: 48))
                    .foregroundStyle(AppTheme.accent)
                    .padding(.bottom, AppTheme.Spacing.sm)
                Text("All sections timed")
                    .font(.title3.weight(.semibold))
                    .foregroundStyle(AppTheme.textPrimary)
                Text("Tap below to align.")
                    .font(.subheadline)
                    .foregroundStyle(AppTheme.textTertiary)
            } else {
                Text("Tap when")
                    .font(.subheadline)
                    .foregroundStyle(AppTheme.textTertiary)
                Text(sectionTitles[pendingIndex])
                    .font(.largeTitle.weight(.bold))
                    .foregroundStyle(AppTheme.textPrimary)
                Text("starts playing")
                    .font(.subheadline)
                    .foregroundStyle(AppTheme.textTertiary)

                Text("\(pendingIndex + 1) of \(sectionTitles.count)")
                    .font(.caption.monospacedDigit())
                    .foregroundStyle(AppTheme.textTertiary)
                    .padding(.top, AppTheme.Spacing.xs)

                if !markedTimes.isEmpty {
                    Button {
                        markedTimes.removeLast()
                    } label: {
                        Label("Undo last mark", systemImage: "arrow.uturn.backward")
                            .font(.caption.weight(.medium))
                            .foregroundStyle(AppTheme.textTertiary)
                    }
                    .buttonStyle(.plain)
                    .padding(.top, AppTheme.Spacing.sm)
                }
            }
        }
        .multilineTextAlignment(.center)
        .padding(.horizontal, AppTheme.Spacing.lg)
    }

    private var markButton: some View {
        VStack(spacing: AppTheme.Spacing.sm) {
            if isDone {
                Button {
                    playback.stop()
                    onComplete(markedTimes)
                    dismiss()
                } label: {
                    Text("Align with These Times")
                        .font(.headline)
                        .foregroundStyle(.black)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 14)
                }
                .buttonStyle(.plain)
                .background(AppTheme.accent)
                .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.pill, style: .continuous))
            } else {
                Button {
                    markedTimes.append(playback.currentTime)
                } label: {
                    HStack(spacing: AppTheme.Spacing.sm) {
                        Image(systemName: "flag.fill")
                        Text("Mark \(sectionTitles[pendingIndex]) Start")
                            .font(.headline)
                    }
                    .foregroundStyle(.black)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 14)
                }
                .buttonStyle(.plain)
                .background(Color.white)
                .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.pill, style: .continuous))

                // Let the user stop early — useful when testing a short clip
                // where only the first few sections fit the audio.
                if !markedTimes.isEmpty {
                    Button {
                        playback.stop()
                        onComplete(markedTimes)
                        dismiss()
                    } label: {
                        Text("Use These \(markedTimes.count) Section\(markedTimes.count == 1 ? "" : "s")")
                            .font(.subheadline.weight(.medium))
                            .foregroundStyle(AppTheme.textSecondary)
                    }
                    .buttonStyle(.plain)
                }
            }
        }
    }

    // MARK: - Helpers

    /// Disambiguates repeated titles: "Chorus" → "Chorus 1", "Chorus 2", etc.
    private func displayLabel(for index: Int) -> String {
        let title = sectionTitles[index]
        guard sectionTitles.filter({ $0 == title }).count > 1 else { return title }
        let occurrence = sectionTitles.prefix(index + 1).filter({ $0 == title }).count
        return "\(title) \(occurrence)"
    }
}

