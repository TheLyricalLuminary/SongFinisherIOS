import Foundation

/// Manages on-disk storage for project audio files under
/// Application Support/Projects/<project-id>/. Local-first: nothing here ever
/// touches the network.
enum FileStorage {
    static var applicationSupportDirectory: URL {
        let url = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
        if !FileManager.default.fileExists(atPath: url.path) {
            try? FileManager.default.createDirectory(at: url, withIntermediateDirectories: true)
        }
        return url
    }

    static var projectsDirectory: URL {
        applicationSupportDirectory.appendingPathComponent("Projects", isDirectory: true)
    }

    static func directory(for projectID: UUID) -> URL {
        projectsDirectory.appendingPathComponent(projectID.uuidString, isDirectory: true)
    }

    @discardableResult
    static func ensureDirectory(for projectID: UUID) throws -> URL {
        let dir = directory(for: projectID)
        if !FileManager.default.fileExists(atPath: dir.path) {
            try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        }
        return dir
    }

    static func audioURL(projectID: UUID, fileName: String) -> URL {
        directory(for: projectID).appendingPathComponent(fileName)
    }

    /// Copies an audio file (from a recording or an imported file) into the given
    /// project's storage directory, returning the stored filename.
    @discardableResult
    static func storeAudio(from sourceURL: URL, projectID: UUID, preferredBaseName: String = "audio") throws -> String {
        let dir = try ensureDirectory(for: projectID)
        let ext = sourceURL.pathExtension.isEmpty ? "m4a" : sourceURL.pathExtension
        let fileName = "\(preferredBaseName).\(ext)"
        let destURL = dir.appendingPathComponent(fileName)

        if FileManager.default.fileExists(atPath: destURL.path) {
            try FileManager.default.removeItem(at: destURL)
        }
        try FileManager.default.copyItem(at: sourceURL, to: destURL)
        return fileName
    }

    static func deleteProjectDirectory(projectID: UUID) {
        let dir = directory(for: projectID)
        try? FileManager.default.removeItem(at: dir)
    }
}
