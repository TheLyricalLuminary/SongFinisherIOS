import SwiftUI

/// A simple animated bar-style level meter driven by a normalized 0...1 value.
struct LevelMeterView: View {
    let level: Float
    var barCount: Int = 24

    var body: some View {
        GeometryReader { geo in
            let activeBars = Int(Float(barCount) * level)
            HStack(spacing: 3) {
                ForEach(0..<barCount, id: \.self) { index in
                    RoundedRectangle(cornerRadius: 2, style: .continuous)
                        .fill(index < activeBars ? AppTheme.accentGradient : LinearGradient(colors: [AppTheme.surfaceElevated], startPoint: .top, endPoint: .bottom))
                        .frame(width: max(2, (geo.size.width - CGFloat(barCount - 1) * 3) / CGFloat(barCount)))
                }
            }
            .frame(height: geo.size.height, alignment: .center)
        }
        .animation(.easeOut(duration: 0.08), value: level)
    }
}

#Preview {
    LevelMeterView(level: 0.6)
        .frame(height: 40)
        .padding()
        .background(AppTheme.background)
}
