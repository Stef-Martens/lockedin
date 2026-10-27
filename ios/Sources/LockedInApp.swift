import SwiftUI

@main
struct LockedInApp: App {
    @State private var connection = Connection.saved()

    var body: some Scene {
        WindowGroup {
            NavigationStack {
                if let connection {
                    SessionsView(connection: connection) { self.connection = $0 }
                } else {
                    SettingsView(current: nil) { connection = $0 }
                }
            }
        }
    }
}
