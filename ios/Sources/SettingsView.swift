import SwiftUI

/// The LockedIn address and the watch key, kept in the Keychain.
struct SettingsView: View {
    let current: Connection?
    let onSave: (Connection) -> Void

    @State private var address = ""
    @State private var key = ""
    @State private var problem: String?

    var body: some View {
        Form {
            Section {
                TextField("lockedin.vercel.app", text: $address)
                    .keyboardType(.URL)
                    .textContentType(.URL)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
            } header: {
                Text("LockedIn address")
            }
            Section {
                SecureField("Watch key", text: $key)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
            } header: {
                Text("Watch key")
            } footer: {
                Text("The WATCH_TOKEN you set on Vercel. It can only read your planned runs and swims.")
            }
            if let problem {
                Text(problem).foregroundStyle(.red)
            }
            Button("Save", action: save)
                .disabled(address.isEmpty || key.isEmpty)
        }
        .navigationTitle("Settings")
        .onAppear {
            address = current?.base.absoluteString ?? ""
            key = current?.key ?? ""
        }
    }

    private func save() {
        guard let connection = Connection(address: address, key: key) else {
            problem = "That address doesn't look right. It should be like lockedin.vercel.app."
            return
        }
        guard connection.save() else {
            problem = "Couldn't save to the Keychain. Try again."
            return
        }
        problem = nil
        onSave(connection)
    }
}
