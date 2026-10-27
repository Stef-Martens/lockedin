import SwiftUI
import WorkoutKit

/// The coming runs and swims by day. A tap opens Apple's sheet, where Add to Watch sends it to the watch.
struct SessionsView: View {
    let connection: Connection
    let onChangeConnection: (Connection) -> Void

    @Environment(\.scenePhase) private var scenePhase
    @State private var feed: Feed?
    @State private var plans: [Int: Result<WorkoutPlan, any Error>] = [:]
    @State private var problem: String?
    @State private var preview: WorkoutPlan?
    @State private var previewing = false
    @State private var editingSettings = false

    var body: some View {
        List {
            if let feed {
                ForEach(days(in: feed), id: \.self) { day in
                    Section(dayLabel(day, today: feed.today)) {
                        ForEach(feed.items.filter { $0.day == day }) { row($0) }
                    }
                }
            }
        }
        .safeAreaInset(edge: .top) {
            if let problem { banner(problem) }
        }
        .overlay {
            if feed == nil && problem == nil {
                ProgressView()
            } else if feed?.items.isEmpty == true {
                ContentUnavailableView("Nothing planned", systemImage: "figure.run",
                                       description: Text("No runs or swims today or in the next 7 days."))
            }
        }
        .refreshable { await load() }
        .task(id: connection) { await load() }
        .onChange(of: scenePhase) { _, phase in
            if phase == .active { Task { await load() } }
        }
        .navigationTitle("Runs and swims")
        .toolbar {
            Button { editingSettings = true } label: { Image(systemName: "gearshape") }
                .accessibilityLabel("Settings")
        }
        .sheet(isPresented: $editingSettings) {
            NavigationStack {
                SettingsView(current: connection) { new in
                    editingSettings = false
                    onChangeConnection(new)
                }
                .toolbar { Button("Cancel") { editingSettings = false } }
            }
        }
        // The modifier needs a plan even while hidden; the placeholder is never shown.
        .workoutPreview(preview ?? WorkoutPlan(.goal(SingleGoalWorkout(activity: .running))), isPresented: $previewing)
    }

    private func row(_ item: FeedItem) -> some View {
        Button { open(item) } label: {
            VStack(alignment: .leading, spacing: 4) {
                HStack {
                    Image(systemName: item.sport == "swim" ? "figure.pool.swim" : "figure.run")
                    Text(item.title).font(.headline)
                    if item.optional {
                        Text("Optional")
                            .font(.caption)
                            .padding(.horizontal, 6)
                            .padding(.vertical, 2)
                            .background(.quaternary, in: Capsule())
                    }
                }
                if let summary = item.summary {
                    Text(summary).font(.subheadline).foregroundStyle(.secondary)
                }
                if item.sport == "swim", let note = item.note, !note.isEmpty {
                    Text(note).font(.footnote)
                }
                if case .failure(let error) = plans[item.id] {
                    Label(error.localizedDescription, systemImage: "exclamationmark.triangle")
                        .font(.footnote)
                        .foregroundStyle(.red)
                }
            }
            .foregroundStyle(.primary)
        }
    }

    private func banner(_ text: String) -> some View {
        Label(text, systemImage: "exclamationmark.triangle.fill")
            .font(.subheadline)
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(12)
            .background(.orange.opacity(0.2), in: RoundedRectangle(cornerRadius: 10))
            .padding(.horizontal)
    }

    private func days(in feed: Feed) -> [String] {
        feed.items.reduce(into: []) { days, item in
            if !days.contains(item.day) { days.append(item.day) }
        }
    }

    private func open(_ item: FeedItem) {
        guard case .success(let plan) = plans[item.id] else { return }
        preview = plan
        previewing = true
    }

    /// Keeps the last list on screen when a refresh fails; the banner says why.
    private func load() async {
        do {
            let fresh = try await fetchFeed(base: connection.base, key: connection.key)
            plans = Dictionary(fresh.items.map { item in (item.id, Result { try workoutPlan(for: item) }) },
                               uniquingKeysWith: { first, _ in first })
            feed = fresh
            problem = nil
        } catch is CancellationError {
            return
        } catch {
            problem = error.localizedDescription
        }
    }
}
