import Foundation
import UniformTypeIdentifiers

/// Handles importing an existing audio file the user picks (m4a, mp3, wav, aiff, ...).
enum AudioImportService {
    static let supportedTypes: [UTType] = [.audio, .mp3, .wav, .aiff, .mpeg4Audio]

    /// Copies a (possibly security-scoped) picked file into the app's temporary
    /// directory so it can be read after the picker's access scope ends.
    static func importFile(from sourceURL: URL) throws -> URL {
        let didStartAccessing = sourceURL.startAccessingSecurityScopedResource()
        defer {
            if didStartAccessing { sourceURL.stopAccessingSecurityScopedResource() }
        }

        let ext = sourceURL.pathExtension.isEmpty ? "m4a" : sourceURL.pathExtension
        let destURL = FileManager.default.temporaryDirectory
            .appendingPathComponent("import-\(UUID().uuidString)")
            .appendingPathExtension(ext)

        if FileManager.default.fileExists(atPath: destURL.path) {
            try FileManager.default.removeItem(at: destURL)
        }
        try FileManager.default.copyItem(at: sourceURL, to: destURL)
        return destURL
    }
}
