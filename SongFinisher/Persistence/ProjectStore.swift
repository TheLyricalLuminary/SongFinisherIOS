import Foundation
import SwiftData

enum ProjectStore {
    /// Local, on-device persistent SwiftData container. No CloudKit sync — every
    /// project lives only on this device, matching the app's local-first design.
    static func makeModelContainer() -> ModelContainer {
        let schema = Schema([Project.self])
        let configuration = ModelConfiguration(schema: schema, isStoredInMemoryOnly: false)
        do {
            return try ModelContainer(for: schema, configurations: [configuration])
        } catch {
            fatalError("Failed to create SwiftData ModelContainer: \(error)")
        }
    }

    /// Creates a new project by copying the given audio file into permanent
    /// project storage, then inserting and saving the SwiftData record.
    @discardableResult
    static func createProject(
        title: String,
        audioURL: URL,
        duration: TimeInterval,
        context: ModelContext
    ) throws -> Project {
        let project = Project(title: title, audioFileName: "", duration: duration)
        let fileName = try FileStorage.storeAudio(from: audioURL, projectID: project.id)
        project.audioFileName = fileName
        context.insert(project)
        try context.save()
        return project
    }

    static func delete(_ project: Project, context: ModelContext) {
        FileStorage.deleteProjectDirectory(projectID: project.id)
        context.delete(project)
        try? context.save()
    }

    /// Persists generated (and possibly user-edited) lyrics and the prompt that
    /// produced them onto an existing project.
    static func saveLyrics(prompt: String, text: String, to project: Project, context: ModelContext) throws {
        project.lyricsPrompt = prompt
        project.lyricsText = text
        project.updatedAt = Date()
        try context.save()
    }

    /// Persists the craft settings (style, rhyme, syllables, musical context) so
    /// they survive relaunches and can be reused or adjusted after alignment.
    static func saveLyricSettings(_ settings: LyricSettings, to project: Project, context: ModelContext) throws {
        project.lyricSettings = settings
        project.updatedAt = Date()
        try context.save()
    }

    /// Persists a completed lyric-to-audio alignment onto an existing project.
    static func saveAlignment(_ aligned: AlignedLyrics, to project: Project, context: ModelContext) throws {
        project.alignmentData = try JSONEncoder().encode(aligned)
        project.updatedAt = Date()
        try context.save()
    }
}
