import SwiftUI

/// The craft controls — rhyme, phrasing, and musical context — shared by the
/// Generate Lyrics screen and the post-alignment tune-up. Keeping them in one
/// sheet is what keeps both host screens uncluttered.
struct LyricCraftSettingsView: View {
    enum Mode {
        /// Everything, shown from the Generate Lyrics screen.
        case full
        /// The subset worth revisiting once a project is aligned, plus actions
        /// to regenerate or re-align with the new values.
        case postAlignment
    }

    let mode: Mode
    @Binding var settings: LyricSettings
    var isBusy: Bool = false
    var onRegenerate: (() -> Void)?
    var onRealign: (() -> Void)?

    @Environment(\.dismiss) private var dismiss

    private var showsMusicalContext: Bool { mode == .full }
    private var showsActions: Bool { mode == .postAlignment }

    var body: some View {
        NavigationStack {
            ZStack {
                AppTheme.background.ignoresSafeArea()

                ScrollView {
                    VStack(alignment: .leading, spacing: AppTheme.Spacing.lg) {
                        rhymeSection
                        phrasingSection
                        if showsMusicalContext { musicalContextSection }
                        if showsActions { actionsSection }
                    }
                    .padding(AppTheme.Spacing.lg)
                }
            }
            .navigationTitle(mode == .full ? "Craft & Music" : "Lyric Settings")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Done") { dismiss() }
                }
            }
        }
    }

    // MARK: - Sections

    private var rhymeSection: some View {
        section("Rhyme") {
            fieldLabel("Scheme")
            chipGrid(RhymeScheme.allCases, minWidth: 84) { scheme in
                CraftChip(
                    title: scheme.rawValue,
                    isSelected: settings.rhymeScheme == scheme
                ) { settings.rhymeScheme = scheme }
            }

            Text(schemeHint)
                .font(.caption2)
                .foregroundStyle(AppTheme.textTertiary)
                .padding(.top, 2)

            fieldLabel("Type").padding(.top, AppTheme.Spacing.sm)
            chipGrid(RhymeType.allCases, minWidth: 108) { type in
                CraftChip(
                    title: type.rawValue,
                    isSelected: settings.rhymeTypes.contains(type)
                ) { toggle(type) }
            }

            Text("Combine freely — End plus Internal asks for lines that rhyme at the end and inside.")
                .font(.caption2)
                .foregroundStyle(AppTheme.textTertiary)
                .padding(.top, 2)
        }
    }

    private var phrasingSection: some View {
        section("Phrasing") {
            HStack {
                VStack(alignment: .leading, spacing: 2) {
                    Text("Syllables per line")
                        .font(.subheadline)
                        .foregroundStyle(AppTheme.textPrimary)
                    Text("Aiming for \(settings.effectiveSyllableTarget) after meter and tempo")
                        .font(.caption2)
                        .foregroundStyle(AppTheme.textTertiary)
                }
                Spacer()
                Text("\(settings.syllableTarget)")
                    .font(.title3.weight(.semibold).monospacedDigit())
                    .foregroundStyle(AppTheme.textPrimary)
                    .frame(minWidth: 30, alignment: .trailing)
                Stepper("Syllables per line", value: $settings.syllableTarget, in: 4...20)
                    .labelsHidden()
                    .fixedSize()
            }

            fieldLabel("Time signature").padding(.top, AppTheme.Spacing.sm)
            chipGrid(TimeSignature.allCases, minWidth: 76) { signature in
                CraftChip(
                    title: signature.rawValue,
                    isSelected: settings.timeSignature == signature
                ) { settings.timeSignature = signature }
            }
        }
    }

    private var musicalContextSection: some View {
        section("Musical Context") {
            fieldLabel("Key")
            TextField("e.g. G major", text: $settings.key)
                .textInputAutocapitalization(.words)
                .autocorrectionDisabled()
                .padding(AppTheme.Spacing.md)
                .background(AppTheme.surfaceElevated)
                .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.sm, style: .continuous))
                .foregroundStyle(AppTheme.textPrimary)

            fieldLabel("Tempo (BPM)").padding(.top, AppTheme.Spacing.sm)
            TextField("e.g. 92", text: bpmText)
                .keyboardType(.numberPad)
                .padding(AppTheme.Spacing.md)
                .background(AppTheme.surfaceElevated)
                .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.sm, style: .continuous))
                .foregroundStyle(AppTheme.textPrimary)

            Text("Key and tempo are context for the writing — leave them blank if you're not sure yet.")
                .font(.caption2)
                .foregroundStyle(AppTheme.textTertiary)
                .padding(.top, 2)
        }
    }

    private var actionsSection: some View {
        VStack(spacing: AppTheme.Spacing.sm) {
            Text("Apply the new settings")
                .font(.caption.weight(.semibold))
                .foregroundStyle(AppTheme.textSecondary)
                .textCase(.uppercase)
                .frame(maxWidth: .infinity, alignment: .leading)

            Button {
                onRegenerate?()
            } label: {
                HStack(spacing: AppTheme.Spacing.sm) {
                    Image(systemName: "sparkles")
                    Text("Regenerate Lyrics").font(.headline)
                }
                .foregroundStyle(.black)
                .frame(maxWidth: .infinity)
                .padding(.vertical, 14)
            }
            .buttonStyle(.plain)
            .disabled(isBusy)
            .background(isBusy ? Color.white.opacity(0.3) : Color.white)
            .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.pill, style: .continuous))

            Button {
                onRealign?()
            } label: {
                HStack(spacing: AppTheme.Spacing.sm) {
                    Image(systemName: "waveform.badge.magnifyingglass")
                    Text("Re-align Lyrics").font(.headline)
                }
                .foregroundStyle(AppTheme.textPrimary)
                .frame(maxWidth: .infinity)
                .padding(.vertical, 14)
            }
            .buttonStyle(.plain)
            .disabled(isBusy)
            .background(AppTheme.surfaceElevated)
            .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.pill, style: .continuous))

            Text("Regenerating rewrites the lyrics with these settings. Re-aligning keeps the words and recomputes their timing.")
                .font(.caption2)
                .foregroundStyle(AppTheme.textTertiary)
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(.top, 2)
        }
    }

    // MARK: - Building blocks

    private func section<Content: View>(_ title: String, @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
            Text(title)
                .font(.caption.weight(.semibold))
                .foregroundStyle(AppTheme.textSecondary)
                .textCase(.uppercase)
            VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
                content()
            }
            .padding(AppTheme.Spacing.md)
            .frame(maxWidth: .infinity, alignment: .leading)
            .cardSurface()
        }
    }

    private func fieldLabel(_ text: String) -> some View {
        Text(text)
            .font(.footnote.weight(.medium))
            .foregroundStyle(AppTheme.textSecondary)
    }

    private func chipGrid<Item: Identifiable, Chip: View>(
        _ items: [Item],
        minWidth: CGFloat,
        @ViewBuilder chip: @escaping (Item) -> Chip
    ) -> some View {
        LazyVGrid(
            columns: [GridItem(.adaptive(minimum: minWidth), spacing: AppTheme.Spacing.sm)],
            alignment: .leading,
            spacing: AppTheme.Spacing.sm
        ) {
            ForEach(items) { item in chip(item) }
        }
    }

    private var schemeHint: String {
        switch settings.rhymeScheme {
        case .aabb: return "Lines 1&2 rhyme, then 3&4."
        case .abab: return "Lines 1&3 rhyme, and 2&4."
        case .abba: return "Lines 1&4 rhyme, wrapping 2&3."
        case .abcb: return "Only lines 2&4 rhyme."
        case .aaaa: return "All four lines rhyme together."
        case .free: return "No rhyme requirement — phrasing leads."
        }
    }

    /// Keeps at least one rhyme type selected so generation always has something
    /// to aim for.
    private func toggle(_ type: RhymeType) {
        if let index = settings.rhymeTypes.firstIndex(of: type) {
            guard settings.rhymeTypes.count > 1 else { return }
            settings.rhymeTypes.remove(at: index)
        } else {
            settings.rhymeTypes.append(type)
        }
    }

    private var bpmText: Binding<String> {
        Binding(
            get: { settings.bpm > 0 ? String(settings.bpm) : "" },
            set: { newValue in
                let digits = newValue.filter(\.isNumber)
                settings.bpm = min(300, Int(digits) ?? 0)
            }
        )
    }
}

/// A selectable pill used for rhyme schemes, rhyme types, and time signatures.
struct CraftChip: View {
    let title: String
    let isSelected: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            Text(title)
                .font(.subheadline.weight(isSelected ? .semibold : .regular))
                .foregroundStyle(isSelected ? Color.black : AppTheme.textPrimary)
                .frame(maxWidth: .infinity)
                .padding(.vertical, 10)
                .background(isSelected ? Color.white : AppTheme.surfaceElevated)
                .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.sm, style: .continuous))
        }
        .buttonStyle(.plain)
    }
}
