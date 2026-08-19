import SwiftUI

/// Renders one lyric line: dimmed and compact when it isn't playing, larger
/// with per-word karaoke-style highlighting (already-sung words in the accent
/// color) when it's the current line.
struct LyricLineView: View {
    let line: AlignedLine
    let isCurrent: Bool
    let currentTime: TimeInterval

    var body: some View {
        Group {
            if isCurrent {
                highlightedText
                    .font(.title2.weight(.bold))
            } else {
                Text(line.text)
                    .font(.title3.weight(.medium))
                    .foregroundStyle(AppTheme.textTertiary)
            }
        }
        .multilineTextAlignment(.center)
        .padding(.horizontal, AppTheme.Spacing.lg)
        .frame(maxWidth: .infinity)
        .animation(.easeInOut(duration: 0.25), value: isCurrent)
    }

    private var highlightedText: Text {
        line.words.indices.reduce(Text("")) { partial, index in
            let word = line.words[index]
            let sung = currentTime >= word.start
            let separator = index == 0 ? "" : " "
            return partial + Text(separator + word.text)
                .foregroundStyle(sung ? AppTheme.accent : AppTheme.textPrimary)
        }
    }
}
