import SwiftUI
import SwiftData

struct ProjectListView: View {
    @Environment(\.modelContext) private var modelContext
    @Query(sort: \Project.updatedAt, order: .reverse) private var projects: [Project]

    @State private var isPresentingNewProject = false
    @State private var selectedProject: Project?

    var body: some View {
        NavigationStack {
            ZStack {
                AppTheme.background.ignoresSafeArea()

                if projects.isEmpty {
                    emptyState
                } else {
                    List {
                        ForEach(projects) { project in
                            Button {
                                selectedProject = project
                            } label: {
                                ProjectRow(project: project)
                            }
                            .buttonStyle(.plain)
                            .listRowBackground(AppTheme.surface)
                            .listRowSeparatorTint(AppTheme.surfaceElevated)
                        }
                        .onDelete(perform: deleteProjects)
                    }
                    .scrollContentBackground(.hidden)
                    .listStyle(.plain)
                }
            }
            .navigationTitle("Song Finisher")
            .toolbar {
                ToolbarItem(placement: .primaryAction) {
                    Button {
                        isPresentingNewProject = true
                    } label: {
                        Image(systemName: "plus.circle.fill")
                            .font(.title2)
                    }
                }
            }
            .sheet(isPresented: $isPresentingNewProject) {
                RecordAudioView()
            }
            .sheet(item: $selectedProject) { project in
                ProjectPlaybackSheet(project: project)
            }
        }
    }

    private var emptyState: some View {
        VStack(spacing: AppTheme.Spacing.md) {
            Image(systemName: "music.mic")
                .font(.system(size: 44))
                .foregroundStyle(AppTheme.textTertiary)
            Text("No songs yet")
                .font(.headline)
                .foregroundStyle(AppTheme.textPrimary)
            Text("Record or import audio to start your first project.")
                .font(.subheadline)
                .foregroundStyle(AppTheme.textSecondary)
                .multilineTextAlignment(.center)
                .padding(.horizontal, AppTheme.Spacing.xl)

            Button {
                isPresentingNewProject = true
            } label: {
                Text("New Song")
                    .font(.headline)
                    .foregroundStyle(.black)
                    .padding(.horizontal, AppTheme.Spacing.lg)
                    .padding(.vertical, 12)
                    .background(Color.white)
                    .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.pill, style: .continuous))
            }
            .buttonStyle(.plain)
            .padding(.top, AppTheme.Spacing.sm)
        }
        .padding()
    }

    private func deleteProjects(at offsets: IndexSet) {
        for index in offsets {
            ProjectStore.delete(projects[index], context: modelContext)
        }
    }
}
