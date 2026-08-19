import Foundation

extension TimeInterval {
    /// Formats as "m:ss", e.g. 75.3 -> "1:15".
    var mmss: String {
        guard isFinite, self >= 0 else { return "0:00" }
        let totalSeconds = Int(self.rounded())
        let minutes = totalSeconds / 60
        let seconds = totalSeconds % 60
        return String(format: "%d:%02d", minutes, seconds)
    }
}
