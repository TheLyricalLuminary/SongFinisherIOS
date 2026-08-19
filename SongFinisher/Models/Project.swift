import Foundation
import SwiftData

/// A saved song project: the user's original audio, generated lyrics and their
/// prompt, and (once aligned) word-level timing for synced playback.
@Model
final class Project {
    @Attribute(.unique) var id: UUID
    var title: String
    var createdAt: Date
    var updatedAt: Date

    /// Filename (not full path) of the audio file inside this project's storage
    /// directory. Resolve with `FileStorage.audioURL(for:)`.
    var audioFileName: String
    var duration: TimeInterval

    /// The short style/mood/theme prompt last used to generate `lyricsText`.
    var lyricsPrompt: String = ""
    /// Generated (and possibly user-edited) lyrics, formatted as plain text with
    /// "[Verse 1]" / "[Chorus]" / "[Bridge]" section labels. Empty until the user
    /// generates lyrics for this project.
    var lyricsText: String = ""

    /// JSON-encoded `LyricSettings` (style, rhyme, syllables, musical context).
    /// Nil until the user changes something; read through `lyricSettings`.
    var lyricSettingsData: Data?

    /// The craft settings used to write this project's lyrics, falling back to
    /// sensible defaults for projects saved before settings existed.
    var lyricSettings: LyricSettings {
        get {
            guard let lyricSettingsData,
                  let decoded = try? JSONDecoder().decode(LyricSettings.self, from: lyricSettingsData)
            else { return .default }
            return decoded
        }
        set { lyricSettingsData = try? JSONEncoder().encode(newValue) }
    }

    /// JSON-encoded `AlignedLyrics` mapping `lyricsText` onto the audio's timing.
    /// Nil until the user runs alignment. Decode via `alignedLyrics`.
    var alignmentData: Data?

    /// Decoded alignment result, if any has been saved.
    var alignedLyrics: AlignedLyrics? {
        guard let alignmentData else { return nil }
        return try? JSONDecoder().decode(AlignedLyrics.self, from: alignmentData)
    }

    var hasAlignment: Bool { alignmentData != nil }

    /// True when lyrics have been edited since the saved alignment was computed,
    /// so timestamps no longer match the current text.
    var isAlignmentStale: Bool {
        guard let alignedLyrics else { return false }
        return alignedLyrics.sourceText != lyricsText
    }

    init(
        id: UUID = UUID(),
        title: String,
        createdAt: Date = Date(),
        updatedAt: Date = Date(),
        audioFileName: String,
        duration: TimeInterval
    ) {
        self.id = id
        self.title = title
        self.createdAt = createdAt
        self.updatedAt = updatedAt
        self.audioFileName = audioFileName
        self.duration = duration
    }
}
