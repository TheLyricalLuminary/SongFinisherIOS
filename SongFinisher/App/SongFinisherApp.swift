import SwiftUI
import SwiftData

@main
struct SongFinisherApp: App {
    let modelContainer: ModelContainer

    init() {
        modelContainer = ProjectStore.makeModelContainer()
        AudioSessionManager.shared.configureForPlaybackAndRecording()
    }

    var body: some Scene {
        WindowGroup {
            ProjectListView()
                .preferredColorScheme(.dark)
                .tint(AppTheme.accent)
        }
        .modelContainer(modelContainer)
    }
}
